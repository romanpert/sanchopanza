"""Lot longdoc-free's dev reading (benchmarks/longdoc_free/dev_read.py): stats rows from the
public rows, the cut, n for the confirmation, the money. Pure."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dr = _load("lf_dev_read", "benchmarks/longdoc_free/dev_read.py")


def _jev(n: int = 40, per: int = 5, p_hi: float = 0.9) -> list[dict]:
    return [{"id": i, "novel": f"n{i // per}", "p": p_hi if i % 2 else 0.2, "kept_chars": 9,
             "empty": False, "gold_in_kept": bool(i % 3)} for i in range(n)]  # fmt: skip


def _sessions(n: int = 40, h_gap: float = 0.0) -> list[dict]:
    out = []
    for i in range(n):
        for arm, f1, usd in (("N", 0.6, 0.10), ("H", 0.6 + h_gap, 0.03), ("H0", 0.5, 0.05),
                             ("HC", 0.1, 0.005)):  # fmt: skip
            out.append({"id": i, "variant": arm, "f1": f1 + (0.1 if i % 4 == 0 else 0.0),
                        "usd": usd, "answer_words": 2, "has_answer_line": True,
                        "no_answer": False, "hit_cap": False})  # fmt: skip
    return out


def test_stats_rows_need_every_arm_and_share_jevs_spend():
    sessions = [s for s in _sessions() if not (s["id"] == 3 and s["variant"] == "H0")]
    rows = dr.stats_rows(_jev(), sessions, jev_spent=0.80)
    assert len(rows) == 39 and all(r["cost"]["J"] == pytest.approx(0.02) for r in rows)
    assert set(rows[0]["f1"]) == {"N", "H", "H0"}


def test_a_tie_sets_a_cut_and_a_confirmation_that_fits():
    got = dr.read(_jev(), _sessions(), jev_spent=0.4, jev_pessimistic=1.44)
    assert got["cut"] == 0.5 and got["complete"] == 40
    assert got["seal_confirmation"] and got["n_needed"] <= dr.CONFIRM_ITEMS
    assert got["jev"]["settled_over_pessimistic"] == pytest.approx(0.4 / 1.44, abs=1e-4)
    assert got["money"]["N"]["mean_usd"] == pytest.approx(0.10)
    assert got["answers"]["HC"]["mean_f1"] < got["answers"]["N"]["mean_f1"]


def test_a_haiku_that_loses_on_the_covered_questions_sets_no_cut():
    got = dr.read(_jev(), _sessions(h_gap=-0.3), jev_spent=0.4, jev_pessimistic=1.44)
    assert got["cut"] is None and not got["seal_confirmation"] and "not confirmed" in got["why"]


def test_n_grows_with_the_design_effect_and_a_dev_gain_is_not_banked():
    assert dr.n_needed(30.0, 2.0, 0.0) == 2 * dr.n_needed(30.0, 1.0, 0.0) or (
        abs(dr.n_needed(30.0, 2.0, 0.0) - 2 * dr.n_needed(30.0, 1.0, 0.0)) <= 1
    )
    assert dr.n_needed(30.0, 1.0, 4.0) == dr.n_needed(30.0, 1.0, 0.0)
    assert dr.n_needed(30.0, 1.0, -5.0) == 10**9  # at the margin: no n gives power


def test_the_design_effect_is_at_least_one_and_sees_clusters():
    rows = [{"novel": f"n{i // 5}", "x": float(i // 5)} for i in range(40)]
    assert dr.design_effect(rows, lambda r: r["x"]) > 3
    flat = [{"novel": f"n{i // 5}", "x": float(i % 2)} for i in range(40)]
    assert dr.design_effect(flat, lambda r: r["x"]) >= 1.0
