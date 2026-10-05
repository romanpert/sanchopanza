"""Sources, version 2: block a web-research session's first stop only on a sign of a weak answer.

Version 1 (`sources_hook`) asked every session that used the web for a source per condition. On
the FRAMES pilot (`docs/results/2026-10-05-browse-frames`) that cost Sonnet 52 % more for the same
answers (11 of its 15 blocks went to sessions already right), made Haiku withdraw one right answer
and pushed four Haiku sessions into their cap; it missed a session whose research a subagent did.
Version 2, switched on by `SANCHOPANZA_SOURCES_VERSION=2`, changes four things:

- Web calls are counted in the session's subagents too (`<session>/subagents/*.jsonl`, beside the
  main transcript), and what the subagents read counts as read.
- With `SANCHOPANZA_SOURCES_CAP_USD` set, the hook stands aside once the session's estimated list
  spend passes `CAP_SHARE` of it: the extra turn must not run the session into its cap. The
  estimate prices every API call in the transcripts once (by message id) at list rates and adds
  `WEB_CALL_USD` per WebSearch or WebFetch for the reader those tools run, which the transcripts do
  not show (fitted on the pilot's 80 sessions: 0.020-0.025 USD per call). Without the variable
  the spend is not checked.
- It blocks only on a deterministic sign of weakness in the final reply: a number in the answer
  that no tool result and not the question shows (computed or counted), words of doubt, or no
  ANSWER line when the question asked for one.
- The request keeps the answer (never withdraw it) and asks about the step no page states - each
  value calculated, counted or chosen between conflicting sources - checked by opening its page.

No model; fail open (the caller catches everything).
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .. import _env
from ..context.transcript import blocks_of, is_prompt, message_text, text_of

WEB_TOOL = re.compile(r"^(?:WebSearch|WebFetch|mcp__.+__(?:browser_.+|fetch\w*))$")
READER_TOOLS = frozenset({"WebSearch", "WebFetch"})
DELEGATE_TOOLS = frozenset({"Agent", "Task"})  # a subagent's report is not a page it read
WEB_CALL_USD = 0.022
CAP_SHARE = 0.6
# USD per million tokens: input, 5-minute cache write, 1-hour cache write, cache read, output.
PRICES = {
    "haiku": (1.0, 1.25, 2.0, 0.1, 5.0),
    "sonnet": (2.0, 2.5, 4.0, 0.2, 10.0),
    "opus": (5.0, 6.25, 10.0, 0.5, 25.0),
}
DOUBT = re.compile(
    r"\b(?:approximately|roughly|likely|probably|possibly|perhaps|presumably|unclear|uncertain|"
    r"not certain|not sure|could not|couldn't|cannot|can't|unable|assum(?:e|ed|ing|ption)|"
    r"estimat(?:e|ed|ion)|conflict(?:s|ing)?|discrepanc(?:y|ies)|ambiguous|unverified|"
    r"best guess|appears to|seems to)\b",
    re.I,
)
_NUMBER = re.compile(r"(?<![\w.,])(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:st|nd|rd|th)?(?!\w)")
_ANSWER = re.compile(r"answer\s*:\s*(.*)", re.I)

REQUEST_V2 = (
    "sanchopanza: before you stop, check the step no page states. Keep your best answer: never "
    "withdraw it. Name each step that no page you read states outright - every value you "
    "calculated, counted, or chose between conflicting sources - and check it now by opening the "
    "page it comes from. Then end with your ANSWER line."
)
REASONS = {
    "number": "your answer has a number that no page you read shows",
    "doubt": "your reply has words of doubt",
    "no_answer": "your reply has no ANSWER line",
}


# --- reading the session ------------------------------------------------------------------------


def _entries(path: Path) -> list[Mapping[str, Any]]:
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line) if line.strip() else None
        except json.JSONDecodeError:
            continue
        if isinstance(entry, Mapping):
            out.append(entry)
    return out


def subagent_transcripts(main: Path) -> list[Path]:
    """The transcripts of the session's subagents: `<session>/subagents/*.jsonl`."""
    folder = main.with_suffix("") / "subagents"
    return sorted(folder.glob("*.jsonl")) if folder.is_dir() else []


def _message(entry: Mapping[str, Any]) -> Mapping[str, Any]:
    message = entry.get("message")
    return message if isinstance(message, Mapping) else {}


def _tool_uses(entries: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """tool_use id -> tool name, each call once."""
    out: dict[str, str] = {}
    for entry in entries:
        for block in blocks_of(_message(entry)) if entry.get("type") == "assistant" else []:
            if isinstance(block, Mapping) and block.get("type") == "tool_use":
                out[str(block.get("id"))] = str(block.get("name") or "")
    return out


def _results(entries: list[Mapping[str, Any]]) -> list[str]:
    """The text of every tool result, except a subagent's report to the main agent."""
    names = _tool_uses(entries)
    out = []
    for entry in entries:
        for block in blocks_of(_message(entry)) if entry.get("type") == "user" else []:
            if not isinstance(block, Mapping) or block.get("type") != "tool_result":
                continue
            if names.get(str(block.get("tool_use_id"))) not in DELEGATE_TOOLS:
                out.append(text_of(block.get("content")))
    return out


def _question(entries: Iterable[Mapping[str, Any]]) -> str:
    for entry in entries:
        message = _message(entry)
        if entry.get("type") == "user" and not entry.get("isMeta") and is_prompt(message):
            return message_text(message)
    return ""


def _last_text(entries: Iterable[Mapping[str, Any]]) -> str:
    last = ""
    for entry in entries:
        if entry.get("type") == "assistant" and not entry.get("isSidechain"):
            text = message_text(_message(entry))
            last = text or last
    return last


# --- the estimate of spend ----------------------------------------------------------------------


def _family(model: str) -> str:
    return next((name for name in PRICES if name in (model or "")), "sonnet")


def call_usd(model: str, usage: Mapping[str, Any]) -> float:
    p_in, p_w5, p_w1, p_read, p_out = PRICES[_family(model)]
    split = usage.get("cache_creation") or {}
    written = int(usage.get("cache_creation_input_tokens") or 0)
    w1h = int(split.get("ephemeral_1h_input_tokens") or 0) if isinstance(split, Mapping) else 0
    tokens = (
        int(usage.get("input_tokens") or 0) * p_in
        + (written - w1h) * p_w5
        + w1h * p_w1
        + int(usage.get("cache_read_input_tokens") or 0) * p_read
        + int(usage.get("output_tokens") or 0) * p_out
    )
    return tokens / 1_000_000


def _spent(groups: Iterable[list[Mapping[str, Any]]]) -> float:
    total = 0.0
    for entries in groups:
        by_id: dict[str, tuple[str, Mapping[str, Any]]] = {}
        for entry in entries:
            message = _message(entry)
            if entry.get("type") != "assistant" or not message.get("id"):
                continue
            usage = message.get("usage") if isinstance(message.get("usage"), Mapping) else {}
            seen = by_id.get(str(message["id"]))
            if seen is None or int(usage.get("output_tokens") or 0) >= int(
                seen[1].get("output_tokens") or 0
            ):
                by_id[str(message["id"])] = (str(message.get("model") or ""), usage)
        total += sum(call_usd(model, usage) for model, usage in by_id.values())
        readers = sum(name in READER_TOOLS for name in _tool_uses(entries).values())
        total += readers * WEB_CALL_USD
    return total


def spent_usd(main: Path) -> float:
    """The session's list spend so far, main agent and subagents, as estimated above."""
    groups = [_entries(main), *(_entries(p) for p in subagent_transcripts(main))]
    return _spent(groups)


# --- the signs ----------------------------------------------------------------------------------


def numbers(text: str) -> set[float]:
    """Every number in a text as a value: separators and ordinal suffixes dropped."""
    return {float(m.group(1).replace(",", "") + (m.group(2) or "")) for m in _NUMBER.finditer(text)}


def answer_line(text: str) -> str:
    found = [m.group(1) for m in _ANSWER.finditer(text or "")]
    return found[-1].strip() if found else ""


def signs(question: str, final: str, results: Iterable[str]) -> list[str]:
    """The names of the weakness signs in a final reply, in `REASONS` order."""
    out = []
    answer = answer_line(final)
    if answer:
        seen = numbers(question).union(*(numbers(r) for r in results))
        if numbers(answer) - seen:
            out.append("number")
    if DOUBT.search(final or ""):
        out.append("doubt")
    if "answer:" in question.lower() and not answer:
        out.append("no_answer")
    return out


def cap_usd(env: Mapping[str, str] | None) -> float | None:
    try:
        value = float(_env.get("SOURCES_CAP_USD", "", env).strip())
    except ValueError:
        return None
    return value if value > 0 else None


def assess(main: Path, last_message: str, env: Mapping[str, str] | None) -> dict[str, Any]:
    """What the hook knows at this stop: web calls, spend, the cap check and the signs."""
    entries = _entries(main)
    subs = [_entries(p) for p in subagent_transcripts(main)]
    every = [entries, *subs]
    web = sum(1 for group in every for name in _tool_uses(group).values() if WEB_TOOL.match(name))
    spent = _spent(every)
    cap = cap_usd(env)
    results = [text for group in every for text in _results(group)]
    final = last_message or _last_text(entries)
    found = signs(_question(entries), final, results) if web else []
    over = cap is not None and spent > CAP_SHARE * cap
    return {"web_calls": web, "spent_usd": round(spent, 4), "cap_usd": cap, "over_cap": over,
            "signs": found, "block": bool(web and found and not over)}  # fmt: skip


def reason(found: Iterable[str]) -> str:
    return f"{REQUEST_V2} (Why: {'; '.join(REASONS[name] for name in found)}.)"
