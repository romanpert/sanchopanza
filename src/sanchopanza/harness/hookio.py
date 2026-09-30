"""A hook's stdin and stdout, in UTF-8 whatever the console code page.

Claude Code sends the event as UTF-8 JSON. On Windows `sys.stdin.read()` decodes it with the
console code page, so "Á" (C3 81), "Ð" (C3 90) or "═" (E2 95 90) become surrogates or raise, the
hook fails open, and a shell guard lets the command through unguarded (found by another session
on a real `claude -p` transcript, 2026-09-30). The event is read as bytes and decoded as UTF-8;
the answer is written as ASCII-escaped JSON, which every code page can carry. Standard library
only: every hook imports this before it knows whether it has anything to decide.
"""

from __future__ import annotations

import json
import sys
from typing import Any


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
