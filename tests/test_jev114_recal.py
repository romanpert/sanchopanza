"""The Jev 1.14 threshold recalibration (docs/results/2026-10-15-jev114-recal/), replayed free.

Pins the sealed registration, the rules, every cut and every verdict the README reports.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "results" / "2026-10-15-jev114-recal"
SCRIPT = ROOT / "benchmarks" / "jev114" / "jev114_recal.py"


def _load():
    spec = importlib.util.spec_from_file_location("jev114_recal", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["jev114_recal"] = module
    spec.loader.exec_module(module)
    return module


recal = _load()


@pytest.fixture(scope="module")
def report():
    if not (OUT / "done-scored.jsonl").exists():
        pytest.skip("check_done scores not present")
    return recal.analyse()


def test_the_registration_is_the_sealed_one():
    digest = hashlib.sha256((OUT / "prereg.md").read_bytes()).hexdigest()
    assert digest == "4ae33222dfcfd2ec8bff2cb8cdd1c0028a901d99159efdddbda7d922cd0d2351"
    assert (OUT / "prereg.sha256").read_text(encoding="utf-8").startswith(digest)


def test_rule_t_matches_the_action_rate_and_reads_no_label():
    def item(ident, p13, p14, y):
        return {"id": ident, "y": y, "p": {"13r": p13, "14": p14}}

    cal = [item("a", 0.9, 0.62, True), item("b", 0.75, 0.55, False), item("c", 0.2, 0.1, True)]
    assert recal.transfer(cal, "goal_met") == 0.55  # 13r acts on 2 at 0.70; 14 on 2 up to 0.55
    flipped = [{**i, "y": not i["y"]} for i in cal]
    assert recal.transfer(flipped, "goal_met") == 0.55
    none = [item("a", 0.1, 0.9, True)]
    assert recal.transfer(none, "goal_met") == 0.70  # 13r acts on nothing: the cut stays


def test_rule_t_for_a_low_cut_is_the_lowest_that_acts_as_often():
    cal = [{"id": str(k), "y": True, "p": {"13r": p13, "14": p14}}
           for k, (p13, p14) in enumerate([(0.2, 0.05), (0.24, 0.12), (0.4, 0.3)])]  # fmt: skip
    assert recal.transfer(cal, "extract_gate") == 0.12


def test_errata_halves_are_split_by_task():
    assert recal.errata_half("x") == recal.errata_half("x")
    assert {recal.errata_half(t) for t in ("a", "b", "c", "d", "e", "f")} == {0, 1}


def test_the_derivations_on_record_reproduce_on_113(report):
    points = report["points"]
    assert points["redundant_page"]["cut_13r_rederived"] == 0.59
    assert points["memory_write"]["cut_13r_rederived"] == 0.54


def test_the_cuts(report):
    cuts = {p: (o["shipped"], o["cut_14"]) for p, o in report["points"].items()}
    assert cuts == {
        "redundant_page": (0.59, 0.61),
        "memory_write": (0.54, None),
        "goal_met": (0.70, 0.57),
        "repeats_check": (0.70, 0.60),
        "extract_gate": (0.25, 0.27),
        "recall": (0.25, 0.10),
        "check_done": (0.5, 0.30),
        "holistic": (0.83, 0.90),
    }
    assert report["profile"] == {"adds_nothing": 0.61, "goal_met": 0.57, "repeats_check": 0.6,
                                 "extract_skip": 0.27, "recall_skip": 0.1, "done": 0.3,
                                 "holistic": 0.9}  # fmt: skip


def test_the_verdicts_on_the_evaluation_parts(report):
    got = {p: (o["test"]["n"], o["test"]["base"], o["test"]["new"], o["test"]["verdict"])
           for p, o in report["points"].items()}  # fmt: skip
    assert got == {
        "redundant_page": (50, 47, 45, "no concluyente"),
        "memory_write": (157, 113, 115, "no concluyente"),
        "goal_met": (14, 12, 14, "no peor"),
        "repeats_check": (12, 12, 12, "no peor"),
        "extract_gate": (16, 15, 16, "no peor"),
        "recall": (14, 14, 14, "no peor"),
        "check_done": (329, 313, 312, "no peor"),
        "holistic": (54, 30, 28, "no concluyente"),
    }
    pooled = report["pooled_all"]
    assert (pooled["n"], pooled["base"], pooled["new"], pooled["verdict"]) == (
        646, 556, 556, "no peor")  # fmt: skip
    assert (pooled["only_new"], pooled["only_base"]) == (13, 13)
    l1 = report["pooled_l1"]
    assert (l1["n"], l1["base"], l1["new"], l1["verdict"]) == (263, 213, 216, "no peor")
    assert not any(o["test"]["verdict"] == "peor" for o in report["points"].values())


def test_the_costly_acts(report):
    ev = {p: (o["ev"]["13r_shipped"]["costly"], o["ev"]["14_profile"]["costly"],
              o["ev"]["14_shipped"]["costly"]) for p, o in report["points"].items()}  # fmt: skip
    assert ev["check_done"] == (7, 8, 15)
    assert ev["memory_write"] == (2, 4, 4)
    assert ev["holistic"] == (3, 3, 7)
    assert ev["redundant_page"] == (0, 0, 0)


def test_the_cross_validation_is_descriptive_and_pinned(report):
    keys = ("13r_shipped", "14_profile_rule_mean", "13r_same_rule_mean")
    cv = {p: tuple(o["cv"][k] for k in keys) for p, o in report["points"].items() if "cv" in o}
    assert cv == {
        "redundant_page": (115, 122.8, 122.8),
        "memory_write": (156, 155.2, 161.6),
        "goal_met": (46, 45.4, 46.0),
        "repeats_check": (50, 48.8, 50.0),
        "extract_gate": (45, 44.0, 45.0),
        "recall": (50, 48.8, 50.0),
    }


def test_the_published_analysis_is_this_one(report):
    published = json.loads((OUT / "analysis.json").read_text(encoding="utf-8"))
    assert published == json.loads(json.dumps(report))
