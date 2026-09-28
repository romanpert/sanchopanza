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
