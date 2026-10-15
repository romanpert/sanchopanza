"""Lot lb162x's guard (benchmarks/h2h/lb162x_guard.py), with no session: the money rule before
each session (never past a phase's ceiling, a died session's reserve, a row with an unknown cost
held at its reservation, reservations matched by id) and the health check after it (an outage at
once, a streak of three infrastructure errors, a session another model served)."""

from __future__ import annotations

import datetime as dt
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


lb = _load("lb162x", "benchmarks/jev114/lb162x.py")
h2h = _load("h2h_lb162x", "benchmarks/h2h/h2h_lb162x.py")
g = h2h.guard_mod
A, B = lb.PHASE_A, lb.PHASE_B
OPUS = "claude-opus-5-5"


class Task:
    def __init__(self, i: int) -> None:
        self.task_id = f"u{i:03d}"


def _budget(tmp_path, phase, now=dt.datetime(2026, 10, 16, 10), cap_rule=None):
    sessions, reservations = tmp_path / "sessions.jsonl", tmp_path / "reservations.jsonl"
    guard = g.Budget(phase, dt.datetime(2026, 10, 16, 9), sessions, reservations,
                     cap_rule=cap_rule, clock=lambda: now, run_dir=tmp_path)  # fmt: skip
    return guard, sessions, reservations


def _row(item, run, arm, usd, **extra):
    return {"task": item[0], "task_id": item[0], "run": run, "arm": arm, "list_usd": usd,
            "ok": True, "final_answer": "A", "hit_cap": False, "subtype": "success",
            "usd_by_model": {OPUS: usd}, **extra}  # fmt: skip


def _infra(item, run, arm, cap):
    return _row(item, run, arm, 0.0, ok=False, final_answer=None, subtype="error_during_execution",
                usd_by_model={}, tokens={"input": 0, "output": 0})  # fmt: skip


def _limits(phase):
    return h2h.phase_loop.Limits(session_max_usd=phase.loop_reserve, ceiling_usd=phase.ceiling)


def _dies(item, run, arm, cap):
    raise KeyboardInterrupt


# --- money ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("phase, usd", [(A, 0.09), (A, 0.5), (A, None), (B, 0.2), (B, 1.0),
                                        (B, None)])  # fmt: skip
def test_a_phase_never_passes_its_ceiling(tmp_path, phase, usd):
    guard, sessions, _ = _budget(tmp_path, phase)
    caps = []

    def session(item, run, arm, cap):
        caps.append(cap)
        cost = cap + phase.worst_turn if usd is None else usd
        return _row(item, run, arm, cost, usd_by_model={phase.model_id: cost})

    code, rows = h2h.phase_loop.run_phase(h2h.steps(phase, [Task(i) for i in range(phase.n)]),
                                          [], _limits(phase), guard.wrap(session),
                                          sessions)  # fmt: skip
    assert sum(r["list_usd"] for r in rows) <= phase.ceiling + 1e-9
    assert all(c >= phase.floor for c in caps) and all(r["arm"] == phase.arm for r in rows)
    if usd in (0.09, 0.2):  # all run, the last ones on a lowered cap
        assert code == 0 and len(rows) == phase.n and caps[0] == phase.full_cap
        assert min(caps) < phase.full_cap
    else:  # the money stops it (the guard or the loop's own check, the same line)
        assert code == 1 and h2h.s162.stop_kind(1, guard) == "ceiling"
        if usd is None:
            assert len(rows) == lb.guaranteed(phase)


def test_a_session_that_died_keeps_its_own_reserve_against_the_ceiling(tmp_path):
    guard, sessions, reservations = _budget(tmp_path, B)
    done = guard.wrap(lambda item, run, arm, cap: _row(item, run, arm, 30.0))(("a",), 1, B.arm)
    sessions.write_text(json.dumps(done) + "\n")
    with pytest.raises(KeyboardInterrupt):
        guard.wrap(_dies)(("b",), 1, B.arm)
    open_ = g.open_reservations([done], reservations)
    assert [(r["task"], r["list_usd"], r["not_run"]) for r in open_] == [
        ("b", pytest.approx(6.0 + 8.64), True)
    ]
    assert g.spent_now(sessions, reservations) == pytest.approx(44.64)
    with pytest.raises(h2h.common.JointCeiling, match="ceiling"):
        guard.wrap(lambda *a: {})(("c",), 1, B.arm)
    assert h2h.phase_loop.counted([done, *open_]) == [done]


def test_the_open_reservation_is_the_one_without_a_row_whatever_its_cap(tmp_path):
    """DEBE 3: the same task reserved twice at different caps; the died one stays open."""
    guard, sessions, reservations = _budget(tmp_path, B)
    with pytest.raises(KeyboardInterrupt):
        guard.wrap(_dies)(("a",), 1, B.arm)  # cap 6.00: died, no row
    other = _row(("x",), 1, B.arm, 20.0)
    sessions.write_text(json.dumps(other) + "\n")
    with_cap = guard.wrap(lambda item, run, arm, cap: _row(item, run, arm, 0.3, cap_usd=cap))
    second = with_cap(("a",), 1, B.arm)  # 20 + 14.64 held: the cap is lowered to 1.72
    assert second["cap_usd"] == pytest.approx(1.72)
    open_ = g.open_reservations([other, second], reservations)
    assert [r["list_usd"] for r in open_] == [pytest.approx(14.64)]  # not 1.72 + 8.64
    lines = [json.loads(x) for x in reservations.read_text().splitlines()]
    legacy = tmp_path / "legacy.jsonl"  # no ids: the earliest reservation of the key stays open
    legacy.write_text("".join(json.dumps({k: v for k, v in r.items() if k != "rid"}) + "\n"
                              for r in lines))  # fmt: skip
    plain = {k: v for k, v in second.items() if k != "reservation"}
    assert [r["list_usd"] for r in g.open_reservations([plain], legacy)] == [pytest.approx(14.64)]


@pytest.mark.parametrize("row, unknown", [
    ({"subtype": "runner: TimeoutExpired", "ok": False, "list_usd": 0.0}, True),
    ({"subtype": "runner: ValueError", "ok": False, "list_usd": 0.0, "tokens": {"input": 0}}, True),
    ({"subtype": "error_during_execution", "ok": False, "list_usd": 0.0,
      "tokens": {"input": 10, "output": 3, "web_searches": 0}}, True),
    ({"subtype": "error_during_execution", "ok": False, "list_usd": 0.0}, True),
    ({"subtype": "error", "ok": False, "list_usd": 0.0,
      "tokens": {"input": 0, "output": 0, "web_searches": 0}}, False),
    ({"subtype": "success", "ok": True, "list_usd": 0.2}, False),
])  # fmt: skip
def test_which_rows_have_an_unknown_cost(row, unknown):
    assert g.cost_unknown(row) is unknown


def test_a_row_with_no_cost_counts_at_its_reservation_so_the_ceiling_holds(tmp_path):
    """DEBE 2: a timed-out session reports 0 USD; it keeps its reserve."""
    guard, sessions, reservations = _budget(tmp_path, A)
    timed_out = guard.wrap(lambda item, run, arm, cap: _row(
        item, run, arm, 0.0, ok=False, final_answer=None, subtype="runner: TimeoutExpired",
        usd_by_model={}))(("a",), 1, A.arm)  # fmt: skip
    sessions.write_text(json.dumps(timed_out) + "\n")
    assert g.open_reservations([timed_out], reservations) == []
    assert g.spent_now(sessions, reservations) == pytest.approx(3.0 + 4.32)
    assert guard.spent() == pytest.approx(7.32)
    no_reservation = tmp_path / "none.jsonl"
    assert g.spent_now(sessions, no_reservation, fallback=7.32) == pytest.approx(7.32)


# --- health ---------------------------------------------------------------------------------------


def test_three_infrastructure_errors_in_a_row_are_an_outage_and_not_run(tmp_path):
    """DEBE 1: the streak's rows are marked not run, the phase stops `outage` (a pause)."""
    guard, sessions, reservations = _budget(tmp_path, B)
    tasks = [Task(i) for i in range(10)]
    code, rows = h2h.common.run_guarded(h2h.steps(B, tasks), [], _limits(B), guard.wrap(_infra),
                                        sessions)  # fmt: skip
    assert code == 1 and guard.kind == "outage"
    assert h2h.s162.stop_kind(code, guard) == "outage" and h2h.exit_code("outage") == 8
    assert len(rows) == 3 and all(r["not_run"] for r in rows)
    assert h2h.phase_loop.counted(rows) == [] and g.spent_now(sessions, reservations) == 0
    guard2, _, _ = _budget(tmp_path, B)  # resumed later: the same three asked again, free
    ok = guard2.wrap(lambda item, run, arm, cap: _row(item, run, arm, 0.2))
    code, rows = h2h.phase_loop.run_phase(h2h.steps(B, tasks[:3]), rows, _limits(B), ok, sessions)
    assert code == 0 and len(h2h.phase_loop.counted(rows)) == 3


def test_an_infrastructure_error_between_answers_is_kept_and_resets_the_streak(tmp_path):
    guard, sessions, _ = _budget(tmp_path, B)

    def answer(item, run, arm, cap):
        return _row(item, run, arm, 0.2)

    plan = iter([_infra, _infra, answer, _infra, _infra, answer])
    session = guard.wrap(lambda item, run, arm, cap: next(plan)(item, run, arm, cap))
    code, rows = h2h.phase_loop.run_phase(h2h.steps(B, [Task(i) for i in range(6)]), [],
                                          _limits(B), session, sessions)  # fmt: skip
    assert code == 0 and len(h2h.phase_loop.counted(rows)) == 6 and guard.kind is None


@pytest.mark.parametrize("text", [
    "API Error: 401 OAuth token has expired",
    "There's an issue with the selected model (claude-opus-5-5). The model claude-opus-5-5 is "
    "not available on your plan",
])  # fmt: skip
def test_an_authentication_or_model_failure_is_an_outage_at_once(tmp_path, text):
    guard, sessions, _ = _budget(tmp_path, B)
    side = tmp_path / "side"
    side.mkdir()
    (side / "stderr.txt").write_text(text)

    def broken(item, run, arm, cap):
        return _infra(item, run, arm, cap) | {"side": str(side)}

    with pytest.raises(g.OutageStop):
        guard.wrap(broken)(("a",), 1, B.arm)
    rows = h2h.gaia.read_rows(sessions)
    assert guard.kind == "outage" and len(rows) == 1 and rows[0]["not_run"]


def test_a_session_another_model_served_is_not_run_and_counts_toward_the_streak(tmp_path):
    guard, sessions, _ = _budget(tmp_path, B)

    def sonnet(item, run, arm, cap):
        return _row(item, run, arm, 0.2, usd_by_model={"claude-sonnet-5-5": 0.2, OPUS: 0.01})

    first = guard.wrap(sonnet)(("a",), 1, B.arm)
    assert first["not_run"] and "served by claude-sonnet-5-5" in first["invalid"]
    (tmp_path / "x").mkdir()
    guard2, sessions2, _ = _budget(tmp_path / "x", B)
    code, rows = h2h.common.run_guarded(h2h.steps(B, [Task(i) for i in range(5)]), [], _limits(B),
                                        guard2.wrap(sonnet), sessions2)  # fmt: skip
    assert guard2.kind == "outage" and len(rows) == 3 and h2h.phase_loop.counted(rows) == []


def test_the_smoke_takes_one_session_at_its_own_cap(tmp_path):
    guard, sessions, _ = _budget(tmp_path, lb.SMOKE, cap_rule=h2h.smoke_cap)
    caps = []

    def session(item, run, arm, cap):
        caps.append(cap)
        return _row(item, run, arm, 0.3)

    limits = h2h.phase_loop.Limits(session_max_usd=lb.SMOKE.full_cap, ceiling_usd=0.80)
    code, rows = h2h.common.run_guarded(h2h.steps(lb.SMOKE, [Task(0), Task(1)]), [], limits,
                                        guard.wrap(session), sessions)  # fmt: skip
    assert caps == [0.80] and len(rows) == 1 and code == 1
