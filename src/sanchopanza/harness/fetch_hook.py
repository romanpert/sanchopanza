"""A `PreToolUse` hook on WebFetch that sends the call to `fetch_passages`, once per URL.

The first WebFetch of a URL in a session is denied with a one-line reason naming the tool; a
second WebFetch of the same URL is let through, so a page the tool cannot read (a PDF, a page
that needs a browser) or a session where the server is missing still gets read. No model.

Environment: `SANCHOPANZA_FETCH_HOOK=0` switches it off; `SANCHOPANZA_FETCH_DIR` moves the marks
(default `~/.sanchopanza/fetch`). Fail open: any error lets the WebFetch run and leaves one line
on stderr. Wired by `sanchopanza install --fetch`, off by default.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import _env
from ..context.archive import safe_name
from ..context.episodes import write_private
from .hookio import stdin_text, stdout_json

PREFIX = "sanchopanza fetch"
FETCH_COMMAND = "sanchopanza fetch-hook"
FETCH_HOOKS = {"PreToolUse": "WebFetch"}
TOOL_NAME = "mcp__sanchopanza-fetch__fetch_passages"
REASON = (
    f"Use {TOOL_NAME}(url, purpose) instead: it returns the page's passages for your purpose, "
    "without a summarising reader. If it cannot read this page, WebFetch the same URL again "
    "and it will run."
)


def state_dir(env: Mapping[str, str] | None = None) -> Path:
    override = _env.get("FETCH_DIR", "", env).strip()
    return Path(override) if override else _env.home_dir() / "fetch"


def _off(env: Mapping[str, str] | None) -> bool:
    return _env.get("FETCH_HOOK", "1", env).strip().lower() in {"0", "false", "no", "off"}


def handle(event: Mapping[str, Any], env: Mapping[str, str] | None = None) -> dict | None:
    """The deny for a URL's first WebFetch in the session, else None (the call runs)."""
    if event.get("hook_event_name") != "PreToolUse" or event.get("tool_name") != "WebFetch":
        return None
    if _off(env):
        return None
    tool_input = event.get("tool_input")
    url = str(tool_input.get("url") or "") if isinstance(tool_input, Mapping) else ""
    if not url:
        return None
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    session = safe_name(str(event.get("session_id") or ""))
    mark = state_dir(env) / f"fetch-{session}-{digest}.json"
    if mark.exists():
        return None
    write_private(mark, json.dumps({"denied_at": time.time()}))
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON,
        }
    }


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        event = json.loads(stdin_text() or "{}")
        if not isinstance(event, Mapping):
            raise ValueError("the event is not a JSON object")
        payload = handle(event)
        if payload is not None:
            stdout_json(payload)
    except Exception as error:  # noqa: BLE001 - fail open, and say so
        with contextlib.suppress(Exception):
            sys.stderr.write(f"{PREFIX}: let the WebFetch run ({error.__class__.__name__})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
