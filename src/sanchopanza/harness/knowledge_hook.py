"""A `PreToolUse` hook on WebSearch and WebFetch that sends each to the knowledge server, once.

The first WebSearch of a query, and the first WebFetch of a URL, in a session (both
normalised: `serp.normalize_query`, `serp.normalize_url`) are denied with one line naming
`search` or `read`; the second runs. Capability is never taken away: a page the server cannot
read, or a session without the server, still gets its WebFetch or WebSearch on the second try.
WebSearch runs at once when the last real search found every backend down (`serp.chain_down`,
written by the server). No model.

Environment: `SANCHOPANZA_KNOWLEDGE_HOOK=0` switches it off; `SANCHOPANZA_KNOWLEDGE_DIR` moves
the marks and the chain's state (default `~/.sanchopanza/knowledge`). Fail open: any error lets
the call run and leaves one line on stderr. Wired by `sanchopanza install --knowledge`, which
takes `--fetch`'s place on WebFetch.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import time
from collections.abc import Mapping
from typing import Any

from .. import _env, serp
from .hookio import safe_name, stdin_text, stdout_json, write_private

PREFIX = "sanchopanza knowledge"
KNOWLEDGE_COMMAND = "sanchopanza knowledge-hook"
KNOWLEDGE_HOOKS = {"PreToolUse": "WebSearch|WebFetch"}
SEARCH_TOOL = "mcp__sanchopanza-knowledge__search"
READ_TOOL = "mcp__sanchopanza-knowledge__read"
PICK_TOOL = "mcp__sanchopanza-knowledge__pick"
SEARCH_REASON = (
    f"Use {SEARCH_TOOL}(query) instead: a compact list from Wikipedia and the web, without a "
    "summarising reader. If it cannot answer, WebSearch the same query again and it will run."
)
READ_REASON = (
    f"Use {READ_TOOL}(url_or_path, purpose) instead: the page's passages for your purpose, "
    "without a summarising reader. If it cannot read this page, WebFetch the same URL again "
    "and it will run."
)


def _off(env: Mapping[str, str] | None) -> bool:
    return _env.get("KNOWLEDGE_HOOK", "1", env).strip().lower() in {"0", "false", "no", "off"}


def _key(tool: str, tool_input: Any) -> str:
    given = tool_input if isinstance(tool_input, Mapping) else {}
    if tool == "WebSearch":
        return serp.normalize_query(str(given.get("query") or ""))
    return serp.normalize_url(str(given.get("url") or ""))


def handle(event: Mapping[str, Any], env: Mapping[str, str] | None = None) -> dict | None:
    """The deny for a query's or a URL's first call in the session, else None (it runs)."""
    tool = event.get("tool_name")
    if _off(env) or event.get("hook_event_name") != "PreToolUse":
        return None
    if tool not in ("WebSearch", "WebFetch"):
        return None
    key = _key(str(tool), event.get("tool_input"))
    if not key:
        return None
    if tool == "WebSearch" and serp.chain_down(serp.chain_path(env)):
        return None
    digest = hashlib.sha256(f"{tool}\n{key}".encode()).hexdigest()[:16]
    session = safe_name(str(event.get("session_id") or ""))
    mark = serp.state_dir(env) / "hook" / f"{session}-{digest}.json"
    if mark.exists():
        return None
    write_private(mark, json.dumps({"denied_at": time.time()}))
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": SEARCH_REASON if tool == "WebSearch" else READ_REASON,
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
            sys.stderr.write(f"{PREFIX}: let the call run ({error.__class__.__name__})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
