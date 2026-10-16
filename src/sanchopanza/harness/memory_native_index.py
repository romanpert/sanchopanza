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
BOM = "\ufeff"
# What JavaScript's String.prototype.trim removes (Claude Code trims the index before cutting).
JS_SPACE = (
    " \t\n\r\v\f\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
    "\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000\ufeff"
)
SWAP_TRIES = 6


def is_ours(line: str) -> bool:
    """`line` (without its "\\n", with or without its "\\r", after a leading BOM) is exactly
    our line."""
    line = line[1:] if line.startswith(BOM) else line
    return bool(_OURS.match(line[:-1] if line.endswith("\r") else line))


def _bom(text: str) -> tuple[str, str]:
    return (BOM, text[1:]) if text.startswith(BOM) else ("", text)


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
    kept = "\n".join(text.strip(JS_SPACE).split("\n")[:INDEX_LINES])
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
    would be past what Claude Code loads or would push any other loaded line out of it."""
    bom, body = _bom(text)
    parts = body.split("\n")
    mine = [i for i, n in enumerate(parts) if is_ours(n)]
    if mine:
        first = mine[0]
        ending = "\r" if parts[first].endswith("\r") else ""
        parts = [line + ending if i == first else n for i, n in enumerate(parts)
                 if i == first or i not in mine]  # fmt: skip
        new = bom + "\n".join(parts)
    else:
        newline = _newline(body)
        head = body if not body or body.endswith("\n") else body + newline
        new = bom + head + line + newline
    after = loaded(new).split("\n")
    if not any(is_ours(n) for n in after):
        return None
    kept = {n.rstrip("\r") for n in after}
    theirs = [n.rstrip("\r") for n in loaded(text).split("\n") if n and not is_ours(n)]
    return new if all(n in kept for n in theirs) else None


def index_without(text: str) -> str:
    bom, body = _bom(text)
    return bom + "\n".join(n for n in body.split("\n") if not is_ours(n))


# ---- files -------------------------------------------------------------------------------------


def linked(path: Path) -> bool:
    """A symbolic link or (Windows) a junction."""
    junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(junction and junction())


def read_only(path: Path) -> bool:
    return path.exists() and not os.access(path, os.W_OK)


def read_text(path: Path) -> str | None:
    """The file as written, "" when absent, None when unreadable or not UTF-8."""
    try:
        return path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return ""
    except (OSError, UnicodeDecodeError):
        return None


def _temp(path: Path, text: str) -> str:
    """`text` in a flushed temporary file beside `path`, with `path`'s mode when it exists
    (always writable by us, so it can be removed)."""
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=TEMP_PREFIX, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        with contextlib.suppress(OSError):
            os.chmod(temp, stat.S_IMODE(path.stat().st_mode) | stat.S_IWUSR)
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


def swap_index(path: Path, build: Callable[[str], str | None], tries: int = SWAP_TRIES) -> str:
    """Rebuild the index from its current text and put it in place unless it changed meanwhile:
    "written", "unchanged", "full" (`build` gave None), "unreadable", "read-only" or "busy". A
    replace Windows refuses (another process has the file open, maybe writing it) goes round
    again from a fresh read: it is never retried over what may have changed."""
    for attempt in range(tries):
        before = read_text(path)
        if before is None:
            return "unreadable"
        if read_only(path):
            return "read-only"
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
                try:
                    os.replace(temp, path)
                    return "written"
                except PermissionError:
                    time.sleep(0.02 * (attempt + 1))
        finally:
            Path(temp).unlink(missing_ok=True)
    return "busy"


def clean_temps(folder: Path, now: float | None = None) -> None:
    cutoff = (time.time() if now is None else now) - STALE_S
    for path in folder.glob(f"{TEMP_PREFIX}*.tmp"):
        with contextlib.suppress(OSError):
            if path.stat().st_mtime < cutoff:
                path.unlink()
