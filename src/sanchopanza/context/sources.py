"""Where the candidates of a search come from: one registry, one `select` over any of them.

`find_in_repo` answered one question, which fragments of code bear on a request. The same shape
answers "which function", "which skill to load", "which agent to hand this to", "which memory",
"which archived output", "which tool": a list of `Candidate(key, title, text)` built by code,
a BM25 shortlist, and a judge in context when there is one (`sanchopanza.select`). A source is
how to build that list for one kind of thing; adding a kind is registering a source, not
writing a tool.

    python -m sanchopanza.context.repo "request" --kind symbol|file|skill|agent|memory|archive|tool

Built-in kinds:
- `code`: fragments at top-level definitions and paragraphs (`context.repo`), the default;
- `symbol`: every Python function, method and class with its line range (`ast`);
- `file`: whole files, their path and head;
- `skill`: `SKILL.md` files (project `.claude/skills`, `skills/`, and `~/.claude/skills`);
- `agent`: agent definitions (`.claude/agents/*.md`, project and user);
- `memory`: memory notes (`.claude/memory/*.md`, and `SANCHOPANZA_MEMORY_DIR`);
- `archive`: tool output archived on arrival or at compaction (`context.archive`);
- `tool`: a tool catalog (`SANCHOPANZA_TOOL_CATALOG`, a JSON list of {name, description}).

Only `code` is measured (docs/results/2026-09-29-find/). The others are the same machinery
over other candidates, unmeasured.
"""

from __future__ import annotations

import ast
import json
import os
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..select import Candidate, index_of
from ..text import BM25Index

HEAD = 3_000  # characters of a file, skill, agent or memory that are scored and judged


@dataclass(frozen=True, slots=True)
class Source:
    """One kind of candidate: which files it reads (for the cache) and how to cut them."""

    name: str
    purpose: str  # what the judge is told the selection is for; `{query}` is filled in
    paths: Callable[[Path], list[Path]]
    build: Callable[[Path, list[Path]], list[Candidate]]


SOURCES: dict[str, Source] = {}


def register(source: Source) -> Source:
    SOURCES[source.name] = source
    return source


def kinds() -> list[str]:
    return list(SOURCES)


_CACHE: dict[tuple[str, str], tuple[tuple[Any, ...], list[Candidate], BM25Index]] = {}


def _stamps(paths: Iterable[Path]) -> tuple[Any, ...]:
    out = []
    for path in paths:
        try:
            st = path.stat()
        except OSError:
            continue
        out.append((str(path), st.st_size, int(st.st_mtime)))
    return tuple(out)


def indexed(kind: str, root: Path) -> tuple[list[Candidate], BM25Index]:
    """The candidates of `kind` under `root` and their BM25 index, rebuilt when a file changed."""
    source = SOURCES[kind]
    root = root.resolve()
    paths = source.paths(root)
    stamps = _stamps(paths)
    cached = _CACHE.get((kind, str(root)))
    if cached is None or cached[0] != stamps:
        candidates = source.build(root, paths)
        cached = (stamps, candidates, index_of(candidates))
        _CACHE[(kind, str(root))] = cached
    return cached[1], cached[2]


# --- helpers --------------------------------------------------------------------------------


def _text(path: Path) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    return "" if b"\0" in raw[:8192] else raw.decode("utf-8", "replace")


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


_FRONT = re.compile(r"\A---\s*\n(.*?)\n---", re.S)


def _front(text: str) -> dict[str, str]:
    """`name:` and `description:` of a markdown front matter, the way skills and agents carry
    them; one line each, which is how they are written."""
    match = _FRONT.match(text)
    if not match:
        return {}
    out = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in ("name", "description"):
            out[key.strip()] = value.strip().strip("\"'")
    return out


def _documents(root: Path, paths: list[Path]) -> list[Candidate]:
    """One candidate per markdown document: title from its front matter or first heading."""
    out = []
    for path in paths:
        text = _text(path)
        if not text.strip():
            continue
        front = _front(text)
        heading = next((ln.lstrip("# ").strip() for ln in text.splitlines() if ln.strip()), "")
        name = front.get("name") or path.parent.name if path.name == "SKILL.md" else path.stem
        title = f"{front.get('name') or name}: {front.get('description') or heading}"[:300]
        out.append(Candidate(_rel(path, root), title, text[:HEAD]))
    return out


def _glob(bases: Iterable[Path], pattern: str) -> list[Path]:
    found: dict[str, Path] = {}
    for base in bases:
        if base.is_dir():
            for path in sorted(base.glob(pattern)):
                found.setdefault(str(path.resolve()), path)
    return list(found.values())


# --- the built-in kinds ---------------------------------------------------------------------


def _code_paths(root: Path) -> list[Path]:
    from .repo import files

    return [root / rel for rel in files(root)]


def _code(root: Path, paths: list[Path]) -> list[Candidate]:
    from .repo import chunks

    return chunks(root)


def _files(root: Path, paths: list[Path]) -> list[Candidate]:
    out = []
    for path in paths:
        text = _text(path)
        if text.strip():
            rel = _rel(path, root)
            head = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")[:100]
            out.append(Candidate(rel, f"{rel} {head}".strip(), text[:HEAD]))
    return out


def _split_name(name: str) -> str:
    """`Invoice.total_due` -> `invoice total due`: an identifier as the words a request uses."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|[_.]", " ", name)
    return " ".join(spaced.lower().split())


def _symbols(root: Path, paths: list[Path]) -> list[Candidate]:
    """Every function, method and class of the Python files, with its qualified name."""
    out: list[Candidate] = []
    for path in paths:
        if path.suffix != ".py":
            continue
        text = _text(path)
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue
        out += _definitions(tree, "", _rel(path, root), text.splitlines())
    return out


_DEFINITION = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _definitions(node: ast.AST, prefix: str, rel: str, lines: list[str]) -> list[Candidate]:
    """The definitions under `node`, depth first, each named by its enclosing ones."""
    out: list[Candidate] = []
    for child in ast.iter_child_nodes(node):
        if isinstance(child, _DEFINITION):
            name = f"{prefix}{child.name}"
            first, last = child.lineno, child.end_lineno or child.lineno
            body = "\n".join(lines[first - 1 : last])[:HEAD]
            head = lines[first - 1].strip()[:120]
            words = _split_name(name)  # BM25 keeps `refund_payment` whole
            out.append(Candidate(f"{rel}:{first}-{last}", f"{rel} {name}: {head} ({words})", body))
            out += _definitions(child, f"{name}.", rel, lines)
    return out


def _skill_paths(root: Path) -> list[Path]:
    home = Path.home() / ".claude" / "skills"
    return _glob([root / ".claude" / "skills", root / "skills", home], "**/SKILL.md")


def _agent_paths(root: Path) -> list[Path]:
    return _glob([root / ".claude" / "agents", Path.home() / ".claude" / "agents"], "*.md")


def _memory_paths(root: Path) -> list[Path]:
    extra = os.environ.get("SANCHOPANZA_MEMORY_DIR", "")
    bases = [root / ".claude" / "memory", *([Path(extra)] if extra else [])]
    return _glob(bases, "*.md")


def _archive_paths(root: Path) -> list[Path]:
    from .archive import root_for

    base = root_for(root)
    return sorted(base.glob("*/*.txt")) if base.is_dir() else []


def _archive(root: Path, paths: list[Path]) -> list[Candidate]:
    from .archive import load_entries, root_for

    return [Candidate(str(e.path), e.title, e.text) for e in load_entries(root_for(root))]


def _catalog_paths(root: Path) -> list[Path]:
    value = os.environ.get("SANCHOPANZA_TOOL_CATALOG", "")
    return [Path(value)] if value else []


def _catalog(root: Path, paths: list[Path]) -> list[Candidate]:
    out = []
    for path in paths:
        try:
            tools = json.loads(_text(path) or "[]")
        except ValueError:
            continue
        for tool in tools if isinstance(tools, list) else []:
            if isinstance(tool, dict) and tool.get("name"):
                name, about = str(tool["name"]), str(tool.get("description") or "")
                out.append(Candidate(name, f"{name}: {about[:200]}", about[:HEAD]))
    return out


register(Source("code", "Find the code or text a developer must read to work on this: {query}",
                _code_paths, _code))  # fmt: skip
register(Source("symbol", "Find the functions, methods or classes to read or change for this: "
                "{query}", _code_paths, _symbols))  # fmt: skip
register(Source("file", "Find the files a developer must open to work on this: {query}",
                _code_paths, _files))  # fmt: skip
register(Source("skill", "Find the skills (instructions) worth loading for this task: {query}",
                _skill_paths, _documents))  # fmt: skip
register(Source("agent", "Find the agents best suited to take this task: {query}",
                _agent_paths, _documents))  # fmt: skip
register(Source("memory", "Find the stored notes that bear on this: {query}",
                _memory_paths, _documents))  # fmt: skip
register(Source("archive", "Find the earlier tool output that holds what this needs: {query}",
                _archive_paths, _archive))  # fmt: skip
register(Source("tool", "Find the tools needed for this task: {query}",
                _catalog_paths, _catalog))  # fmt: skip
