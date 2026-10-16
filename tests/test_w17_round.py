"""The round's shared Jev ledger (benchmarks/w17_round.py, paid_once's shared lots), the launch
rule after a model switch, and B6's asker remembering a failed call within a run. No paid call."""

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
import w17_round  # noqa: E402

spec = importlib.util.spec_from_file_location("b6_run", ROOT / "benchmarks/b6_es/b6_run.py")
br = importlib.util.module_from_spec(spec)
sys.modules["b6_run"] = br
spec.loader.exec_module(br)


def test_each_lots_room_is_its_batch_cap_and_never_past_the_round(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    assert w17_round.room("c4-written", path) == 0.15
    book = w17_round.ledger(path)
    rid = book.reserve(1.0, batch="c6-window")
    book.settle(rid, 4.5)
    assert w17_round.room("c6-window", path) == 0.0
    assert abs(w17_round.room("c5-free", path) - 1.5) < 1e-9  # the round leaves 1.5 of 2.0
    assert sum(w17_round.BATCH_CAPS.values()) > w17_round.CAP_USD  # the round cap binds


def test_a_shared_lot_counts_its_batch_and_the_rounds_total(tmp_path: Path) -> None:
    path = tmp_path / "ledger.json"
    lot = paid_once.Lot(name="c4-written", prereg=tmp_path / "p.md", launcher=tmp_path / "x.cmd",
                        fixture=tmp_path / "f.jsonl", model="jev-1.13.0", cap_usd=0.15,
                        instrument=("src",), home=tmp_path, shared_ledger=path,
                        shared_cap_usd=6.0)  # fmt: skip
    assert lot.ledger == path and paid_once.room(lot) == 0.15
    book = w17_round.ledger(path)
    book.settle(book.reserve(0.01, batch="c4-written"), 0.05)
    book.settle(book.reserve(1.0, batch="c5-free"), 5.9)
    assert abs(paid_once.spent(lot) - 0.05) < 1e-9  # its own batch only
    assert abs(paid_once.room(lot) - 0.05) < 1e-9  # 6.00 - 5.95: the round binds before 0.10


def test_no_relaunch_after_a_model_switch() -> None:
    assert not paid_once.may_launch([{"stop_kind": "model"}])
    assert paid_once.stop_kind("model moved: jev-1.14.0 != jev-1.13.0") == "model"


class _FailsOnce:
    name = "once"

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, point: str, state: Any, qs: Any) -> Decision:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("timed out")  # how a Jev call fails: raised, counted, no halt
        return Decision(point, {k: truth(0.9) for k in qs}, "once", br.MODEL)


def test_with_failures_remembered_a_failed_request_is_never_asked_again() -> None:
    qs = {"Q": Truth("Is it so?")}

    async def twice(asker: Any) -> tuple[Decision, Decision]:
        return (await asker.decide("arm", "p", {"s": 1}, qs),
                await asker.decide("arm", "p", {"s": 1}, qs))  # fmt: skip

    live = _FailsOnce()
    first, second = asyncio.run(twice(br.Asker(live, RecordedDecider([]), memo_failures=True)))
    assert first.failed and second.failed and live.calls == 1
    plain = _FailsOnce()
    _, again = asyncio.run(
        twice(br.Asker(plain, RecordedDecider([])))
    )  # B6's default: asked again, as sealed
    assert not again.failed and plain.calls == 2


def test_a_ledger_lock_not_had_in_time_is_busy_not_the_cap(tmp_path: Path) -> None:
    import pytest

    from sanchopanza import _lockfile
    from sanchopanza.budget import SpendLedger
    from sanchopanza.providers.capped import CappedDecider, LedgerBusy, SpendCapReached

    path = tmp_path / "ledger.json"
    book = SpendLedger(path, cap_usd=6.0, wait_s=0.05)
    capped = CappedDecider(_FailsOnce(), ledger=book, batch="c4-written", max_usd=0.15)
    with _lockfile.locked(path, wait_s=1.0, strict=True):  # another lot holds the ledger
        assert book.reserve(0.01, batch="c4-written") is None and book.busy
        with pytest.raises(LedgerBusy) as busy:
            asyncio.run(capped.decide("p", {"s": 1}, {"Q": Truth("Is it so?")}))
    assert not isinstance(busy.value, SpendCapReached)
    kind = paid_once.stop_kind(f"{type(busy.value).__name__}: {busy.value}")
    assert kind == "busy" and paid_once.may_launch([{"stop_kind": kind}])
    assert book.reserve(0.01, batch="c4-written") and not book.busy
    full = SpendLedger(path, cap_usd=0.001)
    assert full.reserve(0.01, batch="c4-written") is None and not full.busy  # the cap, not busy
    assert br.halt_kind(busy.value) == "busy"
