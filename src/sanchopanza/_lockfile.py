"""One exclusive lock file per guarded file, for read-modify-write across processes.

`<path>.lock` is created with O_CREAT | O_EXCL while the block runs and removed after it. A lock
older than `stale_s` is a crashed holder's and is taken over. Past `wait_s` two policies:

- lenient (the default): the block runs anyway. A hook must never hang the session, and a
  lost memory record is cheaper than a stuck agent (`context.episodes.locked`).
- strict: `LockTimeout`. A spend ledger must never be written without it (`budget.SpendLedger`):
  a cap that two processes can both pass is no cap.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Iterator
from pathlib import Path

WAIT_S = 2.0
STALE_S = 10.0


class LockTimeout(TimeoutError):
    """A strict lock was not taken within its wait."""


@contextlib.contextmanager
def locked(
    path: Path,
    *,
    wait_s: float = WAIT_S,
    stale_s: float = STALE_S,
    strict: bool = False,
) -> Iterator[None]:
    lock = path.with_name(path.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    deadline = time.monotonic() + wait_s
    held = False
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            held = True
            break
        except (FileExistsError, PermissionError):  # Windows: a lock being deleted says denied
            with contextlib.suppress(OSError):
                if time.time() - lock.stat().st_mtime > stale_s:
                    lock.unlink()
                    continue
            if time.monotonic() > deadline:
                break
            time.sleep(0.01)
        except OSError:
            break
    if not held and strict:
        raise LockTimeout(f"{lock} not taken within {wait_s:g} s")
    try:
        yield
    finally:
        if held:
            with contextlib.suppress(OSError):
                lock.unlink()
