"""Lot lb162x (benchmarks/jev114/lb162x.py, lb162x_stats.py, benchmarks/h2h/h2h_lb162x.py), with
no network and no session: lb162's recordings and the two orders, each phase's money rule (a cap
per session from the spend so far, never past the ceiling), reservations, the clock and STOP
stops, the driver's phase order, rows without text, the verdict, the saving, and the seal."""

from __future__ import annotations

import dataclasses
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


lb = _load("lb162x", "benchmarks/jev114/lb162x.py")
h2h = _load("h2h_lb162x", "benchmarks/h2h/h2h_lb162x.py")
st = lb.stats
A, B = lb.PHASE_A, lb.PHASE_B
NO_MIN = {"min_covered": 0, "min_saving": 0}  # the registered minima, off for a few fake tasks


# --- lb162's recordings and the two orders -------------------------------------------------------


def test_lb162s_recordings_are_the_committed_ones():
    assert lb.recorded_problems() == []
    assert len(lb.jev_rows()) == 162


def test_a_changed_recording_is_refused(tmp_path, monkeypatch):
    rows = (LB162 / "jev-scored.jsonl").read_text(encoding="utf-8").splitlines()
    changed = tmp_path / "jev-scored.jsonl"
    changed.write_text("\n".join([rows[0].replace('"gold": "', '"gold": "x'), *rows[1:]]) + "\n")
    recorded = {changed if p.name == "jev-scored.jsonl" else p: sha
                for p, sha in lb.RECORDED.items()}  # fmt: skip
    monkeypatch.setattr(lb, "RECORDED", recorded)
    assert lb.recorded_problems() == ["jev-scored.jsonl is not lb162's recording"]
    with pytest.raises(SystemExit, match="recording"):
        lb.jev_rows()


def test_phase_a_is_the_162_minus_the_60_covered_in_the_frozen_seeded_order():
    rows = lb.jev_rows()
    order = lb.frozen_order(A, rows)
    covered = set(lb.lb162.read_ids(LB162 / "covered-ids.txt"))
    every = set(lb.lb162.frozen_ids())
    assert len(order) == len(set(order)) == A.n == 102 and len(covered) == 60
    assert set(order) == every - covered
    assert order == lb.uncovered(rows) and order != sorted(order)


def test_phase_b_is_all_162_in_its_own_seeded_order():
    rows = lb.jev_rows()
    order = lb.frozen_order(B, rows)
    assert len(order) == B.n == 162 and set(order) == set(lb.lb162.frozen_ids())
    assert order == lb.every_task(rows) and order != sorted(order)
    assert lb.ORDER == (B, A)  # B first: the primary verdict


@pytest.mark.parametrize("phase", [A, B])
def test_a_frozen_file_that_is_not_the_derivation_is_refused(tmp_path, phase):
    rows = lb.jev_rows()
    bad = tmp_path / phase.ids_file.name
    bad.write_text("\n".join(sorted(lb.derive(phase, rows))) + "\n")
    with pytest.raises(SystemExit, match="derivation"):
        lb.frozen_order(dataclasses.replace(phase, ids_file=bad), rows)


# --- money --------------------------------------------------------------------------------------


def test_the_registered_money_constants():
    assert (A.ceiling, A.full_cap, A.floor, A.worst_turn) == (16.0, 3.0, 0.5, 4.32)
    assert (B.ceiling, B.full_cap, B.floor, B.worst_turn) == (45.0, 6.0, 1.0, 8.64)
    assert A.worst_turn == lb.lb162.WORST_TURN_USD and lb.OPUS_SCALE == 2.0
    assert A.loop_reserve == pytest.approx(4.82) and B.loop_reserve == pytest.approx(9.64)
    assert h2h.ld.CAPS["SONNET"] == A.full_cap and h2h.ld.CAPS["OPUS"] == B.full_cap
    assert h2h.gaia.MODELS[B.model] == "claude-opus-5-5" == B.model_id
    default = inspect.signature(h2h.ld.one_session).parameters["caps"].default
    assert default is h2h.ld.CAPS  # other phases keep h2h_longdoc's caps


@pytest.mark.parametrize("phase, spent, cap", [
    (A, 0.0, 3.0), (A, 8.68, 3.0), (A, 8.69, 2.99), (A, 10.505, 1.17), (A, 11.18, 0.5),
    (A, 11.181, None), (A, 15.0, None),
    (B, 0.0, 6.0), (B, 30.36, 6.0), (B, 30.37, 5.99), (B, 33.0, 3.36), (B, 35.36, 1.0),
    (B, 35.361, None), (B, 44.0, None),
])  # fmt: skip
def test_the_cap_is_the_full_one_while_it_fits_then_the_room_left_then_none(phase, spent, cap):
    got = lb.cap_for(spent, phase)
    assert got == (None if cap is None else pytest.approx(cap))
    if got is not None:
        assert spent + got + phase.worst_turn <= phase.ceiling + 1e-9


@pytest.mark.parametrize("phase", [A, B])
def test_the_phase_loop_and_the_cap_rule_stop_at_the_same_spend(phase):
    limits = h2h.phase_loop.Limits(session_max_usd=phase.loop_reserve, ceiling_usd=phase.ceiling)
    for cents in range(int(phase.ceiling * 50), int(phase.ceiling * 100)):
        spent = cents / 100
        loop_stops = h2h.phase_loop.stop_reason([{"list_usd": spent}], limits, 0) is not None
        assert loop_stops == (lb.cap_for(spent, phase) is None), spent


def test_sessions_guaranteed_at_worst_and_at_the_mean():
    assert lb.guaranteed(A) == 2 and lb.guaranteed(B) == 3
    assert lb.at_mean(B, 0.1832, 162) == 162 and lb.at_mean(A, 0.0891, 102) == 102
    # the floor's line: B stops past 45 - 8.64 - 1.00 = 35.36, A past 16 - 4.32 - 0.50 = 11.18
    assert lb.at_mean(B, 0.25) == 142 and lb.at_mean(A, 0.25) == 45


def test_the_clock_refuses_early_starts_and_runs_across_midnight():
    day = dt.datetime(2026, 10, 16)
    assert h2h.clock_refusal(A, day.replace(hour=7, minute=59), 102) != ""
    assert h2h.clock_refusal(A, day.replace(hour=22, minute=13), 102) == ""
    assert "midnight" in h2h.clock_refusal(A, day.replace(hour=22, minute=15), 102)
    assert h2h.clock_refusal(B, day.replace(hour=19, minute=46), 162) == ""
    assert "midnight" in h2h.clock_refusal(B, day.replace(hour=19, minute=48), 162)


def test_the_launcher_takes_this_runner():
    text = (ROOT / "benchmarks/h2h/launch.ps1").read_text(encoding="utf-8")
    assert "'h2h_lb162x.py'" in text and "set DISABLE_AUTOUPDATER=1" in text


# --- the driver -----------------------------------------------------------------------------------


@pytest.mark.parametrize("kinds, final, lot, ran", [
    ({"S": "done", "B": "done", "A": "done"}, {}, "done", ["S", "B", "A"]),
    ({"B": "ceiling", "A": "done"}, {"S": "done"}, "ceiling", ["B", "A"]),
    ({"S": "smoke"}, {}, "smoke", ["S"]),
    ({"S": "ceiling"}, {}, "ceiling", ["S"]),  # a smoke stopped by its ceiling does not pass
    ({"S": "outage"}, {}, "outage", ["S"]),
    ({"B": "limit"}, {"S": "done"}, "limit", ["B"]),
    ({"B": "clock"}, {"S": "done"}, "clock", ["B"]),
    ({"B": "outage"}, {"S": "done"}, "outage", ["B"]),
    ({"A": "manual"}, {"S": "done", "B": "done"}, "manual", ["A"]),
    ({"A": "weird"}, {"S": "done", "B": "done"}, "error", ["A"]),
    ({}, {"S": "done", "B": "ceiling", "A": "done"}, "ceiling", []),
])  # fmt: skip
def test_the_driver_runs_the_smoke_then_b_then_a_and_stops_at_the_first_pause(
    kinds, final, lot, ran
):
    seen = []

    def run_one(phase):
        seen.append(phase.key)
        return kinds[phase.key]

    got, _ = h2h.drive(lb.DRIVEN, run_one, lambda p: final.get(p.key))
    assert got == lot and seen == ran
    assert (
        h2h.exit_code(got)
        == {
            "done": 0,
            "ceiling": 1,
            "limit": 2,
            "clock": 5,
            "manual": 6,
            "error": 7,
            "outage": 8,
            "smoke": 9,
        }[got]
    )


# --- rows without text --------------------------------------------------------------------------


def test_public_rows_keep_lb162s_fields_and_the_cap_only():
    session = {"task_id": "t1", "task": "t1", "run": 1, "arm": "OPUS-CC", "final_answer": "D",
               "ok_oficial": True, "list_usd": 0.22, "wall_s": 20.0, "turns": 4,
               "hit_cap": False, "answer": "SECRET reply", "ok": True, "subtype": "success",
               "cap_usd": 5.5, "workdir": "C:/sp-runs/h2h/lb162x-opus/abc/work"}  # fmt: skip
    rows = [session, {**session, "arm": "SONNET-CC"}, {**session, "task_id": "t2",
                                                       "not_run": True}]  # fmt: skip
    got = h2h.public_rows(rows, B)
    assert len(got) == 1 and got[0]["cap_usd"] == 5.5 and got[0]["id"] == "t1"
    assert set(got[0]) == {"id", "cap_usd", "served_ok", *h2h.s162.ROW_KEYS}
    assert got[0]["served_ok"] is True
    other = {**session, "usd_by_model": {"claude-sonnet-5-5": 0.2, "claude-opus-5-5": 0.02}}
    assert h2h.public_rows([other], B)[0]["served_ok"] is False
    assert "SECRET" not in json.dumps(got) and "sp-runs" not in json.dumps(got)


# --- the verdict (phase B) ------------------------------------------------------------------------


def _jev(i: int, p: float, right: bool, usd: float = 0.01, length: str = "short") -> dict:
    return {"id": f"t{i:03d}", "gold": "A", "length": length, "difficulty": "easy",
            "status": "answered",
            "j14-L": {"letter": "A" if right else "B", "p": p, "usd": usd}}  # fmt: skip


def _ses(i: int, usd: float, ok: bool = True, **extra) -> dict:
    return {"id": f"t{i:03d}", "letter": "A" if ok else "B", "ok": ok, "usd": usd,
            "hit_cap": False, "is_error": False, **extra}  # fmt: skip


@pytest.mark.parametrize("ci, said", [
    ((-0.0999, 0.05), "no peor"), ((-0.10, 0.05), "no concluyente"),
    ((-0.30, -0.10), "no concluyente"), ((-0.30, -0.1001), "peor"), (None, "no medido"),
])  # fmt: skip
def test_the_verdict_rule_at_the_exact_minus_10_edge(ci, said):
    assert st.MARGIN == -0.10 and st.lbs.verdict(ci) == said


def test_hybrid_minus_opus_is_coverage_times_the_mean_covered_gain():
    rows = [_jev(0, 0.9, True), _jev(1, 0.7, False), _jev(2, 0.3, True), _jev(3, 0.2, False)]
    opus = {r["id"]: r for r in (_ses(0, 0.2, ok=False), _ses(1, 0.2), _ses(2, 0.4),
                                 _ses(3, 0.4, ok=False))}  # fmt: skip
    got = st.phase_b(rows, opus, **NO_MIN)
    p = got["primary"]
    assert p["diff"] == 0.0 and p["covered"] == 2 and p["opus_sessions"] == 2
    assert p["mcnemar"] == {"jev_only_right": 1, "opus_only_right": 1, "p": 1.0}
    assert p["coverage"] == 0.5 and p["claim"] in ("sustituye", "no sustituye")
    assert "sonnet" not in json.dumps(p)
    s = got["saving"]  # alone 0.4 + 0.8 = 1.2; hybrid 0.04 + 0.8 = 0.84
    assert s["share"] == pytest.approx(0.3) and s["usd"]["saving"] == pytest.approx(0.36)
    a = got["accuracy"]
    assert a["alone_right"] == 2 and a["hybrid_right"] == 2 and a["tasks_known"] == 4


def test_a_ceiling_stop_keeps_both_ratio_estimators():
    rows = [_jev(i, 0.9 if i < 4 else 0.1, i % 2 == 0) for i in range(8)]
    opus = {r["id"]: r for r in (_ses(0, 1.0, ok=False), _ses(1, 1.0), _ses(4, 0.5))}
    p = st.phase_b(rows, opus, **NO_MIN)["primary"]
    # coverage 4/8 x mean gain over the covered with a session ((1 - 0) + (0 - 1)) / 2 = 0
    assert p["covered_without_opus"] == 2 and p["diff"] == 0.0
    total = st.totals(st.tasks(rows, opus, B.full_cap), list(range(8)))
    assert total["covered"] == pytest.approx(4.0) and total["uncovered"] == pytest.approx(2.0)


def test_the_claim_needs_no_peor_and_twenty_percent_coverage():
    covered = [_jev(i, 0.9, True) for i in range(40)]
    rows = covered + [_jev(100 + i, 0.1, True) for i in range(160)]
    opus = {f"t{i:03d}": _ses(i, 0.2) for i in range(40)}
    p = st.phase_b(rows, opus, **NO_MIN)["primary"]
    assert p["coverage"] == 0.2 and p["verdict"] == "no peor" and p["claim"] == "sustituye"
    few = st.phase_b(
        rows[:39] + rows[40:], {k: v for k, v in opus.items() if k != "t039"}, **NO_MIN
    )
    assert few["primary"]["claim"] == "no sustituye"


def test_lowered_cap_stops_are_not_run_in_the_primary_and_wrong_in_the_sensitivity():
    rows = [_jev(0, 0.9, True), _jev(1, 0.9, True), _jev(2, 0.1, True)]
    lowered = {**_ses(0, 2.5, cap_usd=2.5, hit_cap=True), "letter": None, "ok": False}
    full = {**_ses(1, 6.0, cap_usd=6.0, hit_cap=True), "letter": None, "ok": False}
    got = st.phase_b(rows, {"t000": lowered, "t001": full, "t002": _ses(2, 0.3)}, **NO_MIN)
    assert got["primary"]["opus_sessions"] == 1  # the full-cap stop stays (wrong)
    assert got["sensitivity_not_run_as_wrong"]["opus_sessions"] == 2
    assert got["primary"]["diff"] > 0 and got["sessions"]["lowered_stop_no_letter"] == 1
    assert got["saving_sensitivity_reduced_cap_at_full"]["usd"]["covered"] == pytest.approx(12.0)
    assert got["saving"]["usd"]["covered"] == pytest.approx(8.5)


def test_no_verdict_while_a_phase_is_paused(tmp_path):
    assert lb.pause_reasons(B, {"kind": "done"}, tmp_path) == []
    assert lb.pause_reasons(B, {"kind": "ceiling"}, tmp_path) == []
    assert lb.pause_reasons(B, {"kind": "limit"}, tmp_path) == ["phase B limit"]
    assert lb.pause_reasons(A, None, tmp_path) == ["phase A not run"]
    (tmp_path / "LIMIT.flag").write_text("")
    assert lb.pause_reasons(B, {"kind": "done"}, tmp_path) == ["LIMIT.flag in the run folder"]
    rows = [_jev(0, 0.9, True), _jev(1, 0.1, True)]
    got = st.phase_b(rows, {"t000": _ses(0, 1.0)}, paused=["x"], **NO_MIN)
    assert got["primary"]["verdict"] == "pausa" and got["primary"]["claim"] is None
    assert got["saving"]["reading"] == "pausa"


# --- the saving (phase A) -------------------------------------------------------------------------


def test_the_sonnet_share_is_sonnet_on_the_covered_minus_jev_over_sonnet_alone():
    rows = [_jev(0, 0.9, True), _jev(1, 0.7, False), _jev(2, 0.3, True), _jev(3, 0.2, False)]
    lb162_s = {r["id"]: r for r in (_ses(0, 0.10), _ses(1, 0.30))}
    lb162x_s = {r["id"]: r for r in (_ses(2, 0.20, ok=False), _ses(3, 0.40))}
    got = st.phase_a(rows, lb162_s, lb162x_s, min_saving=0)
    s = got["saving"]  # alone 0.10 + 0.30 + 0.20 + 0.40 = 1.00; hybrid 0.04 Jev + 0.60 = 0.64
    assert s["share"] == pytest.approx(0.36) and s["usd"]["saving"] == pytest.approx(0.36)
    assert s["uncovered_measured"] == 2 and s["bootstrap"]["kept"] == 10_000
    a = got["accuracy"]
    assert a["alone_right_uncovered"] == 1 and a["jev_right_uncovered"] == 1
    assert a["alone_right"] == 3 and a["hybrid_right"] == 2  # Jev wrong on t001
    assert got["hybrid_minus_sonnet_reread"]["diff"] == pytest.approx(-0.25)


def test_a_ceiling_stop_in_phase_a_keeps_a_ratio_estimate_and_no_session_is_no_measure():
    rows = [_jev(0, 0.9, True), _jev(1, 0.1, True), _jev(2, 0.1, True), _jev(3, 0.1, True)]
    lb162_s = {"t000": _ses(0, 1.0)}
    part = st.tasks(rows, {**lb162_s, "t001": _ses(1, 0.5)}, A.full_cap)
    assert st.totals(part, [0, 1, 2, 3])["uncovered"] == pytest.approx(1.5)
    assert st.share(st.tasks(rows, lb162_s, A.full_cap), [0, 1, 2, 3]) is None
    assert st.phase_a(rows, lb162_s, {}, min_saving=0)["saving"]["reading"] == "no medido"


def test_the_saving_reading_rule_and_where_the_estimate_falls():
    assert st.reading((0.0001, 0.4)) == "ahorra"
    assert st.reading((0.0, 0.4)) == "no concluyente"
    assert st.reading((-0.2, 0.0)) == "no ahorra"
    assert st.reading(None) == "no medido"
    assert st.estimate_check((0.20, 0.30)) == "estimate inside the CI"
    assert st.estimate_check((0.28, 0.40)) == "estimate below the CI"
    assert st.estimate_check((0.10, 0.25)) == "estimate above the CI"


def test_lb162s_recorded_rows_alone_give_no_measurement_yet():
    rows = lb.jev_rows()
    got = st.phase_a(rows, lb.by_id(lb.lb162.SONNET_ROWS), {}, paused=["phase A not run"])
    s = got["saving"]
    assert s["n"] == 162 and s["covered"] == 60 and s["uncovered"] == 102
    assert s["uncovered_measured"] == 0 and s["share"] is None and s["reading"] == "pausa"
    b = st.phase_b(rows, {}, paused=["phase B not run"], **NO_MIN)["primary"]
    assert b["covered"] == 60 and b["opus_sessions"] == 0 and b["verdict"] == "pausa"


def test_the_dry_mode_gives_both_phases_money_and_clock():
    lines = lb.dry(dt.datetime(2026, 10, 16, 9), with_power=False)
    text = "\n".join(lines)
    assert "as committed" in lines[0] and text.index("phase B") < text.index("phase A")
    assert "ceiling 45" in text and "ceiling 16" in text
    assert "by 19:46" in text and "by 22:13" in text


# --- the seal -----------------------------------------------------------------------------------


def test_a_seal_round_trip_and_no_quiet_reseal(tmp_path, monkeypatch):
    monkeypatch.setattr(lb, "OUT", tmp_path)
    monkeypatch.setattr(lb, "REPO", tmp_path)
    monkeypatch.setattr(lb, "SEALED", ("code.py",))
    monkeypatch.setattr(lb, "SEALED_GLOBS", ())
    monkeypatch.setattr(lb, "SEALED_DATA", ())
    monkeypatch.setattr(lb, "PIN_FILES", ())
    monkeypatch.setattr(
        lb,
        "ORDER",
        (
            dataclasses.replace(
                B, rows=tmp_path / "opus-rows.jsonl", stop=tmp_path / "opus-stop.json"
            ),
        ),
    )
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
    (tmp_path / "opus-stop.json").write_text('{"kind": "limit"}\n')
    with pytest.raises(SystemExit, match="amendment"):
        lb.seal(again=True)
    (tmp_path / "code.py").write_text("x = 1\n")
    lb.require_prereg()
    docs["value"] = "changed"
    assert lb.docs_problems() != []


def test_the_seal_covers_every_file_the_driver_loads_and_lb162s_recordings():
    probe = (
        "import importlib.util, json, pathlib, sys\n"
        "root = pathlib.Path(sys.argv[1])\n"
        "for name, rel in (('lb162x', 'benchmarks/jev114/lb162x.py'),\n"
        "                  ('h2h_lb162x', 'benchmarks/h2h/h2h_lb162x.py')):\n"
        "    spec = importlib.util.spec_from_file_location(name, root / rel)\n"
        "    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod\n"
        "    spec.loader.exec_module(mod)\n"
        "h2h = sys.modules['h2h_lb162x']; h2h.common.local_hook_problems()\n"
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
    read = {
        p.relative_to(ROOT).as_posix()
        for p in (*lb.RECORDED, lb.lb162.ANSWERS, lb.lb162.IDS_FILE, A.ids_file, B.ids_file)
    }
    assert {"tests/test_lb162x.py", *read} <= sealed


def test_the_seal_takes_every_package_file_and_the_pinned_build(monkeypatch):
    sealed = lb.sealed_paths()
    assert not any("__pycache__" in p for p in sealed)
    assert any(p.startswith("src/sanchopanza/") and not p.endswith(".py") for p in sealed)
    assert lb.PIN_FILES == (".cache/sanchopanza/claude-pin/2.1.287/claude.exe",)
    assert "benchmarks/h2h/lb162x_guard.py" in sealed


# --- the minima, another model, power -------------------------------------------------------------


def test_no_verdict_on_fewer_than_20_covered_opus_sessions_nor_a_saving_on_fewer_than_40():
    assert st.MIN_COVERED_SESSIONS == 20 and st.MIN_SAVING_SESSIONS == 40
    rows = [_jev(i, 0.9, True) for i in range(19)] + [_jev(100 + i, 0.1, True) for i in range(15)]
    opus = {r["id"]: _ses(int(r["id"][1:]), 0.2) for r in rows}
    got = st.phase_b(rows, opus)
    assert got["primary"]["verdict"] == "no medido" and got["primary"]["claim"] is None
    assert got["saving"]["reading"] == "no medido" and got["saving"]["own_sessions"] == 34
    more = rows + [_jev(19, 0.9, True)] + [_jev(200 + i, 0.1, True) for i in range(10)]
    opus = {r["id"]: _ses(int(r["id"][1:]), 0.2) for r in more}
    got = st.phase_b(more, opus)
    assert got["primary"]["verdict"] == "no peor" and got["saving"]["reading"] == "ahorra"
    covered = {r["id"]: opus[r["id"]] for r in more if r["j14-L"]["p"] >= 0.6}
    uncovered = {k: v for k, v in opus.items() if k not in covered}
    sonnet = st.phase_a(more, covered, uncovered)["saving"]
    assert sonnet["own_sessions"] == 25 and sonnet["reading"] == "no medido"
    assert st.phase_a(more, covered, uncovered, min_saving=0)["saving"]["reading"] == "ahorra"


def test_a_session_another_model_served_is_not_run():
    rows = [_jev(0, 0.9, True), _jev(1, 0.9, True)]
    other = _ses(0, 0.3, ok=False, served_ok=False)
    got = st.phase_b(rows, {"t000": other, "t001": _ses(1, 0.3)}, **NO_MIN)
    assert got["primary"]["opus_sessions"] == 1


def test_the_power_table_reaches_the_peor_claim():
    assert {0.9, 0.95} <= set(lb.ACCURACIES)


# --- the live checkout, the refusals and their exit codes -----------------------------------------


def _git(branch=False, message="seal abc", status=""):
    answers = {"symbolic-ref": (0 if branch else 1, ""), "log": (0, message),
               "status": (0, status)}  # fmt: skip
    return lambda args: answers[args[0]]


def test_live_runs_only_from_a_clean_checkout_detached_at_the_sealed_commit():
    assert lb.checkout_problems("abc", _git()) == []
    out = (" M docs/results/2026-10-16-lb162x/opus-rows.jsonl\n"
           "?? docs/results/2026-10-16-lb162x/opus-stop.json\n")  # fmt: skip
    assert lb.checkout_problems("abc", _git(status=out)) == []
    assert "branch" in lb.checkout_problems("abc", _git(branch=True))[0]
    assert "seal" in lb.checkout_problems("abc", _git(message="other"))[0]
    dirty = lb.checkout_problems("abc", _git(status=" M benchmarks/h2h/h2h_lb162x.py\n"))
    assert dirty and "h2h_lb162x.py" in dirty[0]


@pytest.mark.parametrize("raised, kind, code", [
    (SystemExit("no seal"), "preflight", 3), (RuntimeError("boom"), "error", 7),
])  # fmt: skip
def test_a_phase_that_raises_ends_in_a_stop_kind_never_exit_1(tmp_path, raised, kind, code):
    phase = dataclasses.replace(B, stop=tmp_path / "opus-stop.json")

    def run(p, found):
        raise raised

    got = h2h.guarded_run(phase, [], run, tmp_path)
    assert got == kind and h2h.exit_code(got) == code
    assert json.loads(phase.stop.read_text()) == {"kind": kind}


def test_a_usage_limit_writes_the_flag(tmp_path):
    phase = dataclasses.replace(A, stop=tmp_path / "sonnet-stop.json")
    assert h2h.guarded_run(phase, [], lambda p, f: "limit", tmp_path) == "limit"
    assert (tmp_path / "LIMIT.flag").exists() and h2h.exit_code("limit") == 2


def test_the_start_refusals_and_their_exit_codes(tmp_path, monkeypatch):
    monkeypatch.setattr(h2h.lb162x, "require_prereg", lambda: "abc")
    monkeypatch.setattr(h2h.lb162x, "checkout_problems", lambda value: [])
    monkeypatch.setattr(h2h, "pin_problems", lambda: [])
    monkeypatch.setattr(h2h, "final_kind", lambda p: None)
    monkeypatch.setattr(h2h, "done_now", lambda p: 0)
    day = dt.datetime(2026, 10, 16)
    assert h2h.refusal(day.replace(hour=9), tmp_path) is None
    assert h2h.refusal(day.replace(hour=7), tmp_path)[0] == "clock"  # exit 5
    assert h2h.refusal(day.replace(hour=20), tmp_path)[0] == "clock"  # B would cross midnight
    (tmp_path / "LIMIT.flag").write_text("")
    assert h2h.refusal(day.replace(hour=9), tmp_path)[0] == "limit"

    def unsealed():
        raise SystemExit("prereg.md, the code or the inputs differ from the seal")

    monkeypatch.setattr(h2h.lb162x, "require_prereg", unsealed)
    assert h2h.refusal(day.replace(hour=9), tmp_path) == (
        "preflight",
        str(SystemExit("prereg.md, the code or the inputs differ from the seal")),
    )  # exit 3
    assert {k: h2h.exit_code(k) for k in ("clock", "limit", "preflight")} == {
        "clock": 5,
        "limit": 2,
        "preflight": 3,
    }


# --- the smoke ----------------------------------------------------------------------------------


def test_the_smoke_is_one_opus_session_on_a_dev_task_outside_the_162():
    task = h2h.smoke_task()
    assert task.task_id not in set(lb.lb162.frozen_ids())
    assert lb.SMOKE.model_id == "claude-opus-5-5" and lb.SMOKE.ceiling == 0.80
    assert h2h.smoke_cap(0.0) == 0.80 and h2h.smoke_cap(0.01) is None
    assert lb.DRIVEN == (lb.SMOKE, B, A)
    good = {"letter": "C", "is_error": False, "served_ok": True}
    assert h2h.smoke_passed([good]) and not h2h.smoke_passed([{**good, "letter": None}])
    assert not h2h.smoke_passed([{**good, "served_ok": False}]) and not h2h.smoke_passed([])
