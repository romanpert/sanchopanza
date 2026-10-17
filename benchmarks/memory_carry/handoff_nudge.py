"""The equal-work lot's nudge (docs/results/2026-10-17-memory-equal-work/prereg.md, rule R3).

After session 2, the scene's checks run. When `task` fails (step 2 is not there), the arm gets
**one** more turn: session 2 resumed (`claude -p --resume <session 2 id>`) with NUDGE, the same
fixed text in N0 and S', under the run's call cap; then the checks run again and decide. A person
who answers "yes, go ahead" to a session that stopped to ask: perfect (the trigger is the code's
own check) and free (the person's time is not counted). Nothing here calls Claude Code: the call
is `handoff.handoff_step`, reused, and `handoff.nudge_step` around it.

- `wanted`: the trigger, `task` failed after session 2 (and only that: a step 2 that is there but
  breaks C or D gets no nudge, as a person who sees the step done would not send one);
- `cut_of`: why a nudge is NOT RUN (the arm is cut): a timeout, no result, another model or
  Claude Code, a turn that is not session 2's session or did not carry its context. A turn
  stopped by its own budget counts as run, as a session does (`carry.session_ran`);
- `starts_since`: the SessionStart sources S's memory hook logged since a row count (Claude Code
  sends `resume` for a resumed session): recorded, not required;
- `row_facts`: what the row keeps: `kept_all_s2` and the checks after session 2 (`checks_s2`),
  `nudged`, and the nudge's own facts (`nudge`); `kept_all` and the `*_pass` of the row are the
  checks after the nudge when there was one, else those after session 2.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import carry

NUDGE = "Yes, go ahead."
TAG = "nudge"  # its stream: <arm record>/nudge.jsonl
STEP = f"nudge: claude -p --resume <session 2 id> {NUDGE!r}"
KEPT = (
    "tag",
    "returncode",
    "subtype",
    "cost",
    "cost_reported",
    "cost_reported_total",
    "cost_source",
    "cost_charged",
    "resumed",
    "context_carried",
    "same_session",
    "first_prompt",
    "last_prompt",
    "tokens",
    "seconds",
    "started",
    "turns",
    "tools",
    "touched",
    "subagents",
    "timeout",
    "error",
    "init",
    "session_starts",
    "tree_kept",
    "first_request",
    "session_2_last_request",
)


def wanted(after_s2: dict[str, Any]) -> bool:
    """The nudge's trigger: the scene's `task` check failed after session 2."""
    return after_s2.get("task_pass") is False


def cut_of(turn: dict[str, Any], is_pinned: bool) -> str:
    """Why the nudge is NOT RUN ("" when it ran)."""
    if turn.get("timeout"):
        return "nudge: timeout"
    if not carry.session_ran(turn):
        why = turn.get("error") or f"exit {turn.get('returncode')}"
        return f"nudge: the turn ended without a result ({why})"
    if not is_pinned:
        init = turn.get("init") or {}
        return f"nudge: ran {init.get('model')} on {init.get('version')}"
    if turn.get("same_session") is False:
        return "nudge: the resumed turn is not session 2's session"
    if turn.get("context_carried") is False:
        return "nudge: the resumed turn did not carry session 2's context"
    return ""


def starts_since(work: Path, since: int) -> list[str]:
    """The sources of the SessionStart events S's memory hook answered after the first `since`
    rows of its log (`carry_hook.py`'s `hooks.jsonl`)."""
    path = work / "hooks.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[since:]:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        rows += [row] if isinstance(row, dict) else []
    return [str(r.get("source")) for r in rows
            if r.get("sub") == "memory-hook" and r.get("event") == "SessionStart"]  # fmt: skip


def usages(stream: Path) -> list[dict[str, int]]:
    """Each request's tokens in a stream (its assistant events' usage), in order."""
    out = []
    raw = stream.read_text(encoding="utf-8") if stream.exists() else ""
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") if isinstance(event, dict) else None
        if event.get("type") == "assistant" and isinstance(message, dict):
            used = message.get("usage") or {}
            kinds = {"input": "input_tokens", "cache_read": "cache_read_input_tokens",
                     "cache_write": "cache_creation_input_tokens"}  # fmt: skip
            out.append({k: int(used.get(v) or 0) for k, v in kinds.items()})
    return out


def requests(rec: Path) -> dict[str, Any]:
    """The nudge's first request and session 2's last one: a warm resume reads session 2's
    context from the cache; a cold one writes it again (reported, not deciding)."""
    first = usages(rec / f"{TAG}.jsonl")[:1]
    last = usages(rec / "session-2.jsonl")[-1:]
    return {"first_request": first[0] if first else None,
            "session_2_last_request": last[0] if last else None}  # fmt: skip


def facts(push: dict[str, Any]) -> dict[str, Any]:
    if not push:
        return {}
    return {**{k: push[k] for k in KEPT if k in push}, "chars": len(str(push.get("text") or ""))}


def row_facts(on: bool, before: dict[str, Any], push: dict[str, Any]) -> dict[str, Any]:
    """The row's nudge fields (none in a run without the nudge, or before session 2's checks)."""
    if not on or not before:
        return {}
    return {"checks_s2": before, "kept_all_s2": before["kept_all"], "nudged": bool(push),
            "nudge": facts(push)}  # fmt: skip
