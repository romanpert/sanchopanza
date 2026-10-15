"""The statistics and the arm wrapper of benchmarks/jev114/l4.py, with no network."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from sanchopanza.contract import Answer, Decision, Truth

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("jev114_l4", ROOT / "benchmarks/jev114/l4.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["jev114_l4"] = module
    spec.loader.exec_module(module)
    return module


l4 = _load()
st = sys.modules["l4_stats"]


def test_mcnemar_exact_matches_the_binomial_tail():
    assert st.mcnemar_exact(0, 0) == 1.0
    assert st.mcnemar_exact(5, 5) == 1.0
    assert st.mcnemar_exact(10, 0) == pytest.approx(2 / 2**10)
    assert st.mcnemar_exact(8, 2) == pytest.approx(2 * (1 + 10 + 45) / 2**10)


def test_holm_is_monotone_and_capped():
    out = st.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert out == {"a": 0.03, "c": 0.06, "b": 0.06}
    assert st.holm({"x": 0.9, "y": 0.8}) == {"y": 1.0, "x": 1.0}


def test_paired_binary_reports_discordant_pairs_and_a_ci():
    new = [True] * 8 + [False] * 2
    old = [True] * 5 + [False] * 5
    out = st.paired_binary(new, old, [str(i) for i in range(10)])
    assert (out["only_new"], out["only_old"], out["diff"]) == (3, 0, 0.3)
    assert out["ci95"][0] <= 0.3 <= out["ci95"][1]


def test_paired_auc_on_identical_arms_is_zero_difference():
    labels = [True, False] * 10
    scores = [0.9 if y else 0.1 for y in labels]
    out = st.paired_auc(labels, scores, scores, [str(i // 2) for i in range(20)])
    assert out["new"] == out["old"] == 1.0
    assert out["diff"] == 0.0 and out["ci95"] == out["ci95_cluster"] == (0.0, 0.0)


def test_verdict_rule():
    assert st.verdict({"diff": 0.1, "ci95": (0.02, 0.2)}, 0.01) == "mejora"
    assert st.verdict({"diff": 0.0, "ci95": (-0.01, 0.02)}, 1.0) == "no peor"
    assert st.verdict({"diff": -0.03, "ci95": (-0.08, 0.01)}, 1.0) == "no concluyente o peor"
    assert st.verdict({"diff": 0.0, "ci95": (-0.01, 0.02)}, 1.0, 0.05) == "no concluyente o peor"
    assert st.verdict({"diff": None, "ci95": None}, 1.0) == "no medido"


def test_cluster_bootstrap_resamples_whole_clusters():
    units = st.clusters_as_units(["a", "b", "a", "c"])
    assert sorted(map(sorted, units)) == [[0, 2], [1], [3]]
    sizes = set(st.bootstrap(lambda idx: float(len(idx)), units))
    assert sizes <= {3.0, 4.0, 5.0, 6.0}


def test_family_counts_a_missing_comparison_as_p_one():
    out = l4.analyse({})
    assert set(out["family"]) == set(l4.FAMILY)
    assert all(v["verdict"] == "no medido" and v["p_holm"] == 1.0 for v in out["family"].values())


def test_launch_order_is_seeded_and_complete():
    assert l4.launch_order(10) == l4.launch_order(10)
    assert sorted(l4.launch_order(10)) == list(range(10))


def test_find_rankings_prod_keeps_kept_first_and_free_orders_by_p():
    keys = ["a.py:1-2", "b.py:1-2", "c.py:1-2"]
    verdicts = [(False, 0.4), (True, 0.6), (False, 0.9)]
    out = l4.find_rankings(keys, verdicts)
    assert out["prod"] == ["b.py", "a.py", "c.py"]
    assert out["free"] == ["c.py", "b.py", "a.py"]


class _Live:
    name = "jev"

    def __init__(self, model: str, fail: bool = False) -> None:
        self.model, self.fail, self.calls = model, fail, 0

    async def decide(self, point, state, questions):
        self.calls += 1
        if self.fail:
            raise RuntimeError("down")
        answers = {"q": Answer(kind="truth", confidence=0.9, truth=0.7)}
        return Decision(point, answers, "jev", self.model, cost_usd=0.001)


def test_arm_records_then_replays_for_free(tmp_path):
    live = _Live("jev-1.14.0")

    async def go():
        gate = asyncio.Semaphore(1)
        arm = l4.Arm("j14", tmp_path / "a.jsonl", "jev-1.14.0", live, gate)
        first = await arm.decide("p", "s", {"q": Truth("?")})
        again = l4.Arm("j14", tmp_path / "a.jsonl", "jev-1.14.0", None, gate)
        second = await again.decide("p", "s", {"q": Truth("?")})
        return arm, first, again, second

    arm, first, again, second = asyncio.run(go())
    assert first.answer("q").truth == second.answer("q").truth == 0.7
    assert (live.calls, arm.live_calls, again.live_calls, again.failures) == (1, 1, 0, 0)
    assert arm.usd == again.usd == 0.001


def test_arm_counts_a_failure_and_refuses_a_wrong_model(tmp_path):
    async def go(live, model):
        arm = l4.Arm("x", tmp_path / f"{model}.jsonl", model, live, asyncio.Semaphore(1))
        decision = await arm.decide("p", "s", {"q": Truth("?")})
        return arm, decision

    arm, decision = asyncio.run(go(_Live("jev-1.14.0", fail=True), "jev-1.14.0"))
    assert decision.failed and arm.failures == 1
    with pytest.raises(SystemExit):
        asyncio.run(go(_Live("jev-1.13.0"), "jev-1.14.0"))
