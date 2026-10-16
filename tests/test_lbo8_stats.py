"""Lot lbo8's analysis (benchmarks/jev114/lbo8_stats.py), on synthetic rows: Tango's interval
on known cases, the verdict at the -5-point margin, "no medido", how sessions with no letter are
read, the saving's paired bootstrap, the secondaries and summary.json. No network, no session."""

from __future__ import annotations

import importlib.util
import json
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
st = _load("lbo8_stats", "benchmarks/jev114/lbo8_stats.py")
CELL = lbo8.lb162.CELL


def _jev(i: int, p: float | None, right: bool, usd: float = 0.001, status: str = "answered"):
    letter = None if p is None else ("A" if right else "B")
    return {"id": f"t{i:02d}", "gold": "A", "length": "short", "difficulty": "hard",
            "status": status, CELL: {"letter": letter, "p": p, "usd": usd}}  # fmt: skip


def _ses(i: int, ok: bool = True, usd: float = 0.10, **extra):
    return {"id": f"t{i:02d}", "letter": "A" if ok else "B", "ok": ok, "usd": usd,
            "hit_cap": False, "is_error": False, "cap_usd": 6.0, "served_ok": True,
            **extra}  # fmt: skip


def _lot(covered: int, jev_only: int = 0, opus_only: int = 0, n: int = 78):
    """`n` tasks, the first `covered` at p 0.9, with `jev_only` and `opus_only` disagreements
    among them; Opus has a session on every task (0.10 USD), Jev costs 0.001 a task."""
    rows, opus = [], {}
    for i in range(n):
        cov = i < covered
        jev_ok = not (cov and jev_only <= i < jev_only + opus_only)
        opus_ok = not (cov and i < jev_only)
        rows.append(_jev(i, 0.9 if cov else 0.3, jev_ok))
        opus[f"t{i:02d}"] = _ses(i, opus_ok)
    return rows, opus


# ---- Tango ---------------------------------------------------------------------------------------


def test_no_disagreement_at_78_tasks_gives_the_closed_form_floor():
    z = lbo8.Z
    est, lo, hi = lbo8.tango_ci(0, 0, 78)
    assert est == 0.0 and lo == pytest.approx(-(z**2) / (78 + z**2), abs=1e-9)
    assert round(lo * 100, 1) == -4.7 and hi == pytest.approx(-lo, abs=1e-9)


@pytest.mark.parametrize("b, c, lo_pts, hi_pts", [
    (0, 1, -6.911, 3.472), (1, 1, -5.788, 5.788), (0, 2, -8.875, 2.250),
    (2, 0, -2.250, 8.875), (0, 3, -10.708, 1.028),
])  # fmt: skip
def test_tango_at_78_tasks_on_known_cases(b, c, lo_pts, hi_pts):
    est, lo, hi = lbo8.tango_ci(b, c, 78)
    assert est == pytest.approx((b - c) / 78)
    assert (lo * 100, hi * 100) == (
        pytest.approx(lo_pts, abs=1e-3),
        pytest.approx(hi_pts, abs=1e-3),
    )


# ---- the verdict at -5 ---------------------------------------------------------------------------


@pytest.mark.parametrize("lo, hi, said", [
    (-0.0499999, 0.03, "no peor"), (-0.05, 0.03, "no concluyente"),
    (-0.09, -0.05, "no concluyente"), (-0.09, -0.0500001, "peor"),
])  # fmt: skip
def test_the_verdict_at_the_exact_minus_5_edge_unrounded(lo, hi, said):
    assert st.MARGIN == -0.05 and lbo8.verdict(lo, hi, st.MARGIN) == said


@pytest.mark.parametrize("jev_only, opus_only, said", [
    (0, 0, "no peor"),  # the floor, -4.69, is above -5
    (1, 0, "no peor"),
    (0, 1, "no concluyente"),  # one Opus-only disagreement: -6.91
    (1, 1, "no concluyente"),  # -5.79
    (0, 7, "no concluyente"),  # upper bound -3.86
    (0, 8, "peor"),  # upper bound -5.08
])  # fmt: skip
def test_the_primary_verdict_over_the_78(jev_only, opus_only, said):
    rows, opus = _lot(13, jev_only, opus_only)
    v = st.analyse(rows, opus)["primary"]
    assert v["n"] == 78 and v["covered"] == 13 and v["covered_with_opus"] == 13
    assert (v["jev_only_right"], v["opus_only_right"]) == (jev_only, opus_only)
    assert v["verdict"] == said and v["method"].startswith("Tango")
    assert v["diff"] == pytest.approx((jev_only - opus_only) / 78, abs=1e-6)


def test_eight_opus_only_disagreements_are_worse_than_minus_5():
    rows, opus = _lot(13, 0, 8)
    assert st.analyse(rows, opus)["primary"]["ci95"][1] < -0.05


def test_no_verdict_under_8_covered_tasks_with_an_opus_session():
    rows, opus = _lot(7)
    assert st.verdict(st.tasks(rows, opus))["verdict"] == "no medido"
    rows, opus = _lot(8)
    assert st.verdict(st.tasks(rows, opus))["verdict"] == "no peor"
    rows, opus = _lot(9)
    del opus["t00"], opus["t01"]  # two covered tasks without a session: 7 left
    v = st.verdict(st.tasks(rows, opus))
    assert v["verdict"] == "no medido" and v["covered_without_opus"] == 2 and v["n"] == 76


def test_an_uncovered_task_without_a_session_stays_in_n():
    rows, opus = _lot(10)
    del opus["t50"]
    assert st.verdict(st.tasks(rows, opus))["n"] == 78


def test_a_paused_lot_has_no_verdict():
    rows, opus = _lot(13)
    got = st.analyse(rows, opus, paused=["phase O limit"])
    assert got["primary"]["verdict"] == "pausa" and got["saving"]["reading"] == "pausa"


# ---- sessions with no letter ---------------------------------------------------------------------


def test_infrastructure_errors_are_not_run_in_the_primary_and_wrong_in_the_sensitivity():
    rows, opus = _lot(10)
    opus["t00"] = {**opus["t00"], "letter": None, "ok": False, "is_error": True}  # Jev right
    got = st.analyse(rows, opus)
    p, s = got["primary"], got["sensitivity_not_run_as_wrong"]
    assert (p["n"], p["covered_with_opus"], p["opus_only_right"], p["jev_only_right"]) == (
        77, 9, 0, 0)  # fmt: skip
    assert (s["n"], s["covered_with_opus"], s["jev_only_right"]) == (78, 10, 1)


def test_a_lowered_cap_stop_is_not_run_but_a_full_cap_stop_is_wrong():
    rows, opus = _lot(10)
    opus["t00"] = {**opus["t00"], "letter": None, "ok": False, "hit_cap": True, "cap_usd": 2.5}
    opus["t01"] = {**opus["t01"], "letter": None, "ok": False, "hit_cap": True, "cap_usd": 6.0}
    p = st.analyse(rows, opus)["primary"]
    assert p["covered_with_opus"] == 9 and p["jev_only_right"] == 1


def test_a_session_another_model_served_is_out_of_both_readings():
    rows, opus = _lot(10)
    opus["t00"] = {**opus["t00"], "served_ok": False}
    got = st.analyse(rows, opus)
    assert got["primary"]["covered_with_opus"] == 9
    assert got["sensitivity_not_run_as_wrong"]["covered_with_opus"] == 9


def test_a_task_phase_j_left_unasked_is_uncovered():
    rows, opus = _lot(10)
    rows[0] = _jev(0, None, False, usd=0.0, status="stopped")
    v = st.verdict(st.tasks(rows, opus))
    assert v["covered"] == 9 and v["n"] == 78


# ---- the saving ----------------------------------------------------------------------------------


def test_the_saving_share_is_opus_on_the_covered_minus_jev_over_opus_alone():
    rows, opus = _lot(13)
    s = st.analyse(rows, opus)["saving"]
    # alone 78 x 0.10 = 7.80; hybrid 78 x 0.001 + 65 x 0.10 = 6.578; saving 1.222
    assert s["usd"]["alone"] == pytest.approx(7.8) and s["usd"]["hybrid"] == pytest.approx(6.578)
    assert s["share"] == pytest.approx(1.222 / 7.8, abs=1e-4)
    assert s["bootstrap"] == {"draws": 10_000, "kept": 10_000, "seed": 20261016, "unit": "task"}
    assert s["ci95"][0] > 0 and s["reading"] == "ahorra"


def test_the_bootstrap_is_deterministic_and_seeded():
    rows, opus = _lot(13)
    for i in range(78):  # costs that vary, so the resamples differ
        opus[f"t{i:02d}"] = {**opus[f"t{i:02d}"], "usd": 0.05 + (i * 37 % 11) / 50}
    ts = st.tasks(rows, opus)
    first, again = st.bootstrap(ts, 2_000), st.bootstrap(ts, 2_000)
    assert first == again and len(set(first)) > 100
    assert st.bootstrap(ts, 2_000, seed=1) != first
    assert st.saving(ts, draws=2_000) == st.saving(ts, draws=2_000)


def test_no_jev_saving_when_jev_costs_more_than_the_opus_it_avoids():
    rows, opus = _lot(13)
    rows = [{**r, CELL: {**r[CELL], "usd": 0.05}} for r in rows]  # 3.90 of Jev for 1.30 avoided
    s = st.analyse(rows, opus)["saving"]
    assert s["share"] < 0 and s["reading"] == "no ahorra"


def test_no_measured_cost_is_no_measure():
    rows, _ = _lot(13)
    s = st.saving(st.tasks(rows, {}))
    assert s["share"] is None and s["ci95"] is None and s["reading"] == "no medido"


# ---- secondaries and summary.json ----------------------------------------------------------------


def test_the_secondaries():
    rows, opus = _lot(13, jev_only=1, opus_only=2)
    got = st.analyse(rows, opus)
    acc = got["covered_accuracy"]
    assert (acc["covered"], acc["jev_right"], acc["opus_graded"], acc["opus_right"]) == (
        13, 11, 13, 12)  # fmt: skip
    assert acc["jev_precision"] == pytest.approx(11 / 13, abs=1e-4)
    assert got["primary"]["mcnemar_p"] == pytest.approx(1.0)
    cuts = {c["cut"]: c for c in got["descriptive_cuts"]}
    assert set(cuts) == {0.6, 0.7} and all(c["descriptive"] for c in cuts.values())
    assert cuts[0.6]["covered"] == 13  # p 0.9 and 0.3: the same 13 at every cut here
    assert got["overall"]["opus_right"] == 77 and got["overall"]["hybrid_right"] == 76
    assert got["jev"]["status"]["answered"] == 78


def test_lower_cuts_cover_more_on_the_same_rows():
    rows, opus = _lot(10)
    rows[20] = _jev(20, 0.65, True)
    rows[21] = _jev(21, 0.75, False)
    cuts = {c["cut"]: c for c in st.analyse(rows, opus)["descriptive_cuts"]}
    assert (cuts[0.6]["covered"], cuts[0.7]["covered"]) == (12, 11)
    assert cuts[0.7]["opus_only_right"] == 1


def test_summary_json_is_written(tmp_path):
    rows, opus = _lot(13)
    out = st.analyse(rows, opus)
    path = tmp_path / "sub" / "summary.json"
    st.write_summary(path, out)
    back = json.loads(path.read_text(encoding="utf-8"))
    assert back["primary"]["verdict"] == "no peor" and back["margin"] == -0.05
