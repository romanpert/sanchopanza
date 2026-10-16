"""A paid call is asked once, even when the same request is in flight twice at the same moment.

C5b's recording holds 8,869 lines for 8,868 distinct keys: two identical sentence calls overlapped,
the asker's memo held only finished answers, and Jev was asked twice (and answered differently).
B6's asker now shares the in-flight call per key; `paid_once.ask_missing` asks each distinct key
once. Replays are untouched: they never reach a live call. No paid call.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any

from sanchopanza import truth
from sanchopanza.contract import Decision, Truth
from sanchopanza.providers.recorded import RecordedDecider

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(ROOT / "benchmarks" / "b6_es"))

import paid_once  # noqa: E402

spec = importlib.util.spec_from_file_location("b6_run", ROOT / "benchmarks/b6_es/b6_run.py")
br = importlib.util.module_from_spec(spec)
sys.modules["b6_run"] = br
spec.loader.exec_module(br)

QS = {"Q": Truth("Is it so?")}


class _Slow:
    """Answers after a pause, differently each time, as a live model may."""

    name = "slow"

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def decide(self, point: str, state: Any, qs: Any) -> Decision:
        self.calls += 1
        await asyncio.sleep(0.05)
        if self.fail:
            raise TimeoutError("timed out")
        return Decision(point, {k: truth(0.5 + self.calls / 10) for k in qs}, "slow", br.MODEL)


def _two_at_once(live: _Slow) -> tuple[Decision, Decision, Any]:
    asker = br.Asker(live, RecordedDecider([]))

    async def both() -> list[Decision]:
        return await asyncio.gather(asker.decide("a", "p", {"s": 1}, QS),
                                    asker.decide("b", "p", {"s": 1}, QS))  # fmt: skip

    first, second = asyncio.run(both())
    return first, second, asker


def test_two_identical_requests_in_flight_make_one_live_call_and_share_its_answer() -> None:
    live = _Slow()
    first, second, asker = _two_at_once(live)
    assert live.calls == 1
    assert first.answer("Q").truth == second.answer("Q").truth
    assert sum(c["calls"] for c in asker.calls.values()) == 1


def test_a_failed_call_in_flight_is_shared_as_the_same_failure() -> None:
    live = _Slow(fail=True)
    first, second, asker = _two_at_once(live)
    assert live.calls == 1 and first.failed and second.failed
    assert asker.failures == 1 and len(asker.failed_keys) == 1


def test_different_requests_still_run_side_by_side() -> None:
    live = _Slow()
    asker = br.Asker(live, RecordedDecider([]))

    async def both() -> list[Decision]:
        return await asyncio.gather(asker.decide("a", "p", {"s": 1}, QS),
                                    asker.decide("a", "p", {"s": 2}, QS))  # fmt: skip

    asyncio.run(both())
    assert live.calls == 2 and not asker.in_flight


class _Once:
    name = "once"

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, point: str, state: Any, qs: Any) -> Decision:
        self.calls += 1
        return Decision(point, {k: truth(0.9) for k in qs}, "once", "jev-1.13.0", cost_usd=2e-5)


def test_paid_once_asks_each_distinct_query_once(tmp_path: Path) -> None:
    lot = paid_once.Lot(name="t", prereg=tmp_path / "p.md", launcher=tmp_path / "x.cmd",
                        fixture=tmp_path / "f.jsonl", model="jev-1.13.0", cap_usd=0.01,
                        instrument=("src",), home=tmp_path)  # fmt: skip
    query = ("p", {"s": 1}, QS)
    live = _Once()
    got = asyncio.run(paid_once.ask_missing([query, query, ("p", {"s": 2}, QS)], lot, live=live))
    assert live.calls == 2 and got["asked"] == 2 and got["missing_at_start"] == 2
    assert paid_once.plan([query, query], lot)["to_ask"] == 0
