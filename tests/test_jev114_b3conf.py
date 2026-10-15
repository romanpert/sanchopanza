"""The B3 0.6 confirmation's power analysis (docs/results/2026-10-15-jev114-b3conf), free."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "b3conf_power", ROOT / "benchmarks" / "jev114" / "b3conf_power.py"
)
mod = importlib.util.module_from_spec(_SPEC)
sys.modules["b3conf_power"] = mod
_SPEC.loader.exec_module(mod)


def _row(covered: bool, jev_ok: bool, sonnet_ok: bool) -> object:
    return mod.Row(covered=covered, jev_ok=jev_ok, sonnet_ok=sonnet_ok, sonnet_usd=0.1, jev_usd=0.0)


def test_l6_counts_at_the_cut_match_the_published_sweep() -> None:
    d = mod.describe(mod.load())
    assert d["tasks"] == 50
    assert d["covered"] == 27  # 54 % coverage at 0.6 in L6's sweep
    assert d["jev_right_covered"] == 17
    assert d["sonnet_right_covered"] == 17
    assert d["discordant_covered"] == 8
    assert mod.sonnet_mean(mod.load()) == 0.62


def test_paired_gain_only_counts_covered_tasks() -> None:
    sample = [_row(True, True, False), _row(False, False, True), _row(True, False, False)] * 4
    d, lo, hi = mod.paired_ci(sample)
    assert d == 1 / 3
    assert lo < d < hi


def test_jev_only_ci_adds_the_reference_variance() -> None:
    sample = [_row(True, True, False), _row(True, False, False), _row(False, False, False)] * 10
    _, lo_small, hi_small = mod.jev_only_ci(sample, 0.6, 50)
    _, lo_big, hi_big = mod.jev_only_ci(sample, 0.6, 5000)
    assert hi_small - lo_small > hi_big - lo_big


def test_fifty_fresh_tasks_rarely_decide_at_the_two_point_margin() -> None:
    rows = mod.load()
    for design in (lambda s: mod.jev_only_ci(s, mod.sonnet_mean(rows), len(rows)), mod.paired_ci):
        got = mod.power(rows, design, 50, -0.02, reps=1000)
        assert got["no_peor"] + got["peor"] < 0.15
        assert got["half_width"] > 0.10


def test_paired_tasks_needed_exceed_longbench() -> None:
    assert mod.n_for_power(mod.load(), 0.0, -0.02) > 503
