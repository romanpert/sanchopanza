"""A PreToolUse hook that puts a time limit on every Playwright MCP `browser_evaluate`.

python benchmarks/browse/evaluate_guard.py < event.json     # what Claude Code runs

Playwright MCP never stops an evaluate. Twice in the strategy rounds a loop that could not end
(H1 in development; D5 in confirmation 2) hung a session for 30 minutes, and in confirmation 2 one
such hang decided the cost hypothesis. The strategy line asked the model to cap its loops and the
model wrote `while (true)` anyway: a safety property does not belong in a clause the model must
obey. This hook enforces it instead. It rewrites the call's `function` so that it races a timer;
an asynchronous loop that does not finish in time becomes an error the agent reads and can fix.

What it cannot stop: a synchronous loop with no `await` inside it holds the page's only thread,
so no timer can fire. Both recorded hangs awaited inside their loops.

What it does not do: kill the loop. The agent gets its turn back, but an abandoned asynchronous
loop keeps running in the page until the page navigates or closes.

`SANCHOPANZA_EVALUATE_LIMIT_S` sets the limit (default 120 s: a 50-page fetch crawl measured here
takes well under that). No model, no network, no decision: a rewrite.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

EVALUATE = "mcp__playwright__browser_evaluate"
MARK = "/* sanchopanza evaluate guard */"
DEFAULT_LIMIT_S = 120


def wrap(function: str, limit_s: int) -> str:
    """The same function, raced against a timer. Its arguments pass through untouched."""
    message = (
        f"evaluate stopped after {limit_s} s: the code did not return. Cap its loops, or fetch "
        "the data the page loads instead of waiting on the page."
    )
    return (
        f"{MARK} async (...args) => {{ const run = ({function}); "
        f"let timer; const limit = new Promise((_, reject) => {{ timer = setTimeout("
        f"() => reject(new Error({json.dumps(message)})), {limit_s * 1000}); }}); "
        f"try {{ return await Promise.race("
        f"[Promise.resolve().then(() => run(...args)), limit]); }} "
        f"finally {{ clearTimeout(timer); }} }}"
    )


def decide(event: dict[str, Any], limit_s: int) -> dict[str, Any] | None:
    """The hook's answer for one event, or None to leave the call as it is."""
    if event.get("tool_name") != EVALUATE:
        return None
    tool_input = dict(event.get("tool_input") or {})
    function = str(tool_input.get("function") or "")
    if not function.strip() or function.lstrip().startswith(MARK):
        return None
    updated = {**tool_input, "function": wrap(function, limit_s)}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": updated,
        }
    }


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        limit_s = int(os.environ.get("SANCHOPANZA_EVALUATE_LIMIT_S") or DEFAULT_LIMIT_S)
    except ValueError:
        return 0  # fail open: a guard that cannot read its event leaves the call alone
    answer = decide(event, limit_s)
    if answer is not None:
        sys.stdout.write(json.dumps(answer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
