"""Lot lbo8's plan (benchmarks/jev114/lbo8.py, a draft: nothing sealed, nothing paid): the fresh
pool, the descriptive cut table from lb162/lb162x's recordings, Tango's paired score interval,
the power of the confirmation and its money rule. No network, no session."""

from __future__ import annotations

import importlib.util
import math
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


lbo8 = _load("lbo8", "benchmarks/jev114/lbo8.py")


# ---- the fresh pool ------------------------------------------------------------------------------


def _row(i: str, domain: str = "Single-Document QA", chars: int = 60_000) -> dict:
    return {"_id": i, "domain": domain, "context": "x" * chars}


def test_fresh_qa_is_the_qa_domains_outside_every_used_id_at_any_length():
    rows = [_row("a"), _row("b", chars=300_000), _row("c", "Multi-Document QA"),
            _row("d", "Code Repository Understanding"), _row("e")]  # fmt: skip
    assert lbo8.fresh_qa(rows, used={"e"}) == ["a", "b", "c"]


def test_the_frozen_ids_do_not_overlap_any_earlier_lot():
    ids = lbo8.read_ids(lbo8.IDS_FILE)
    assert len(ids) == len(set(ids)) == lbo8.N_TASKS
    lb162_ids = set(lbo8.read_ids(ROOT / "docs/results/2026-10-15-lb162/ids.txt"))
    dev = set(lbo8.read_ids(ROOT / "benchmarks/h2h/longdoc-dev-ids.txt"))
    assert not set(ids) & lb162_ids
    assert not set(ids) & dev


# ---- the descriptive table (lb162 + lb162x recordings) ------------------------------------------


def test_the_cut_table_gives_lb162x_published_readings():
    by_cut = {r["cut"]: r for r in lbo8.cut_table(lbo8.recorded(), (0.6, 0.8))}
    six, eight = by_cut[0.6], by_cut[0.8]
    assert (six["covered"], six["jev_right"], six["opus_right"]) == (60, 31, 37)
    assert six["hybrid_minus_opus_pts"] == pytest.approx(-3.70, abs=0.01)
    assert six["net_saving_usd"] == pytest.approx(5.353, abs=0.001)
    assert six["net_saving_share"] == pytest.approx(0.295, abs=0.001)
    assert (eight["covered"], eight["jev_right"], eight["opus_right"]) == (27, 17, 18)
    assert (eight["jev_only"], eight["opus_only"]) == (0, 1)
    assert eight["hybrid_minus_opus_pts"] == pytest.approx(-0.62, abs=0.01)
    assert eight["opus_avoided_usd"] == pytest.approx(2.806, abs=0.001)
    assert eight["net_saving_usd"] == pytest.approx(1.932, abs=0.001)


# ---- Tango's score interval for a paired difference ---------------------------------------------


@pytest.mark.parametrize(
    ("b", "c", "n", "delta"),
    [(3, 7, 60, -0.05), (0, 1, 27, -0.1), (5, 0, 40, 0.08), (0, 0, 78, -0.03)],
)
def test_tangos_nuisance_is_the_constrained_maximum_likelihood(b, c, n, delta):
    """p21 maximizes the multinomial likelihood under p12 - p21 = delta (a grid check)."""

    def loglik(p21: float) -> float:
        p12 = p21 + delta
        rest = 1 - p12 - p21
        if min(p12, p21, rest) <= 0:
            return -math.inf
        return b * math.log(p12) + c * math.log(p21) + (n - b - c) * math.log(rest)

    lo = max(0.0, -delta)
    grid = [lo + (1 - abs(delta)) * k / 200_000 for k in range(1, 100_000)]
    best = max(grid, key=loglik)
    assert lbo8.tango_p21(b, c, n, delta) == pytest.approx(best, abs=1e-4)


def test_no_discordant_pair_still_leaves_the_closed_form_width():
    n, z = 78, lbo8.Z
    delta, lo, hi = lbo8.tango_ci(0, 0, n)
    assert delta == 0.0
    assert lo == pytest.approx(-(z**2) / (n + z**2), abs=1e-6)
    assert hi == pytest.approx(z**2 / (n + z**2), abs=1e-6)


def test_the_bounds_solve_the_score_equation_and_hold_the_estimate():
    delta, lo, hi = lbo8.tango_ci(4, 10, 162)
    assert delta == pytest.approx(-6 / 162)
    assert lo < delta < hi
    assert lbo8.tango_z(4, 10, 162, lo) == pytest.approx(lbo8.Z, abs=1e-6)
    assert lbo8.tango_z(4, 10, 162, hi) == pytest.approx(-lbo8.Z, abs=1e-6)


def test_more_tasks_narrow_the_interval():
    narrow = lbo8.tango_ci(2, 4, 300)
    wide = lbo8.tango_ci(1, 2, 150)
    assert narrow[2] - narrow[1] < wide[2] - wide[1]


def test_the_verdict_reads_the_lower_and_upper_bounds_against_the_margin():
    assert lbo8.verdict(-0.04, 0.01, margin=-0.05) == "no peor"
    assert lbo8.verdict(-0.09, -0.06, margin=-0.05) == "peor"
    assert lbo8.verdict(-0.06, 0.01, margin=-0.05) == "no concluyente"


# ---- power and money -----------------------------------------------------------------------------


def test_a_margin_inside_the_zero_discordance_floor_can_never_pass():
    floor = lbo8.Z**2 / (78 + lbo8.Z**2)
    tight = lbo8.power(78, coverage=0.2, jev_only=0.0, opus_only=0.0, margin=-(floor - 0.005))
    loose = lbo8.power(78, coverage=0.2, jev_only=0.0, opus_only=0.0, margin=-(floor + 0.005))
    assert tight == 0.0
    assert loose == 1.0


def test_power_grows_with_the_tasks():
    small = lbo8.power(78, coverage=0.2, jev_only=0.04, opus_only=0.08, margin=-0.07, draws=400)
    large = lbo8.power(281, coverage=0.2, jev_only=0.04, opus_only=0.08, margin=-0.07, draws=400)
    assert small < large


def test_the_money_rule_runs_every_session_at_the_expected_cost_and_stays_under_the_ceiling():
    phase = lbo8.PHASE_O
    lb162x = lbo8.lb162x
    assert lb162x.at_mean(phase, lbo8.OPUS_EST_USD * 1.6, phase.n) == phase.n
    assert lb162x.guaranteed(phase) >= 1
    spent, cap = 0.0, lb162x.cap_for(0.0, phase)
    while cap is not None:  # every session at its cap plus one worst turn
        spent += cap + phase.worst_turn
        assert spent <= phase.ceiling + 1e-9
        cap = lb162x.cap_for(spent, phase)
