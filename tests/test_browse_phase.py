"""The end-to-end browse runners' shared loop: ceilings, early stop, warm-up on resume, own log."""

import asyncio
import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("browse_phase", ROOT / "benchmarks/browse/phase.py")
phase = importlib.util.module_from_spec(spec)
sys.modules["browse_phase"] = phase
spec.loader.exec_module(phase)

TASKS = [(f"T{i}", "https://example.com", "q", ["a"]) for i in range(1, 5)]


def row(task, run, arm, usd=0.1, jev=0.0):
    return {"task": task, "run": run, "arm": arm, "success": True, "list_usd": usd,
            "jev_usd": jev, "turns": 4}  # fmt: skip


def fake_session(cost=0.1, jev=0.0):
    calls = []

    def session(task, run, arm):
        calls.append((task[0], run, arm))
        return row(task[0], run, arm, cost, jev)

    return session, calls


def limits(**kw):
    base = {"session_max_usd": 1.0, "ceiling_usd": 100.0}
    return phase.Limits(**{**base, **kw})


def test_early_stop_counts_the_first_two_tasks_only(tmp_path):
    # Phase 3i stopped at 64 of 72 sessions: the rule summed every row, not the first two tasks.
    rows = [row(t, r, a, usd=0.6) for t in ("T1", "T2", "T3") for r in (1, 2, 3)
            for a in ("PLAIN", "LEAN")]  # fmt: skip
    rule = limits(early_stop_usd=8.0, early_tasks=frozenset({"T1", "T2"}))
    assert phase.stop_reason(rows, rule, task_index=3) is None  # 10.8 in all, 7.2 in T1-T2
    heavy = [row("T1", 1, "PLAIN", usd=8.5)]
    assert "first two tasks" in phase.stop_reason(heavy, rule, task_index=2)
    assert phase.stop_reason(heavy, rule, task_index=1) is None  # still inside the first two


def test_ceilings_count_the_warm_up_sessions_too():
    rows = [row("T1", -9, "PLAIN", usd=19.5)]
    assert "ceiling" in phase.stop_reason(rows, limits(ceiling_usd=20.0), task_index=0)
    jev = [row("T1", 1, "LEAN", jev=1.9)]
    rule = limits(jev_ceiling_usd=2.0, jev_session_max_usd=0.2)
    assert "Jev ceiling" in phase.stop_reason(jev, rule, task_index=0)


def test_a_resumed_phase_warms_the_cache_again_with_a_new_uncounted_run(tmp_path):
    sink = tmp_path / "s.jsonl"
    done = [row("T1", -9, "PLAIN")] + [row("T1", 1, a) for a in ("PLAIN", "LEAN")]
    session, calls = fake_session()
    plan = phase.planned(TASKS[:2], [1], ("PLAIN", "LEAN"))
    code, rows = phase.run_phase(plan, done, limits(), session, sink, warmup_task=TASKS[0])
    assert code == 0
    assert calls[0] == ("T1", -10, "PLAIN")  # a second warm-up, not counted (run <= 0)
    assert calls[1:] == [("T2", 1, "PLAIN"), ("T2", 1, "LEAN")]
    assert len(done) == 3 and len(rows) == 6  # the caller's list is not changed
    written = [json.loads(x) for x in sink.read_text(encoding="utf-8").splitlines()]
    assert [r["run"] for r in written] == [-10, 1, 1]


def test_nothing_left_means_no_warm_up(tmp_path):
    done = [row("T1", 1, a) for a in ("PLAIN", "LEAN")]
    session, calls = fake_session()
    plan = phase.planned(TASKS[:1], [1], ("PLAIN", "LEAN"))
    code, _ = phase.run_phase(plan, done, limits(), session, tmp_path / "s.jsonl", TASKS[0])
    assert code == 0 and calls == []


def test_the_runner_logs_its_own_progress_beside_the_sessions(tmp_path):
    # 3i lost its start: the log path lived in a shell variable of another background job.
    sink = tmp_path / "e2e-x-sessions.jsonl"
    session, _ = fake_session()
    plan = phase.planned(TASKS[:1], [1], ("PLAIN",))
    phase.run_phase(plan, [], limits(), session, sink)
    log = sink.with_suffix(".log").read_text(encoding="utf-8").splitlines()
    assert len(log) == 1 and json.loads(log[0])["task"] == "T1"


class FakeSession:
    def __init__(self, usd, cached=False):
        self.list_cost_usd, self.cached = usd, cached


class FakeClient:
    """A harness client that, like the real one, would report the cache's total as its spend."""

    def __init__(self, usd, cached=False):
        self.usd, self.cached, self.spent_usd = usd, cached, 99.0

    async def run(self, text, schema=None):
        await asyncio.sleep(0)  # the real one awaits a `claude -p` process
        return FakeSession(self.usd, self.cached)


def test_one_ceiling_holds_across_two_clients_and_counts_each_session_once():
    # Phase 2d ran two clients, each with the whole 15 USD ceiling, and reported 14.99 USD
    # (each client's view of the cache) where its sessions cost 10.12.
    budget = phase.PhaseBudget(ceiling_usd=1.0, concurrency=1)
    cheap, dear = FakeClient(0.1), FakeClient(0.5)

    async def go():
        await budget.run(cheap, 0.1, "a")
        await budget.run(dear, 0.6, "b")
        await budget.run(cheap, 0.1, "c")
        await budget.run(FakeClient(0.5, cached=True), 0.6, "replayed: free")
        return await budget.run(dear, 0.6, "d")

    with pytest.raises(RuntimeError, match="phase ceiling"):
        asyncio.run(go())
    # 0.1 + 0.5 + 0.1: the replay and the refused session cost nothing
    assert budget.spent_usd == pytest.approx(0.7)


def test_concurrent_sessions_reserve_their_cap_before_they_start():
    budget = phase.PhaseBudget(ceiling_usd=1.0, concurrency=3)

    async def go():
        return await asyncio.gather(
            *(budget.run(FakeClient(0.1), 0.4, str(i)) for i in range(3)), return_exceptions=True
        )

    results = asyncio.run(go())
    assert sum(isinstance(r, RuntimeError) for r in results) == 1  # 3 x 0.4 > 1.0 reserved


def test_queued_sessions_do_not_reserve_while_they_wait():
    # 246 sessions gathered at once with a 15 USD ceiling: reserving in the queue would refuse
    # most of them before a cent was spent.
    budget = phase.PhaseBudget(ceiling_usd=1.0, concurrency=2)

    async def go():
        return await asyncio.gather(*(budget.run(FakeClient(0.01), 0.4, str(i)) for i in range(20)))

    assert len(asyncio.run(go())) == 20
    assert budget.spent_usd == pytest.approx(0.2)


def test_a_stop_is_logged_and_spends_nothing_more(tmp_path):
    sink = tmp_path / "s.jsonl"
    session, calls = fake_session(cost=0.6)
    plan = phase.planned(TASKS[:2], [1], ("PLAIN", "LEAN"))
    code, rows = phase.run_phase(plan, [], limits(ceiling_usd=2.0), session, sink)
    assert code == 1 and len(calls) == 2  # 1.2 spent; a third could pass 2.0
    assert "ceiling" in sink.with_suffix(".log").read_text(encoding="utf-8")
