"""Lot lbo8's live driver (benchmarks/h2h/h2h_lbo8.py) and phase J's live entry and seal
(benchmarks/jev114/lbo8.py), with no network and no session: the refusals and their exit codes
(no seal, a dirty or attached checkout, LIMIT.flag, the clock), phase O's money rule, the phase
order, phase J's own ledger and stops, rows without text, and the seal."""

from __future__ import annotations

import dataclasses
import datetime as dt
import importlib.util
import json
import os
import subprocess
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
h2h = _load("h2h_lbo8", "benchmarks/h2h/h2h_lbo8.py")
lb162x = lbo8.lb162x
O, J, S = lbo8.PHASE_O, lbo8.PHASE_J, lbo8.SMOKE  # noqa: E741
DAY = dt.datetime(2026, 10, 16)


# --- the registered constants ---------------------------------------------------------------------


def test_the_registered_lot():
    assert lbo8.MARGIN == -0.05 and lbo8.CUT == 0.8 and lbo8.MIN_COVERED_SESSIONS == 8
    assert (O.ceiling, O.full_cap, O.floor, O.worst_turn) == (30.0, 6.0, 1.0, 8.64)
    assert O.model_id == "claude-opus-5-5" and O.n == 78 and O.arm == "OPUS-CC"
    assert lbo8.JEV_CAP_USD == 0.20 and lbo8.LOT_CEILING_USD == 31.00
    assert (S.ceiling, S.full_cap, S.model_id) == (0.80, 0.80, "claude-opus-5-5")
    assert lbo8.DRIVEN == (S, J, O)


def test_the_smoke_and_phase_o_have_their_own_folders_and_results_not_lb162xs():
    for mine, theirs in ((S, lb162x.SMOKE), (O, lb162x.PHASE_B)):
        assert mine.name != theirs.name and mine.rows != theirs.rows and mine.stop != theirs.stop
        assert mine.rows.parent == lbo8.OUT and mine.stop.parent == lbo8.OUT
        assert h2h.sessions_of(mine) != h2h.sessions_of(theirs)


def test_phase_js_ledger_is_this_lots_own():
    assert Path("C:/sp-runs/lbo8") == lbo8.RUN_DIR
    assert lbo8.jev_ledger() == Path("C:/sp-runs/lbo8/jev-ledger.jsonl")
    assert lbo8.BATCH == "lbo8" and lbo8.BATCH != lbo8.lb162.BATCH
    assert lbo8.jev_ledger() != lbo8.lb162.LEDGER_PATH
    assert h2h.ledger_problems(Path("C:/sp-runs/lbo8")) == []
    assert h2h.ledger_problems(Path("C:/sp-runs/w17-jev")) != []
    assert h2h.ledger_problems(Path("C:/sp-runs/lb162")) != []


def test_phase_o_runs_all_78_in_a_seeded_order():
    ids = lbo8.read_ids(lbo8.IDS_FILE)
    order = lbo8.opus_order()
    assert sorted(order) == sorted(ids) and len(order) == 78 and order != sorted(order)
    assert order == lb162x.shuffled(ids, 20261016) == lbo8.opus_order(list(reversed(ids)))
    with pytest.raises(SystemExit, match="78"):
        lbo8.opus_order(ids[:77])


# --- money ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("spent, cap", [
    (0.0, 6.0), (15.36, 6.0), (15.37, 5.99), (18.0, 3.36), (20.36, 1.0), (20.361, None),
    (29.0, None),
])  # fmt: skip
def test_cap_for_is_the_full_cap_while_it_fits_then_the_room_left_then_none(spent, cap):
    got = lb162x.cap_for(spent, O)
    assert got == (None if cap is None else pytest.approx(cap))
    if got is not None:
        assert spent + got + O.worst_turn <= O.ceiling + 1e-9


def test_the_phase_loop_and_the_cap_rule_stop_at_the_same_spend():
    limits = h2h.x.phase_loop.Limits(session_max_usd=O.loop_reserve, ceiling_usd=O.ceiling)
    for cents in range(1500, 3000):
        spent = cents / 100
        loop_stops = h2h.x.phase_loop.stop_reason([{"list_usd": spent}], limits, 0) is not None
        assert loop_stops == (lb162x.cap_for(spent, O) is None), spent


def test_sessions_at_worst_and_at_one_point_six_times_the_expected_cost():
    assert lb162x.guaranteed(O) == 2
    assert lb162x.at_mean(O, lbo8.OPUS_EST_USD * 1.6, O.n) == O.n


def test_the_guard_takes_this_lots_run_folder(tmp_path):
    sessions, reservations = tmp_path / "s.jsonl", tmp_path / "r.jsonl"
    guard = h2h.guard_mod.Budget(O, DAY.replace(hour=9), sessions, reservations,
                                 clock=lambda: DAY.replace(hour=9), run_dir=tmp_path)  # fmt: skip
    called = []

    def session(item, run, arm, cap):
        called.append(cap)
        return {"task_id": item[0], "run": run, "arm": arm, "list_usd": 0.1, "ok": True,
                "final_answer": "A", "usd_by_model": {O.model_id: 0.1}}  # fmt: skip

    one = guard.wrap(session)
    one(("t1", "", "", None), 1, O.arm)
    assert called == [6.0]
    (tmp_path / "STOP").write_text("")
    with pytest.raises(h2h.s162.ClockStop):
        one(("t2", "", "", None), 1, O.arm)
    assert guard.kind == "manual" and called == [6.0]


# --- the clock ------------------------------------------------------------------------------------


def test_the_clock_refuses_early_starts_and_runs_across_midnight():
    assert h2h.clock_refusal(O, DAY.replace(hour=7, minute=59), 78) != ""
    assert h2h.clock_refusal(O, DAY.replace(hour=23, minute=1), 78) == ""
    assert "midnight" in h2h.clock_refusal(O, DAY.replace(hour=23, minute=2), 78)
    assert h2h.clock_refusal(J, DAY.replace(hour=7), 78) != ""
    assert h2h.clock_refusal(J, DAY.replace(hour=23, minute=40), 78) != ""
    assert h2h.clock_refusal(J, DAY.replace(hour=9), 78) == ""


# --- the start refusals ---------------------------------------------------------------------------


def _git(branch=False, message="seal abc", status=""):
    answers = {"symbolic-ref": (0 if branch else 1, ""), "log": (0, message),
               "status": (0, status)}  # fmt: skip
    return lambda args: answers[args[0]]


@pytest.fixture
def sealed(monkeypatch):
    monkeypatch.setattr(lbo8, "require_prereg", lambda: "abc")
    monkeypatch.setattr(h2h.x, "pin_problems", lambda: [])
    monkeypatch.setattr(h2h, "final_kind", lambda p: None)
    monkeypatch.setattr(h2h, "done_now", lambda p: 0)


def test_a_sealed_clean_detached_checkout_may_start(tmp_path, sealed):
    assert h2h.refusal(DAY.replace(hour=9), tmp_path, _git()) is None


def test_no_seal_refuses_with_exit_3(tmp_path, sealed, monkeypatch):
    def unsealed():
        raise SystemExit("prereg.md, the code or the inputs differ from the seal: nothing spent")

    monkeypatch.setattr(lbo8, "require_prereg", unsealed)
    kind, why = h2h.refusal(DAY.replace(hour=9), tmp_path, _git())
    assert kind == "preflight" and "seal" in why and h2h.exit_code(kind) == 3


@pytest.mark.parametrize("git, said", [
    (_git(branch=True), "branch"),
    (_git(message="other"), "seal"),
    (_git(status=" M benchmarks/h2h/h2h_lbo8.py\n"), "h2h_lbo8.py"),
    (_git(status="?? notes.txt\n"), "notes.txt"),
])  # fmt: skip
def test_a_dirty_or_attached_checkout_refuses_with_exit_3(tmp_path, sealed, git, said):
    kind, why = h2h.refusal(DAY.replace(hour=9), tmp_path, git)
    assert kind == "preflight" and said in why and h2h.exit_code(kind) == 3


def test_this_lots_outputs_do_not_dirty_the_checkout():
    status = "".join(f"?? {p}\n" for p in lbo8.OUTPUTS)
    assert lbo8.checkout_problems("abc", _git(status=status)) == []
    assert {
        "docs/results/2026-10-16-lbo8/opus-rows.jsonl",
        "docs/results/2026-10-16-lbo8/jev-scored.jsonl",
        "docs/results/2026-10-16-lbo8/jev-answers-j14-L.jsonl",
    } <= set(lbo8.OUTPUTS)


def test_a_limit_flag_refuses_with_exit_2(tmp_path, sealed):
    (tmp_path / "LIMIT.flag").write_text("")
    kind, _ = h2h.refusal(DAY.replace(hour=9), tmp_path, _git())
    assert kind == "limit" and h2h.exit_code(kind) == 2


@pytest.mark.parametrize("hour, minute", [(7, 0), (1, 30), (23, 2), (23, 50)])
def test_the_clock_refuses_with_exit_5(tmp_path, sealed, hour, minute):
    kind, _ = h2h.refusal(DAY.replace(hour=hour, minute=minute), tmp_path, _git())
    assert kind == "clock" and h2h.exit_code(kind) == 5


def test_another_lots_run_folder_refuses(sealed):
    kind, why = h2h.refusal(DAY.replace(hour=9), Path("C:/sp-runs/w17-jev"), _git())
    assert kind == "preflight" and "another lot" in why


def test_nothing_left_is_done(tmp_path, sealed, monkeypatch):
    monkeypatch.setattr(h2h, "final_kind", lambda p: "done")
    assert h2h.refusal(DAY.replace(hour=9), tmp_path, _git())[0] == "done"


# --- the phase order and the stop kinds -----------------------------------------------------------


@pytest.mark.parametrize("kinds, final, lot, ran", [
    ({"S": "done", "J": "done", "O": "done"}, {}, "done", ["S", "J", "O"]),
    ({"S": "smoke"}, {}, "smoke", ["S"]),
    ({"S": "ceiling"}, {}, "ceiling", ["S"]),  # a smoke stopped by its ceiling does not pass
    ({"J": "jev"}, {"S": "done"}, "jev", ["J"]),
    ({"J": "ceiling", "O": "done"}, {"S": "done"}, "ceiling", ["J", "O"]),  # J's cap is final
    ({"J": "manual"}, {"S": "done"}, "manual", ["J"]),
    ({"J": "preflight"}, {"S": "done"}, "preflight", ["J"]),
    ({"O": "limit"}, {"S": "done", "J": "done"}, "limit", ["O"]),
    ({"O": "clock"}, {"S": "done", "J": "done"}, "clock", ["O"]),
    ({"O": "outage"}, {"S": "done", "J": "done"}, "outage", ["O"]),
    ({"O": "ceiling"}, {"S": "done", "J": "done"}, "ceiling", ["O"]),
    ({"O": "weird"}, {"S": "done", "J": "done"}, "error", ["O"]),
    ({}, {"S": "done", "J": "done", "O": "done"}, "done", []),
])  # fmt: skip
def test_the_driver_runs_the_smoke_then_j_then_o_and_stops_at_the_first_pause(
    kinds, final, lot, ran
):
    seen = []

    def run_one(phase):
        seen.append(phase.key)
        return kinds[phase.key]

    got, _ = h2h.x.drive(lbo8.DRIVEN, run_one, lambda p: final.get(p.key))
    assert got == lot and seen == ran
    codes = {"done": 0, "ceiling": 1, "limit": 2, "preflight": 3, "jev": 4, "clock": 5,
             "manual": 6, "error": 7, "outage": 8, "smoke": 9}  # fmt: skip
    assert h2h.exit_code(got) == codes[got]


def test_final_kinds_read_this_lots_stop_files(tmp_path):
    phase = dataclasses.replace(J, stop=tmp_path / "jev-stop.json")
    assert h2h.final_kind(phase) is None
    phase.stop.write_text('{"kind": "jev"}\n')
    assert h2h.final_kind(phase) is None
    phase.stop.write_text('{"kind": "ceiling"}\n')
    assert h2h.final_kind(phase) == "ceiling"
    smoke = dataclasses.replace(S, stop=tmp_path / "smoke-stop.json")
    smoke.stop.write_text('{"kind": "ceiling"}\n')
    assert h2h.final_kind(smoke) is None  # the smoke passes only as done


@pytest.mark.parametrize("raised, kind", [
    (SystemExit("phase J does not fit"), "preflight"), (RuntimeError("boom"), "error"),
])  # fmt: skip
def test_a_phase_that_raises_ends_in_a_stop_kind(tmp_path, raised, kind):
    phase = dataclasses.replace(J, stop=tmp_path / "jev-stop.json")

    def run(p, found):
        raise raised

    assert h2h.x.guarded_run(phase, [], run, tmp_path) == kind
    assert json.loads(phase.stop.read_text()) == {"kind": kind}


def test_a_usage_limit_in_phase_o_writes_the_flag_in_this_lots_folder(tmp_path):
    phase = dataclasses.replace(O, stop=tmp_path / "opus-stop.json")
    assert h2h.x.guarded_run(phase, [], lambda p, f: "limit", tmp_path) == "limit"
    assert (tmp_path / "LIMIT.flag").exists()


# --- phase J --------------------------------------------------------------------------------------


@pytest.mark.parametrize("stop, kind", [
    (None, "done"), ("cap", "ceiling"), ("manual", "manual"), ("funds", "jev"),
    ("limit", "jev"), ("outage", "jev"), ("failures", "jev"),
])  # fmt: skip
def test_phase_js_stops_as_the_drivers_kinds(stop, kind):
    assert lbo8.jev_kind(stop) == kind
    assert kind in h2h.EXIT


def test_phase_j_refuses_before_any_call_with_a_preflight_problem_the_clock_or_stop(tmp_path):
    called = []

    def run(run_dir):
        called.append(run_dir)
        return "done"

    with pytest.raises(SystemExit, match="preflight"):
        h2h.run_jev(["no pinned claude"], tmp_path, lambda: DAY.replace(hour=9), run)
    assert h2h.run_jev([], tmp_path, lambda: DAY.replace(hour=7), run) == "clock"
    (tmp_path / "STOP").write_text("")
    assert h2h.run_jev([], tmp_path, lambda: DAY.replace(hour=9), run) == "manual"
    assert called == []
    (tmp_path / "STOP").unlink()
    assert h2h.run_jev([], tmp_path, lambda: DAY.replace(hour=9), run) == "done"
    assert called == [tmp_path]


def _task(i: int, chars: int = 70_000):
    return dataclasses.make_dataclass("T", ["task_id", "chars"])(f"t{i:02d}", chars)


def test_phase_j_scored_already_is_not_asked_again(tmp_path, monkeypatch):
    rows = tmp_path / "jev-scored.jsonl"
    rows.write_text(json.dumps({"id": "t00", "status": "answered"}) + "\n")
    monkeypatch.setattr(lbo8, "JEV_ROWS", rows)

    def never(*_):
        raise AssertionError("called")

    assert lbo8.run_phase_j(tmp_path, [_task(0)], never, never, never) == "done"


def test_phase_j_that_does_not_fit_its_cap_refuses_before_the_key_or_a_call(tmp_path, monkeypatch):
    monkeypatch.setattr(lbo8, "JEV_ROWS", tmp_path / "jev-scored.jsonl")
    started = []
    huge = [_task(i, 900_000) for i in range(78)]  # 70.2 M characters shown: about 1.05 USD
    with pytest.raises(SystemExit, match="does not fit"):
        lbo8.run_phase_j(tmp_path, huge, lambda *a: None, lambda: started.append(1), list)
    assert started == []
    assert lbo8.jev_plan_refusal(0.0, [_task(i) for i in range(78)]) == ""
    assert lbo8.jev_plan_refusal(0.15, [_task(i) for i in range(78)]) != ""


def test_phase_j_is_over_when_all_78_are_scored_or_its_cap_stopped_it():
    done = [{"status": "answered"}] * 77 + [{"status": "failed"}]
    assert lbo8.phase_j_final(done, None) == ""
    assert "78" in lbo8.phase_j_final(done[:77], None)
    stopped = done[:77] + [{"status": "stopped"}]
    assert "paused" in lbo8.phase_j_final(stopped, {"kind": "jev"})
    assert lbo8.phase_j_final(stopped, {"kind": "ceiling"}) == ""


def test_no_reading_while_a_phase_is_paused(tmp_path, monkeypatch):
    monkeypatch.setattr(lbo8, "JEV_ROWS", tmp_path / "jev-scored.jsonl")
    monkeypatch.setattr(lbo8, "PHASE_J", dataclasses.replace(J, stop=tmp_path / "j.json"))
    monkeypatch.setattr(lbo8, "PHASE_O", dataclasses.replace(O, stop=tmp_path / "o.json"))
    assert lbo8.pause_reasons(tmp_path) == ["phase J has not scored the 78 tasks",
                                            "phase O not run"]  # fmt: skip
    lbo8.lb162.write_jsonl(lbo8.JEV_ROWS, [{"status": "answered"}] * 78)
    (tmp_path / "o.json").write_text('{"kind": "done"}\n')
    assert lbo8.pause_reasons(tmp_path) == []
    (tmp_path / "LIMIT.flag").write_text("")
    assert lbo8.pause_reasons(tmp_path) == ["LIMIT.flag in the run folder"]


# --- rows without text ----------------------------------------------------------------------------


def test_public_rows_keep_ids_letters_grades_and_costs_only():
    session = {"task_id": "t1", "task": "t1", "run": 1, "arm": "OPUS-CC", "final_answer": "D",
               "ok_oficial": True, "list_usd": 0.12, "wall_s": 20.0, "turns": 4,
               "hit_cap": False, "answer": "SECRET reply", "ok": True, "subtype": "success",
               "cap_usd": 6.0, "workdir": "C:/sp-runs/h2h/lbo8-opus/abc/work",
               "usd_by_model": {"claude-opus-5-5": 0.12}}  # fmt: skip
    rows = [session, {**session, "arm": "SONNET-CC"}, {**session, "task_id": "t2",
                                                       "not_run": True}]  # fmt: skip
    got = h2h.x.public_rows(rows, O)
    assert len(got) == 1 and got[0]["id"] == "t1" and got[0]["served_ok"] is True
    assert set(got[0]) == {"id", "cap_usd", "served_ok", *h2h.s162.ROW_KEYS}
    text = json.dumps(got)
    assert "SECRET" not in text and "sp-runs" not in text


class _Answer:
    empty, choice, probabilities = False, "A", {"A": 0.91, "B": 0.09}


class _Decision:
    error, cost_usd, input_tokens, answers = None, 0.0012, 17_000, True

    def answer(self, _name):
        return _Answer()


class _Arm:
    def __init__(self):
        self.seen = []

    async def decide(self, point, state, questions):
        self.seen.append(state)
        return _Decision()


def test_phase_js_rows_hold_letters_and_probabilities_not_text(tmp_path):
    import asyncio

    doc = tmp_path / "doc.txt"
    doc.write_text("SECRET document " * 100, encoding="utf-8")
    fields = ["task_id", "gold", "chars", "length", "difficulty", "doc_path", "question",
              "choices"]  # fmt: skip
    task = dataclasses.make_dataclass("Task", fields)(
        "t1", "A", 1600, "short", "hard", str(doc), "SECRET question?",
        ("SECRET a", "SECRET b", "SECRET c", "SECRET d"))  # fmt: skip
    arm = _Arm()
    row = asyncio.run(lbo8.lb162.jev_one(task, arm, lbo8.lb162.Stop(max_consecutive=None)))
    assert arm.seen and "SECRET" in json.dumps(arm.seen)  # the request had the text
    assert "SECRET" not in json.dumps(row)  # the row keeps none of it
    assert row["status"] == "answered" and row[lbo8.lb162.CELL]["p"] == 0.91
    assert lbo8.lb162.stats.is_covered(row, lbo8.CUT)


# --- the launcher and the preflight ---------------------------------------------------------------


def test_the_launcher_check(tmp_path):
    good = tmp_path / "launch.ps1"
    good.write_text("[ValidateSet('h2h_gaia.py', 'h2h_lb162x.py', 'h2h_lbo8.py')]")
    assert h2h.launcher_problems(good) == []
    bad = tmp_path / "old.ps1"
    bad.write_text("[ValidateSet('h2h_gaia.py', 'h2h_lb162x.py')]")
    assert h2h.launcher_problems(bad) != []


# --- the seal -------------------------------------------------------------------------------------


def test_a_seal_round_trip_and_no_quiet_reseal(tmp_path, monkeypatch):
    for name, value in (
        ("OUT", tmp_path),
        ("REPO", tmp_path),
        ("SEALED", ("code.py",)),
        ("SEALED_GLOBS", ()),
        ("SEALED_DATA", ()),
        ("PIN_FILES", ()),
        ("ANSWERS", tmp_path / "answers.jsonl"),
        ("DRIVEN", (dataclasses.replace(O, rows=tmp_path / "o.jsonl", stop=tmp_path / "o.json"),)),
    ):
        monkeypatch.setattr(lbo8, name, value)  # fmt: skip
    docs = {"value": "first"}
    monkeypatch.setattr(lbo8, "docs_digest", lambda: docs["value"])
    (tmp_path / "prereg.md").write_text("plan\n")
    (tmp_path / "code.py").write_text("x = 1\n")
    assert lbo8.seal_state() == "not sealed"
    with pytest.raises(SystemExit, match="seal"):
        lbo8.require_prereg()
    value = lbo8.seal()
    assert lbo8.require_prereg() == value and lbo8.seal_state() == "sealed, matches"
    (tmp_path / "code.py").write_text("x = 2\n")
    assert lbo8.seal_state() == "MISMATCH"
    with pytest.raises(SystemExit, match="another seal"):
        lbo8.seal()
    (tmp_path / "answers.jsonl").write_text("{}\n")
    with pytest.raises(SystemExit, match="amendment"):
        lbo8.seal(again=True)
    (tmp_path / "code.py").write_text("x = 1\n")
    lbo8.require_prereg()
    docs["value"] = "changed"
    assert lbo8.docs_problems() != []


def test_the_seal_covers_every_file_the_driver_loads():
    probe = (
        "import importlib.util, json, pathlib, sys\n"
        "root = pathlib.Path(sys.argv[1])\n"
        "for name, rel in (('lbo8', 'benchmarks/jev114/lbo8.py'),\n"
        "                  ('h2h_lbo8', 'benchmarks/h2h/h2h_lbo8.py')):\n"
        "    spec = importlib.util.spec_from_file_location(name, root / rel)\n"
        "    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod\n"
        "    spec.loader.exec_module(mod)\n"
        "import lbo8_stats\n"
        "h2h = sys.modules['h2h_lbo8']; h2h.common.local_hook_problems()\n"
        "files = {pathlib.Path(m.__file__).resolve() for m in list(sys.modules.values())\n"
        "         if getattr(m, '__file__', None)}\n"
        "print(json.dumps(sorted(p.relative_to(root).as_posix() for p in files\n"
        "                        if root in p.parents)))\n"
    )  # fmt: skip
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    done = subprocess.run([sys.executable, "-c", probe, str(ROOT)], capture_output=True,
                          text=True, env=env, timeout=120, check=True)  # fmt: skip
    loaded = {p for p in json.loads(done.stdout) if p.startswith(("benchmarks/", "src/"))}
    sealed = set(lbo8.sealed_paths())
    assert loaded and loaded <= sealed, sorted(loaded - sealed)
    assert {"tests/test_lbo8.py", "tests/test_lbo8_live.py", "tests/test_lbo8_stats.py",
            "docs/results/2026-10-16-lbo8/ids.txt", "benchmarks/h2h/launch.ps1",
            "benchmarks/h2h/lb162x_guard.py"} <= sealed  # fmt: skip
    assert not any("__pycache__" in p for p in sealed)
    assert lbo8.PIN_FILES == (".cache/sanchopanza/claude-pin/2.1.287/claude.exe",)
    assert ".cache/sanchopanza/longdoc/lbo8/tasks.jsonl" in lbo8.SEALED_DATA
