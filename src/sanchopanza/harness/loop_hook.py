"""The loop guard as a Claude Code hook: "you already have this", "that changed nothing".

`points/loop.py` has existed for a while and has never been wired to a harness: it lived in
`benches/loop.jsonl` and in the evolve runner. This is the wire. It is a `PostToolUse` hook, it
**advises and never denies**, and what it returns is `additionalContext` the agent reads before
its next move.

Why it is worth asking at all, and why that is not settled: the study behind the point measured
coding-agent runs that fell into redundant verification at 18x the clean-run median with no gain
in success (Weinberger and Hozez, 2026). Nobody had looked for the same shape in a *browsing*
session, so it was counted: across 1,124 recorded browsing sessions
(`docs/results/2026-10-02-browse-nav/waste.json`) 9.9 % of tool calls are a read of a page
nothing had changed and 13.7 % come after the last call that changed anything, in a third of the
sessions - **an upper bound, because no counter can tell a redundant read from a necessary
second one.** That is enough to justify asking a judge and not enough to claim a saving.

What it asks, once per acted-on tool result (`points.loop.questions`):

- `goal_met`: does what the agent has established already answer the whole request?
- `repeats_check`: is the call it just made one it has already made, to the same end?

It speaks only above the `saturated` threshold, and only ever one sentence per question. An
agent told "you already have this" that disagrees carries on, which is correct: stopping too
early is the expensive mistake and the person sees it.

Environment (every name is `SANCHOPANZA_<NAME>`):

    LOOP_HOME          where the per-session ledger lives (default `~/.sanchopanza/loop`)
    LOOP_MIN_CALLS     calls in the session before it asks anything at all (default 4)
    LOOP_EVERY         ask once every N tool results (default 1)
    SESSION_MAX_USD    ceiling for this hook per session (default 0.50), shared with autopilot
    T_SATURATED        the threshold the advice speaks above (the policy's own default)
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .. import _env
from ..points import loop as point
from ..text import truncate
from . import hookio

NARRATION = 8  # the last few things the agent said it had found
NARRATION_LIMIT = 170
ACTIONS = 6
ACTION_LIMIT = 70
READ_ONLY = (
    "browser_snapshot", "browser_take_screenshot", "browser_console_messages",
    "browser_network_requests", "Read", "Grep", "Glob", "WebFetch", "find",
)  # fmt: skip


def say(text: str) -> None:
    sys.stderr.write(f"sanchopanza loop: {text}\n")


def _int(name: str, default: int) -> int:
    try:
        return int(_env.get(name, str(default)))
    except ValueError:
        return default


def _ledger_root() -> Path:
    """The autopilot's ledger, reused rather than copied: it already holds dollars and
    decisions per session across processes, and a hook is a fresh process every time.

    `LOOP_HOME` moves it, which a phase needs (one ledger per arm) and a test needs (the
    first version of these tests wrote into the real `~/.sancho`).
    """
    home = _env.get("LOOP_HOME", "")
    return (Path(home) if home else _env.home_dir() / "loop") / "archive"


def short_input(tool: str, arguments: Mapping[str, Any]) -> str:
    """What a call was, in a few words: the URL, the ref, the pattern - not the whole input."""
    for key in ("url", "target", "ref", "pattern", "file_path", "query", "text", "key"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return truncate(value.strip(), ACTION_LIMIT)
    if isinstance(arguments.get("fields"), list):
        names = [str(f.get("name") or f.get("target")) for f in arguments["fields"][:3]]
        return truncate(", ".join(n for n in names if n and n != "None"), ACTION_LIMIT)
    return ""


def established(messages: Sequence[Mapping[str, Any]]) -> str:
    """What the agent says it has: its own narration, which is where findings are stated.

    Not the tool results: a snapshot is 50,000 characters of page and the point's `done` holds
    1,600. The agent's prose between calls is both the shortest and the most faithful record of
    what it believes it has established.
    """
    from ..context.transcript import message_text

    lines = [
        " ".join(message_text(m).split())
        for m in messages
        if m.get("role") == "assistant" and message_text(m).strip()
    ]
    kept = [truncate(line, NARRATION_LIMIT) for line in lines[-NARRATION:]]
    return "\n".join(kept)


def actions_taken(calls: Sequence[Any]) -> str:
    out = []
    for call in calls[-ACTIONS:]:
        name = str(call.tool).split("__")[-1]
        what = short_input(name, call.input)
        out.append(f"{name} {what}".strip() + (" [failed]" if call.is_error else ""))
    return "\n".join(out)


def pending_of(event: Mapping[str, Any]) -> str:
    tool = str(event.get("tool_name") or "").split("__")[-1]
    arguments = event.get("tool_input")
    what = short_input(tool, arguments if isinstance(arguments, Mapping) else {})
    return f"{tool} {what}".strip()


def advice_text(advice: Any) -> str:
    return f"sanchopanza, on the loop: {advice.message}."


async def post_tool_use(event: Mapping[str, Any], squire: Any) -> dict[str, Any]:
    """`additionalContext` when the loop guard has something to say, otherwise nothing."""
    from ..context.transcript import calls as calls_of
    from ..context.transcript import messages_from_claude_code, task_of
    from .autopilot import _charged, read_ledger, write_ledger

    path = event.get("transcript_path")
    if not path or not Path(str(path)).exists():
        return {}
    messages = messages_from_claude_code(str(path))
    calls = calls_of(messages)
    if len(calls) < _int("LOOP_MIN_CALLS", 4):
        return {}
    every = max(1, _int("LOOP_EVERY", 1))
    if len(calls) % every:
        return {}
    goal = task_of(messages)
    done = established(messages)
    if not goal or not done:
        return {}
    root = _ledger_root()
    session = str(event.get("session_id") or "")
    ledger = read_ledger(root, session)
    ceiling = float(_env.get("SESSION_MAX_USD", "0.50") or 0.50)
    if float(ledger.get("usd", 0.0)) >= ceiling:
        say(f"session ceiling reached ({ledger.get('usd'):.4f} of {ceiling:g} USD): silent")
        return {}
    state, questions = point.questions(
        goal=goal,
        done=f"{done}\n\nActions taken:\n{actions_taken(calls)}",
        pending=pending_of(event),
    )
    decision = await squire.decide("loop", state, questions)
    squire.record(decision, calls=len(calls))
    write_ledger(root, session, _charged(ledger, squire))
    advice = point.decide(decision, squire.thresholds)
    if not advice.speaks:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": advice_text(advice),
        }
    }


def main(argv: list[str] | None = None) -> int:
    raw = hookio.stdin_text()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0
    if not isinstance(event, dict) or event.get("hook_event_name") != "PostToolUse":
        return 0
    try:
        from .claude_code import squire_from_env

        output = asyncio.run(post_tool_use(event, squire_from_env(redact=True)))
    except Exception as error:  # fail open at the process boundary, never silently
        say(f"said nothing ({error.__class__.__name__}: {error})")
        return 0
    if output:
        hookio.stdout_json(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
