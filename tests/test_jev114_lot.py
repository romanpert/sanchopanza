"""The 2026-10-16 lots' paid path (benchmarks/jev114/lot.py) end to end with a fake Jev, no
network: preflight, both arms, two passes, and no live decider used under two event loops.

The fake remembers the loop of its first call and fails like httpx does ("Event loop is
closed") when called from another one: the way a runner that reused one live client across two
`asyncio.run` lost 498 of 500 calls of an arm.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JEV114 = ROOT / "benchmarks" / "jev114"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, JEV114 / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(JEV114))
lots = _load("lot")

from sanchopanza.contract import Answer, Decision  # noqa: E402
from sanchopanza.points import completion  # noqa: E402
from sanchopanza.providers import jev as jev_module  # noqa: E402


class LoopBoundJev:
    """A stand-in for JevDecider whose client binds to the first loop that uses it."""

    made: list[LoopBoundJev] = []
    seen: set[tuple[str, str]] = set()

    def __init__(self, *_: object, model: str = "jev-1.13.0", **__: object) -> None:
        self.model, self.name, self.loop, self.closed, self.calls = model, "jev", None, False, 0
        LoopBoundJev.made.append(self)

    async def decide(self, point, state, questions):
        loop = asyncio.get_running_loop()
        if self.loop is None:
            self.loop = loop
        elif self.loop is not loop:
            raise RuntimeError("Event loop is closed")
        self.calls += 1
        first = (self.model, state["task"])
        if first not in LoopBoundJev.seen and state["task"].endswith("0"):
            LoopBoundJev.seen.add(first)  # a transient failure: asked again in pass 2
            raise RuntimeError("transient")
        answer = Answer(kind="truth", confidence=0.8, truth=0.9)
        return Decision(point=point, answers={"done": answer}, provider="jev", model=self.model)

    async def aclose(self) -> None:
        self.closed = True


def test_the_fake_catches_a_client_reused_across_two_loops():
    fake = LoopBoundJev(model="jev-1.14.0")
    state, qs = completion.questions(task="t1", record="r")
    asyncio.run(fake.decide("completion", state, qs))
    with pytest.raises(RuntimeError, match="Event loop is closed"):
        asyncio.run(fake.decide("completion", state, qs))


def test_the_paid_path_keeps_every_live_decider_in_one_loop(tmp_path, monkeypatch):
    LoopBoundJev.made.clear()
    LoopBoundJev.seen.clear()
    monkeypatch.setattr(jev_module, "JevDecider", LoopBoundJev)

    def fake_preflight(model: str):
        decider = LoopBoundJev(model=model)  # its own client in its own loop, as the real one
        decider.preflight = True
        state, qs = completion.questions(task="preflight", record="")

        async def once():
            try:
                await decider.decide("completion", state, qs)
            finally:
                await decider.aclose()

        asyncio.run(once())
        return jev_module.PreflightResult(True, "ok", 200, 0.0, model, "fake")

    monkeypatch.setattr(jev_module, "preflight", fake_preflight)
    components = _load("jev114_components")
    monkeypatch.setattr(components, "load_key", lambda: None)
    lot = lots.Lot(name="test-loop", out=tmp_path, run=tmp_path / "run", batch_cap=0.01,
                   sealed=(), fixture_stem="t", ledger=tmp_path / "ledger.json")  # fmt: skip
    cases = []
    for i in range(12):
        state, qs = completion.questions(task=f"task {i}", record="AGENT: done")
        cases.append({"id": str(i), "point": "completion", "state": state, "questions": qs})

    async def ask(case, decider):
        return await decider.decide(case["point"], case["state"], case["questions"]), None

    async def answered(case, arm):
        d = await arm.recorded.decide(case["point"], case["state"], case["questions"])
        return bool(d.answers)

    code = lots.paid_launch(lot, lambda: asyncio.run(lots.run_cases(lot, cases, ask, answered)))
    assert code == 0
    assert json.loads(lots.launches(lot).read_text().splitlines()[-1])["outcome"] == "complete"
    for arm in lots.ARMS:
        assert len(lots.read_recording(lot.fixture(arm))[0]) == 12
    run = [d for d in LoopBoundJev.made if d.calls and not getattr(d, "preflight", False)]
    assert len(run) == 4  # two arms, two passes: fresh clients per pass
    assert len({id(d.loop) for d in run}) == 1  # all in the run's one loop
    assert all(d.closed for d in LoopBoundJev.made if d.calls)


# --- a 402 is a pause; the launcher seals with its local values as placeholders --------------


class BrokeJev(LoopBoundJev):
    """Runs out of funds on its third call."""

    async def decide(self, point, state, questions):
        from sanchopanza.contract import DeciderOutOfFunds

        if self.calls >= 2:
            raise DeciderOutOfFunds("jev did not answer: HTTP 402 (out of funds)")
        self.calls += 1
        answer = Answer(kind="truth", confidence=0.8, truth=0.9)
        return Decision(point=point, answers={"done": answer}, provider="jev", model=self.model)


def _lot(tmp_path, name="test-pause"):
    return lots.Lot(name=name, out=tmp_path, run=tmp_path / "run", batch_cap=0.01, sealed=(),
                    fixture_stem="t", ledger=tmp_path / "ledger.json")  # fmt: skip


def _ok_preflight(model: str):
    return jev_module.PreflightResult(True, "ok", 200, 0.0, model, "fake")


def _cases(n: int = 8):
    out = []
    for i in range(n):
        state, qs = completion.questions(task=f"job {i}", record="AGENT: done")
        out.append({"id": str(i), "point": "completion", "state": state, "questions": qs})
    return out


async def _ask(case, decider):
    return await decider.decide(case["point"], case["state"], case["questions"]), None


async def _answered(case, arm):
    d = await arm.recorded.decide(case["point"], case["state"], case["questions"])
    return bool(d.answers)


def test_a_402_in_the_preflight_pauses_and_allows_a_relaunch(tmp_path, monkeypatch):
    monkeypatch.setattr(jev_module, "preflight", lambda model: jev_module.PreflightResult(
        False, "no_funds", 402, 0.0, model, "402"))  # fmt: skip
    monkeypatch.setattr(_load("jev114_components"), "load_key", lambda: None)
    lot = _lot(tmp_path)
    for _ in range(3):  # paused launches never use up the relaunch
        assert lots.paid_launch(lot, lambda: (0, "")) == lots.PAUSED_EXIT
    assert [r["outcome"] for r in lots.read_launches(lots.launches(lot))][-1] == "paused"
    assert lots.may_launch(lot) is None


def test_a_402_mid_run_pauses_with_no_verdict_and_allows_a_relaunch(tmp_path, monkeypatch):
    monkeypatch.setattr(jev_module, "JevDecider", BrokeJev)
    monkeypatch.setattr(jev_module, "preflight", _ok_preflight)
    monkeypatch.setattr(_load("jev114_components"), "load_key", lambda: None)
    lot, cases = _lot(tmp_path), _cases()
    code = lots.paid_launch(lot, lambda: asyncio.run(lots.run_cases(lot, cases, _ask, _answered)))
    assert code == lots.PAUSED_EXIT
    past = lots.read_launches(lots.launches(lot))
    assert past[-1]["outcome"] == "paused" and "402" in past[-1]["why"]
    assert lots.may_launch(lot) is None
    stats = _load("lot_stats")

    (tmp_path / "launches.jsonl").write_text(lots.launches(lot).read_text(), encoding="utf-8")
    assert stats.launch_status(tmp_path) == "paused"  # the analysis gives no verdict


def test_a_cap_still_ends_the_lot(tmp_path):
    lot = _lot(tmp_path)
    lots.log_launch(lot, "started", "")
    lots.log_launch(lot, "stopped", "SpendCapReached: batch full")
    assert "cap" in lots.may_launch(lot)


def test_filling_the_local_values_keeps_the_launchers_seal(tmp_path, monkeypatch):
    for rel in ("checkdone114-run.cmd", "redundant-drop-run.cmd"):
        tracked = ROOT / rel
        text = tracked.read_text(encoding="utf-8")
        filled = (text.replace('set "PY=<PYTHON>"', r'set "PY=C:\py\python.exe"')
                  .replace('set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"',
                           r'set "SANCHOPANZA_KEYS_ENV=D:\keys\.env"')
                  .replace('set "WT=<WORKTREE>"', r'set "WT=C:\wt\lot"'))  # fmt: skip
        assert filled != text
        copy = tmp_path / rel
        copy.write_text(filled.replace("\n", "\r\n"), encoding="utf-8", newline="")
        assert lots.launcher_text(copy) == lots.launcher_text(tracked)
        lot = lots.Lot(name="t", out=tmp_path, run=tmp_path, batch_cap=0.01, sealed=(rel,),
                       fixture_stem="t", launcher=rel)  # fmt: skip
        monkeypatch.setenv("SANCHOPANZA_LAUNCHER", str(copy))
        lots.require_launcher(lot)
        for other in ("set MODE=--paid", "set ROOT=", "exit /b %CODE%"):
            changed = filled.replace(other, other + " ", 1)
            assert changed != filled, other
            copy.write_text(changed, encoding="utf-8")
            assert lots.launcher_text(copy) != lots.launcher_text(tracked), other
            with pytest.raises(SystemExit):
                lots.require_launcher(lot)
        monkeypatch.delenv("SANCHOPANZA_LAUNCHER")
        with pytest.raises(SystemExit):
            lots.require_launcher(lot)


def test_the_seal_reads_the_launcher_with_placeholders():
    plain = lots.Lot(name="t", out=ROOT, run=ROOT, batch_cap=0.01,
                     sealed=("checkdone114-run.cmd",), fixture_stem="t")  # fmt: skip
    sealed = lots.Lot(name="t", out=ROOT, run=ROOT, batch_cap=0.01,
                      sealed=("checkdone114-run.cmd",), fixture_stem="t",
                      launcher="checkdone114-run.cmd")  # fmt: skip
    import hashlib

    expected = hashlib.sha256(lots.launcher_text(ROOT / "checkdone114-run.cmd")).hexdigest()
    assert lots.digest(sealed) == expected != lots.digest(plain)
