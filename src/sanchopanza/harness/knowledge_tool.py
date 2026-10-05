"""`sanchopanza knowledge-mcp`: search, read and pick, one MCP server for large results and large
knowledge bases. Not a search engine: it finds what to read and hands over little and good text.

- `search(query, k=8)`: `serp.Searcher` (Wikipedia's search API and a free web chain, a day of
  cache, "already searched", breakers by answer, not by flag). A compact results page, no reader.
- `read(url_or_path, purpose, budget)`: a web page (fetch v2: `fetch_tool.PageFetcher`, every
  address checked public, redirects checked, a PDF or an Office file read too) or a local file
  under the server's roots (PDF, DOCX, XLSX, CSV, TSV, Markdown, text, HTML). A document past
  `knowledge.LONG_CHARS` goes through the cascade (places, passages, sentences), by the decision
  model when a key is set (`TYPESAFE_API_KEY` or `SANCHOPANZA_PROVIDER`), else by BM25. Each
  passage is under its place (page or section) for citing.
- `pick(purpose, sources, budget)`: many documents (folders, files, globs, URLs) to the few that
  serve the purpose and their best passages (`knowledge.pick_docs`).

Local files: only under the roots (the directory the server starts in, plus
`SANCHOPANZA_KNOWLEDGE_ROOTS`, separated by the OS path separator), never through a hidden
component (`.env`, `.git`, `.ssh`): Claude Code's own permission rules do not see an MCP tool's
reads, so the tool keeps to the project. The text reaches the model with no reader in between;
`install --knowledge --scan-content` scans what `read` and `pick` return.

    sanchopanza knowledge-mcp
    claude mcp add-json --scope user sanchopanza-knowledge \\
        '{"command":"sanchopanza","args":["knowledge-mcp"],"alwaysLoad":true}'
"""

from __future__ import annotations

import asyncio
import os
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .. import _env, documents, knowledge, serp, webpage
from .fetch_tool import DISAMBIGUATION, MAX_BUDGET, MIN_BUDGET, PageFetcher, Response, http_opener

SERVER = "sanchopanza-knowledge"
SEARCH_DESCRIPTION = (
    "Search the web and Wikipedia. Returns a compact list (title, url, short snippet), no "
    "summary. Then read(url, purpose) the results that look right. Use instead of WebSearch."
)
READ_DESCRIPTION = (
    "Read a web page or a local file (pdf, docx, xlsx, csv, txt, md, html) and get only the "
    "passages relevant to purpose, each under its page or section for citing. Use instead of "
    "WebFetch. Ask again with another purpose for other passages; budget is in characters."
)
PICK_DESCRIPTION = (
    "Given many documents (folders, files, globs or urls), pick the ones that serve purpose and "
    "return their best passages. For a knowledge base too large to read file by file."
)
INSTRUCTIONS = (
    "sanchopanza-knowledge: search(query) for candidates, read(url_or_path, purpose) for a "
    "page's or a file's passages, pick(purpose, sources) to choose among many documents."
)
MAX_BYTES = 40_000_000  # a downloaded document (long PDFs of official reports run to tens of MB)
MAX_FILES = 400
MAX_URLS = 25
DOC_CACHE = 512
CONCURRENCY = 6
SKIP_DIRS = frozenset(["node_modules", "__pycache__", "venv", "site-packages", "dist", "build"])
_FROM_ENV = object()


def _parse(response: Response) -> webpage.Page | str:
    name = urllib.parse.urlsplit(response.url).path.rsplit("/", 1)[-1]
    if len(response.body) > MAX_BYTES:
        return f"{response.url} is larger than {MAX_BYTES:,} bytes: not read here."
    try:
        return documents.page_from_bytes(response.body, name=name,
                                         content_type=response.content_type)  # fmt: skip
    except documents.Unreadable as error:
        return f"{response.url}: {error}. WebFetch it instead."


def page_fetcher(
    opener: Callable[[str], Response] | None = None, env: Mapping[str, str] | None = None
) -> PageFetcher:
    """fetch v2's fetcher, reading every kind of document `documents` reads."""
    env = {**(os.environ if env is None else env), "SANCHOPANZA_FETCH_VERSION": "2"}
    return PageFetcher(opener or http_opener(env, MAX_BYTES), env=env, parse=_parse)


def roots_from_env(env: Mapping[str, str] | None = None) -> list[Path]:
    extra = _env.get("KNOWLEDGE_ROOTS", "", env)
    return [Path.cwd(), *(Path(p) for p in extra.split(os.pathsep) if p.strip())]


def _is_url(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


class Knowledge:
    """The three tools' logic, network and files behind injectable parts."""

    def __init__(
        self,
        *,
        fetcher: PageFetcher | None = None,
        searcher: Any = None,
        squire: Any = _FROM_ENV,
        roots: Sequence[Path] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self.fetcher = fetcher or page_fetcher(env=env)
        self.searcher = searcher or serp.default_searcher(env)
        self._squire = squire
        self.roots = [Path(r).resolve() for r in (roots or roots_from_env(env))]
        self.files: dict[tuple[str, int, int], webpage.Page] = {}

    @property
    def squire(self) -> Any:
        if self._squire is _FROM_ENV:
            from .mcp import _squire_if_keyed

            self._squire = _squire_if_keyed()
        return self._squire

    def search(self, query: str, k: int = serp.DEFAULT_K) -> str:
        return self.searcher.search(query, k)

    # local files
    def _resolve(self, raw: str) -> Path | str:
        path = Path(raw).expanduser()
        path = (path if path.is_absolute() else self.roots[0] / path).resolve()
        root = next((r for r in self.roots if path == r or r in path.parents), None)
        if root is None:
            return f"Refused: {raw} is outside the folders this server reads. Use Read for it."
        if any(part.startswith(".") for part in path.relative_to(root).parts):
            return f"Refused: {raw} is hidden (a name starting with a dot). Use Read for it."
        return path

    def _file(self, path: Path) -> webpage.Page | str:
        if not path.is_file():
            return f"No such file: {path}"
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size)
        if key in self.files:
            return self.files[key]
        try:
            page = documents.page_from_path(path)
        except documents.Unreadable as error:
            return f"{error}. Use Read for it."
        kept = dict(list(self.files.items())[-(DOC_CACHE - 1) :])
        self.files = {**kept, key: page}
        return page

    def load(self, source: str) -> knowledge.Doc | str:
        """A URL or a path as a document, or the reason it was not read."""
        source = source.strip()
        if _is_url(source):
            final, page = self.fetcher.load(source)
            return page if isinstance(page, str) else knowledge.Doc(final, page)
        path = self._resolve(source)
        if isinstance(path, str):
            return path
        page = self._file(path)
        return page if isinstance(page, str) else knowledge.Doc(str(path), page)

    async def read(
        self, url_or_path: str, purpose: str, budget: int = webpage.DEFAULT_BUDGET
    ) -> str:
        budget = max(MIN_BUDGET, min(MAX_BUDGET, int(budget or webpage.DEFAULT_BUDGET)))
        doc = await asyncio.to_thread(self.load, url_or_path)
        if isinstance(doc, str):
            return doc
        page = doc.page
        named = f"{page.title}\n{doc.source}" if page.title else doc.source
        if not page.chunks:
            return f"{named}\nNo text in the document (it may need a browser, or OCR)."
        note = f"{DISAMBIGUATION}\n" if page.disambiguation else ""
        out = await knowledge.read_page(page, purpose, budget, squire=self.squire)
        return f"{named}\n{note}{out}"

    # many documents
    def expand(self, sources: Sequence[str]) -> tuple[list[str], list[str]]:
        """Sources to single documents: a folder's readable files (recursive, hidden and
        dependency folders left out), a glob's matches; capped. Returns (documents, refusals)."""
        out: list[str] = []
        refused: list[str] = []
        for raw in sources:
            raw = str(raw).strip()
            if not raw:
                continue
            if _is_url(raw):
                out.append(raw)
                continue
            if any(c in raw for c in "*?["):
                base = self.roots[0]
                matches = sorted(base.glob(raw)) if not Path(raw).is_absolute() else []
                out.extend(str(m) for m in matches if m.suffix.lower() in documents.SUFFIXES)
                continue
            path = self._resolve(raw)
            if isinstance(path, str):
                refused.append(path)
            elif path.is_dir():
                out.extend(str(p) for p in self._walk(path))
            else:
                out.append(str(path))
        urls = [s for s in out if _is_url(s)][:MAX_URLS]
        files = [s for s in out if not _is_url(s)][:MAX_FILES]
        return [*dict.fromkeys([*urls, *files])], refused

    def _walk(self, folder: Path) -> list[Path]:
        found: list[Path] = []
        for current, dirs, names in os.walk(folder):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in SKIP_DIRS)
            for name in sorted(names):
                if not name.startswith(".") and Path(name).suffix.lower() in documents.SUFFIXES:
                    found.append(Path(current) / name)
                if len(found) >= MAX_FILES:
                    return found
        return found

    async def pick(
        self, purpose: str, sources: Sequence[str], budget: int = webpage.DEFAULT_BUDGET
    ) -> str:
        budget = max(MIN_BUDGET, min(MAX_BUDGET, int(budget or webpage.DEFAULT_BUDGET)))
        wanted, refused = self.expand(sources if not isinstance(sources, str) else [sources])
        if not wanted:
            return "No readable document in the sources." + (f" {refused[0]}" if refused else "")
        gate = asyncio.Semaphore(CONCURRENCY)

        async def one(source: str) -> knowledge.Doc | str:
            async with gate:
                return await asyncio.to_thread(self.load, source)

        loaded = await asyncio.gather(*(one(s) for s in wanted))
        docs = [d for d in loaded if isinstance(d, knowledge.Doc) and d.page.chunks]
        skipped = len(loaded) - len(docs) + len(refused)
        if not docs:
            return f"None of the {len(loaded)} documents could be read."
        return await knowledge.pick_docs(docs, purpose, budget, squire=self.squire,
                                         skipped=skipped)  # fmt: skip


def add_knowledge(server: Any, tool: Knowledge | None = None) -> Any:
    """Register `search`, `read` and `pick` on an MCP server."""
    kit = tool or Knowledge()

    @server.tool(name="search", description=SEARCH_DESCRIPTION)
    def search(query: str, k: int = serp.DEFAULT_K) -> str:
        return kit.search(query, k)

    @server.tool(name="read", description=READ_DESCRIPTION)
    async def read(url_or_path: str, purpose: str, budget: int = webpage.DEFAULT_BUDGET) -> str:
        return await kit.read(url_or_path, purpose, budget)

    @server.tool(name="pick", description=PICK_DESCRIPTION)
    async def pick(purpose: str, sources: list[str], budget: int = webpage.DEFAULT_BUDGET) -> str:
        return await kit.pick(purpose, sources, budget)

    return server


def main(argv: list[str] | None = None) -> int:
    """`sanchopanza knowledge-mcp`: the stdio server."""
    del argv
    from .mcp import _server

    add_knowledge(_server(SERVER, INSTRUCTIONS)).run()
    return 0
