"""Planning, applying and reporting a pruning: pairs intact, stubs reversible, loud failures."""

from __future__ import annotations

import random

import pytest

from sanchopanza import Thresholds
from sanchopanza.context import calls, compact, messages_from_claude_code
from sanchopanza.context.compact import Plan, Step
from sanchopanza.points import context as q

from .context_helpers import APP, BrokenDecider, ScriptedDecider, write_transcript
from .helpers import squire


def _session(tmp_path):
    return messages_from_claude_code(write_transcript(tmp_path / "s.jsonl"))


def _ids(messages, kind: str) -> list[str]:
    key = "id" if kind == "tool_use" else "tool_use_id"
    return [
        str(b[key])
        for m in messages
        if isinstance(m["content"], list)
        for b in m["content"]
        if isinstance(b, dict) and b.get("type") == kind
    ]


def _random_plan(messages, rng: random.Random) -> Plan:
    steps = tuple(
        Step(c.id, c.tool, rng.choice(("keep", "stub", "truncate", "drop")), "random", c.chars)
        for c in calls(messages)
    )
    return Plan("random", steps)


def _synthetic(rng: random.Random) -> list[dict]:
    messages: list[dict] = [{"role": "user", "content": "start"}]
    n = 0
    for _ in range(rng.randint(1, 8)):
        uses = []
        for _ in range(rng.randint(1, 3)):
            uses.append({"type": "tool_use", "id": f"u{n}", "name": "Bash", "input": {"n": n}})
            n += 1
        text = [{"type": "text", "text": "thinking aloud"}] if rng.random() < 0.5 else []
        messages.append({"role": "assistant", "content": [*text, *uses]})
        results = [
            {
                "type": "tool_result",
                "tool_use_id": u["id"],
                "content": "r" * rng.randint(0, 900),
                "is_error": rng.random() < 0.2,
            }
            for u in uses
        ]
        messages.append({"role": "user", "content": results})
    return messages


def test_pairs_and_order_survive_any_plan(tmp_path):
    rng = random.Random(20260928)
    for trial in range(300):
        messages = _synthetic(rng) if trial else _session(tmp_path)
        pruned = compact.apply(messages, _random_plan(messages, rng), tmp_path / "archive")
        uses, results = _ids(pruned, "tool_use"), _ids(pruned, "tool_result")
        assert sorted(uses) == sorted(results)  # never one without the other
        before = _ids(messages, "tool_use")
        assert uses == [i for i in before if i in set(uses)]  # same order
        assert all(m["content"] for m in pruned)


def test_a_stub_archives_the_full_text_and_keeps_the_block(tmp_path):
    messages = _session(tmp_path)
    plan = Plan("x", (Step("t4", "Read", "stub", "not_needed", len(APP)),))
    archive = tmp_path / "archive" / "s"
    pruned = compact.apply(messages, plan, archive)
    block = pruned[8]["content"][0]
    saved = (archive / "t4.txt").resolve()
    assert block["tool_use_id"] == "t4" and block["type"] == "tool_result"
    assert block["content"] == (
        f"[sanchopanza pruned this Read result: {len(APP)} chars. Full text saved at {saved}; "
        "Read it if you need it.]"
    )
    assert saved.read_text(encoding="utf-8") == APP.replace("-", "+")  # verbatim, round trip
    assert pruned[0] is messages[0]  # untouched messages are the same objects
    assert messages[8]["content"][0]["content"] != block["content"]  # input not mutated


def test_a_stubbed_error_keeps_is_error(tmp_path):
    messages = _session(tmp_path)
    pruned = compact.apply(messages, Plan("x", (Step("t2", "Bash", "stub", "r", 10),)), tmp_path)
    assert pruned[4]["content"][0]["is_error"] is True


def test_no_archive_no_stub(tmp_path):
    messages = _session(tmp_path)
    with pytest.raises(ValueError):
        compact.apply(messages, Plan("x", (Step("t4", "Read", "stub", "r", 1),)), None)


def test_file_names_are_safe():
    assert compact.safe_name("toolu_01/../../etc") == "toolu_01_.._.._etc"
    assert compact.safe_name("...") == "call"


async def test_rules_arm_asks_nothing(tmp_path):
    decider = ScriptedDecider(lambda *_: 0.0)
    sq, _ = squire(decider)
    plan = await compact.plan(sq, _session(tmp_path), arm="rules", keep_recent=0)
    steps = plan.by_id()
    assert decider.calls == [] and steps["t4"].reason == "rules_only"
    assert steps["t1"].action == "stub" and steps["t4"].action == "keep"


async def test_our_arm_asks_once_over_what_the_rules_left(tmp_path):
    decider = ScriptedDecider(lambda point, key, state: 0.1 if key == "C01" else 0.9)
    sq, journal = squire(decider)
    plan = await sq.prune_context(_session(tmp_path), keep_recent=0)
    assert len(decider.calls) == 1 and decider.calls[0][0] == "context"
    assert list(decider.calls[0][2]) == ["C01", "C02"]  # t4 and t5
    steps = plan.by_id()
    assert (steps["t4"].action, steps["t4"].reason, steps["t4"].probability) == (
        "stub",
        "not_needed",
        0.1,
    )
    assert (steps["t5"].action, steps["t5"].reason) == ("keep", "needed")
    assert steps["t1"].reason == "read_superseded" and plan.decisions == 1
    assert journal.decisions()[0]["point"] == "context"


async def test_the_cut_is_context_keep(tmp_path):
    decider = ScriptedDecider(lambda *_: 0.6)
    sq, _ = squire(decider, context_keep=0.7)
    plan = await sq.prune_context(_session(tmp_path), keep_recent=0)
    assert plan.by_id()["t4"].action == "stub"
    assert Thresholds.from_mapping({"context_keep": "0.3"}).context_keep == 0.3


async def test_an_outage_keeps_everything_and_is_counted(tmp_path):
    sq, _ = squire(BrokenDecider())
    messages = _session(tmp_path)
    plan = await sq.prune_context(messages, keep_recent=0)
    steps = plan.by_id()
    assert steps["t4"].action == "keep" and steps["t4"].reason == "unanswered"
    assert plan.failed == 1 and "provider down" in plan.errors[0]
    summary = compact.report(messages, compact.apply(messages, plan, tmp_path / "archive"), plan)
    assert summary["failed_decisions"] == 1


def _many(n: int) -> list[dict]:
    messages: list[dict] = [{"role": "user", "content": "Audit every module"}]
    for i in range(n):
        messages.append(
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": f"r{i}",
                        "name": "Grep",
                        "input": {"pattern": f"p{i}"},
                    }
                ],
            }
        )
        messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": f"r{i}", "content": f"hit {i} " * 90}
                ],
            }
        )
    return messages


async def test_past_call_max_it_is_a_tournament(tmp_path):
    def answer(point, key, state):
        return 0.9 if key in ("C01", "C02") else 0.05

    decider = ScriptedDecider(answer)
    sq, _ = squire(decider)
    messages = _many(45)
    plan = await sq.prune_context(messages, keep_recent=0)
    sizes = [len(c[2]) for c in decider.calls]
    assert sizes[:2] == [23, 22] and len(sizes) == 3  # two groups, then the survivors together
    kept = [s.id for s in plan.steps if s.action == "keep"]
    assert kept == ["r0", "r1"]


async def test_fastjev_arm_uses_their_table(tmp_path):
    def answer(point, key, state):
        return {"call_t1": 0.9, "result_t1": 0.1, "call_t2": 0.1, "result_t2": 0.1}.get(key, 0.9)

    decider = ScriptedDecider(answer)
    sq, _ = squire(decider)
    messages = _session(tmp_path)
    plan = await sq.prune_context(messages, arm="fastjev")
    steps = plan.by_id()
    assert decider.calls[0][0] == "context_fastjev"
    assert (steps["t1"].action, steps["t2"].action, steps["t4"].reason) == (
        "truncate",
        "drop",
        "pinned",
    )
    pruned = compact.apply(messages, plan, None)
    assert "t2" not in _ids(pruned, "tool_use") and "t2" not in _ids(pruned, "tool_result")
    assert "fast-jev-compaction truncated" in str(pruned)
    summary = compact.report(messages, pruned, plan)
    assert summary["actions"] == {"truncate": 1, "drop": 1, "keep": 3}
    assert summary["reasons"]["drop:call_dropped"] == 1
    assert 0 < summary["reduction"] < 1 and summary["chars_after"] < summary["chars_before"]


async def test_an_unknown_arm_is_refused(tmp_path):
    sq, _ = squire(ScriptedDecider(lambda *_: None))
    with pytest.raises(ValueError):
        await sq.prune_context(_session(tmp_path), arm="summary")


def test_report_of_nothing():
    summary = compact.report([], [], Plan("rules", ()))
    assert summary["reduction"] == 0.0 and summary["calls"] == 0
    assert q.call_id(0) == "C01" and Plan("x", (Step("a", "B", "stub", "r", 5),)).freed == 5
