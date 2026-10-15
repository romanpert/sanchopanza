"""Lot L1 of the Jev 1.14 plan: the paired rules and the runner, without the network."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "jev114"))

import jev114_components as components  # noqa: E402
import jev114_paired as paired  # noqa: E402

from sanchopanza.contract import Answer, Decision  # noqa: E402


def test_verdicts_follow_the_sealed_rule():
    assert paired.verdict(0.03, 0.01, 0.05, 0.01) == "mejora"
    assert paired.verdict(0.03, 0.01, 0.05, 0.20) == "no peor"
    assert paired.verdict(0.0, -0.019, 0.02, 1.0) == "no peor"
    assert paired.verdict(-0.01, -0.03, 0.01, 0.5) == "no concluyente"
    assert paired.verdict(-0.04, -0.06, -0.01, 0.01) == "peor"


def test_holm_is_step_down_and_monotone():
    adjusted = paired.holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert adjusted == pytest.approx({"a": 0.03, "c": 0.06, "b": 0.06})


def test_compare_pairs_only_the_shared_keys():
    out = paired.compare({"x": True, "y": False, "z": True}, {"x": True, "y": True})
    assert (out["n"], out["base"], out["new"], out["only_new"], out["only_base"]) == (2, 1, 2, 1, 0)


def test_policy_item_leaves_out_what_the_code_decided_and_counts_abstention_as_wrong():
    model_call = [{"answers": {"x": {}}}]
    assert paired.policy_item({"correct": True, "decided": True, "calls": model_call}) is True
    assert paired.policy_item({"correct": None, "decided": False, "calls": model_call}) is False
    assert paired.policy_item({"correct": True, "decided": True, "provider": "code",
                               "calls": []}) is None  # fmt: skip


def test_collision_is_two_binary_items_and_duplicate_does_not_constrain_contradicts():
    row = {
        "id": "c1",
        "point": "memory_collision",
        "expected": "duplicate",
        "newer": None,
        "calls": [{"answers": {"adds_nothing": {"truth": 0.9}, "contradicts": {"truth": 0.1}}}],
    }
    assert paired.free_items(row) == [("c1:adds_nothing", 0.9, True)]


def test_a_failed_call_makes_the_row_unusable():
    assert paired.failed({"calls": [{"answers": {}, "error": "HTTP 500"}]})
    assert not paired.failed({"calls": [{"answers": {"x": {"truth": 0.2}}, "error": None}]})


def test_supersede_rule_is_the_shipped_one():
    from jev114_extras import supersede_row

    assert supersede_row({"id": "p", "label": 1}, 0.55, 0.40)["predicted"] is True
    assert supersede_row({"id": "p", "label": 1}, 0.54, 0.40)["predicted"] is False
    assert supersede_row({"id": "n", "label": 0}, 0.60, 0.61)["correct"] is True
    assert supersede_row({"id": "n", "label": 0}, None, None)["correct"] is True


class _Fake:
    def __init__(self, name: str, log: list[str]) -> None:
        self.name, self._log, self._arm = "jev", log, name
        self.model = components.MODELS[name]

    async def decide(self, point, state, questions):
        self._log.append(self._arm)
        return Decision(point, {k: Answer("truth", 0.9, truth=0.9) for k in questions},
                        "jev", self.model, input_tokens=10, cost_usd=1e-6)  # fmt: skip


def test_arms_alternate_per_case_and_rows_are_written(tmp_path, monkeypatch):
    monkeypatch.setattr(components, "RUN", tmp_path)
    monkeypatch.setattr(components, "CASES_AT_ONCE", 1)
    log: list[str] = []
    stacks = {"13r": _Fake("13r", log), "14": _Fake("14", log)}
    cases = [{"id": f"c{i}", "file": "f", "component": "x", "point": "recall",
              "input": {"turn": "t"}, "expected": "look"} for i in range(3)]  # fmt: skip
    out = tmp_path / "rows.jsonl"
    counts = asyncio.run(components.run_cases(cases, stacks, out, components.ask_bench))
    assert counts["asked"] == 6
    assert log == ["13r", "14", "14", "13r", "13r", "14"]
    rows = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    assert {(r["arm"], r["id"]) for r in rows} == {(a, f"c{i}") for a in ("13r", "14")
                                                   for i in range(3)}  # fmt: skip
    again = asyncio.run(components.run_cases(cases, stacks, out, components.ask_bench))
    assert again["asked"] == 0 and again["skipped"] == 6


def test_a_stop_file_stops_scheduling(tmp_path, monkeypatch):
    monkeypatch.setattr(components, "RUN", tmp_path)
    (tmp_path / "STOP").write_text("", encoding="utf-8")
    stacks = {"13r": _Fake("13r", []), "14": _Fake("14", [])}
    cases = [{"id": "c0", "file": "f", "component": "x", "point": "recall",
              "input": {"turn": "t"}, "expected": "look"}]  # fmt: skip
    counts = asyncio.run(components.run_cases(cases, stacks, tmp_path / "r.jsonl",
                                              components.ask_bench))  # fmt: skip
    assert counts["asked"] == 0


def test_the_113_rerun_never_writes_into_a_published_fixture():
    assert components.fixture_for("14").parent.name == "jev114"
    assert components.fixture_for("13r").parent.name == "jev114"
    assert components.fixture_for("13r").name.endswith("-113r.jsonl")


def test_a_failed_case_is_asked_once_more_then_left(tmp_path):
    out = tmp_path / "rows.jsonl"
    bad = {"arm": "14", "file": "f", "id": "c0", "calls": [{"answers": {}, "error": "HTTP 500"}]}
    out.write_text(json.dumps(bad) + "\n", encoding="utf-8")
    assert ("14", "f", "c0") not in components.done_keys(out)
    with out.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(bad) + "\n" + '{"cut short')
    assert ("14", "f", "c0") in components.done_keys(out)


def test_a_case_one_arm_failed_is_that_arms_error():
    import jev114_report as report

    ok = {"calls": [{"answers": {"x": {}}}]}
    lost = {"calls": [{"answers": {}, "error": "HTTP 400"}]}
    base_rows = {"f:c1": ok, "f:c2": ok}
    new_rows = {"f:c1": ok, "f:c2": lost}
    b, n = report.with_failures({"f:c1": True, "f:c2": True}, {"f:c1": True},
                                base_rows, new_rows)  # fmt: skip
    assert b == {"f:c1": True, "f:c2": True}
    assert n == {"f:c1": True, "f:c2": False}


def test_the_gate_needs_both_global_tests():
    import jev114_report as report

    g = {"policy": {"verdict": "no peor"}, "at_half": {"verdict": "mejora"},
         "auc": {"verdict": "no concluyente"}}  # fmt: skip
    assert report.gate(g)["passes"] is True
    g["policy"]["verdict"] = "no concluyente"
    assert report.gate(g) | {} == {**report.gate(g), "passes": False, "recalibrate_first": True}


def test_an_answer_from_another_model_is_caught():
    probe = components.Probe(_Fake("14", []))
    probe.calls.append({"provider": "jev", "model": "jev-1.13.0", "answers": {"x": {}}})
    assert components.wrong_model("14", probe)
    assert not components.wrong_model("13r", probe)


RESULTS = ROOT / "docs" / "results" / "2026-10-15-jev114-l1"


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    """The published report, rebuilt from the committed rows and recordings. No network."""
    import argparse
    import contextlib
    import io

    if not (RESULTS / "rows" / "rows-bench.jsonl").exists():
        pytest.skip("rows not present")
    out = tmp_path_factory.mktemp("l1")
    args = argparse.Namespace(rows=str(RESULTS / "rows"), out=str(out))
    with contextlib.redirect_stdout(io.StringIO()):
        components.cmd_report(args)
    return json.loads((out / "report.json").read_text(encoding="utf-8"))


def test_the_gate_passes_as_published(published):
    g = published["tests"]["global"]
    assert (g["policy"]["n"], g["policy"]["base"], g["policy"]["new"]) == (1437, 1259, 1253)
    assert (g["at_half"]["n"], g["at_half"]["base"], g["at_half"]["new"]) == (1320, 1227, 1224)
    assert published["tests"]["gate"]["passes"] is True
    assert published["served"]["wrong"] == {}
    assert published["failed"]["14"] == 0 and published["failed"]["13r"] == 0


def test_the_figures_to_beat_as_published(published):
    f13, f14 = published["figures"]["13r"], published["figures"]["14"]
    assert (f13["routing"], f14["routing"]) == ("14/20", "14/20")
    assert (f13["injection_28"], f14["injection_28"]) == ("27/28", "27/28")
    assert (f13["fifty_policy"], f14["fifty_policy"]) == ("200/212", "196/212")
    assert (f13["substitution_jev"], f14["substitution_jev"], f14["substitution_opus55"]) == (
        200, 196, 199)  # fmt: skip
    assert round(f14["ece_score"], 3) == 0.109 and round(f13["ece_score"], 3) == 0.152
    assert (f13["agentdojo_caught"], f14["agentdojo_caught"]) == ("99/124", "101/124")
    assert f14["agentdojo_false_alarms"] == "0/149"


def test_the_redundant_page_cut_is_where_14_loses(published):
    """Exploratory, outside the sealed rule: same ordering, lower scores on the drop side."""
    group = published["tests"]["global"]["auc"]["per_group"]["redundant_page"]
    assert group["base"] > 0.99 and group["new"] > 0.99
