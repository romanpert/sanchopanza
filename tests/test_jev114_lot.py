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
