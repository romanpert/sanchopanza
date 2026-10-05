"""The offline cut analysis of free sessions: matching the gold, and where each rule stops a
session and what that saves or loses. No model, no transcript, no money."""

from __future__ import annotations

import importlib.util
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "browse_free_cut", ROOT / "benchmarks/browse/free_cut.py"
)
cut = importlib.util.module_from_spec(spec)
sys.modules["browse_free_cut"] = cut
spec.loader.exec_module(cut)


def view(traj, success=False, cap=1.0, searches=None, others=None, seen=None, jev=None):
    n = len(traj)
    return {
        "traj": traj,
        "cap": cap,
        "success": success,
        "searches": searches or [1] * n,
        "others": others or [0] * n,
        "gold_seen": seen or [False] * n,
        "jev": jev,
    }


def test_matcher_numbers_within_one_percent_and_names_as_substrings():
    m = cut.matcher("14.2")
    assert m("the mean was 14.25 percent") and not m("the mean was 15")
    n = cut.matcher("Glass Onion: A Knives Out Mystery")
    assert n("I think it is glass onion  a knives out mystery, 2022")
    assert not n("Knives Out")
    assert not cut.matcher("")("anything")


def test_cumulative_and_carry():
    assert cut.cumulative([False, True, False]) == [False, True, True]
    assert cut.carry([None, 0.2, None, 0.9, None]) == [None, 0.2, 0.2, 0.9, 0.9]


def test_budget_stops_at_the_first_call_over_its_share_and_never_on_the_last():
    v = view([0.1, 0.3, 0.6, 0.9])
    assert cut.cut_at(v, "budget", f=0.5) == 2
    assert cut.cut_at(v, "budget", f=0.95) is None
    assert cut.cut_at(view([0.6]), "budget", f=0.5) is None


def test_oracle_waits_while_the_gold_has_reached_the_agent():
    v = view([0.1, 0.6, 0.7, 0.9], seen=[False, True, True, True])
    assert cut.cut_at(v, "oracle", f=0.5) is None
    v = view([0.1, 0.6, 0.7, 0.9], seen=[False, False, True, True])
    assert cut.cut_at(v, "oracle", f=0.5) == 1


def test_jev_rules():
    v = view([0.1, 0.6, 0.7, 0.8, 0.9], jev=[0.05, 0.6, 0.1, 0.1, 0.1])
    assert cut.cut_at(v, "jev_none", f=0.5, t=0.5) is None  # it once reached 0.6
    assert cut.cut_at(v, "jev_now", f=0.5, t=0.5) == 2
    assert cut.cut_at(view([0.1, 0.6, 0.7], jev=None), "jev_now", f=0.5, t=0.5) is None


def test_streak_counts_searches_with_nothing_else_between():
    v = view([0.1] * 6, searches=[1, 1, 0, 1, 2, 1], others=[0, 0, 1, 0, 0, 0])
    assert cut.cut_at(v, "streak", n=3) == 4
    assert cut.cut_at(v, "streak", n=5) is None


def test_streak_jev_restarts_at_a_judged_candidate():
    v = view([0.1] * 6, searches=[1, 1, 1, 1, 1, 1], jev=[0.0, 0.9, 0.0, 0.0, 0.0, 0.0])
    assert cut.cut_at(v, "streak_jev", n=3, t=0.5) == 4
    assert cut.cut_at(v, "streak_jev", n=2, t=0.5) == 3


def test_evaluate_counts_savings_on_wrong_and_answers_lost_on_right():
    wrong = view([0.2, 0.6, 1.0])
    right = view([0.2, 0.55, 0.7], success=True)
    early_right = view([0.2, 0.4], success=True)
    out = cut.evaluate([wrong, right, early_right], "budget", f=0.5)
    assert out["wrong_cut"] == "1/1"
    assert out["usd_saved_on_wrong"] == pytest.approx(0.4)
    assert out["share_of_wrong_spend_saved"] == pytest.approx(0.4)
    assert out["right_cut_answers_lost"] == "1/2"
    assert out["usd_saved_on_right"] == pytest.approx(0.15)


def test_best_picks_the_largest_saving_at_each_loss_and_can_leave_the_oracle_out():
    rows = [
        {"rule": "oracle", "_lost": 0, "_saved": 9.0},
        {"rule": "budget", "_lost": 0, "_saved": 1.0},
        {"rule": "streak", "_lost": 0, "_saved": 2.0},
        {"rule": "budget", "_lost": 1, "_saved": 5.0},
    ]
    live = cut.best(rows, live=True)
    assert [r["rule"] for r in live] == ["streak", "budget"]
    assert cut.best(rows, live=False)[0]["rule"] == "oracle"
    assert all(not k.startswith("_") for r in live for k in r)
