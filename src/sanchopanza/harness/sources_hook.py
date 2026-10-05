"""Sources: a Claude Code `Stop` hook that asks a web-research session to show its sources once.

At the first `Stop` of a session that searched or browsed the web, the hook blocks the stop with
one request: list every condition in the question, and for each the source (URL and exact
sentence) that meets it for the answer; look for a missing one or say it is unsourced; then
repeat the final answer line. Claude Code feeds the reason back and the agent continues once.

No model and no decision: the only judgment left is the agent's own, on its own transcript.
It asks once per session, ever: a mark per `session_id` is written before the block, and the
hook stands aside when `stop_hook_active` is set (Claude Code's own guard against stop loops).
`SubagentStop` is not handled: a subagent's stop is not the answer. A session with no web call
(`WebSearch`, `WebFetch`, any MCP server's `browser_*` or `fetch` tools) is never asked.

Environment: `SANCHOPANZA_SOURCES=0` switches it off; `SANCHOPANZA_SOURCES_DIR` moves the marks
(default `~/.sanchopanza/sources`). Fail open everywhere: any error lets the session stop and
leaves one line on stderr.

Not measured yet: wired by `sanchopanza install --sources`, off by default.
"""

from __future__ import annotations

import contextlib
import json
import re
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .. import _env
from ..context.archive import safe_name
from ..context.episodes import write_private
from ..context.transcript import calls, messages_from_claude_code
from .hookio import stdin_text, stdout_json

PREFIX = "sanchopanza sources"
SOURCES_COMMAND = "sanchopanza sources-hook"
# Event -> matcher for sources (`--sources`): the main agent's stop only.
SOURCES_HOOKS = {"Stop": ""}
WEB_TOOL = re.compile(r"^(?:WebSearch|WebFetch|mcp__.+__(?:browser_.+|fetch\w*))$")
MIN_WEB_CALLS = 1

REQUEST = (
    "sanchopanza: before you stop, show your sources. List every condition in the question, "
    "and for each one give the source that meets it for your answer: the URL and the exact "
    "sentence from that page. If a condition has no source, look for one now, or say plainly "
    "that it is unsourced. Then end by repeating your final answer line in the same format as "
    'before ("ANSWER: ..." if you used it).'
)


def state_dir() -> Path:
    override = _env.get("SOURCES_DIR").strip()
    return Path(override) if override else _env.home_dir() / "sources"


def _off(env: Mapping[str, str] | None) -> bool:
    return _env.get("SOURCES", "1", env).strip().lower() in {"0", "false", "no", "off"}


def web_calls(transcript: Path) -> int:
    return sum(1 for c in calls(messages_from_claude_code(transcript)) if WEB_TOOL.match(c.tool))


def handle(event: Mapping[str, Any], env: Mapping[str, str] | None = None) -> dict | None:
    """`Stop`: the block with the request, or None to let the session stop."""
    if event.get("hook_event_name") != "Stop" or event.get("stop_hook_active") or _off(env):
        return None
    mark = state_dir() / f"sources-{safe_name(str(event.get('session_id') or ''))}.json"
    if mark.exists():
        return None
    if web_calls(Path(str(event.get("transcript_path") or ""))) < MIN_WEB_CALLS:
        return None
    write_private(mark, json.dumps({"asked_at": time.time()}))  # first: never ask twice
    return {"decision": "block", "reason": REQUEST}


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
            name = error.__class__.__name__
            sys.stderr.write(f"{PREFIX}: let the session stop ({name}: {error})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
