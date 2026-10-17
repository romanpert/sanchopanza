"""Lot longdoc-free's statistics (benchmarks/longdoc_free/stats.py): the router from per-arm rows,
the bootstrap by novel, the dev cut and the fixed sequence. Pure, no model."""

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


stats = _load("lf_stats", "benchmarks/longdoc_free/stats.py")


def _row(i: int, novel: str, n: float, h: float, p: float | None, h0: float = 0.5) -> dict:
    return {"id": i, "novel": novel, "p": p, "f1": {"N": n, "H": h, "H0": h0},
            "cost": {"N": 0.10, "H": 0.03, "H0": 0.05, "J": 0.02}}  # fmt: skip


def test_the_router_answers_with_haiku_only_where_the_gate_reaches_the_cut():
    hi, lo, none = (
        _row(0, "a", 1.0, 0.0, 0.9),
        _row(1, "a", 1.0, 0.0, 0.4),
        _row(2, "a", 1, 0, None),
    )
    assert stats.router_f1(hi, 0.8) == 0.0 and stats.router_f1(lo, 0.8) == 1.0
    assert stats.router_f1(none, 0.0) == 1.0  # no usable answer from Jev: not covered
    assert stats.router_cost(hi, 0.8) == pytest.approx(0.05)
    assert stats.router_cost(lo, 0.8) == pytest.approx(0.12)


def test_saving_and_coverage():
    rows = [_row(i, "a", 1, 1, 0.9 if i < 5 else 0.1) for i in range(10)]
    assert stats.coverage(rows, 0.8) == 0.5
    # cost_R = 0.02 + (0.03 or 0.10): 5 * 0.05 + 5 * 0.12 = 0.85 against 1.00
    assert stats.saving(0.8)(rows) == pytest.approx(0.15)


def test_the_bootstrap_resamples_whole_novels():
    rows = [_row(i, f"n{i // 5}", 1.0, 1.0 if i // 5 % 2 else 0.0, 0.9) for i in range(40)]
    h_minus_n = stats.mean_diff(lambda r: r["f1"]["H"], lambda r: r["f1"]["N"])
    interval = stats.bootstrap(rows, h_minus_n, draws=2000)
    assert interval.clusters == 8
    assert interval.estimate == pytest.approx(-50.0)
    # each draw takes novels whole, so a draw's mean is a multiple of 100/8 points
    assert (interval.low / 12.5) == pytest.approx(round(interval.low / 12.5))


def test_the_dev_cut_is_the_lowest_whose_covered_items_hold_within_two_points():
    # 30 questions: 4 at p 0.65 where Haiku loses everything, 10 at 0.85 that tie, 16 under
    rows = ([_row(i, f"n{i}", 1.0, 0.0, 0.65) for i in range(4)]
            + [_row(i, f"n{i}", 1.0, 1.0, 0.85) for i in range(4, 14)]
            + [_row(i, f"n{i}", 1.0, 1.0, 0.1) for i in range(14, 30)])  # fmt: skip
    # at 0.5 and 0.6 the covered lose 400/14 points; at 0.7 and 0.8 they tie, 10 of 30 covered
    assert stats.dev_cut(rows) == 0.7
    assert stats.dev_cut([_row(0, "a", 1.0, 0.0, 0.99)]) is None


def test_a_cut_that_covers_too_little_is_no_cut():
    """The review's probe: 1 of 41 covered and tied set the cut at 0.5 before the rule."""
    rows = [_row(0, "n0", 0.6, 0.6, 0.95)] + [_row(i, f"n{i}", 0.6, 0.6, 0.1) for i in range(1, 41)]
    assert stats.dev_cut(rows) is None
    few = [_row(i, f"n{i}", 0.6, 0.6, 0.95) for i in range(7)]  # 100 % covered but 7 questions
    assert stats.dev_cut(few) is None


def _confirm(h_gap: float, coverage: float, n_novels: int = 40, per: int = 5) -> list[dict]:
    rows = []
    for i in range(n_novels * per):
        p = 0.9 if (i % 10) < coverage * 10 else 0.1
        rows.append(_row(i, f"n{i // per}", 0.6, 0.6 + h_gap, p))
    return rows


def test_a_tie_passes_both_hypotheses_and_substitutes():
    v = stats.verdict(_confirm(0.0, 0.5), 0.8, draws=500)
    assert v.router_passes and v.haiku_passes and v.substitutes
    assert v.coverage == 0.5 and v.saving.low > 0


def test_haiku_is_not_read_when_the_router_fails():
    v = stats.verdict(_confirm(-0.3, 1.0), 0.8, draws=500)
    assert not v.router_passes and v.haiku is None and v.haiku_passes is None
    assert not v.substitutes


def test_low_coverage_passes_the_router_but_does_not_substitute():
    v = stats.verdict(_confirm(0.0, 0.1), 0.8, draws=500)
    assert v.router_passes and v.coverage == pytest.approx(0.1) and not v.substitutes


def test_secondaries_carry_attribution_against_h0():
    s = stats.secondary(_confirm(0.0, 0.5), 0.8, draws=200)
    assert s["H_minus_H0"].estimate == pytest.approx(10.0)
    assert s["mean_f1"]["N"] == pytest.approx(60.0)
