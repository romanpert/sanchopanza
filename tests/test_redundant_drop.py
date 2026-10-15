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
    assert runner.LOT.batch_cap <= 0.10


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
    result = analysis.analyse(_draw1_rows())
    assert result["cuts"]["14_derived"] == 0.61
    assert result["evaluation"]["hand_written"]["n"] == 50
    assert result["decision"]["propose_adds_nothing_14"] is None
