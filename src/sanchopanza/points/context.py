"""Context pruning at compaction: which old tool results the rest of the work still needs.

Two question sets, one for us and one for the arm we compare against.

`prune_questions` is ours. One call per set of candidate results (up to `CALL_MAX`, a
tournament past it), one Truth per result, each read with the whole condensed conversation in
view: the shape of `chunks.context_questions`, which kept 98.3 % of needed pages at 34 % of
the text where asking page by page kept 94.3 % (docs/results/2026-09-27-chunks/). The question
is about **contribution** (will a fact that only this result holds be used?), with criteria in
the style of `triage.CONTRIBUTES` rewritten for tool output, because asking whether a text
"matters" kept both needed paragraphs in 19.7 % of multi-part questions where contribution
kept 93.3 % (docs/results/2026-09-25-triage/). None of that was measured on coding
transcripts: the question is carried over from pages, not confirmed here.

`fastjev_questions` replicates fast-jev-compaction (MIT License,
github.com/tamaratran/fast-jev-compaction, `src/compact.ts` and `src/state.ts` as of
2026-09-28): the same state (the whole conversation, each tool output replaced by a one-line
note), the same two questions per call, verbatim, and the same table at a 0.5 cut, with the
first message and the last six pinned. Its state-fitting stages are simplified (inputs capped
at 1,000 then 200 characters, then long texts abridged); on the sizes this is compared at,
their later stages do not trigger. It is here to be measured against, not used.

Every state is passed through `redact.redact_secrets` before it is returned: a tool result is
where an API key printed by `env` or read from a `.env` file ends up, and the decider is a
third party.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ..context.transcript import Call, blocks_of, is_prompt, message_text
from ..contract import Decision, Question, Truth
from ..redact import redact_secrets
from ..text import truncate

CALL_MAX = 30
RESULT_LIMIT = 700  # characters of a candidate result shown, head and tail
OTHER_RESULT_LIMIT = 300  # a result that is not a candidate in this call
INPUT_LIMIT = 300
TEXT_LIMIT = 1_500
TASK_LIMIT = 1_500
HISTORY_LIMIT = 60_000  # about 15k tokens, half of Jev's state window
# Round one of the tournament, past `CALL_MAX` candidates. Not derived: lenient on purpose,
# because keeping is the cheap direction and the survivors are judged again together.
FIRST_ROUND_CUT = 0.25

CONTEXT = (
    "A coding assistant's conversation is being compacted. `history` is the conversation so "
    "far, oldest first, with long texts and tool outputs shortened. Tool calls marked with an "
    "id (C01, C02, ...) are the candidates: the full output of each one will be removed from "
    "the conversation unless the assistant still needs it."
)


def call_id(index: int) -> str:
    return f"C{index + 1:02d}"


def head_tail(text: str, limit: int) -> str:
    """The start and the end of a long text: an output's command and its verdict, typically."""
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    tail = limit - head
    return f"{text[:head]}\n[... {len(text) - limit} chars omitted ...]\n{text[-tail:]}"


def _needed(cid: str) -> Truth:
    return Truth(
        f"To continue the work from where `history` stops, will the assistant still need at "
        f"least one fact that appears only in the output of tool call {cid} (not elsewhere in "
        "`history`), and that running the tool again would not cheaply give back?",
        criteria={
            "true": {
                "what": "A value, path, identifier, error message or finding shown in that "
                "output which the next steps of `task` would use, and which the assistant has "
                "not restated in its own text or in a later output",
                "examples": [
                    "a test run whose failures the assistant is still fixing",
                    "a search listing the files the assistant said it will edit next",
                    "a fetched page whose figures the answer being written relies on",
                ],
            },
            "false": {
                "what": "Its facts were already used or restated, a later call superseded "
                "it, it belongs to a finished step, or reading the same file again gives it "
                "back exactly",
                "examples": [
                    "a directory listing the assistant already acted on",
                    "a file whose relevant lines the assistant quoted in its reply",
                    "the output of a build that a later run replaced",
                ],
            },
        },
    )


def _input(arguments: Mapping[str, Any], limit: int) -> str:
    return truncate(json.dumps(arguments, ensure_ascii=False, default=str), limit)


def _result_line(call: Call, label: str | None, hidden: Mapping[str, str]) -> str:
    status = "error" if call.is_error else "ok"
    if call.id in hidden:
        return f"  RESULT ({status}, {call.chars} chars): [removed: {hidden[call.id]}]"
    if label is not None:
        shown = head_tail(call.result, RESULT_LIMIT)
        return f"  RESULT {label} ({status}, {call.chars} chars): {shown}"
    return f"  RESULT ({status}, {call.chars} chars): {head_tail(call.result, OTHER_RESULT_LIMIT)}"


def _render(
    messages: Sequence[Mapping[str, Any]],
    calls: Sequence[Call],
    labels: Mapping[str, str],
    hidden: Mapping[str, str],
) -> list[str]:
    by_use = {c.id: c for c in calls}
    lines: list[str] = []
    for message in messages:
        role = str(message.get("role", "")).upper()
        text = message_text(message)
        if text:
            lines.append(f"{role}: {truncate(text, TEXT_LIMIT)}")
        for block in blocks_of(message):
            if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                continue
            call = by_use.get(str(block.get("id")))
            if call is None:
                continue
            label = labels.get(call.id)
            tag = f"CALL {label}" if label else "CALL"
            lines.append(f"{tag} {call.tool} {_input(call.input, INPUT_LIMIT)}")
            lines.append(_result_line(call, label, hidden))
    return lines


def _fit(lines: list[str], labels: Mapping[str, str]) -> str:
    """Under `HISTORY_LIMIT`: shorten unlabelled lines oldest first, then cut the middle."""
    body = "\n".join(lines)
    if len(body) <= HISTORY_LIMIT:
        return body
    marks = tuple(f" {label} " for label in labels.values())
    short = [line if any(m in line for m in marks) else truncate(line, 160) for line in lines[:-12]]
    body = "\n".join([*short, *lines[-12:]])
    return head_tail(body, HISTORY_LIMIT)


def prune_questions(
    task: str,
    history: Sequence[Mapping[str, Any]],
    calls: Sequence[Call],
    *,
    candidates: Sequence[str] = (),
    hidden: Mapping[str, str] | None = None,
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """State and one Truth per candidate, keyed `C01`, `C02`, ... in the order given.

    `history` is the message list and `calls` its tool calls (`transcript.calls`). The
    candidates are call ids; at most `CALL_MAX` are asked, the rest are the caller's to
    split. `hidden` maps ids the rules already stubbed to their reason: their output is not
    shown, so the decider does not count it as still in the history.
    """
    chosen = list(candidates)[:CALL_MAX]
    labels = {cid: call_id(i) for i, cid in enumerate(chosen)}
    lines = _render(history, calls, labels, hidden or {})
    state = {
        "context": CONTEXT,
        "task": truncate(task, TASK_LIMIT),
        "history": _fit(lines, labels),
    }
    questions: dict[str, Question] = {call_id(i): _needed(call_id(i)) for i in range(len(chosen))}
    return redact_secrets(state), questions


# --- the fast-jev-compaction replica ------------------------------------------------------

FASTJEV_CONTEXT = (
    "A coding assistant conversation is being compacted to free context. `history` is the "
    "whole conversation so far, oldest first; tool outputs are replaced by a short `result` "
    "note and long texts may be abridged. Each question asks whether one tool call, or the "
    "full output of that call, still needs to stay in the history verbatim. Whatever is not "
    "kept is deleted permanently, but the assistant can always re-run a tool or re-read a file."
)
FASTJEV_CUT = 0.5
FASTJEV_RECENT = 6
FASTJEV_HEAD = 300
FASTJEV_STATE_CHARS = 75_000  # their 25k-token state budget, at about 3 chars per token


def fastjev_id(index: int) -> str:
    return f"t{index + 1}"


def fastjev_pinned(call: Call, total: int, recent: int = FASTJEV_RECENT) -> bool:
    """The first message and the last `recent` are never touched."""

    def pinned(index: int) -> bool:
        return index == 0 or index >= total - recent

    return pinned(call.use_msg) or pinned(call.result_msg)


def _fastjev_goal(messages: Sequence[Mapping[str, Any]]) -> str:
    prompts = [truncate(message_text(m), 500) for m in messages if is_prompt(m)]
    return "\n".join(prompts[-3:])


def _fastjev_history(
    messages: Sequence[Mapping[str, Any]], calls: Sequence[Call], input_chars: int, text_cap: int
) -> list[dict[str, Any]]:
    by_msg: dict[int, list[tuple[int, Call]]] = {}
    for index, call in enumerate(calls):
        by_msg.setdefault(call.use_msg, []).append((index, call))
    history = []
    for i, message in enumerate(messages):
        text = message_text(message)
        if text_cap and len(text) > text_cap:
            text = head_tail(text, text_cap)
        tool_calls = [
            {
                "id": fastjev_id(index),
                "tool": call.tool,
                "input": truncate(json.dumps(call.input, default=str), input_chars),
                "result": f"{'error' if call.is_error else 'ok'}, {call.chars} chars (omitted)",
            }
            for index, call in by_msg.get(i, [])
        ]
        if not text and not tool_calls:
            continue
        entry: dict[str, Any] = {"i": i, "role": message.get("role"), "text": text}
        if tool_calls:
            entry["tool_calls"] = tool_calls
        history.append(entry)
    return history


def fastjev_state(
    messages: Sequence[Mapping[str, Any]], calls: Sequence[Call]
) -> Mapping[str, Any]:
    """Their state: context, goal (the last three prompts) and the history, fitted."""
    for input_chars, text_cap in ((1_000, 0), (200, 0), (200, 550)):
        history = _fastjev_history(messages, calls, input_chars, text_cap)
        state = {"context": FASTJEV_CONTEXT, "goal": _fastjev_goal(messages), "history": history}
        if len(json.dumps(state, ensure_ascii=False)) <= FASTJEV_STATE_CHARS:
            break
    return redact_secrets(state)


def fastjev_questions(
    messages: Sequence[Mapping[str, Any]], calls: Sequence[Call], ids: Sequence[int]
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """Their two questions for each call index in `ids`, over their state of every call."""
    qs: dict[str, Question] = {}
    for index in ids:
        call, tid = calls[index], fastjev_id(index)
        qs[f"call_{tid}"] = Truth(
            f"Tool call {tid} ({call.tool}) should stay in the history: knowing this call was "
            "made, with its input, still matters for what the assistant does next"
        )
        qs[f"result_{tid}"] = Truth(
            f"The full output of tool call {tid} ({call.tool}, {call.chars} chars) should stay "
            "in the history verbatim: the assistant still needs its contents and re-running "
            "the tool would not do"
        )
    return fastjev_state(messages, calls), qs


FastjevAction = Literal["keep", "truncate", "drop"]


@dataclass(frozen=True, slots=True)
class FastjevVerdict:
    action: FastjevAction
    reason: str
    keep_call: float
    keep_result: float


def fastjev_decide(decision: Decision, index: int, cut: float = FASTJEV_CUT) -> FastjevVerdict:
    """Their table. An unanswered question counts as 1, as theirs does: in doubt, keep."""
    tid = fastjev_id(index)
    p_call = decision.answer(f"call_{tid}").truth
    p_result = decision.answer(f"result_{tid}").truth
    keep_call = 1.0 if p_call is None else p_call
    keep_result = 1.0 if p_result is None else p_result
    if keep_result >= cut:
        return FastjevVerdict("keep", "kept", keep_call, keep_result)
    if keep_call >= cut:
        return FastjevVerdict("truncate", "result_dropped", keep_call, keep_result)
    return FastjevVerdict("drop", "call_dropped", keep_call, keep_result)


def fastjev_truncated(text: str, is_error: bool, head: int = FASTJEV_HEAD) -> str:
    """Their note for a dropped result: the first `head` characters and one line."""
    if len(text) <= head + 120:
        return text
    prefix = f"{text[:head]}\n" if head > 0 else ""
    return (
        f"{prefix}[fast-jev-compaction truncated {len(text) - head} chars of this tool result"
        f"{' (error)' if is_error else ''}; re-run the tool if needed]"
    )
