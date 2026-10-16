"""The memory bridge's file work in Claude Code's auto-memory folder (`memory_native`).

Never harm what is not ours:

- **Our line** is one exact line, `- [TITLE](NOTE) — read before continuing: "<hook>"`, matched
  whole (`is_ours`). A person's line that links the same name is theirs. Lines split on "\\n"
  only; every other byte of the index (a "\\r", U+2028, U+0085) is kept as it was, and an added
  line ends the way the file's lines end.
- **Our note** carries an owner mark in its front matter (`is_owned_note`); a file of that name
  without it is never written or removed.
- **The swap** (`swap_index`): the index is read, the new text built from it, written to a
  temporary file and flushed, and read again just before `os.replace`. If it changed in between
  (Claude Code saving a memory), the new text is built again from the fresh one; after a second
  change nothing is written. A link (symbolic) is refused, the file's mode is kept, and our own
  temporaries older than STALE_S are removed.
- **What Claude Code loads** (`loaded`): the trimmed index's first 200 lines, then 25,000 UTF-16
  units cut back to a line end (`_hn` in Claude Code 2.1.287).
"""

from __future__ import annotations

import contextlib
import os
import re
import stat
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

NOTE = "sanchopanza-next.md"
INDEX = "MEMORY.md"
INDEX_LINES = 200
INDEX_UNITS = 25_000
TITLE = "Where the last session left off"
LINE_HEAD = f"- [{TITLE}]({NOTE}) — read before continuing: "
OWNER = "  owner: sanchopanza"
NOTE_HEAD = "---\nname: sanchopanza-next\n"
TEMP_PREFIX = ".sanchopanza-"
STALE_S = 600.0
_OURS = re.compile("^" + re.escape(LINE_HEAD) + '"[^"\n]*"$')


def is_ours(line: str) -> bool:
    """`line` (without its "\\n", with or without its "\\r") is exactly our line."""
    return bool(_OURS.match(line[:-1] if line.endswith("\r") else line))


def is_owned_note(text: str) -> bool:
    if not text.startswith(NOTE_HEAD):
        return False
    end = text.find("\n---", len(NOTE_HEAD) - 1)
    return end > 0 and f"\n{OWNER}\n" in text[: end + 1]


def _units(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def _prefix(text: str, units: int) -> int:
    """How many characters of `text` fit in `units` UTF-16 units."""
    count = 0
    for i, char in enumerate(text):
        count += 2 if ord(char) > 0xFFFF else 1
        if count > units:
            return i
    return len(text)


def loaded(text: str) -> str:
    kept = "\n".join(text.strip().split("\n")[:INDEX_LINES])
    if _units(kept) > INDEX_UNITS:
        room = _prefix(kept, INDEX_UNITS)
        cut = kept.rfind("\n", 0, room)
        kept = kept[: cut if cut > 0 else room]
    return kept


def _newline(text: str) -> str:
    lines = text.split("\n")[:-1]
    crlf = sum(1 for n in lines if n.endswith("\r"))
    return "\r\n" if lines and crlf * 2 > len(lines) else "\n"


def index_with(text: str, line: str) -> str | None:
    """The index with our line (ours replaced in place, else appended), or None when our line
    would be past what Claude Code loads."""
    parts = text.split("\n")
    mine = [i for i, n in enumerate(parts) if is_ours(n)]
    if mine:
        first = mine[0]
        ending = "\r" if parts[first].endswith("\r") else ""
        parts = [line + ending if i == first else n for i, n in enumerate(parts)
                 if i == first or i not in mine]  # fmt: skip
        new = "\n".join(parts)
    else:
        newline = _newline(text)
        head = text if not text or text.endswith("\n") else text + newline
        new = head + line + newline
    return new if any(is_ours(n) for n in loaded(new).split("\n")) else None


def index_without(text: str) -> str:
    return "\n".join(n for n in text.split("\n") if not is_ours(n))


# ---- files -------------------------------------------------------------------------------------


def linked(path: Path) -> bool:
    return path.is_symlink()


def read_text(path: Path) -> str | None:
    """The file as written, "" when absent, None when unreadable or not UTF-8."""
    try:
        return path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError):
        return None


def _temp(path: Path, text: str) -> str:
    """`text` in a flushed temporary file beside `path`, with `path`'s mode when it exists."""
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=TEMP_PREFIX, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        with contextlib.suppress(OSError):
            os.chmod(temp, stat.S_IMODE(path.stat().st_mode))
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return temp


def _replace(temp: str, path: Path, tries: int = 25) -> None:
    """`os.replace`, again while Windows says the file is busy."""
    for attempt in range(tries):
        try:
            os.replace(temp, path)
            return
        except PermissionError:
            if attempt == tries - 1:
                raise
            time.sleep(0.01)


def write(path: Path, text: str) -> None:
    """Atomic: flushed to a temporary file beside `path`, then put in its place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = _temp(path, text)
    try:
        _replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def before_swap(path: Path) -> None:
    """Called between building the new index and checking it again (a seam for the tests)."""


def swap_index(path: Path, build: Callable[[str], str | None], tries: int = 2) -> str:
    """Rebuild the index from its current text and put it in place unless it changed meanwhile:
    "written", "unchanged", "full" (`build` gave None), "unreadable" or "busy"."""
    for _ in range(tries):
        before = read_text(path)
        if before is None:
            return "unreadable"
        new = build(before)
        if new is None:
            return "full"
        if new == before:
            return "unchanged"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = _temp(path, new)
        try:
            before_swap(path)
            if read_text(path) == before:
                _replace(temp, path)
                return "written"
        finally:
            Path(temp).unlink(missing_ok=True)
    return "busy"


def clean_temps(folder: Path, now: float | None = None) -> None:
    cutoff = (time.time() if now is None else now) - STALE_S
    for path in folder.glob(f"{TEMP_PREFIX}*.tmp"):
        with contextlib.suppress(OSError):
            if path.stat().st_mtime < cutoff:
                path.unlink()
