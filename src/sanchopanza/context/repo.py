"""Find what to read in a repository: the fragments of code and docs that bear on a request.

    python -m sanchopanza.context.repo "why does pagination skip the first page" [--root .]

The same two stages as every other "few among many" in the package (`sanchopanza.select`):
the repository is cut into fragments by code (`context.blocks.split`: top-level definitions
for code, paragraphs for prose), BM25 over path and text keeps a shortlist, and, with a
decider, `triage_many` judges the shortlist in context. Without a key it is a free, local
BM25 search with line numbers, which is already more than `grep` for a question in words.

Files come from `git ls-files` when the root is a git work tree (so `.gitignore` holds), else
from a walk that skips dependency, build and cache directories. Binary files, files over
`MAX_FILE_BYTES` and lock files are skipped. The index is kept in memory per root and rebuilt
when a file's size or modification time changes.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any

from ..select import Candidate, Pick, index_of, select
from ..text import BM25Index
from .archive import best_window
from .blocks import CODE_SUFFIXES, PROSE_SUFFIXES, split

MAX_FILE_BYTES = 300_000
MAX_FRAGMENTS = 200_000
TARGET = 1_200  # characters per fragment: a function or two, a few paragraphs
SKIP_DIRS = frozenset(
    [
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "dist",
        "build",
        "target",
        ".next",
        ".cache",
        ".sanchopanza",
        ".idea",
        ".vscode",
    ]
)
SKIP_NAMES = frozenset(
    ["package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock"]
)
TEXT_SUFFIXES = (
    CODE_SUFFIXES
    | PROSE_SUFFIXES
    | frozenset(
        [
            ".cfg",
            ".ini",
            ".toml",
            ".yaml",
            ".yml",
            ".json",
            ".sh",
            ".ps1",
            ".sql",
            ".txt",
            ".rst",
            ".html",
            ".css",
            ".xml",
            ".gradle",
        ]
    )
)
PURPOSE = "Find the code or text a developer must read to work on this: {query}"


def _git_files(root: Path) -> list[str] | None:
    try:
        run = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if run.returncode != 0:
        return None
    return [p for p in run.stdout.decode("utf-8", "replace").split("\0") if p]


def _walk_files(root: Path) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        rel = Path(dirpath).relative_to(root)
        out += [(rel / name).as_posix() for name in sorted(filenames)]
    return out


def files(root: Path) -> list[str]:
    """Relative paths of the text files worth indexing, in a stable order."""
    listed = _git_files(root)
    if listed is None:
        listed = _walk_files(root)
    keep = []
    for rel in listed:
        parts = PurePath(rel).parts
        if any(p in SKIP_DIRS for p in parts[:-1]) or parts[-1] in SKIP_NAMES:
            continue
        suffix = PurePath(rel).suffix.lower()
        if suffix and suffix not in TEXT_SUFFIXES:
            continue
        keep.append(rel)
    return sorted(set(keep))


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return None
        raw = path.read_bytes()
    except OSError:
        return None
    if b"\0" in raw[:8192]:
        return None
    return raw.decode("utf-8", "replace")


def _headline(text: str) -> str:
    """The first meaningful line of a fragment: usually its definition or heading."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith(("#!", '"""', "'''")):
            return stripped[:100]
    return ""


def chunks(root: Path) -> list[Candidate]:
    """Every fragment of every indexed file: key `path:first-last`, title with the headline."""
    out: list[Candidate] = []
    for rel in files(root):
        text = _read(root / rel)
        if not text or not text.strip():
            continue
        kind = "prose" if PurePath(rel).suffix.lower() in PROSE_SUFFIXES else "code"
        for block in split(text, kind, target=TARGET):
            body = block.of(text)
            if not body.strip():
                continue
            key = f"{rel}:{block.first_line}-{block.last_line}"
            out.append(Candidate(key, f"{key} {_headline(body)}".strip(), body))
            if len(out) >= MAX_FRAGMENTS:
                return out
    return out


@dataclass
class _Cached:
    fingerprint: tuple[Any, ...]
    candidates: list[Candidate]
    index: BM25Index


_CACHE: dict[str, _Cached] = {}


def _fingerprint(root: Path, listed: list[str]) -> tuple[Any, ...]:
    stamps = []
    for rel in listed:
        try:
            st = (root / rel).stat()
        except OSError:
            continue
        stamps.append((rel, st.st_size, int(st.st_mtime)))
    return tuple(stamps)


def indexed(root: Path) -> tuple[list[Candidate], BM25Index]:
    """The fragments of `root` and their BM25 index, rebuilt only when a file changed."""
    root = root.resolve()
    fingerprint = _fingerprint(root, files(root))
    cached = _CACHE.get(str(root))
    if cached is None or cached.fingerprint != fingerprint:
        candidates = chunks(root)
        cached = _Cached(fingerprint, candidates, index_of(candidates))
        _CACHE[str(root)] = cached
    return cached.candidates, cached.index


def _source(kind: str, root: Path) -> tuple[list[Candidate], BM25Index, str]:
    """The candidates, index and judge's purpose of one kind (`context.sources`). `code` is the
    measured path, its own cache and purpose unchanged."""
    if kind == "code":
        candidates, index = indexed(root)
        return candidates, index, PURPOSE
    from .sources import SOURCES
    from .sources import indexed as source_indexed

    candidates, index = source_indexed(kind, root)
    return candidates, index, SOURCES[kind].purpose


async def search(
    query: str,
    root: Path,
    *,
    squire: Any = None,
    k: int = 8,
    shortlist_k: int = 60,
    kind: str = "code",
) -> list[Pick]:
    candidates, index, purpose = _source(kind, root)
    return await select(
        query,
        candidates,
        squire=squire,
        purpose=purpose.format(query=query),
        shortlist_k=shortlist_k,
        keep=k,
        index=index,
    )


def render(picks: list[Pick], query: str, *, root: Path, searched: int) -> str:
    if not picks:
        return f"Nothing in {root} matches {query!r} ({searched} fragments searched)."
    judged = any(p.p is not None for p in picks)
    head = "judged in context" if judged else "BM25, no judge"
    lines = [f"{len(picks)} of {searched} candidates ({head}). Read a path for the full text."]
    for n, pick in enumerate(picks, 1):
        mark = f" p={pick.p:.2f}" if pick.p is not None else ""
        excerpt = best_window(pick.candidate.text, query, 300).strip()
        lines.append(f"[{n}] {pick.candidate.key}{mark}\n{excerpt}")
    return "\n\n".join(lines)


async def find(
    query: str, root: Path, *, squire: Any = None, k: int = 8, kind: str = "code"
) -> str:
    """Search `root` for candidates of `kind` (`context.sources`: code, symbol, file, skill,
    agent, memory, archive, tool, or any registered one) and render them as keys to Read."""
    from .sources import kinds

    query = str(query or "").strip()
    if not query:
        return "Give a query: what you are trying to do or find, in words or identifiers."
    kind = str(kind or "code").strip().lower()
    if kind not in kinds():
        return f"Unknown kind {kind!r}; known: {', '.join(kinds())}."
    picks = await search(query, root, squire=squire, k=max(1, min(int(k), 20)), kind=kind)
    return render(picks, query, root=root, searched=len(_source(kind, root)[0]))


HINT_MAX_FILES = 3_000  # a hook is a fresh process: past this, indexing would stall the prompt
HINT_HEADER = "Files that may bear on this request (BM25 over the repository; Read to check):"


def hint(query: str, root: Path, *, k: int = 5) -> str:
    """One short appended note for a prompt: the likely files and lines, free (BM25 only), or
    nothing. Skipped for a repository with more than `HINT_MAX_FILES` text files, because a
    hook cannot keep the index between prompts. Unmeasured end to end: opt-in."""
    query = str(query or "").strip()
    if len(query) < 12 or len(files(root)) > HINT_MAX_FILES:
        return ""
    candidates, index = indexed(root)
    picks = [candidates[i].key for i, _ in index.top(query, k)]
    return "\n".join([HINT_HEADER, *(f"- {key}" for key in picks)]) if picks else ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sanchopanza.context.repo")
    parser.add_argument("query")
    parser.add_argument("--root", default=".")
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--free", action="store_true", help="BM25 only, never a decider")
    parser.add_argument("--kind", default="code", help="code, symbol, file, skill, agent, ...")
    args = parser.parse_args(argv)
    squire = None
    if not args.free:
        from ..harness.claude_code import squire_from_env

        squire = squire_from_env()
    found = find(args.query, Path(args.root), squire=squire, k=args.k, kind=args.kind)
    sys.stdout.write(asyncio.run(found))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
