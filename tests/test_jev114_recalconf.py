"""Lot jev114-recalconf (docs/results/2026-10-15-jev114-recalconf/): the analysis, free.

Pins that the cuts under test are the ones `policy.MODEL_PROFILES` ships, that the analysis
reproduces the recalibration when it is pointed at the recalibration's own draw, and the
registered recommendation rule.
"""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JEV114 = ROOT / "benchmarks" / "jev114"
RECAL = ROOT / "docs" / "results" / "2026-10-15-jev114-recal" / "analysis.json"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, JEV114 / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


analysis = _load("recalconf_analysis")


def test_cuts_are_the_shipped_profile():
    recal = json.loads(RECAL.read_text(encoding="utf-8"))
    for point, out in recal["points"].items():
        expected = out["shipped"] if out["cut_14"] is None else out["cut_14"]
        assert analysis.cuts(point) == {"13r": out["shipped"], "14": expected}, point


def test_rank_auc_matches_the_pairwise_count():
    rng = random.Random(3)
    for _ in range(20):
        scores = [round(rng.random(), 1) for _ in range(40)]
        labels = [rng.random() < 0.4 for _ in range(40)]
        pos = [s for s, y in zip(scores, labels, strict=True) if y]
        neg = [s for s, y in zip(scores, labels, strict=True) if not y]
        expected = analysis.l4_stats.auc(pos, neg)
        assert abs(analysis.auc(scores, labels) - expected) < 1e-12


def test_auc_is_none_with_one_class():
    assert analysis.auc([0.1, 0.2], [True, True]) is None


def test_the_recalibration_draw_reproduces_its_verdicts(monkeypatch):
    monkeypatch.setitem(analysis.SOURCES, 2, analysis.SOURCES[1])
    b = analysis.part_b()
    recal = json.loads(RECAL.read_text(encoding="utf-8"))
    for point, out in recal["points"].items():
        mine = b["points"][point]["test"]
        assert (mine["base"], mine["new"], mine["n"]) == (
            out["test"]["base"], out["test"]["new"], out["test"]["n"]), point  # fmt: skip
        assert mine["verdict"] == out["test"]["verdict"], point
        assert b["points"][point]["noise"]["13r"]["decisions_flipped"] == 0
    assert (b["pooled_all"]["base"], b["pooled_all"]["new"]) == (556, 556)
    assert b["pooled_all"]["verdict"] == "no peor"


def _b(pooled: str, *points: str) -> dict:
    return {"pooled_all": {"verdict": pooled},
            "points": {p: {"test": {"verdict": v}} for p, v in
                       zip(("a", "b", "c"), points, strict=False)}}  # fmt: skip


def test_cuts_are_the_registered_table():
    for point, (c13, c14) in analysis.PREREG_CUTS.items():
        assert analysis.cuts(point) == {"13r": c13, "14": c14}, point


def test_recommendation_rule():
    ok_c = {"test": {"verdict": "no peor"}, "candor_criterion_14": True}
    no_guard = {"test": {"verdict": "no peor"}, "candor_criterion_14": False}
    assert analysis.recommendation(_b("no peor"), no_guard)["switch"] == "no admisible"
    assert analysis.recommendation(_b("no peor", "no peor", "no concluyente"), ok_c)[
        "switch"] == "admisible"  # fmt: skip
    assert analysis.recommendation(_b("mejora", "peor"), ok_c)["switch"] == "no admisible"
    assert analysis.recommendation(_b("no concluyente"), ok_c)["switch"] == "no admisible"
    bad_c = {"test": {"verdict": "no concluyente"}}
    assert analysis.recommendation(_b("no peor"), bad_c)["switch"] == "no admisible"
    missing_c = {"test": {"verdict": "no medido"}}
    assert analysis.recommendation(_b("no peor"), missing_c)["switch"] == "no admisible"


runner = _load("recalconf")


def test_an_unanswered_bench_case_has_no_probability(monkeypatch, tmp_path):
    """The squire fails open to a default probability; a case without a recorded answer must
    come out of `rows` as missing, never as that default."""
    import asyncio

    monkeypatch.setattr(runner, "fixture", lambda part, arm: tmp_path / f"{part}-{arm}.jsonl")
    cases = runner.l1_cases()
    picked = [next(c for c in cases if c["point"] == p) for p in analysis.recal.L1_POINTS]
    rows = asyncio.run(runner.rows_of("l1", picked))
    assert len(rows) == 2 * len(picked)
    assert all(r["probability"] is None for r in rows)


class _Probe:
    def __init__(self, *calls):
        self.calls = list(calls)


def test_a_refusal_inside_the_squire_stops_the_part(monkeypatch):
    monkeypatch.setattr(runner, "arms_of", lambda part, live, gate: {})
    run = runner.Run("l1")
    assert run.outcome_of(_Probe({"answers": {"x": 1}})) == "asked"
    assert run.outcome_of(_Probe({"error": "TimeoutError: slow"})) == "failed"
    assert not run.stop.is_set()
    assert run.outcome_of(_Probe({"error": "SpendCapReached: spend cap"})) == "stopped"
    assert run.stop.is_set() and run.why.startswith("SpendCapReached")


def test_relaunch_rules(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "LAUNCHES", tmp_path / "launches.jsonl")
    monkeypatch.setattr(runner, "RUN", tmp_path)
    monkeypatch.setattr(runner, "fixture", lambda part, arm: tmp_path / f"fx-{part}-{arm}.jsonl")
    assert runner.may_launch() is None
    (tmp_path / "fx-cf-14.jsonl").write_text("{}\n", encoding="utf-8")
    assert runner.may_launch().startswith("answers recorded before any launch")
    (tmp_path / "fx-cf-14.jsonl").unlink()
    runner.log_launch("started", "")
    runner.log_launch("stopped", "done: 25 failed calls")
    assert runner.may_launch() is None
    runner.log_launch("started", "")
    runner.log_launch("stopped", "cf: TimeoutError")
    assert runner.may_launch() == "2 launches already"
    (tmp_path / "launches.jsonl").write_text(
        '{"outcome": "stopped", "why": "l1: SpendCapReached: spend cap"}\n', encoding="utf-8"
    )
    assert "cap" in runner.may_launch()
    (tmp_path / "launches.jsonl").write_text(
        '{"outcome": "started", "why": ""}\n{"outcome": "complete", "why": ""}\n',
        encoding="utf-8",
    )
    assert runner.may_launch() == "an earlier launch completed"


def test_a_402_outside_the_bench_is_a_final_stop(monkeypatch, tmp_path):
    from sanchopanza.contract import DeciderOutOfFunds

    monkeypatch.setattr(runner, "LAUNCHES", tmp_path / "launches.jsonl")
    monkeypatch.setattr(runner, "RUN", tmp_path)
    monkeypatch.setattr(runner, "arms_of", lambda part, live, gate: {})

    class Broke:
        async def decide(self, *_):
            raise DeciderOutOfFunds("jev did not answer: HTTP 402 (out of funds)")

    import asyncio

    run = runner.Run("done")
    run.arms = {"13r": Broke(), "14": Broke()}
    case = {"point": "completion", "state": {}, "questions": {}}
    asyncio.run(run.one(0, case, {"13r", "14"}))
    assert run.stop.is_set() and run.why.startswith("DeciderOutOfFunds")
    runner.log_launch("started", "")
    runner.log_launch("stopped", f"done: {run.why}")
    assert "402" in runner.may_launch()
    (tmp_path / "launches.jsonl").write_text(
        '{"outcome": "started", "why": ""}\n'
        '{"outcome": "stopped", "why": "preflight: no_funds (HTTP 402)"}\n',
        encoding="utf-8",
    )
    assert "402" in runner.may_launch()


def test_a_part_never_asked_is_not_measured(monkeypatch, tmp_path):
    empty = tmp_path / "errata-scored.jsonl"
    empty.write_text("", encoding="utf-8")
    monkeypatch.setitem(analysis.SOURCES, 2, {**analysis.SOURCES[1], "ERRATA": empty})
    b = analysis.part_b()
    assert b["points"]["holistic"]["test"]["verdict"] == "no medido"
    assert b["pooled_all"]["verdict"] == "no medido"
    assert b["pooled_l1"]["verdict"] == "no peor"
