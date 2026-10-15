"""Lot lb162's stops, with no network and no session: which Jev errors fail a task and which
pause phase J, failed calls in a row, documents read a few at a time, phase S's reservations
and infrastructure errors, the "pausa" reading, the product claim, and what the seal covers."""

from __future__ import annotations

import asyncio
import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sanchopanza.contract import Answer, DeciderUnavailable, Decision

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


lb = _load("lb162", "benchmarks/jev114/lb162.py")
h2h = _load("h2h_lb162", "benchmarks/h2h/h2h_lb162.py")
st = lb.stats


def _decision(letter: str | None, p: float = 0.7, probs: dict | None = None) -> Decision:
    if letter is None:
        return Decision("longbench_choice", {}, "jev", "jev-1.14.0", cost_usd=0.001)
    probs = probs if probs is not None else {k: (p if k == letter else (1 - p) / 3) for k in "ABCD"}
    answer = Answer(kind="choice", confidence=p, choice=letter, probabilities=probs)
    return Decision("longbench_choice", {"answer": answer}, "jev", "jev-1.14.0", cost_usd=0.001)


class Raising:
    name = "fake"

    def __init__(self, error: Exception) -> None:
        self.error, self.calls = error, 0

    async def decide(self, point, state, questions):
        self.calls += 1
        raise self.error


# --- phase J: a task failure or a pause -------------------------------------------------------


@pytest.mark.parametrize("said", [
    "jev did not answer: HTTP 400 max_tokens_exceeded (the state is over 262k tokens)",
    "jev did not answer: HTTP 400",
    "jev unreachable: ReadTimeout",
])  # fmt: skip
def test_a_400_or_a_read_timeout_fails_the_call_and_does_not_stop(said):
    inner, stop = Raising(DeciderUnavailable(said)), lb.Stop(max_consecutive=None)
    halting = lb.Halting(inner, stop)
    for _ in range(2):
        with pytest.raises(DeciderUnavailable):
            asyncio.run(halting.decide("p", {}, {}))
    assert stop.kind is None and inner.calls == 2


@pytest.mark.parametrize("said", [
    "jev unreachable: ConnectError",  # the network, other than a read timeout
    "jev unreachable: ConnectTimeout",
    "jev did not answer: HTTP 500",  # 5xx
    "jev did not answer: HTTP 503",
    "jev did not answer: HTTP 529",  # after the client's bounded retries
    "jev did not answer: HTTP 401",  # the key refused
    "jev did not answer: HTTP 403",
    "jev returned a non-JSON body",
])  # fmt: skip
def test_any_other_error_is_an_outage_that_stops_every_further_call(said):
    inner, stop = Raising(DeciderUnavailable(said)), lb.Stop()
    halting = lb.Halting(inner, stop)
    for _ in range(3):
        with pytest.raises(DeciderUnavailable):
            asyncio.run(halting.decide("p", {}, {}))
    assert stop.kind == "outage" and inner.calls == 1
    assert lb.jev_exit(stop.kind) == 2 and lb.jev_exit("cap") == 0 and lb.jev_exit(None) == 0


def test_an_unexpected_exception_is_an_outage_too():
    assert lb.stop_kind(RuntimeError("boom")) == "outage"
    assert lb.stop_kind(DeciderUnavailable("jev unreachable: ReadTimeout")) is None


class FakeTask:
    def __init__(self, path: Path, i: int = 0) -> None:
        self.task_id, self.gold, self.chars = f"t{i}", "B", 10
        self.length, self.difficulty = "short", "hard"
        self.question, self.choices = "q", ("a", "b", "c", "d")
        self.doc_path = str(path)


class Script:
    """An arm answering from a list; an exception is noted in `stop` like Halting would."""

    def __init__(self, replies: list, stop) -> None:
        self.replies, self.stop, self.calls = list(replies), stop, 0

    async def decide(self, point, state, questions):
        self.calls += 1
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            if kind := lb.stop_kind(reply):
                self.stop.note(kind, str(reply))
            return Decision(point, {}, "jev", "-", error=type(reply).__name__)
        return reply


def test_a_choice_with_no_probability_for_its_pick_is_a_failed_call(tmp_path):
    doc = tmp_path / "d.txt"
    doc.write_text("abc", encoding="utf-8")
    stop = lb.Stop()
    no_p = _decision("B", probs={"A": 0.5, "C": 0.5})
    row = asyncio.run(lb.jev_one(FakeTask(doc), Script([no_p, _decision("B")], stop), stop))
    assert row["status"] == "answered" and row[lb.CELL]["tries"] == 2 and stop.kind is None


def test_three_failed_calls_in_a_row_pause_phase_j_and_the_task_stays_failed(tmp_path):
    doc = tmp_path / "d.txt"
    doc.write_text("abc", encoding="utf-8")
    stop = lb.Stop()
    arm = Script([_decision(None)] * 3, stop)
    row = asyncio.run(lb.jev_one(FakeTask(doc), arm, stop))
    assert row["status"] == "failed" and stop.kind == "failures"
    later = asyncio.run(lb.jev_one(FakeTask(doc, 1), Script([], stop), stop))
    assert later["status"] == "stopped" and later[lb.CELL]["tries"] == 0


def test_an_answer_resets_the_count_of_failed_calls(tmp_path):
    stop = lb.Stop()
    for answered in (False, False, True, False, False):
        stop.call_done(answered)
    assert stop.kind is None and stop.consecutive == 2


def test_an_outage_on_the_last_length_leaves_the_task_to_the_relaunch(tmp_path):
    doc = tmp_path / "d.txt"
    doc.write_text("abc", encoding="utf-8")
    stop = lb.Stop(max_consecutive=None)
    replies = [_decision(None), _decision(None), DeciderUnavailable("jev did not answer: HTTP 503")]
    row = asyncio.run(lb.jev_one(FakeTask(doc), Script(replies, stop), stop))
    assert row["status"] == "stopped" and stop.kind == "outage"


def test_a_call_refused_by_the_stop_is_not_a_try(tmp_path):
    doc = tmp_path / "d.txt"
    doc.write_text("abc", encoding="utf-8")
    stop = lb.Stop()

    class Refused:
        async def decide(self, point, state, questions):
            stop.note("limit", "HTTP 429")
            return Decision(point, {}, "jev", "-", error=lb.NotCalled.__name__)

    row = asyncio.run(lb.jev_one(FakeTask(doc), Refused(), stop))
    assert row["status"] == "stopped" and row[lb.CELL]["tries"] == 0


def test_documents_are_read_a_few_tasks_at_a_time(tmp_path, monkeypatch):
    live = {"now": 0, "most": 0}
    real = lb.jev_one

    async def counted(task, arm, stop):
        live["now"] += 1
        live["most"] = max(live["most"], live["now"])
        await asyncio.sleep(0)
        try:
            return await real(task, arm, stop)
        finally:
            live["now"] -= 1

    class Decider:
        name = "fake"

        async def decide(self, point, state, questions):
            await asyncio.sleep(0)
            return _decision("A", 0.9)

    doc = tmp_path / "d.txt"
    doc.write_text("abc", encoding="utf-8")
    monkeypatch.setattr(lb, "jev_one", counted)
    tasks = [FakeTask(doc, i) for i in range(12)]
    rows = asyncio.run(lb.run_j(tasks, Decider(), tmp_path / "answers.jsonl", lb.Stop()))
    assert [r["id"] for r in rows] == [t.task_id for t in tasks]
    assert live["most"] <= lb.CONCURRENCY and all(r["status"] == "answered" for r in rows)


# --- phase S: reservations and infrastructure errors ------------------------------------------


def test_a_session_that_died_mid_way_keeps_its_reserve_against_the_ceiling(tmp_path):
    path = tmp_path / "reservations.jsonl"
    guard = h2h.Guard(dt.datetime(2026, 10, 16, 10), clock=lambda: dt.datetime(2026, 10, 16, 11),
                      run_dir=tmp_path, reservations=path)  # fmt: skip
    done = {"task": "a", "task_id": "a", "run": 1, "arm": h2h.ARM, "list_usd": 0.2}
    guard.wrap(lambda item, run, arm: done)(("a",), 1, h2h.ARM)

    def dies(item, run, arm):
        raise KeyboardInterrupt  # the process ends inside the session: no row recorded

    with pytest.raises(KeyboardInterrupt):
        guard.wrap(dies)(("b",), 1, h2h.ARM)
    open_ = h2h.open_reservations([done], path)
    assert [(r["task"], r["list_usd"], r["not_run"]) for r in open_] == [
        ("b", lb.SONNET_RESERVE_USD, True)]  # fmt: skip
    limits = h2h.phase.Limits(session_max_usd=lb.SONNET_RESERVE_USD, ceiling_usd=h2h.CEILING_USD)
    spent = [done, *open_]
    assert sum(r["list_usd"] for r in spent) == pytest.approx(0.2 + lb.SONNET_RESERVE_USD)
    assert h2h.phase.stop_reason([*spent, {"list_usd": 3.2}], limits, 0) is not None  # 18.04
    assert h2h.phase.counted(spent) == [done]  # the open reserve is not a session


def _row(i: int, letter: str | None, p: float | None, gold: str = "A",
         status: str = "answered") -> dict:  # fmt: skip
    return {"id": f"t{i:03d}", "gold": gold, "chars": 1, "length": "short", "difficulty": "easy",
            "status": status, lb.CELL: {"letter": letter, "p": p, "usd": 0.001}}  # fmt: skip


def test_infrastructure_errors_are_not_run_in_the_primary_and_wrong_in_the_sensitivity():
    rows = [_row(i, "A", 0.9) for i in range(4)]
    sonnet = {
        "t000": {"letter": "A", "ok": True, "usd": 0.1, "hit_cap": False, "is_error": False},
        "t001": {"letter": None, "ok": False, "usd": 0.1, "hit_cap": False, "is_error": True,
                 "subtype": "runner: TimeoutExpired"},
        "t002": {"letter": None, "ok": False, "usd": 3.0, "hit_cap": True, "is_error": True,
                 "subtype": "error_max_budget_usd"},  # its cap: wrong, as on 2026-10-06
        "t003": {"letter": None, "ok": False, "usd": 0.1, "hit_cap": False, "is_error": True},
    }  # fmt: skip
    got = st.analyse(rows, sonnet)
    first, sens = got["primary"], got["sensitivity_infra_as_wrong"]
    assert first["sonnet_sessions"] == 2 and first["covered_without_sonnet"] == 2
    assert first["mcnemar"]["jev_only_right"] == 1  # t002 only
    assert sens["sonnet_sessions"] == 4 and sens["mcnemar"]["jev_only_right"] == 3
    assert got["costs"]["sonnet_infra_covered"] == 2


# --- the reading: pause, no medido, the claim ---------------------------------------------------


def test_no_verdict_while_the_lot_is_paused(tmp_path):
    rows = [_row(i, "A", 0.9) for i in range(lb.N_TASKS)]
    done, ceiling = {"kind": "done"}, {"kind": "ceiling"}
    assert lb.pause_reasons(rows, None, done, tmp_path) == []
    assert lb.pause_reasons(rows, None, ceiling, tmp_path) == []
    for kind in ("clock", "manual", "limit", "preflight", "error"):
        assert lb.pause_reasons(rows, None, {"kind": kind}, tmp_path) == [f"phase S {kind}"]
    assert lb.pause_reasons(rows, None, None, tmp_path) == ["phase S not run"]
    (tmp_path / "LIMIT.flag").write_text("")
    assert "LIMIT.flag in the run folder" in lb.pause_reasons(rows, None, done, tmp_path)
    paused_j = [*rows[:-1], _row(999, None, None, status="stopped")]
    assert lb.pause_reasons(paused_j, {"kind": "outage"}, done, tmp_path)[-1].startswith("phase J")
    sonnet = {f"t{i:03d}": {"letter": "A", "ok": True, "usd": 0.1} for i in range(lb.N_TASKS)}
    got = st.analyse(rows, sonnet, paused=["phase S clock"])
    assert got["primary"]["verdict"] == "pausa" and got["claim"] is None


def test_nothing_covered_is_no_medido_and_a_low_coverage_is_no_claim():
    none = [_row(i, "A", 0.3) for i in range(50)]
    got = st.analyse(none, {})
    assert got["primary"]["verdict"] == "no medido" and got["claim"] is None
    low = [_row(i, "A", 0.9 if i < 5 else 0.3) for i in range(50)]  # 10 % covered, all right
    sonnet = {f"t{i:03d}": {"letter": "B", "ok": False, "usd": 0.1} for i in range(5)}
    got = st.analyse(low, sonnet)
    assert got["primary"]["verdict"] == "no peor" and got["claim"] == "no sustituye"
    high = [_row(i, "A", 0.9 if i < 20 else 0.3) for i in range(50)]  # 40 % covered
    sonnet = {f"t{i:03d}": {"letter": "A", "ok": True, "usd": 0.1} for i in range(20)}
    got = st.analyse(high, sonnet)
    assert got["primary"]["verdict"] == "no peor" and got["claim"] == "sustituye"


def test_the_ci_is_compared_with_the_margin_unrounded():
    assert st.verdict((-0.099996, 0.0)) == "no peor"  # -0.1 once rounded to 4 decimals
    assert st.percentile_ci([0.5]) == (0.5, 0.5) and st.percentile_ci([]) is None


def test_the_stop_files_keep_the_kind_only(tmp_path, monkeypatch):
    for name in ("OUT", "RUN_DIR"):
        monkeypatch.setattr(lb, name, tmp_path)
    monkeypatch.setattr(lb, "JEV_ROWS", tmp_path / "jev-scored.jsonl")
    monkeypatch.setattr(lb, "STOP_FILE", tmp_path / "jev-stop.json")
    monkeypatch.setattr(lb, "SONNET_STOP", tmp_path / "sonnet-stop.json")
    monkeypatch.setattr(lb, "SONNET_ROWS", tmp_path / "sonnet-rows.jsonl")
    monkeypatch.setattr(lb, "SUMMARY", tmp_path / "summary.json")
    monkeypatch.setattr(lb, "LEDGER_PATH", tmp_path / "ledger.json")
    lb.write_jsonl(lb.JEV_ROWS, [_row(i, "A", 0.3) for i in range(lb.N_TASKS)])
    lb.write_jsonl(lb.STOP_FILE, [{"kind": "cap"}])
    out = lb.analysis()
    assert out["jev_stop"] == "cap" and out["sonnet_stop"] is None
    assert str(tmp_path) not in lb.SUMMARY.read_text(encoding="utf-8")


# --- the launcher and the seal -------------------------------------------------------------------


def test_the_launcher_turns_the_updater_off_and_takes_the_keys_path_only():
    text = (ROOT / "benchmarks/h2h/launch.ps1").read_text(encoding="utf-8")
    assert "set DISABLE_AUTOUPDATER=1" in text
    assert "[string]$KeysEnv = ''" in text and "set SANCHOPANZA_KEYS_ENV=$KeysEnv" in text
    assert "Get-Content" not in text  # the file it names is never opened


def test_the_seal_covers_every_file_the_runners_load():
    probe = (
        "import importlib.util, json, pathlib, sys\n"
        "root = pathlib.Path(sys.argv[1])\n"
        "for name, rel in (('lb162', 'benchmarks/jev114/lb162.py'),\n"
        "                  ('h2h_lb162', 'benchmarks/h2h/h2h_lb162.py')):\n"
        "    spec = importlib.util.spec_from_file_location(name, root / rel)\n"
        "    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod\n"
        "    spec.loader.exec_module(mod)\n"
        "h2h = sys.modules['h2h_lb162']; h2h.common.local_hook_problems()\n"
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
    assert "tests/test_lb162_stops.py" in sealed
