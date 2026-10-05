"""What one find-auto probe session did with the hook: whether and where it fired, the places it
showed, whether one was a gold file or held a changed gold line, whether the agent Read a shown
place next, and the need probe's measures on top (`need_facts.describe`). Pure parsing of the
evidence folder; no Docker, no API.

The fire's tool call is found by the `tool_use_id` the hook journals; the call the live rule
should have fired after is the replay of `harness.find_auto.step` over the stream's main-thread
calls, so a hook that never ran shows as `expected_fire_call` without a journal row.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmarks.find_auto.evaluate import gold_lines, hits
from benchmarks.find_need.replay import jsonl, stream_calls

from sanchopanza.harness.find_auto import HEADER, NTH, State, relative, step

from .need_facts import describe as need_describe

SHOWN = ("fired", "free")


def tool_use_ids(stream: Path) -> list[str]:
    """The main-thread tool use ids in `replay.stream_calls`' order (deduplicated by id)."""
    seen: set[str] = set()
    out: list[str] = []
    for e in jsonl(stream):
        if e.get("type") != "assistant" or e.get("parent_tool_use_id"):
            continue
        content = (e.get("message") or {}).get("content")
        for b in content if isinstance(content, list) else []:
            if isinstance(b, Mapping) and b.get("type") == "tool_use" and b.get("id") not in seen:
                seen.add(str(b.get("id")))
                out.append(str(b.get("id")))
    return out


def expected_fire(calls: list[Any], work: str) -> int | None:
    """The 1-based call after which the live rule reaches its NTH search with the window open."""
    state = State()
    for i, call in enumerate(calls):
        state, due = step(state, call.name, call.input, failed=call.error, root=work)
        if state.closed:
            return None
        if due and state.searches == NTH:
            return i + 1
    return None


def journal_rows(evidence: Path) -> list[dict[str, Any]]:
    return [dict(e.get("data") or {}) for e in jsonl(evidence / "journal.jsonl")
            if e.get("kind") == "find_auto"]  # fmt: skip


def _path_of(call: Any, work: str) -> str:
    raw = str(call.input.get("file_path") or call.input.get("notebook_path") or "")
    return relative(raw, work) if raw else ""


SHELL = frozenset({"Bash", "PowerShell"})


def names_shown(call: Any, paths: set[str]) -> bool:
    """A shell call whose command names a shown file (`sed -n 1,80p django/x.py`, `cat ...`)."""
    if call.name not in SHELL:
        return False
    command = str(call.input.get("command") or "").replace("\\", "/").lower()
    return any(path in command for path in paths)


def after_fire(calls: list[Any], fire: int, shown: list[str], work: str) -> dict[str, Any]:
    """What the agent did after the call the hook fired on (`fire`, 1-based): a Read of a shown
    file, and apart from it a shell command naming one (Haiku often reads with sed/cat)."""
    paths = {key.rsplit(":", 1)[0].lower() for key in shown}
    rest = list(enumerate(calls[fire:], fire + 1))
    reads = [(n, _path_of(c, work)) for n, c in rest if c.name == "Read"]
    shown_reads = [n for n, path in reads if path in paths]
    shells = [n for n, c in rest if names_shown(c, paths)]
    following = calls[fire] if fire < len(calls) else None
    follows = following is not None and (
        (following.name == "Read" and _path_of(following, work) in paths)
        or names_shown(following, paths))  # fmt: skip
    return {
        "next_call": None if following is None else {"name": following.name,
                                                     "path": _path_of(following, work)},
        "next_call_follows": follows,
        "next_read_is_shown": bool(reads) and reads[0][1] in paths,
        "first_shown_read_call": shown_reads[0] if shown_reads else None,
        "calls_to_shown_read": (shown_reads[0] - fire) if shown_reads else None,
        "first_shown_shell_call": shells[0] if shells else None,
        "calls_to_shown_shell": (shells[0] - fire) if shells else None,
    }  # fmt: skip


def describe(evidence: Path, gold: list[str], patch: str, record: Mapping[str, Any],
             work: str) -> dict[str, Any]:  # fmt: skip
    facts = need_describe(evidence, gold, record)
    stream = evidence / "stream-1.jsonl"
    _meta, calls = stream_calls(stream)
    ids = tool_use_ids(stream)
    rows = journal_rows(evidence)
    shown_row = next((r for r in rows if r.get("outcome") in SHOWN), None)
    fire = (ids.index(shown_row["tool_use_id"]) + 1
            if shown_row and shown_row.get("tool_use_id") in ids else None)  # fmt: skip
    shown = list((shown_row or {}).get("keys") or [])
    hit = hits(shown, gold_lines(patch)) if shown else {}
    transcript = evidence / "transcript.jsonl"
    injected = transcript.exists() and HEADER in transcript.read_text("utf-8", "replace")
    return {
        **facts,
        "auto": {
            "journal": [{k: r.get(k) for k in ("outcome", "search", "tool", "tool_use_id", "keys",
                                               "jev_usd", "seconds", "waited_s",
                                               "index_build_s")} for r in rows],
            "expected_fire_call": expected_fire(calls, work),
            "fired": shown_row is not None,
            "fire_call": fire,
            "fire_search": (shown_row or {}).get("search"),
            "outcome": rows[-1].get("outcome") if rows else None,
            "shown": shown,
            "shown_gold_file": bool(hit.get("any@5")),
            "shown_gold_hunk": bool(hit.get("hunk@5")),
            "shown_gold_first": bool(hit.get("any@1")),
            "injected_in_transcript": injected,
            "jev_usd": round(sum(float(r.get("jev_usd") or 0.0) for r in rows), 6),
            **(after_fire(calls, fire, shown, work) if fire else {}),
        },
    }  # fmt: skip


def need_reference(folder: Path) -> dict[str, Any] | None:
    """The need probe's recorded S row of one instance (dev-need/<id>/S), read only."""
    row_path = folder / "row.json"
    if not row_path.exists():
        return None
    row = json.loads(row_path.read_text(encoding="utf-8"))
    call = row["calls"][0]
    facts_path, grade = folder / "need-facts.json", folder / "grade.json"
    facts = json.loads(facts_path.read_text(encoding="utf-8")) if facts_path.exists() else {}
    return {"resolved": json.loads(grade.read_text(encoding="utf-8"))["resolved"]
            if grade.exists() else None,
            "turns": call.get("turns"),
            "cost_usd": round(call.get("cost_usd", 0.0) + row.get("jev_usd", 0.0), 4),
            "searches_before_gold_read": facts.get("searches_before_gold_read"),
            "tool_calls": facts.get("tool_calls")}  # fmt: skip
