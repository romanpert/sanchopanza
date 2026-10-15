"""Lot lb102 (benchmarks/jev114/lb102.py, lb102_stats.py, benchmarks/h2h/h2h_lb102.py), with no
network and no session: the 102 tasks and their order, the money rule (a cap per session from
the spend so far, never past the ceiling), reservations, the clock and STOP stops, rows without
text, the measured saving and its readings, the seal and what it covers."""

from __future__ import annotations

import datetime as dt
import importlib.util
import inspect
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LB162 = ROOT / "docs" / "results" / "2026-10-15-lb162"


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lb = _load("lb102", "benchmarks/jev114/lb102.py")
h2h = _load("h2h_lb102", "benchmarks/h2h/h2h_lb102.py")
st = lb.stats


# --- the 102 tasks ------------------------------------------------------------------------------


def test_the_102_are_lb162s_uncovered_tasks_in_the_frozen_seeded_order():
    rows = lb.jev_rows()
    order = lb.frozen_order(rows)
    covered = set(lb.lb162.read_ids(LB162 / "covered-ids.txt"))
    assert len(order) == len(set(order)) == lb.N_UNCOVERED == 102
    assert not covered & set(order) and covered | set(order) == set(lb.lb162.frozen_ids())
    assert order == lb.uncovered(rows) and order != sorted(order)
    assert lb.check_derivation(rows) == []


def test_a_frozen_file_that_is_not_the_derivation_is_refused(tmp_path, monkeypatch):
    rows = lb.jev_rows()
    bad = tmp_path / "uncovered-ids.txt"
    bad.write_text("\n".join(sorted(lb.uncovered(rows))) + "\n")
    monkeypatch.setattr(lb, "IDS_FILE", bad)
    with pytest.raises(SystemExit, match="derivation"):
        lb.frozen_order(rows)
    with pytest.raises(SystemExit, match="frozen"):
        lb.freeze_ids()


# --- money --------------------------------------------------------------------------------------


def test_the_registered_money_constants():
    assert lb.CEILING_USD == 16.0 and lb.FULL_CAP_USD == 3.00 and lb.WORST_TURN_USD == 4.32
    assert lb.CAP_FLOOR_USD == 0.50 and h2h.RESERVE[h2h.MODEL] == pytest.approx(4.82)
    assert h2h.ld.CAPS[h2h.MODEL] == 3.00
    default = inspect.signature(h2h.ld.one_session).parameters["caps"].default
    assert default is h2h.ld.CAPS  # other phases keep h2h_longdoc's caps


@pytest.mark.parametrize("spent, cap", [
    (0.0, 3.0), (8.68, 3.0), (8.69, 2.99), (9.0, 2.68), (10.505, 1.17), (11.18, 0.5),
    (11.181, None), (11.19, None), (15.0, None),
])  # fmt: skip
def test_the_cap_is_the_full_one_while_it_fits_then_the_room_left_then_none(spent, cap):
    got = lb.cap_for(spent)
    assert got == (None if cap is None else pytest.approx(cap))
    if got is not None:
        assert spent + got + lb.WORST_TURN_USD <= lb.CEILING_USD + 1e-9


def test_the_phase_loop_and_the_cap_rule_stop_at_the_same_spend():
    limits = h2h.phase.Limits(session_max_usd=h2h.RESERVE[h2h.MODEL], ceiling_usd=lb.CEILING_USD)
    for cents in range(1000, 1300):
        spent = cents / 100
        loop_stops = h2h.phase.stop_reason([{"list_usd": spent}], limits, 0) is not None
        assert loop_stops == (lb.cap_for(spent) is None), spent


class Task:
    def __init__(self, i: int) -> None:
        self.task_id = f"u{i:03d}"


def _budget(tmp_path, now=dt.datetime(2026, 10, 16, 10)):
    sessions, reservations = tmp_path / "sessions.jsonl", tmp_path / "reservations.jsonl"
    guard = h2h.Budget(dt.datetime(2026, 10, 16, 9), clock=lambda: now, run_dir=tmp_path,
                       spent=lambda: h2h.spent_now(sessions, reservations),
                       reservations=reservations)  # fmt: skip
    return guard, sessions, reservations


@pytest.mark.parametrize("usd", [0.09, 0.5, None])  # None: every session at its cap + worst turn
def test_the_phase_never_passes_the_ceiling(tmp_path, usd):
    guard, sessions, _ = _budget(tmp_path)
    caps = []

    def session(item, run, arm, cap):
        caps.append(cap)
        cost = cap + lb.WORST_TURN_USD if usd is None else usd
        return {"task": item[0], "task_id": item[0], "run": run, "arm": arm, "list_usd": cost}

    limits = h2h.phase.Limits(session_max_usd=h2h.RESERVE[h2h.MODEL], ceiling_usd=lb.CEILING_USD)
    code, rows = h2h.phase.run_phase(h2h.steps([Task(i) for i in range(102)]), [], limits,
                                     guard.wrap(session), sessions)  # fmt: skip
    assert sum(r["list_usd"] for r in rows) <= lb.CEILING_USD + 1e-9
    assert all(c >= lb.CAP_FLOOR_USD for c in caps)
    if usd == 0.09:  # 9.18 USD: all 102 run, the last ones on a lowered cap
        assert code == 0 and len(rows) == 102 and caps[0] == 3.0 and min(caps) < 3.0
    else:  # the loop's own check stops first (the same line as cap_for's None)
        assert code == 1 and h2h.s162.stop_kind(1, guard) == "ceiling"


def test_a_session_that_died_keeps_its_own_reserve_against_the_ceiling(tmp_path):
    guard, sessions, reservations = _budget(tmp_path)
    done = {"task": "a", "task_id": "a", "run": 1, "arm": h2h.ARM, "list_usd": 9.0}
    guard.wrap(lambda item, run, arm, cap: done)(("a",), 1, h2h.ARM)
    sessions.write_text(json.dumps(done) + "\n")

    def dies(item, run, arm, cap):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        guard.wrap(dies)(("b",), 1, h2h.ARM)
    open_ = h2h.open_reservations([done], reservations)
    got = [(r["task"], r["list_usd"], r["not_run"]) for r in open_]
    assert got == [("b", pytest.approx(2.68 + 4.32), True)]  # 16 - 9 - 4.32 = 2.68: its own cap
    assert h2h.spent_now(sessions, reservations) == pytest.approx(16.0)
    with pytest.raises(h2h.common.JointCeiling, match="ceiling"):
        guard.wrap(lambda *a: {})(("c",), 1, h2h.ARM)
    assert h2h.phase.counted([done, *open_]) == [done]


@pytest.mark.parametrize("now, kind", [
    (dt.datetime(2026, 10, 16, 23, 55), "clock"),
    (dt.datetime(2026, 10, 17, 3, 0), "clock"),
    (dt.datetime(2026, 10, 16, 7, 30), "clock"),
])  # fmt: skip
def test_no_session_starts_outside_the_phases_day_and_hours(tmp_path, now, kind):
    guard, _, reservations = _budget(tmp_path, now)
    ran = []
    with pytest.raises(h2h.common.JointCeiling):
        guard.wrap(lambda *a: ran.append(a) or {})(("t",), 1, h2h.ARM)
    assert guard.kind == kind and ran == [] and not reservations.exists()


def test_a_stop_file_stops_before_the_next_session(tmp_path):
    guard, _, _ = _budget(tmp_path)
    one = guard.wrap(lambda *a: {"list_usd": 0.1})
    one(("t",), 1, h2h.ARM)
    (tmp_path / "STOP").write_text("")
    with pytest.raises(h2h.common.JointCeiling, match="STOP"):
        one(("u",), 1, h2h.ARM)
    assert guard.kind == "manual" and h2h.EXIT["manual"] == 6


def test_the_clock_refuses_early_starts_and_runs_across_midnight():
    day = dt.datetime(2026, 10, 16)
    assert h2h.clock_refusal(day.replace(hour=7, minute=59), 102) != ""
    assert h2h.clock_refusal(day.replace(hour=9), 102) == ""
    assert h2h.clock_refusal(day.replace(hour=22, minute=13), 102) == ""
    assert "midnight" in h2h.clock_refusal(day.replace(hour=22, minute=15), 102)


def test_the_launcher_takes_this_runner():
    text = (ROOT / "benchmarks/h2h/launch.ps1").read_text(encoding="utf-8")
    assert "'h2h_lb102.py'" in text and "set DISABLE_AUTOUPDATER=1" in text


# --- rows without text --------------------------------------------------------------------------


def test_public_rows_keep_lb162s_fields_and_the_cap_only():
    session = {"task_id": "t1", "task": "t1", "run": 1, "arm": "SONNET-CC", "final_answer": "D",
               "ok_oficial": True, "list_usd": 0.12, "wall_s": 20.0, "turns": 4,
               "hit_cap": False, "answer": "SECRET reply", "ok": True, "subtype": "success",
               "cap_usd": 2.5, "workdir": "C:/sp-runs/h2h/lb102/abc/work"}  # fmt: skip
    rows = [session, {**session, "arm": "SONNET-SP"}, {**session, "task_id": "t2",
                                                       "not_run": True}]  # fmt: skip
    got = h2h.public_rows(rows)
    assert len(got) == 1 and got[0]["cap_usd"] == 2.5 and got[0]["id"] == "t1"
    assert set(got[0]) == {"id", "cap_usd", *h2h.s162.ROW_KEYS}
    assert "SECRET" not in json.dumps(got)


# --- the measured saving ------------------------------------------------------------------------


def _jev(i: int, p: float, right: bool, usd: float = 0.01, length: str = "short") -> dict:
    return {"id": f"t{i:03d}", "gold": "A", "length": length, "difficulty": "easy",
            "status": "answered",
            "j14-L": {"letter": "A" if right else "B", "p": p, "usd": usd}}  # fmt: skip


def _son(i: int, usd: float, ok: bool = True, **extra) -> dict:
    return {"id": f"t{i:03d}", "letter": "A" if ok else "B", "ok": ok, "usd": usd,
            "hit_cap": False, "is_error": False, **extra}  # fmt: skip


def test_the_share_is_sonnet_on_the_covered_minus_jev_over_sonnet_alone():
    rows = [_jev(0, 0.9, True), _jev(1, 0.7, False), _jev(2, 0.3, True), _jev(3, 0.2, False)]
    lb162_s = {r["id"]: r for r in (_son(0, 0.10), _son(1, 0.30))}
    lb102_s = {r["id"]: r for r in (_son(2, 0.20, ok=False), _son(3, 0.40))}
    got = st.analyse(rows, lb162_s, lb102_s)
    p = got["primary"]
    # alone 0.10 + 0.30 + 0.20 + 0.40 = 1.00; hybrid 0.04 Jev + 0.60 = 0.64
    assert p["share"] == pytest.approx(0.36) and p["usd"]["saving"] == pytest.approx(0.36)
    assert p["uncovered_measured"] == 2 and p["bootstrap"]["kept"] == 10_000
    a = got["accuracy"]
    assert a["sonnet_right_uncovered"] == 1 and a["jev_right_uncovered"] == 1
    assert a["sonnet_alone_right"] == 3 and a["hybrid_right"] == 2  # Jev wrong on t001


def test_a_ceiling_stop_keeps_a_ratio_estimate_of_the_uncovered_cost():
    rows = [_jev(0, 0.9, True), _jev(1, 0.1, True), _jev(2, 0.1, True), _jev(3, 0.1, True)]
    lb162_s = {"t000": _son(0, 1.0)}
    part = st.tasks(rows, {**lb162_s, "t001": _son(1, 0.5)})
    total = st.totals(part, [0, 1, 2, 3])
    assert total["sonnet_uncovered"] == pytest.approx(1.5)  # 3 tasks x 0.5, not 0.5
    none = st.tasks(rows, lb162_s)
    assert st.share(none, [0, 1, 2, 3]) is None
    assert st.analyse(rows, lb162_s, {})["primary"]["reading"] == "no medido"


def test_infrastructure_errors_and_lowered_caps_have_their_sensitivity_readings():
    rows = [_jev(0, 0.9, True), _jev(1, 0.1, True), _jev(2, 0.1, True)]
    lb162_s = {"t000": _son(0, 1.0)}
    broken = {**_son(1, 0.9), "letter": None, "is_error": True}
    cut = _son(2, 0.6, hit_cap=True, cap_usd=0.6)
    got = st.analyse(rows, lb162_s, {"t001": broken, "t002": cut})
    assert got["primary"]["usd"]["sonnet_uncovered"] == pytest.approx(1.2)  # 2 x 0.6
    assert got["sensitivity_infra_counted"]["usd"]["sonnet_uncovered"] == pytest.approx(1.5)
    assert got["sensitivity_reduced_cap_at_full"]["usd"]["sonnet_uncovered"] == pytest.approx(6.0)
    s = got["sessions"]
    assert s["infra"] == 1 and s["reduced_cap"] == 1 and s["reduced_cap_hit"] == 1


def test_the_reading_rule_and_where_the_estimate_falls():
    assert st.reading((0.0001, 0.4)) == "ahorra"
    assert st.reading((0.0, 0.4)) == "no concluyente"
    assert st.reading((-0.2, 0.0)) == "no ahorra"
    assert st.reading(None) == "no medido"
    assert st.estimate_check((0.20, 0.30)) == "estimate inside the CI"
    assert st.estimate_check((0.28, 0.40)) == "estimate below the CI"
    assert st.estimate_check((0.10, 0.25)) == "estimate above the CI"


def test_no_reading_while_the_lot_is_paused(tmp_path):
    assert lb.pause_reasons({"kind": "done"}, tmp_path) == []
    assert lb.pause_reasons({"kind": "ceiling"}, tmp_path) == []
    assert lb.pause_reasons({"kind": "limit"}, tmp_path) == ["phase limit"]
    assert lb.pause_reasons(None, tmp_path) == ["phase not run"]
    (tmp_path / "LIMIT.flag").write_text("")
    assert lb.pause_reasons({"kind": "done"}, tmp_path) == ["LIMIT.flag in the run folder"]
    rows = [_jev(0, 0.9, True), _jev(1, 0.1, True)]
    got = st.analyse(rows, {"t000": _son(0, 1.0)}, {"t001": _son(1, 0.5)}, paused=["x"])
    assert got["primary"]["reading"] == "pausa" and got["primary"]["estimate_check"] is None


def test_lb162s_recorded_rows_alone_give_no_measurement_yet():
    rows = lb.jev_rows()
    got = st.analyse(rows, lb.by_id(lb.lb162.SONNET_ROWS), {}, paused=["phase not run"])
    p = got["primary"]
    assert p["n"] == 162 and p["covered"] == 60 and p["uncovered"] == 102
    assert p["uncovered_measured"] == 0 and p["share"] is None and p["reading"] == "pausa"


def test_the_dry_mode_lists_the_102_and_the_money_rule():
    lines = lb.dry(dt.datetime(2026, 10, 16, 9))
    assert sum(1 for x in lines if " est " in x and "chars" in x) == 102
    assert any(x.startswith("102 sessions") and "problems: none" in x for x in lines)
    assert any("ceiling 16" in x for x in lines) and any("by 22:13" in x for x in lines)


# --- the seal -----------------------------------------------------------------------------------


def test_a_seal_round_trip_and_no_quiet_reseal(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "OUT", tmp_path)
    monkeypatch.setattr(lb, "REPO", tmp_path)
    monkeypatch.setattr(lb, "SEALED", ("code.py",))
    monkeypatch.setattr(lb, "SEALED_GLOBS", ())
    monkeypatch.setattr(lb, "SEALED_DATA", ())
    monkeypatch.setattr(lb, "SONNET_ROWS", tmp_path / "sonnet-rows.jsonl")
    docs = {"value": "first"}
    monkeypatch.setattr(lb.lb162, "docs_digest", lambda tasks=None: docs["value"])
    (tmp_path / "prereg.md").write_text("plan\n")
    (tmp_path / "code.py").write_text("x = 1\n")
    assert lb.seal_state() == "not sealed"
    with pytest.raises(SystemExit, match="seal"):
        lb.require_prereg()
    lb.seal()
    lb.require_prereg()
    (tmp_path / "code.py").write_text("x = 2\n")
    assert lb.seal_state() == "MISMATCH"
    with pytest.raises(SystemExit, match="another seal"):
        lb.seal()
    (tmp_path / "sonnet-rows.jsonl").write_text("{}\n")
    with pytest.raises(SystemExit, match="amendment"):
        lb.seal(again=True)
    (tmp_path / "code.py").write_text("x = 1\n")
    lb.require_prereg()
    docs["value"] = "changed"
    assert lb.docs_problems() != []


def test_the_seal_covers_every_file_the_runner_loads():
    probe = (
        "import importlib.util, json, pathlib, sys\n"
        "root = pathlib.Path(sys.argv[1])\n"
        "for name, rel in (('lb102', 'benchmarks/jev114/lb102.py'),\n"
        "                  ('h2h_lb102', 'benchmarks/h2h/h2h_lb102.py')):\n"
        "    spec = importlib.util.spec_from_file_location(name, root / rel)\n"
        "    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod\n"
        "    spec.loader.exec_module(mod)\n"
        "h2h = sys.modules['h2h_lb102']; h2h.common.local_hook_problems()\n"
        "files = {pathlib.Path(m.__file__).resolve() for m in list(sys.modules.values())\n"
        "         if getattr(m, '__file__', None)}\n"
        "print(json.dumps(sorted(p.relative_to(root).as_posix() for p in files\n"
        "                        if root in p.parents)))\n"
    )  # fmt: skip
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    done = subprocess.run([sys.executable, "-c", probe, str(ROOT)], capture_output=True,
                          text=True, env=env, timeout=120, check=True)  # fmt: skip
    loaded = {p for p in json.loads(done.stdout) if p.startswith(("benchmarks/", "src/"))}
    sealed = set(lb.sealed_paths())
    assert loaded and loaded <= sealed, sorted(loaded - sealed)
    assert {"tests/test_lb102.py", "docs/results/2026-10-16-lb102/uncovered-ids.txt"} <= sealed
