"""A5 (`benchmarks/facts_gate/`) and the shared paid helper (`benchmarks/paid_once.py`).

Nothing here calls a paid API: the live decider is a fake, and the ledger a temporary file.
"""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import pathlib
import sys

import pytest

from sanchopanza.contract import Answer, Decision

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


cases = _load("facts_gate_cases", ROOT / "benchmarks" / "facts_gate" / "cases.py")
run = _load("facts_gate_run", ROOT / "benchmarks" / "facts_gate" / "run.py")
paid_once = sys.modules["paid_once"]


def test_the_committed_batch_is_the_seeded_one_and_its_hash_holds():
    text = cases.text_of(cases.build())
    committed = (ROOT / "benchmarks" / "facts_gate" / "cases.jsonl").read_bytes()
    assert committed.replace(b"\r\n", b"\n").decode("utf-8") == text
    sealed = (ROOT / "benchmarks" / "facts_gate" / "cases.sha256").read_text().strip()
    assert hashlib.sha256(text.encode("utf-8")).hexdigest() == sealed


def test_the_batch_mix_is_the_registered_one():
    built = cases.build()
    assert len(built) == 500
    labels = [c["expected"] for c in built]
    assert (labels.count("unrelated"), labels.count("agree"), labels.count("conflict")) == (
        200,
        150,
        150,
    )
    assert len({c["id"] for c in built}) == 500
    assert {c["lang"] for c in built} == {"es", "en"}


def test_each_shape_is_its_label_by_construction():
    for c in cases.build():
        a, b = c["input"]["fact_a"], c["input"]["fact_b"]
        assert a != b
        if c["shape"] == "restated" or c["shape"] == "detail":
            assert c["expected"] == "agree"
        elif c["shape"] == "values":
            assert c["expected"] == "conflict"
        else:
            assert c["expected"] == "unrelated"
        assert " de el " not in a + b


def test_a_conflict_states_two_values_and_an_agreement_one():
    rng = __import__("random").Random(3)
    v = cases.draw(rng, "museum", "visitors")
    w = cases.other_value(rng, "museum", "visitors", v)
    assert abs(w - v) >= 0.15 * v


def _rows(spec):
    """spec: (expected, shipped verdict, verdict at every gate >= threshold)."""
    out = []
    for i, (expected, shipped, opens_at) in enumerate(spec):
        row = {"id": str(i), "expected": expected, "shipped": shipped}
        for g in run.GATES:
            row[f"g{g:.2f}"] = shipped or ("unrelated" if g <= opens_at else None)
        out.append(row)
    return out


def test_added_counts_only_what_the_shipped_policy_left_undecided():
    rows = _rows([("unrelated", None, 0.66), ("agree", None, 0.62), ("unrelated", "agree", 0.9)])
    got = run.added(rows, 0.60)
    assert (got["added"], got["right"], got["wrong"]) == (2, 1, 1)
    assert got["net"] == 1 - 4


def test_the_derived_gate_is_the_best_net_and_ties_go_stricter():
    rows = _rows([("unrelated", None, 0.66), ("unrelated", None, 0.66), ("agree", None, 0.55)])
    assert run.derive(rows) == 0.65
    assert run.derive(_rows([("agree", None, 0.70)])) is None


def test_the_verdict_needs_enough_cases_and_the_target():
    few = _rows([("unrelated", None, 0.70)] * 10)
    assert run.verdict(few, 0.65)["verdict"].startswith("undecided")
    good = _rows([("unrelated", None, 0.70)] * 30)
    assert run.verdict(good, 0.65)["verdict"] == "the gate beats the shipped policy"
    bad = _rows([("unrelated", None, 0.70)] * 20 + [("conflict", None, 0.70)])
    assert run.verdict(bad, 0.65)["verdict"] == "the gate does not beat the shipped policy"
    assert "stands" in run.verdict(good, None)["verdict"]


class Live:
    name = "live"

    def __init__(self, fail_at=None):
        self.calls = 0
        self.fail_at = fail_at

    async def decide(self, point, state, questions):
        self.calls += 1
        if self.fail_at is not None and self.calls >= self.fail_at:
            return Decision(point, {}, "live", "-", error="HTTP 500")
        answers = {k: Answer("choice", 0.9, choice="agree") for k in questions}
        return Decision(point, answers, "live", "jev-1.13.0", cost_usd=2e-5)


def _queries(n):
    return [run.query({"input": {"fact_a": f"A {i}.", "fact_b": f"B {i}."}}) for i in range(n)]


def test_plan_prices_what_is_missing_and_ask_missing_asks_it_once(tmp_path):
    fixture = tmp_path / "rec.jsonl"
    asks = _queries(3)
    plan = paid_once.plan(asks, fixture)
    assert (plan["to_ask"], plan["usd_at_median_request"]) == (3, round(3 * 71e-6, 6))
    live = Live()
    got = asyncio.run(
        paid_once.ask_missing(
            asks, fixture, live=live, ledger=tmp_path / "l.jsonl", batch="t", cap_usd=0.01
        )
    )
    assert got["stopped"] is None and live.calls == 3
    assert paid_once.plan(asks, fixture)["to_ask"] == 0  # a relaunch asks nothing
    asyncio.run(
        paid_once.ask_missing(
            asks, fixture, live=live, ledger=tmp_path / "l.jsonl", batch="t", cap_usd=0.01
        )
    )
    assert live.calls == 3


def test_ask_missing_stops_at_the_first_failure_and_at_the_cap(tmp_path):
    live = Live(fail_at=2)
    got = asyncio.run(
        paid_once.ask_missing(
            _queries(5), tmp_path / "r.jsonl", live=live, ledger=tmp_path / "l", batch="t",
            cap_usd=0.01,
        )
    )  # fmt: skip
    assert got["stopped"] == "failed or empty answer" and live.calls == 2
    capped = Live()
    got = asyncio.run(
        paid_once.ask_missing(
            _queries(5), tmp_path / "r2.jsonl", live=capped, ledger=tmp_path / "l2",
            batch="t", cap_usd=1e-9,
        )
    )  # fmt: skip
    assert got["stopped"].startswith("SpendCapReached") and capped.calls == 0


def test_a_run_needs_a_sealed_prereg_and_room(tmp_path):
    prereg = tmp_path / "prereg.md"
    prereg.write_text("rule\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        paid_once.require_sealed(prereg)
    (tmp_path / "prereg.sha256").write_text(paid_once.digest(prereg) + "\n", encoding="utf-8")
    paid_once.require_sealed(prereg)
    with pytest.raises(SystemExit):
        paid_once.require_room(
            {"usd_at_median_request": 0.2, "usd_pessimistic_estimate": 0.01}, 0.1
        )


def test_a_seal_is_written_once_and_the_cases_are_pinned(tmp_path):
    prereg = tmp_path / "prereg.md"
    prereg.write_text("rule\n", encoding="utf-8")
    first = paid_once.seal(prereg)
    assert paid_once.seal(prereg) == first  # the same text seals to the same hash
    prereg.write_text("rule, edited after the seal\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        paid_once.seal(prereg)
    paid_once.require_file(run.CASES, run.CASES_SHA256)
    with pytest.raises(SystemExit):
        paid_once.require_file(prereg, run.CASES_SHA256)


def test_the_recorded_free_derivation_is_the_published_one():
    if not (ROOT / "docs" / "results" / "2026-10-16-a5-unrelated" / "free.json").exists():
        pytest.skip("free.json not written")
    got = asyncio.run(run.free())
    published = json.loads(
        (ROOT / "docs" / "results" / "2026-10-16-a5-unrelated" / "free.json").read_text("utf-8")
    )
    assert got == published
    assert got["derived_gate"] == run.GATE_UNDER_TEST == 0.65
