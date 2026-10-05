"""A `PreToolUse` hook on WebFetch that sends the call to `fetch_passages`, once per URL.

The first WebFetch of a URL in a session is denied with a one-line reason naming the tool; a
second WebFetch of the same URL is let through, so a page the tool cannot read (a PDF, a page
that needs a browser) or a session where the server is missing still gets read. No model.

The page budget, for a small model that opens pages instead of searching (fetch v2): with
`SANCHOPANZA_FETCH_MAX_PAGES=N`, the hook counts a session's pages (`fetch_passages` or WebFetch,
on `PostToolUse`) since its last WebSearch (`PreToolUse`), and from page N + 1 on adds one short
line after the page saying to search first. It never blocks a page. Unset, not a number or
negative: off, and the hook keeps no count. On the fetch pilot one Haiku session opened 28 pages
in a row, one per candidate, at three times the cost of the base session's three searches.

Environment: `SANCHOPANZA_FETCH_HOOK=0` switches it off; `SANCHOPANZA_FETCH_DIR` moves the marks
(default `~/.sanchopanza/fetch`). Fail open: any error lets the WebFetch run and leaves one line
on stderr. Wired by `sanchopanza install --fetch` on WebFetch, off by default; the page budget
needs the hook on WebSearch (`PreToolUse`) and on the two page tools (`PostToolUse`) as well.
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
PAGE_TOOLS = frozenset([TOOL_NAME, "WebFetch"])
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


def max_pages(env: Mapping[str, str] | None = None) -> int | None:
    """Pages in a row with no search before the note; None when the budget is off."""
    raw = _env.get("FETCH_MAX_PAGES", "", env).strip()
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value >= 0 else None


def page_note(pages: int) -> str:
    return (
        f"{pages} pages in a row with no search. Search first (WebSearch) to find the right "
        "page, instead of opening more pages by guesswork."
    )


def _count(event: Mapping[str, Any], env: Mapping[str, str] | None, limit: int) -> dict | None:
    """Count a page, or start again on a search; the note past `limit` pages."""
    session = safe_name(str(event.get("session_id") or ""))
    mark = state_dir(env) / f"pages-{session}.json"
    if event.get("tool_name") == "WebSearch":
        if mark.exists():
            write_private(mark, json.dumps({"pages": 0}))
        return None
    pages = 1 + (int(json.loads(mark.read_text(encoding="utf-8"))["pages"]) if mark.exists() else 0)
    write_private(mark, json.dumps({"pages": pages}))
    if pages <= limit:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "additionalContext": page_note(pages)}}  # fmt: skip


def handle(event: Mapping[str, Any], env: Mapping[str, str] | None = None) -> dict | None:
    """The deny for a URL's first WebFetch in the session; with the page budget on, the count
    and its note; else None (the call runs as it is)."""
    if _off(env):
        return None
    name, tool = event.get("hook_event_name"), event.get("tool_name")
    limit = max_pages(env)
    if limit is not None and (
        (name == "PreToolUse" and tool == "WebSearch")
        or (name == "PostToolUse" and tool in PAGE_TOOLS)
    ):
        return _count(event, env, limit)
    if name != "PreToolUse" or tool != "WebFetch":
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
