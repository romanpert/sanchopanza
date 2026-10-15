"""The truncations as parameters: the same defaults as the measured runs, raised on demand.

With Jev's long-context header a state may be 262k tokens, but what a point shows was cut by
this package (900 characters a page, 2,000 an injection window, 24,000 of a record, ...). These
tests pin the defaults and check that each cut can be moved, alone or through `Squire(limits=)`.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import Squire
from sanchopanza.contract import Answer, Decision
from sanchopanza.limits import Limits
from sanchopanza.points import chunks, completion, injection, memory, triage
from sanchopanza.points import context as context_point

LONG = "word " * 4000  # 20,000 characters


def test_the_defaults_are_the_measured_cuts() -> None:
    limits = Limits()
    assert limits.page_chars == chunks.PAGE_LIMIT == 900
    assert limits.pages_per_call == chunks.PAGE_MAX == 30
    assert limits.triage_chars == triage.TEXT_LIMIT == 1500
    assert limits.completion_record_chars == completion.RECORD_LIMIT == 24_000
    assert limits.history_chars == context_point.HISTORY_LIMIT == 60_000
    assert limits.result_chars == context_point.RESULT_LIMIT == 700
    assert limits.memory_record_chars == memory.RECORD_LIMIT == 900
    assert limits.injection_window_chars == injection.TEXT_LIMIT == 2000


@pytest.mark.parametrize("field", ["page_chars", "pages_per_call", "injection_window_chars"])
def test_a_limit_must_be_a_positive_integer(field: str) -> None:
    with pytest.raises(ValueError):
        Limits(**{field: 0})


def test_an_injection_window_must_be_wider_than_its_overlap() -> None:
    with pytest.raises(ValueError, match="overlap|share"):
        Limits(injection_window_chars=injection.WINDOW_OVERLAP)


# --- the pure question builders --------------------------------------------------------------


def test_pages_are_cut_at_the_default_or_at_the_limit_given() -> None:
    pages = [("t", LONG)] * 40
    state, qs = chunks.context_questions(purpose="p", pages=pages)
    assert len(qs) == 30 and len(state["pages"]) < 40 * 1000
    assert (state, qs) == chunks.context_questions(purpose="p", pages=pages, page_limit=900)
    wide, many = chunks.context_questions(purpose="p", pages=pages, page_limit=20_000, page_max=40)
    assert len(many) == 40 and LONG.strip() in wide["pages"]


def test_triage_text_can_be_longer() -> None:
    short, _ = triage.questions(purpose="p", text=LONG)
    assert len(short["text"]) <= 1500 + 10
    for build in (triage.questions, triage.contribution_questions):
        state, _ = build(purpose="p", text=LONG, text_limit=30_000)
        assert state["text"] == LONG
    state, _ = triage.redundancy_questions(purpose="p", text=LONG, known="k", text_limit=30_000)
    assert state["text"] == LONG


def test_completion_record_can_be_longer() -> None:
    record = "x" * 50_000
    assert len(completion.questions(task="t", record=record)[0]["record"]) <= 24_010
    state, _ = completion.questions(task="t", record=record, record_limit=60_000)
    assert state["record"] == record


def test_memory_records_can_be_longer() -> None:
    state, _ = memory.related_questions(request="r", records=[LONG])
    assert len(state["records"]) < 1000
    state, _ = memory.related_questions(request="r", records=[LONG], record_limit=30_000)
    assert LONG in state["records"]


def test_injection_text_can_be_longer() -> None:
    assert len(injection.questions(purpose="p", text=LONG)[0]["text"]) <= 2010
    assert injection.questions(purpose="p", text=LONG, limit=30_000)[0]["text"] == LONG


def test_context_history_and_results_can_be_longer() -> None:
    from sanchopanza.context.transcript import calls

    result = "line\n" * 2000  # 10,000 characters
    messages = [
        {"role": "user", "content": "fix the bug"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "u1", "name": "Bash",
                                           "input": {"command": "pytest"}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "u1",
                                      "content": result}]},
    ]  # fmt: skip
    found = calls(messages)
    short, _ = context_point.prune_questions("t", messages, found, candidates=["u1"])
    assert "omitted" in short["history"]
    assert (short, _) == context_point.prune_questions(
        "t", messages, found, candidates=["u1"], history_limit=60_000, result_limit=700
    )
    wide, _ = context_point.prune_questions(
        "t", messages, found, candidates=["u1"], result_limit=20_000
    )
    assert "omitted" not in wide["history"] and result.strip() in wide["history"]
    tight, _ = context_point.prune_questions(
        "t", messages, found, candidates=["u1"], history_limit=500
    )
    assert len(tight["history"]) <= 600


def test_the_transcript_record_can_keep_longer_results(tmp_path: Path) -> None:
    from sanchopanza.harness.claude_code import transcript_task_and_record

    rows = [
        {"type": "user", "message": {"role": "user", "content": "do it"}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "a", "content": "y" * 5000}]}},
    ]  # fmt: skip
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    _, record = transcript_task_and_record(path)
    assert "y" * 1500 in record and "y" * 1501 not in record
    _, wide = transcript_task_and_record(path, result_limit=10_000, record_limit=100_000)
    assert "y" * 5000 in wide
    _, tight = transcript_task_and_record(path, record_limit=100)
    assert len(tight) == 100


def test_memory_gate_pages_can_be_longer() -> None:
    from sanchopanza.harness.memory_gate import Memory, pages_of

    memo = Memory(file="f.md", name="n", description="", body=LONG)
    ((_, short),) = pages_of([memo], "word")
    assert len(short) <= 1000
    ((_, wide),) = pages_of([memo], "word", limit=30_000)
    assert wide == LONG.strip()


# --- through the squire ----------------------------------------------------------------------


class Seen:
    name = "seen"

    def __init__(self) -> None:
        self.states: list[Any] = []

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        self.states.append(state)
        answers = {k: Answer("truth", 0.8, truth=0.1) for k in questions}
        return Decision(point, answers, self.name, "m")


def test_the_squire_uses_its_limits_and_a_fork_keeps_them() -> None:
    seen = Seen()
    squire = Squire(seen, limits=Limits(page_chars=20_000, triage_chars=30_000))
    asyncio.run(squire.triage_pages(purpose="p", pages=[("t", LONG)]))
    assert LONG.strip() in seen.states[-1]["pages"]
    asyncio.run(squire.fork().triage_part(purpose="p", text=LONG))
    assert seen.states[-1]["text"] == LONG
    assert squire.fork().limits == squire.limits


def test_the_default_squire_cuts_as_before() -> None:
    seen = Seen()
    asyncio.run(Squire(seen).triage_pages(purpose="p", pages=[("t", LONG)]))
    assert LONG.strip() not in seen.states[-1]["pages"]


def test_a_wider_injection_window_means_fewer_calls() -> None:
    text = "plain prose without any instruction. " * 300  # about 11,000 characters
    narrow, wide = Seen(), Seen()
    asyncio.run(Squire(narrow).scan_content(purpose="p", text=text))
    flag = asyncio.run(
        Squire(wide, limits=Limits(injection_window_chars=20_000)).scan_content(
            purpose="p", text=text
        )
    )
    assert len(narrow.states) == len(injection.windows(text)) == 7 and len(wide.states) == 1
    assert flag.complete and not flag.flagged


def test_check_done_sees_the_longer_record() -> None:
    seen = Seen()
    record = "z" * 40_000
    squire = Squire(seen, limits=Limits(completion_record_chars=50_000))
    asyncio.run(squire.check_done(task="t", record=record))
    assert seen.states[-1]["record"] == record
