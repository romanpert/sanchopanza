"""D replay (benchmarks/h2h/d_replay.py): the pure parts, no data, no Jev."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "h2h"))
spec = importlib.util.spec_from_file_location("h2h_d_replay", ROOT / "benchmarks/h2h/d_replay.py")
d = importlib.util.module_from_spec(spec)
sys.modules["h2h_d_replay"] = d
spec.loader.exec_module(d)


def _s(task, group, docs, arm="SONNET-SP"):
    return {"task": task, "arm": arm, "group": group, "docs": docs}


def test_chosen_takes_every_wrong_session_with_gold_and_fixed_samples(monkeypatch):
    monkeypatch.setattr(d, "SAMPLE", {"right_with_gold": 2, "wrong_never": 1})
    pool = [_s("w1", "wrong_with_gold", []), _s("w2", "wrong_with_gold", [])]
    pool += [_s(f"r{i}", "right_with_gold", []) for i in range(5)]
    pool += [_s(f"n{i}", "wrong_never", []) for i in range(3)]
    first, again = d.chosen(pool), d.chosen(list(reversed(pool)))
    assert [s["task"] for s in first] == [s["task"] for s in again]  # fixed by seed, not order
    groups = [s["group"] for s in first]
    assert groups.count("wrong_with_gold") == 2 and groups.count("right_with_gold") == 2
    assert groups.count("wrong_never") == 1


def test_pairs_are_unique_per_query_and_document():
    picked = [_s("q1", "x", ["a", "b"]), _s("q1", "x", ["b", "c"], arm="SONNET-CC"),
              _s("q2", "x", ["a"])]  # fmt: skip
    assert d.pairs(picked) == [("q1", "a"), ("q1", "b"), ("q1", "c"), ("q2", "a")]


def test_auc():
    assert d.auc([0.9, 0.8], [0.1, 0.2]) == 1.0
    assert d.auc([0.5], [0.5]) == 0.5
    assert d.auc([], [0.1]) is None


def test_report_counts_sessions_whose_gold_is_flagged_and_their_false_flags():
    picked = [_s("q1", "wrong_with_gold", ["g", "x", "y"]), _s("q2", "wrong_never", ["z"])]
    decided = {
        ("q1", "g"): {"gold": True, "evidence": True, "p": 0.85},
        ("q1", "x"): {"gold": False, "evidence": False, "p": 0.9},
        ("q1", "y"): {"gold": False, "evidence": False, "p": 0.1},
        ("q2", "z"): {"gold": False, "evidence": False, "p": 0.75},
    }
    out = d.report(picked, decided)
    wrong = out["groups"]["wrong_with_gold"]["by_cut"]
    assert wrong["0.8"]["sessions_gold_flagged"] == 1 and wrong["0.8"]["false_flags_mean"] == 1
    assert wrong["0.9"]["sessions_gold_flagged"] == 0
    assert out["groups"]["wrong_never"]["by_cut"]["0.7"]["false_flags_mean"] == 1
    assert out["auc_gold_vs_rest"] == 0.667
