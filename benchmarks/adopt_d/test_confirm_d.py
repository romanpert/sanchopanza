"""Free tests of phase D's verdicts on fixed numbers (no session, no Docker, no spend):

Run: .venv/Scripts/python.exe -m pytest benchmarks/adopt_d/test_confirm_d.py -q
"""

from __future__ import annotations

import json
import sys
from fractions import Fraction
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import confirm_d  # noqa: E402
import run_d  # noqa: E402


def pair(res_n: int, res_s: int, cost_n: float = 1.0, cost_s: float = 1.0, turns_n: int = 10,
         turns_s: int = 10, find: int = 0) -> dict:  # fmt: skip
    n = {"why": "", "resolved": res_n, "cost": cost_n, "turns": turns_n, "jev": 0.0, "find": 0,
         "tool_search": 0, "skill": 0}  # fmt: skip
    s = {**n, "resolved": res_s, "cost": cost_s, "turns": turns_s, "find": find}
    return {"N": n, "S": s, "complete": True}


def item(name: str, pairs: list[dict], stratum: str = "general-easy") -> dict:
    reps = [{"rep": k, **p} for k, p in enumerate(pairs, start=1)]
    return confirm_d.summarize({"instance": name, "stratum": stratum, "reps": reps})


def missing(name: str) -> dict:
    gone = {"why": "no row"}
    return item(name, [{"N": gone, "S": gone, "complete": False}])


# ---- the bootstrap -------------------------------------------------------------------------------


def test_percentiles_by_index() -> None:
    draws = list(range(10_000))
    assert confirm_d.lower_bound(draws) == 500  # the 5th percentile, one-sided
    assert confirm_d.interval(draws) == (250, 9749)  # as confirm.paired_interval


def test_bootstrap_is_seeded_and_constant_items_give_a_point() -> None:
    assert confirm_d.SEED == 20261004 and confirm_d.RESAMPLES == 10_000
    draws = confirm_d.resample([Fraction(1, 3)] * 26, confirm_d.mean)
    assert len(draws) == 10_000 and set(draws) == {Fraction(1, 3)}
    mixed = [0.0, 1.0] * 13
    assert confirm_d.resample(mixed, confirm_d.mean) == confirm_d.resample(mixed, confirm_d.mean)


def test_bootstrap_on_two_values_stays_in_its_lattice() -> None:
    """A resample of 26 zeros and ones has a mean of k/26: every draw is one of those, and the
    5th percentile of a mean of 1/2 sits below it."""
    draws = confirm_d.resample([Fraction(0), Fraction(1)] * 13, confirm_d.mean)
    assert all((d * 26).denominator == 1 for d in draws)
    assert confirm_d.lower_bound(draws) < Fraction(1, 2) < confirm_d.interval(draws)[1]


# ---- H1 ------------------------------------------------------------------------------------------


def test_h1_holds_when_the_arms_resolve_alike() -> None:
    table = [item(f"i{k}", [pair(k % 2, k % 2)] * 3) for k in range(26)]
    out = confirm_d.h1(table)
    assert out["difference"] == 0.0 and out["lower_bound_5pct"] == 0.0 and out["holds"] is True


def test_h1_does_not_hold_when_s_loses_one_in_three_everywhere() -> None:
    table = [item(f"i{k}", [pair(1, 1), pair(1, 1), pair(1, 0)]) for k in range(26)]
    out = confirm_d.h1(table)
    assert out["difference"] == round(-1 / 3, 4) and out["holds"] is False


def test_h1_margin_is_inclusive() -> None:
    """Two instances lose a whole instance each (-1), the rest are equal: D = -2/26 exactly;
    a resample with neither loser has D = 0 and one with three has -3/26."""
    table = [item(f"i{k}", [pair(1, 0)] * 3) for k in range(2)]
    table += [item(f"j{k}", [pair(1, 1)] * 3) for k in range(24)]
    out = confirm_d.h1(table)
    assert out["difference"] == round(-2 / 26, 4)
    draws = confirm_d.resample([t["res_S"] - t["res_N"] for t in table], confirm_d.mean)
    assert out["holds"] is (confirm_d.lower_bound(draws) >= -Fraction(2, 26))
    assert Fraction(-2, 26) >= -confirm_d.MARGIN  # at the margin: holds


def test_h1_is_undecided_while_an_instance_has_no_complete_pair() -> None:
    table = [item(f"i{k}", [pair(1, 1)] * 3) for k in range(25)] + [missing("gone")]
    out = confirm_d.h1(table)
    assert out["holds"] is None and out["missing"] == ["gone"]
    assert out["instances"] == 25


def test_res_is_a_mean_over_complete_pairs_only() -> None:
    gone = {"why": "not the treatment: (g) deferred"}
    one = item("i", [pair(1, 0), {"N": pair(1, 1)["N"], "S": gone, "complete": False},
                     pair(0, 0)])  # fmt: skip
    assert one["pairs"] == 2 and one["res_N"] == Fraction(1, 2) and one["res_S"] == 0


# ---- H2 ------------------------------------------------------------------------------------------


def test_h2_on_fixed_ratios() -> None:
    same = [item(f"i{k}", [pair(1, 1, 1.0, 1.0)] * 3) for k in range(26)]
    out = confirm_d.h2(same)
    assert out["median_ratio"] == 1.0 and out["interval"] == [1.0, 1.0]
    assert out["non_inferior"] is True and out["cheaper"] is False
    cheaper = [item(f"i{k}", [pair(1, 1, 0.50, 0.40)] * 3) for k in range(26)]
    assert confirm_d.h2(cheaper)["median_ratio"] == 0.8 and confirm_d.h2(cheaper)["cheaper"]
    dearer = [item(f"i{k}", [pair(1, 1, 0.40, 0.50)] * 3) for k in range(26)]
    assert confirm_d.h2(dearer)["non_inferior"] is False


def test_h2_uses_instances_with_a_complete_pair_and_lists_the_others() -> None:
    table = [item("a", [pair(1, 1, 1.0, 2.0)]), item("b", [pair(1, 1, 1.0, 1.0)]),
             item("c", [pair(1, 1, 1.0, 1.5)]), missing("gone")]  # fmt: skip
    out = confirm_d.h2(table)
    assert out["instances"] == 3 and out["median_ratio"] == 1.5 and out["not_used"] == ["gone"]


# ---- adoption and the rest -----------------------------------------------------------------------


def test_adoption_share_and_calls_per_session() -> None:
    table = [item("a", [pair(1, 1, find=2), pair(1, 1), pair(1, 1)]),
             item("b", [pair(1, 1, find=1), pair(1, 1, find=1), pair(1, 1)], "hard")]  # fmt: skip
    out = confirm_d.adoption(table)
    assert out["sessions"] == 6 and out["find"]["share"] == 0.5
    assert out["find"]["per_session"] == round(4 / 6, 4) and out["tool_search"]["share"] == 0.0
    strata = confirm_d.by_stratum(table, confirm_d.adoption)
    assert strata["hard"]["find"]["share"] == round(2 / 3, 4)


def test_an_untreated_s_session_is_left_out_of_adoption() -> None:
    out_of = {"why": "not the treatment: (g) deferred: a deferred_tools_delta names it"}
    table = [item("a", [pair(1, 1, find=1), {"N": pair(1, 1)["N"], "S": out_of,
                                             "complete": False}])]  # fmt: skip
    assert confirm_d.adoption(table)["sessions"] == 1


def test_exploratory_turns_and_find_split() -> None:
    table = [item(f"i{k}", [pair(1, 1, 1.0, 1.2, 10, 12, find=k % 2)] * 3) for k in range(4)]
    out = confirm_d.exploratory(table)
    assert out["turns_ratio"]["median_ratio"] == 1.2
    assert out["cost_per_turn_ratio"]["median_ratio"] == 1.0
    assert out["find_split"]["called_find"]["sessions"] == 6


def test_flips_and_totals_beside(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_d, "RUNS_D", tmp_path)  # no stream there: no guard block to read
    table = [item("steady", [pair(1, 1)] * 3), item("flip", [pair(1, 0), pair(1, 1)], "hard")]
    out = confirm_d.beside(table)
    assert out["flips"] == {"N": [], "S": ["flip"]}
    assert out["totals"]["S"] == {"sessions": 5, "resolved": 4, "cost": 5.0, "turns": 50}
    assert out["totals_by_stratum"]["hard"]["N"]["resolved"] == 2


# ---- reading sessions and the seal ---------------------------------------------------------------


def test_why_not_reads_a_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert confirm_d.why_not(tmp_path / "absent", "N") == "no row"
    (tmp_path / "rowless").mkdir()
    assert confirm_d.why_not(tmp_path / "rowless", "N") == "started, no row"
    evidence = tmp_path / "N"
    evidence.mkdir()
    call = {"subtype": "success", "exit": 0, "cost_usd": 0.3, "turns": 5}
    row = {"model": run_d.D_MODEL, "calls": [call], "jev_usd": 0.0}
    (evidence / "row.json").write_text(json.dumps(row), encoding="utf-8")
    assert confirm_d.why_not(evidence, "N") == "not graded"
    (evidence / "grade.json").write_text('{"resolved": true}', encoding="utf-8")
    assert confirm_d.why_not(evidence, "N") == ""
    row["calls"] = [{**call, "status": run_d.NOT_RUN_ERROR}]
    (evidence / "row.json").write_text(json.dumps(row), encoding="utf-8")
    assert confirm_d.why_not(evidence, "N").startswith("did not run")


def test_an_empty_diff_session_counts_as_a_loss(tmp_path: Path) -> None:
    """The grade `run_d.grade_arm` writes for an empty diff: graded, resolved 0, in the pair."""
    evidence = tmp_path / "N"
    evidence.mkdir()
    call = {"request": 1, "subtype": "success", "exit": 0, "cost_usd": 0.3, "turns": 5}
    row = {"model": run_d.D_MODEL, "calls": [call], "jev_usd": 0.0}
    (evidence / "row.json").write_text(json.dumps(row), encoding="utf-8")
    (evidence / "final.patch").write_text("", encoding="utf-8")
    (evidence / "grade.json").write_text(json.dumps({"resolved": False,
                                                     "reason": run_d.EMPTY_DIFF}))  # fmt: skip
    out = confirm_d.session(evidence, "N")
    assert out["why"] == "" and out["resolved"] == 0 and out["cost"] == pytest.approx(0.3)


def test_verdicts_refuse_to_read_until_sealed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(run_d, "D_COMMIT", "")
    assert "D_COMMIT" in confirm_d.refusal()
    monkeypatch.setattr(run_d, "D_COMMIT", "0" * 40)
    monkeypatch.setattr(run_d, "seal_refusal", lambda: "phase D is not sealed")
    monkeypatch.setattr(run_d, "instances", lambda: pytest.fail("read before the seal"))
    with pytest.raises(SystemExit, match="not sealed"):
        confirm_d.main([])
