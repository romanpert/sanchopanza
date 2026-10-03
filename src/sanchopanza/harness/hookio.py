"""A hook's stdin and stdout, in UTF-8 whatever the console code page.

Claude Code sends the event as UTF-8 JSON. On Windows `sys.stdin.read()` decodes it with the
console code page, so "Á" (C3 81), "Ð" (C3 90) or "═" (E2 95 90) become surrogates or raise, the
hook fails open, and a shell guard lets the command through unguarded (found by another session
on a real `claude -p` transcript, 2026-09-30). The event is read as bytes and decoded as UTF-8;
the answer is written as ASCII-escaped JSON, which every code page can carry. Standard library
only (and `_env`, which is too): every hook imports this before it knows whether it has anything
to decide.

Per-session state lives in one folder, `SANCHOPANZA_GUARD_DIR` (default `~/.sanchopanza/guard`),
never the project directory, which the agent searches: one private file per session and purpose.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from .. import _env


def stdin_text() -> str:
    buffer = getattr(sys.stdin, "buffer", None)
    if buffer is None:
        return sys.stdin.read()
    return buffer.read().decode("utf-8", "replace")


def stdout_text(text: str) -> None:
    buffer = getattr(sys.stdout, "buffer", None)
    if buffer is None:
        sys.stdout.write(text)
        return
    buffer.write(text.encode("utf-8"))
    buffer.flush()


def stdout_json(payload: Any) -> None:
    stdout_text(json.dumps(payload))  # ASCII-escaped: safe on any console code page


def state_dir() -> Path:
    return Path(_env.get("GUARD_DIR", "") or _env.home_dir() / "guard")


def safe_name(session: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in session) or "session"


def write_private(path: Path, text: str) -> None:
    """Write `text` readable by this user only (state can hold command output)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
