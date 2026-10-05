"""What phase D's runner checks that no seal covers. Free, no session.

- `inputs`: the sha256 of what both arms (or the grade) load from outside the repository: Claude
  Code's user instructions (`~/.claude/CLAUDE.md`) and rules (`~/.claude/rules/*.md`), the
  harness's copy of the dataset rows (`verified-rows.json`) and its Windows wrapper (`run_swe.py`).
  Recorded when the batch starts and compared before every pair (`run_d.pair_refusal`).
- `take_lock`: one batch at a time, by a lock file created exclusively with the process id; the
  lock of a process that is gone (a crash) is taken over, and said.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable
from pathlib import Path


def file_sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def inputs(claude_home: Path, swe: Path) -> dict[str, str | None]:
    """path (under ~ written as such) -> sha256, None for a file that is not there."""
    paths = [claude_home / "CLAUDE.md", *sorted((claude_home / "rules").glob("*.md")),
             swe / "verified-rows.json", swe / "run_swe.py"]  # fmt: skip
    home = Path.home()
    return {("~/" + p.relative_to(home).as_posix()) if home in p.parents else p.as_posix():
            file_sha(p) for p in paths}  # fmt: skip


def changed(recorded: dict[str, str | None], now: dict[str, str | None]) -> list[str]:
    return sorted(k for k in {*recorded, *now} if recorded.get(k) != now.get(k))


def pid_alive(pid: str) -> bool:
    if not pid.isdigit():
        return False
    done = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True,
                          text=True)  # fmt: skip
    return pid in done.stdout.split()


def take_lock(lock: Path, say: Callable[[str], None]) -> Path:
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        holder = lock.read_text(encoding="utf-8").strip()
        if pid_alive(holder):
            raise SystemExit(f"another batch runs (pid {holder}, {lock})")
        say(f"stale lock of pid {holder} taken over")
        lock.unlink()
    handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        os.write(handle, str(os.getpid()).encode())
    finally:
        os.close(handle)
    return lock
