# ruff: noqa: E501, F811
"""The guard's cascade as a package (`context.keep`, questions in `points.keep`).

Plumbing proposes every line; nothing is asked when it all fits; the decider scores blocks and
then lines with the whole request in view; its lines at MUST come before the rule's; on a
failure the rule stands.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from sanchopanza.context import guard, keep
from sanchopanza.context.transcript import Call
from sanchopanza.contract import Answer, Decision, Score
from sanchopanza.points import keep as q

from .test_context_guard import _result, _run, _use, env, write_session  # noqa: F401

LONG_REQUEST = ("Finish the release. " * 40) + "Use the limit the diagnostic run complained about."


class ScoreSquire:
    """Scores 3 for any block or line holding one of `wanted`, 0 otherwise; records states."""

    provider = "fake"

    def __init__(self, wanted: tuple[str, ...], *, fail: bool = False) -> None:
        self.wanted = wanted
        self.fail = fail
        self.states: list[Any] = []

    async def decide(self, point: str, state: Any, qs: dict[str, Any]) -> Decision:
        self.states.append(state)
        if self.fail:
            return Decision(point, {}, "fake", "-", error="down")
        text = state["outputs"] if point == "keep_blocks" else state["output"]
        items = dict(re.findall(r"^([BL]\d+)\| (.*?)(?=^[BL]\d+\| |\Z)", text, re.M | re.S))
        answers = {
            key: Answer(kind="score", confidence=0.9,
                        score=3.0 if any(w in items.get(key, "") for w in self.wanted) else 0.0)
            for key in qs
        }  # fmt: skip
        return Decision(point, answers, "fake", "fake-1")

    def record(self, decision: Decision, **_: Any) -> None:
        return None


def _history(output: str, prompt: str = LONG_REQUEST) -> list[dict[str, Any]]:
    return [
        {"role": "user", "content": prompt},
        {"role": "assistant", "content": [_use("c1", "Bash", command="./diagnose")]},
        {"role": "user", "content": [_result("c1", output)]},
    ]


NOISE = "\n".join(f"row {i} of 60: item=K-{1000 + i} qty={i % 7}" for i in range(60))
OUTPUT = f"{NOISE}\nla sonda se quejo: margen 0.37, referencia ref-olmo-garza\n{NOISE}"


def test_the_questions_carry_the_whole_request_and_score_levels():
    state, qs = q.block_questions(requests=LONG_REQUEST, blocks=[("$ ./x", "a\nb")])
    assert state["requests"].endswith("complained about.")
    assert all(isinstance(x, Score) and len(x.levels) == 4 for x in qs.values())
    with_notes, _ = q.line_questions(requests="r", command="$ ./x", lines=["a"], notes="summary")
    assert with_notes["notes"] == "summary" and "notes" not in state


def test_nothing_is_asked_when_the_pool_fits():
    squire = ScoreSquire(("ref-olmo-garza",))
    g = asyncio.run(keep.build(squire, _history("margen 0.37 ref-olmo-garza")))
    assert g.chooser == "keep (all fit)" and squire.states == []


def test_the_decider_finds_what_no_rule_sees_and_it_goes_first():
    squire = ScoreSquire(("ref-olmo-garza",))
    g = asyncio.run(keep.build(squire, _history(OUTPUT), facts_chars=400))
    lines = [f.line for f in g.facts]
    assert g.chooser == "keep" and any("ref-olmo-garza" in x for x in lines)
    assert all(s["requests"].endswith("complained about.") for s in squire.states)


def test_the_rule_fills_what_the_decider_leaves_and_stands_alone_on_failure():
    pieces = guard.pieces_of(guard.calls(_history(OUTPUT)))
    rule = frozenset({pieces[3].line})
    scores = [3.0 if "ref-olmo" in p.line else None for p in pieces]
    order = keep.cascade(pieces, rule, scores)
    assert "ref-olmo-garza" in order[0].line and order[1] == pieces[3] and len(order) == 2
    assert keep.cascade(pieces, rule, None) == [pieces[3]]
    down = asyncio.run(keep.build(ScoreSquire((), fail=True), _history(OUTPUT), facts_chars=400))
    assert down.chooser == "keep (decider failed: rule only)" and down.requests


def test_a_line_the_decider_scores_low_never_enters():
    pieces = guard.pieces_of(guard.calls(_history(OUTPUT)))
    assert keep.cascade(pieces, frozenset(), [0.4] * len(pieces)) == []


def test_an_output_the_harness_cut_is_said_to_be_cut():
    clipped = "head of the log\n\n... [10687 characters truncated] ...\n\ntail of the log"
    g = guard.build(_history(clipped))
    assert g.clipped == ("$ ./diagnose (10687 characters cut)",)
    assert "was never seen" in guard.block(g)
    assert guard.build(_history("short output")).clipped == ()


def test_the_hook_builds_keep_after_the_summary_and_reads_it_as_notes(env, monkeypatch):
    squire = ScoreSquire(("PRB-9015",))
    monkeypatch.setattr("sanchopanza.harness.claude_code.squire_from_env", lambda **_: squire)
    monkeypatch.setenv("SANCHOPANZA_GUARD_CHOOSER", "keep")
    monkeypatch.setenv("SANCHOPANZA_GUARD_FACTS_CHARS", "150")
    path = write_session(env / "s.jsonl", compacted=True)
    note = _run({"hook_event_name": "PreCompact", "trigger": "auto", "session_id": "k",
                 "transcript_path": str(path)}, monkeypatch)  # fmt: skip
    assert note == guard.INSTRUCTIONS and squire.states == []  # nothing asked before the summary
    out = json.loads(_run({"hook_event_name": "SessionStart", "source": "compact", "session_id": "k",
                           "transcript_path": str(path)}, monkeypatch))  # fmt: skip
    assert "PRB-9015" in out["hookSpecificOutput"]["additionalContext"]
    assert squire.states and all(s.get("notes") == "Summary: work so far." for s in squire.states)


def test_a_one_shot_tool_that_failed_both_times_keeps_its_first_output():
    history = [
        Call(id="a", tool="Bash", input={"command": "./probe"}, result="ProbeError (code PRB-1)", is_error=True),
        Call(id="b", tool="Bash", input={"command": "./probe"}, result="already consumed", is_error=True),
        Call(id="c", tool="Bash", input={"command": "make"}, result="fail", is_error=True),
        Call(id="d", tool="Bash", input={"command": "make"}, result="fail", is_error=True),
    ]
    assert [c.id for _, c in guard.latest_only(history)] == ["a", "b", "d"]


def test_notes_are_the_open_tasks_of_the_latest_todo_list():
    todo = [{"content": "wire the probe", "status": "pending"}, {"content": "read", "status": "completed"}]
    history = [
        Call(id="a", tool="TodoWrite", input={"todos": [{"content": "old", "status": "pending"}]}),
        Call(id="b", tool="TodoWrite", input={"todos": todo}),
    ]
    assert keep.pending_tasks(history) == "Open tasks:\n- [pending] wire the probe"
    assert keep.pending_tasks([]) == ""


def test_a_secret_straddling_a_cut_is_masked():
    secret = "sk-ant-api03-" + "A1b2C3d4" * 6
    output = "x" * 290 + " " + secret
    pieces = guard.pieces_of(guard.calls(_history(output)))
    assert all("A1b2C3d4" not in p.line for p in pieces)


class NullSquire(ScoreSquire):
    provider = "null"


def test_a_null_provider_is_a_failure_and_the_rule_stands():
    squire = NullSquire(("ref-olmo-garza",))
    g = asyncio.run(keep.build(squire, _history(OUTPUT), facts_chars=400))
    assert g.chooser == "keep (decider failed: rule only)" and squire.states == []


def test_empty_answers_are_a_failure_too():
    class Empty(ScoreSquire):
        async def decide(self, point, state, qs):
            return Decision(point, {}, "fake", "fake-1")

    g = asyncio.run(keep.build(Empty(()), _history(OUTPUT), facts_chars=400))
    assert g.chooser == "keep (decider failed: rule only)"


def test_the_hook_falls_back_to_the_rule_on_any_error(env, monkeypatch):
    def broken(**_):
        raise ValueError("boom")

    monkeypatch.setattr("sanchopanza.harness.claude_code.squire_from_env", lambda **_: ScoreSquire(()))
    monkeypatch.setattr("sanchopanza.context.keep.build", lambda *a, **k: broken())
    monkeypatch.setenv("SANCHOPANZA_GUARD_CHOOSER", "keep")
    path = write_session(env / "s.jsonl", compacted=True)
    out = json.loads(_run({"hook_event_name": "SessionStart", "source": "compact", "session_id": "e",
                           "transcript_path": str(path)}, monkeypatch))  # fmt: skip
    assert "PRB-9015" in out["hookSpecificOutput"]["additionalContext"]
    log = [json.loads(x) for x in (env / "log.jsonl").read_text("utf-8").splitlines()]
    assert log[-1]["chooser"] == "keep (error: rule only)" and log[-1]["notes_origin"] == "previous summary"
