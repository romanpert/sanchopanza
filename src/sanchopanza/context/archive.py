"""Where cut and pruned tool output goes: `.sanchopanza/archive/<session>/`, beside the project.

Nothing the autopilot takes out of the context is deleted. The full text is written here first
and the agent is told the path, so `Read` gives it back verbatim; a re-run is not the same
thing when the file changed or the page moved.

Each entry is `<name>.txt` (the text, exactly as the tool returned it) and, for entries the
autopilot writes, `<name>.meta.json` (tool, a short summary of the input, characters, time),
which the recall gate reads as the entry's title. Compaction stubs from before the autopilot
have no sidecar and are titled by their file name.

The folder ignores itself in git (`keep_out_of_git`): it holds the conversation's tool output,
secrets included, and must never reach a commit through `git add .`.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HOME = ".sanchopanza"
ARCHIVE = "archive"
META = ".meta.json"
LOAD_LIMIT = 400  # newest entries the recall gate looks at; BM25 over more is still cheap


def keep_out_of_git(path: Path) -> None:
    """A `.sanchopanza` folder on the way to `path` ignores itself: the conversation and the
    pruned results it holds must never reach a commit through `git add .`."""
    for parent in (path, *path.parents):
        if parent.name == HOME:
            parent.mkdir(parents=True, exist_ok=True)
            ignore = parent / ".gitignore"
            if not ignore.exists():
                ignore.write_text("*\n", encoding="utf-8")
            return


def safe_name(value: str) -> str:
    """A file name: letters, digits, `_`, `-` and `.` only, never empty."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", value).strip(".")[:120]
    return cleaned or "entry"


def root_for(cwd: str | Path | None = None, *, override: str | Path | None = None) -> Path:
    """The archive root: `override` if given, else `<cwd>/.sanchopanza/archive`."""
    if override:
        return Path(override)
    base = Path(cwd) if cwd else Path.cwd()
    return base / HOME / ARCHIVE


def session_dir(root: Path, session: str) -> Path:
    return root / safe_name(session or "session")


def write_entry(directory: Path, name: str, text: str, meta: Mapping[str, Any]) -> Path:
    """Write the text and its sidecar; returns the resolved path of the text."""
    keep_out_of_git(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = (directory / f"{safe_name(name)}.txt").resolve()
    path.write_text(text, encoding="utf-8")
    sidecar = {**dict(meta), "chars": len(text), "written": time.time()}
    path.with_name(path.stem + META).write_text(
        json.dumps(sidecar, ensure_ascii=False), encoding="utf-8"
    )
    return path


@dataclass(frozen=True, slots=True)
class Entry:
    path: Path
    text: str
    meta: Mapping[str, Any] = field(default_factory=dict)
    mtime: float = 0.0

    @property
    def title(self) -> str:
        tool = str(self.meta.get("tool") or "")
        about = str(self.meta.get("about") or "")
        if tool or about:
            return f"{tool} {about}".strip()
        return self.path.stem


def _meta(path: Path) -> dict[str, Any]:
    sidecar = path.with_name(path.stem + META)
    try:
        value = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def load_entries(root: Path, *, limit: int = LOAD_LIMIT) -> tuple[Entry, ...]:
    """The newest `limit` archived texts under `root`, every session. Unreadable ones skipped."""
    if not root.is_dir():
        return ()
    found = []
    for path in root.glob("*/*.txt"):
        try:
            found.append((path.stat().st_mtime, path))
        except OSError:
            continue
    found.sort(key=lambda mp: mp[0], reverse=True)
    out: list[Entry] = []
    for mtime, path in found[:limit]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out = [*out, Entry(path.resolve(), text, _meta(path), mtime)]
    return tuple(out)


# --- pull recall: the agent searches the archive itself, no decider -------------------------

SEARCH_MAX = 5
WINDOW = 600
EMPTY = "The archive at {root} holds no entries yet: nothing was cut or pruned in this project."


def _terms(query: str) -> list[str]:
    from ..text import _bm25_words

    return _bm25_words(query)


def best_window(text: str, query: str, size: int = WINDOW) -> str:
    """The `size`-character slice of `text` with the most query-term hits; the head if none."""
    if len(text) <= size:
        return text
    terms = _terms(query)
    lowered = text.lower()
    step = max(1, size // 4)
    best, best_score = 0, 0
    for start in range(0, len(text) - size + step, step):
        chunk = lowered[start : start + size]
        score = sum(chunk.count(t) for t in terms)
        if score > best_score:
            best, best_score = start, score
    start = min(best, len(text) - size)
    prefix = "..." if start > 0 else ""
    suffix = "..." if start + size < len(text) else ""
    return f"{prefix}{text[start : start + size]}{suffix}"


def _meta_line(entry: Entry) -> str:
    shown = {k: v for k, v in entry.meta.items() if k != "written"}
    return json.dumps(shown, ensure_ascii=False) if shown else "(no sidecar)"


def search(root: Path, query: str, k: int = 3) -> str:
    """BM25 over every archived entry under `root`: path, meta line and best window per hit.

    Pure code: no decider, no key. `k` is clamped to 1..`SEARCH_MAX`.
    """
    from ..text import bm25_scores

    query = str(query or "").strip()
    if not query:
        return "Give a query: words, a code or a file name that the archived output holds."
    entries = load_entries(root)
    if not entries:
        return EMPTY.format(root=root)
    k = max(1, min(int(k), SEARCH_MAX))
    scores = bm25_scores(query, [f"{e.title}\n{e.text}" for e in entries])
    ranked = sorted((i for i, s in enumerate(scores) if s > 0), key=lambda i: -scores[i])[:k]
    if not ranked:
        return f"No archived entry under {root} matches {query!r} ({len(entries)} searched)."
    hits = [
        f"[{n}] {entries[i].path}\nmeta: {_meta_line(entries[i])}\n"
        f"{best_window(entries[i].text, query)}"
        for n, i in enumerate(ranked, 1)
    ]
    return "\n\n".join(hits) + "\n\nRead a path above for the full text."
