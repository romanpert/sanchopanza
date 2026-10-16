"""Lot jev114-redundant-drop (docs/results/2026-10-16-redundant-drop/): the generator, the
runner's free parts and the analysis, with no network and no model.

Pins that every generated label follows from its construction, that the file is what the
generator writes, and that the analysis reproduces the recalibration's redundant_page cuts
(0.61 for 1.14, 0.59 for 1.13 on retrieval-c, lot L1's draw) and flags that derivation as
hinging on single cases.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JEV114 = ROOT / "benchmarks" / "jev114"
L1_ROWS = ROOT / "docs" / "results" / "2026-10-15-jev114-l1" / "rows" / "rows-bench.jsonl"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, JEV114 / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


gen = _load("redundant_gen")
runner = _load("redundant_drop")
analysis = _load("redundant_drop_analysis")


def test_the_file_is_what_the_generator_writes():
    assert runner.CASES.read_text(encoding="utf-8") == gen.render_file()


def test_every_label_follows_from_its_construction():
    assert [(c["id"], p) for c in gen.cases() for p in gen.problems(c)] == []


def test_counts_families_and_halves():
    cases = gen.cases()
    assert len(cases) == 405 and len({c["id"] for c in cases}) == 405
    cal_drop = [c for c in cases if c["half"] == "cal" and c["expected"] == "drop"]
    assert len(cal_drop) == 90
    for family in gen.KEEP:
        assert sum(c["family"] == family for c in cases) == 27
    halves = {}
    for c in cases:
        halves.setdefault(c["scenario"], set()).add(c["half"])
    assert all(len(h) == 1 for h in halves.values())  # no `known` crosses the partition


def test_the_check_catches_a_planted_new_figure_and_a_missing_item():
    drop = next(c for c in gen.cases() if c["family"] == "wire")
    planted = {**drop, "input": {**drop["input"], "text": drop["input"]["text"] + " Y 913 mas."}}
    assert gen.problems(planted)
    keep = next(c for c in gen.cases() if c["family"] == "qualify")
    emptied = {**keep, "input": {**keep["input"], "text": "Nada nuevo."}}
    assert gen.problems(emptied)


def test_a_drop_adds_no_word_outside_its_frame():
    for case in (c for c in gen.cases() if c["expected"] == "drop"):
        s = next(x for x in gen.SCENARIOS if x["sid"] == case["scenario"])
        added = gen.words(case["input"]["text"]) - gen.words(case["input"]["known"])
        assert added - gen.words(s["source"]) <= gen.FRAME[case["family"]], case["id"]
    drop = next(c for c in gen.cases() if c["family"] == "headline")
    planted = {**drop, "input": {**drop["input"], "text": drop["input"]["text"] + " Provisional."}}
    assert any("frame" in p for p in gen.problems(planted))


def test_no_uncontracted_or_mismatched_spanish():
    for case in gen.cases():
        for text in (case["input"]["known"], case["input"]["text"]):
            assert " de el " not in text and " a el " not in text, case["id"]
            assert "su cuentas" not in text and "primer cuentas" not in text, case["id"]


def test_rounding_keeps_less_precision():
    assert gen.rounded_down(2350) == 2000 and gen.rounded_down(37) == 30
    assert gen.fmt(84300000) == "84.300.000"


def test_the_runner_reads_the_registered_cases():
    cases = runner.cases()
    assert len(cases) == 530
    assert runner.inputs_digest(cases) == runner.inputs_digest(runner.cases())
    assert runner.duplicates_of_old(runner.new_cases(), runner.old_cases()) == 0
    for rel in runner.LOT.sealed:
        assert (ROOT / rel).exists(), rel
    for rel in ("redundant-drop-run.cmd", "src/sanchopanza/points/triage.py",
                "src/sanchopanza/squire.py", *sys.modules["lot"].COMMON_SEALED):  # fmt: skip
        assert rel in runner.LOT.sealed, rel
    assert runner.LOT.batch_cap <= 0.10
    assert '"SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"' in (ROOT / "redundant-drop-run.cmd").read_text(
        encoding="utf-8"
    )


def test_the_signed_request_is_what_the_bench_path_sends():
    import asyncio

    from sanchopanza.contract import Decision
    from sanchopanza.providers.recorded import key_of

    comp = sys.modules["jev114_components"]
    sent = []

    class Capture:
        name = "capture"

        async def decide(self, point, state, questions):
            sent.append(key_of(point, state, questions))
            return Decision(point=point, answers={}, provider="capture", model="-")

    cases = runner.cases()
    picked = [cases[0], cases[60], cases[124], cases[200], cases[-1]]
    for case in picked:
        asyncio.run(comp.ask_bench(case, Capture()))
    assert sent == [key_of(runner.POINT, *runner.request_of(c)) for c in picked]


def test_hand_written_cases_cluster_by_event():
    by_id = {c["id"]: runner.cluster_of(c) for c in runner.old_cases()}
    assert by_id["rd-01"] == by_id["rd-77"] == by_id["rd-03"] == by_id["rd-06"]
    assert by_id["rd-08"] == by_id["rd-29"] and by_id["rd-13"] == by_id["rd-61"]
    assert by_id["rd-51"] != by_id["rd-01"]
    new = runner.new_cases()
    assert runner.cluster_of(new[0]) == f"record:{new[0]['scenario']}"


def _draw1_rows():
    by: dict[str, dict] = {}
    for line in L1_ROWS.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["point"] != "redundant_page":
            continue
        item = by.setdefault(
            row["id"],
            {
                "id": row["id"],
                "file": row["file"],
                "family": "bench",
                "expected": row["expected"],
                "half": "cal" if row["file"] == "retrieval-c" else "ev",
                "cluster": row["id"],
                "scenario": None,
            },
        )
        item[f"p_{row['arm']}"] = row["probability"]
    return list(by.values())


def test_the_recalibrations_derivation_reproduces_and_hinges():
    cal = [r for r in _draw1_rows() if r["half"] == "cal"]
    assert analysis.derive(cal, "14") == 0.61 and analysis.derive(cal, "13r") == 0.59
    loo = analysis.leave_one_out(cal, "14")
    assert not loo["stable"] and "rd-118" in loo["cases_that_move_it"]


def test_the_analysis_runs_on_the_old_cases_and_withholds_a_proposal():
    result = analysis.analyse(_draw1_rows(), launch="complete")
    assert result["cuts"]["14_derived"] == 0.61
    assert result["hand_stratum"]["n"] == 50
    assert result["decision"]["propose_adds_nothing_14"] is None
    assert "derivation stable" in result["decision"]["failed_checks"]


def _synthetic(hand_losses: int, template_disagree: int = 0):
    rows = []
    for i in range(50):
        drop = i < 18
        p = 0.9 if drop else 0.1
        rows.append({"id": f"h{i}", "file": "retrieval", "half": "ev", "family": "bench",
                     "expected": "drop" if drop else "keep", "scenario": None,
                     "cluster": f"event:{i % 16}", "p_13r": p,
                     "p_14": 0.05 if drop and i < hand_losses else p})  # fmt: skip
    for s in range(30):
        for f, label in (("wire", "drop"), ("ficha", "drop"), ("extra", "keep")):
            p = 0.9 if label == "drop" else 0.1
            flip = s < template_disagree and f == "wire"
            rows.append({"id": f"t{s}{f}", "file": "generated", "half": "ev", "family": f,
                         "expected": label, "scenario": f"g{s}", "cluster": f"record:g{s}",
                         "p_13r": p, "p_14": 0.05 if flip else p})  # fmt: skip
    for i in range(60):  # a calibration part that derives a cut
        drop = i < 45
        rows.append({"id": f"c{i}", "file": "generated", "half": "cal", "family": "wire",
                     "expected": "drop" if drop else "keep", "scenario": f"k{i % 10}",
                     "cluster": f"record:k{i % 10}", "p_13r": 0.9 if drop else 0.1,
                     "p_14": 0.9 if drop else 0.1})  # fmt: skip
    return rows


def test_hand_losses_cannot_hide_behind_templates():
    agree = analysis.analyse(_synthetic(0), launch="complete")
    assert agree["primary_stratified"]["verdict"] == "no peor"
    assert agree["hand_stratum"]["count_guard"] and agree["hand_stratum"]["verdict"] == "no peor"
    lost = analysis.analyse(_synthetic(4), launch="complete")
    assert lost["hand_stratum"]["net_loss"] == 4 and not lost["hand_stratum"]["count_guard"]
    assert lost["hand_stratum"]["verdict"] not in ("no peor", "mejora")
    assert lost["decision"]["propose_adds_nothing_14"] is None


def test_the_stratified_interval_is_zero_when_the_arms_agree():
    rows = [r for r in _synthetic(0) if r["half"] == "ev"]
    hand = [r for r in rows if r["file"] != "generated"]
    tmpl = [r for r in rows if r["file"] == "generated"]
    result = analysis.stratified(hand, tmpl, 0.59, 0.5, replicas=200)
    assert result["diff"] == 0.0 and result["ci95"] == (0.0, 0.0)


def _hand(wins_on_drops: int, losses_on_keeps: int, losses_on_drops: int):
    rows = []
    for i in range(50):
        drop = i < 18
        p13 = 0.9 if drop else 0.1
        p14 = p13
        if drop and i < wins_on_drops:
            p13 = 0.1  # only 1.14 catches this drop
        if drop and wins_on_drops <= i < wins_on_drops + losses_on_drops:
            p14 = 0.1  # only 1.13 catches this drop
        if not drop and i < 18 + losses_on_keeps:
            p14 = 0.9  # 1.14 drops a keep page
        rows.append({"expected": "drop" if drop else "keep", "cluster": f"e{i % 9}",
                     "p_13r": p13, "p_14": p14})  # fmt: skip
    return analysis.hand_stratum(rows, 0.59, 0.5)


def test_the_count_guard_lets_a_balanced_exchange_through_and_stops_net_losses():
    assert _hand(1, 1, 0)["count_guard"]  # 1 / 1
    assert _hand(2, 2, 0)["count_guard"]  # 2 / 2
    assert _hand(0, 1, 0)["count_guard"]  # one keep page dropped
    assert not _hand(0, 0, 1)["count_guard"]  # one drop missed: fewer hits
    assert not _hand(0, 0, 4)["count_guard"]  # the recalibration's 0 / 4
    assert not _hand(0, 2, 0)["count_guard"]  # a net loss of two


def test_the_whole_decision_on_patterns_and_on_draw_1():
    tmpl = analysis._template_ev()
    assert len(tmpl) == 270
    clusters, drop = analysis._hand_ev()
    agree = [analysis._row(d, "agree", cluster=c) for c, d in zip(clusters, drop, strict=True)]
    assert analysis.passes(agree, tmpl, 0.5, replicas=200)["passes"]
    lost = [analysis._row(d, "loss" if i in (0, 1, 2, 3) else "agree", cluster=c)
            for i, (c, d) in enumerate(zip(clusters, drop, strict=True))]  # fmt: skip
    assert not analysis.passes(lost, tmpl, 0.5, replicas=200)["passes"]
    found = analysis.draw1_by_cut(analysis._template_ev, (0.61, 0.30), replicas=300)
    by_cut = {r["draw1_cut_14"]: r for r in found}
    assert not by_cut[0.61]["passes"] and not by_cut[0.61]["count_guard"]
    assert by_cut[0.30]["passes"]


def test_the_hand_stratums_own_verdict_is_not_required():
    rows = _synthetic(0)
    for row in rows:  # one balanced exchange on the hand-written pages
        if row["id"] == "h0":
            row["p_13r"] = 0.05
        if row["id"] == "h20":
            row["p_14"] = 0.95
    result = analysis.analyse(rows, launch="complete")
    assert result["hand_stratum"]["count_guard"]
    assert "hand stratum no peor or mejora" not in result["checks"]
