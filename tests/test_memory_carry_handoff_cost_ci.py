"""F2's descriptive cost intervals (`benchmarks/memory_carry/handoff_cost_ci.py`): the bootstrap
resamples the same paired ratios F2's table takes the median of."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
F2 = ROOT / "docs" / "results" / "2026-10-16-memory-f2"
ci = bench_module(ROOT / "benchmarks" / "memory_carry", "handoff_cost_ci")


def test_bootstrap_is_seeded_and_brackets_the_median() -> None:
    values = [1.0, 1.1, 1.2, 1.3, 1.4, 0.9, 1.25]
    a = ci.bootstrap_median(values, draws=500)
    assert a == ci.bootstrap_median(values, draws=500)
    lo, hi = a["ci95"]
    assert lo <= a["median"] == 1.2 <= hi
    with pytest.raises(ValueError):
        ci.bootstrap_median([])


def test_published_rows_give_the_table_s_medians() -> None:
    got = ci.intervals(F2)
    for model in ci.MODELS:
        table = json.loads((F2 / f"f2-{model}-table.json").read_text(encoding="utf-8"))
        for key, value in table["cost_ratio_median"].items():
            assert got[model][key]["median"] == pytest.approx(value, abs=1e-6)
            assert got[model][key]["triples"] == table["triples"]
    # Sonnet 5.5, as published: S/N0 above 1 across the interval, S/H below 1.
    assert got["sonnet"]["S/N0"]["ci95"][0] > 1
    assert got["sonnet"]["S/H"]["ci95"][1] < 1
