"""Writes that survive the machine going down, not only the process.

A temporary file renamed over the target (`os.replace`) keeps a reader from seeing half a file
while the machine runs. It does not keep the data when the machine stops: the rename can reach
the disk before the temporary file's bytes do, and after an unclean shutdown the target is left
empty or filled with zeros. An appended line likewise can be lost or zeroed. So each write here
flushes and `os.fsync`s the file before the rename (or after the append), and then syncs the
directory entry where the platform allows it.

Used where a crash would lose a record that outlives the process: spend ledgers, the funds
breaker, memory's episodes and benchmark rows. Caches and per-session hook state, which a crash
makes moot, keep their plain writes.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path
from typing import IO, Any


def sync(handle: IO[Any]) -> None:
    """Python's buffer to the OS, and the OS's to the disk."""
    handle.flush()
    os.fsync(handle.fileno())


def sync_dir(directory: Path) -> None:
    """The directory entry of a rename, on POSIX. Windows cannot open a directory for this (NTFS
    journals the rename itself): a no-op there, as wherever the OS refuses."""
    if os.name == "nt":
        return
    with contextlib.suppress(OSError):
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def replace_text(path: Path, text: str, *, temp: Path | None = None, encoding: str = "utf-8",
                 newline: str | None = None) -> None:  # fmt: skip
    """`text` in `temp` (default `<name>.tmp` beside `path`), synced, then put in `path`'s place
    and the directory synced. The bytes are those of `path.write_text(text, encoding, newline)`."""
    temp = temp or path.with_name(path.name + ".tmp")
    with temp.open("w", encoding=encoding, newline=newline) as handle:
        handle.write(text)
        sync(handle)
    os.replace(temp, path)
    sync_dir(path.parent)


def append_text(path: Path, text: str, *, encoding: str = "utf-8",
                newline: str | None = None) -> None:  # fmt: skip
    """`text` appended to `path` and synced before returning."""
    with path.open("a", encoding=encoding, newline=newline) as handle:
        handle.write(text)
        sync(handle)
