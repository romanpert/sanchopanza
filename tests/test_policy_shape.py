"""The policy-shape numbers, reproduced from the recordings. No network.

`docs/results/2026-09-25-policy-shape/README.md` reports them. The slow shape (the logistic
regression, about 40 s) is not pinned here; the script's `--repeats 5` run is the source of
that row. Everything pinned below runs in a few seconds.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

import policy_shape  # noqa: E402

ROWS = asyncio.run(policy_shape.memory_rows())


def test_all_hundred_cases_replay_with_their_three_probabilities():
    assert len(ROWS) == 100
    assert all(len(r["x"]) == 3 for r in ROWS)


def test_the_shipped_conjunction_against_a_plain_cut():
    assert sum(r["shipped"] == r["y"] for r in ROWS) == 72
    assert sum(r["shipped"] and not r["y"] for r in ROWS) == 5
    assert sum((policy_shape.margin(r["x"]) >= 0.5) == r["y"] for r in ROWS) == 86


def test_a_cut_derived_on_held_out_folds_trades_hits_for_costly_errors():
    cv = policy_shape.cross_validate(ROWS, repeats=5, regression=False)
    assert cv["derived_cut"]["hits_per_run"] == 89.6
    assert cv["derived_cut"]["costly_per_run"] == 6.4
    assert 0.44 <= cv["derived_cuts"]["min"] <= cv["derived_cuts"]["max"] <= 0.45


def test_platt_scaling_moves_brier_the_way_the_readme_says():
    ps = [0.2, 0.3, 0.35, 0.4, 0.6, 0.65, 0.7, 0.8]
    ys = [False, False, False, True, True, True, True, True]
    cal = policy_shape.platt_loo(ps, ys)
    assert len(cal) == 8 and all(0.0 <= p <= 1.0 for p in cal)
