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

It speaks only above the `saturated` threshold, and only ever one sentence per question.

And one thing it counts rather than asks: a streak of failed tool calls. At two failures in a
row, and again at four, it says so once, and for browser calls it points at `browser_snapshot`
(`error_note`, with the session that showed why). An
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
import re
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
FACTS_LIMIT = 600
LINE_LIMIT = 240  # one line of a page: long enough for a sentence, short of a whole paragraph
ACTIONS = 6
ACTION_LIMIT = 70
ERROR_NOTES_AT = (2, 4)  # a failed streak of this length gets one deterministic note
REASON_LIMIT = 90


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


def narration(messages: Sequence[Mapping[str, Any]]) -> str:
    """What the agent says it is doing: its prose between calls."""
    from ..context.transcript import message_text

    lines = [
        " ".join(message_text(m).split())
        for m in messages
        if m.get("role") == "assistant" and message_text(m).strip()
    ]
    return "\n".join(truncate(line, NARRATION_LIMIT) for line in lines[-NARRATION:])


_CODE = re.compile(r"```(?:js|javascript|ts|typescript)\b.*?```", re.S)
# A snapshot line: `- role "name" [attr] [ref=e12] [cursor=pointer]: text`. Groups: role, name,
# and whatever follows the colon.
_TREE = re.compile(
    r"^-\s*(?P<role>[\w-]+)"  # the role
    r'(?:\s+"(?P<name>(?:[^"\\]|\\.)*)")?'  # its quoted name, if any
    r"(?:\s*\[[^\]]*\])*"  # [ref=e12] [cursor=pointer] [level=2] ...
    r"\s*:?\s*(?P<text>.*)$"  # and what follows the colon
)
_NOISE = (
    "###", "```", "[image]", "[Image", "- [Screenshot", "- Console:", "- New console",
    "/url:", "Found ", "await page", "//",
)  # fmt: skip
_CONTAINERS = frozenset({"generic", "group", "list", "listitem", "main", "banner", "navigation",
                         "contentinfo", "complementary", "region", "document", "img", "row",
                         "rowgroup", "table", "cell", "form", "article", "section"})  # fmt: skip


def page_line(line: str) -> str:
    """One line of a tool result as what it says, or "" when it says nothing.

    `- generic [ref=e276]: "Item total: $55.97"` becomes `Item total: $55.97`;
    `- button "Finish" [ref=e255] [cursor=pointer]` becomes `button Finish`; a bare container,
    Playwright's own code, a screenshot's path and a console count become nothing.
    """
    raw = line.strip()
    if not raw:
        return ""
    if raw.startswith(("- Page URL:", "- Page Title:")):
        return raw[2:].strip()
    if raw.startswith(_NOISE):
        return ""
    match = _TREE.match(raw)
    if not match:
        return "" if raw.startswith("-") else raw
    role, name = match["role"], (match["name"] or "").replace('\\"', '"')
    text = match["text"].strip().strip('"').strip()
    if role == "text":
        return text
    if role in _CONTAINERS:
        return " ".join(part for part in (name, text) if part)
    return " ".join(part for part in (role, name, text) if part) if (name or text) else ""


def facts_seen(result: str, goal: str, budget: int = FACTS_LIMIT) -> str:
    """What the result in front of the agent says, short enough to be part of `done`.

    Measured reasons, both from 2026-10-02:

    - With `done` built from the narration alone, `goal_met` stayed at 0.01-0.03 right through
      sessions that ended with the answer in hand: a small model narrates its intent ("let me
      take a screenshot"), not its findings.
    - The first fix passed anything that was not a snapshot through whole, cut at 600
      characters. For a screenshot that was Playwright's code and an image path; for a
      `browser_find` it was ten levels of `generic [ref=...]:` before the line that held the
      total, which the cut then dropped. The guard counted that as having seen the page, and
      stayed at 0.01-0.04 through a live session that ended with the totals on screen.

    So every result - snapshot, `find`, click, screenshot - is reduced to the lines that say
    something, in page order. A large snapshot is first pruned by `browse.prune_snapshot` (the
    pruning the browse hook was measured with). If what is left is over `budget`, BM25 against
    the goal picks which lines stay. A result with nothing to say returns "", and the guard
    records that decision as blind.
    """
    from ..browse import prune_snapshot, snapshot_block
    from ..text import BM25Index

    if not result.strip():
        return ""
    body = _CODE.sub("", result)
    span = snapshot_block(body)
    if span is not None and span[1] - span[0] > budget * 4:
        pruned, _ = prune_snapshot(body[span[0] : span[1]], [], purpose=goal, text_budget=budget)
        body = body[: span[0]] + pruned + body[span[1] :]
    lines = list(
        dict.fromkeys(truncate(x, LINE_LIMIT) for x in map(page_line, body.splitlines()) if x)
    )
    if sum(len(x) + 1 for x in lines) <= budget:
        return "\n".join(lines)
    scores = BM25Index(lines).scores(goal) if goal else [0.0] * len(lines)
    keep, used = set(), 0
    for i in sorted(range(len(lines)), key=lambda k: (-scores[k], k)):
        if used + len(lines[i]) + 1 > budget:
            continue
        keep.add(i)
        used += len(lines[i]) + 1
    return "\n".join(lines[i] for i in sorted(keep))


def established(messages: Sequence[Mapping[str, Any]], result: str = "", goal: str = "") -> str:
    """What the agent has: what it said, and what the last page it looked at says."""
    said = narration(messages)
    facts = facts_seen(result, goal)
    if not facts:
        return said
    return f"{said}\n\nOn the page now:\n{facts}" if said else f"On the page now:\n{facts}"


def actions_taken(calls: Sequence[Any]) -> str:
    out = []
    for call in calls[-ACTIONS:]:
        name = str(call.tool).split("__")[-1]
        what = short_input(name, call.input)
        out.append(f"{name} {what}".strip() + (" [failed]" if call.is_error else ""))
    return "\n".join(out)


def result_text(event: Mapping[str, Any]) -> str:
    """The text of the result just returned, whatever shape the tool uses to hold it."""
    response = event.get("tool_response")
    if isinstance(response, str):
        return response
    if isinstance(response, Mapping):
        for key in ("stdout", "result", "content", "text"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value
            if isinstance(value, list):
                parts = [b.get("text", "") for b in value if isinstance(b, Mapping)]
                if any(parts):
                    return "\n".join(parts)
        return ""
    if isinstance(response, list):
        return "\n".join(b.get("text", "") for b in response if isinstance(b, Mapping))
    return ""


def pending_of(event: Mapping[str, Any]) -> str:
    tool = str(event.get("tool_name") or "").split("__")[-1]
    arguments = event.get("tool_input")
    what = short_input(tool, arguments if isinstance(arguments, Mapping) else {})
    return f"{tool} {what}".strip()


def advice_text(advice: Any) -> str:
    return f"sanchopanza, on the loop: {advice.message}."


def failed(text: str, is_error: bool = False) -> bool:
    """A tool result that reports a failure: Playwright MCP returns its errors as text that
    starts `### Error`, with the call itself not marked as an error."""
    return is_error or text.lstrip().startswith(("### Error", "Error:"))


def _reason(text: str) -> str:
    line = next((x for x in text.splitlines() if x.strip().startswith("Error")), text)
    return truncate(" ".join(line.split()), REASON_LIMIT)


def _is_browser(tool: str) -> bool:
    return str(tool).split("__")[-1].startswith("browser_")


def error_streak(
    calls: Sequence[Any], result: str, tool: str = "", use_id: str = ""
) -> tuple[int, list[str], bool]:
    """How many tool calls in a row have failed, ending with the one just returned; their
    reasons; and whether they were all browser calls.

    The transcript may or may not hold the call this event is about yet. It is recognised by
    the event's `tool_use_id`; only when the event carries none is it recognised by its text,
    which undercounts a retry that fails with the same message (the first version of this
    compared text alone, and a streak of two identical misses counted as one). A result that
    did not fail ends any streak: the note is about what is happening now."""
    if not failed(result):
        return 0, [], False
    earlier = [c for c in calls if not (use_id and getattr(c, "id", "") == use_id)]
    trail: list[Any] = []
    for call in reversed(earlier):
        if not failed(call.result, call.is_error):
            break
        trail.append(call)
    trail.reverse()
    if not use_id and trail and trail[-1].result.strip() == result.strip():
        trail = trail[:-1]  # no id to go by: the last failure is taken to be this one
    reasons = [_reason(c.result) for c in trail] + [_reason(result)]
    tools = [c.tool for c in trail] + [tool]
    return len(reasons), reasons, all(_is_browser(t) for t in tools)


def error_note(streak: int, reasons: Sequence[str], browser: bool) -> str:
    """Said once at a streak of 2 and once at 4, never on every failure.

    Why it exists, measured: in the longest session of 2026-10-02 (37 turns on B2, against 19-21
    for the same task elsewhere) the agent never took a snapshot. It worked from screenshots,
    guessed CSS selectors, and five of its calls failed with "does not match any elements" or a
    selector it could not parse. That waste is not a repeat and not a goal already met, so the
    two questions above cannot see it; a streak of failures can be counted for free.
    """
    if streak not in ERROR_NOTES_AT:
        return ""
    last = "; ".join(dict.fromkeys(reasons[-2:]))
    if browser:
        return (
            f"sanchopanza, on the loop: your last {streak} browser actions failed ({last}). "
            "`browser_snapshot` lists the page's elements with refs you can act on directly, "
            "which is more reliable than guessing selectors."
        )
    return f"sanchopanza, on the loop: your last {streak} tool calls failed ({last})."


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
    result = result_text(event)
    notes: list[str] = []
    streak, reasons, browser = error_streak(
        calls, result, str(event.get("tool_name") or ""), str(event.get("tool_use_id") or "")
    )
    note = error_note(streak, reasons, browser)
    if note:
        notes.append(note)
        squire.journal.record(
            "loop_note", {"kind": "errors", "streak": streak, "calls": len(calls)}
        )
    asked = len(calls) >= _int("LOOP_MIN_CALLS", 4) and not len(calls) % max(
        1, _int("LOOP_EVERY", 1)
    )
    goal = task_of(messages) if asked else ""
    facts = facts_seen(result, goal) if goal else ""
    done = established(messages, result, goal) if goal else ""
    root = _ledger_root()
    session = str(event.get("session_id") or "")
    ledger = read_ledger(root, session)
    ceiling = float(_env.get("SESSION_MAX_USD", "0.50") or 0.50)
    if goal and done and float(ledger.get("usd", 0.0)) >= ceiling:
        say(f"session ceiling reached ({ledger.get('usd'):.4f} of {ceiling:g} USD): silent")
    elif goal and done:
        state, questions = point.questions(
            goal=goal,
            done=f"{done}\n\nActions taken:\n{actions_taken(calls)}",
            pending=pending_of(event),
        )
        decision = await squire.decide("loop", state, questions)
        advice = point.decide(decision, squire.thresholds)
        # What the guard saw and said, so a phase can tell a silent guard from a blind one.
        squire.record(decision, calls=len(calls), page_chars=len(facts), spoke=advice.speaks)
        write_ledger(root, session, _charged(ledger, squire))
        if advice.speaks:
            notes.append(advice_text(advice))
    if not notes:
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n".join(notes),
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
    squire = None
    try:
        from .claude_code import squire_from_env

        squire = squire_from_env(redact=True)
        output = asyncio.run(post_tool_use(event, squire))
    except Exception as error:  # fail open at the process boundary, never silently
        say(f"said nothing ({error.__class__.__name__}: {error})")
        _journal_failure(squire, error)
        return 0
    if output:
        hookio.stdout_json(output)
    return 0


def _journal_failure(squire: Any, error: Exception) -> None:
    """Leave a trace of a failure where the session's decisions go, not only on stderr.

    A hook that fails on every call and writes nothing to the journal looks, from outside,
    exactly like a hook that never ran: that is what one HAIKU-LOOP session of 2026-10-02 looked
    like, twenty tool calls and no journal, with its stderr thrown away. With this, "the
    decider was down" and "the hook was absent" are two different records."""
    if squire is None:
        return
    try:
        squire.journal.record(
            "loop_error", {"error": f"{error.__class__.__name__}: {truncate(str(error), 200)}"}
        )
    except Exception as journal_error:  # noqa: BLE001 - nothing left to fail open to
        say(f"and could not write that down ({journal_error.__class__.__name__})")


if __name__ == "__main__":
    raise SystemExit(main())
