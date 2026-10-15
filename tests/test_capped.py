"""A hard spend cap shared by every process of an experiment batch: a ledger file under an
exclusive lock, and a decider wrapper that refuses before calling when the call may not fit."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import _lockfile
from sanchopanza.budget import SpendLedger
from sanchopanza.contract import Answer, DeciderUnavailable, Decision, Truth
from sanchopanza.media import image
from sanchopanza.providers.capped import CappedDecider, SpendCapReached, estimate_usd
from sanchopanza.providers.fixed import BrokenDecider, FixedDecider

QS = {"q": Truth("Is it?")}


def ledger(tmp_path: Path, cap: float = 0.01, **kwargs: Any) -> SpendLedger:
    return SpendLedger(tmp_path / "ledger.jsonl", cap_usd=cap, **kwargs)


# --- the ledger ----------------------------------------------------------------------------


def test_a_reservation_counts_until_settled_at_what_it_cost(tmp_path: Path) -> None:
    book = ledger(tmp_path)
    rid = book.reserve(0.004, batch="a")
    assert rid is not None and book.spent() == pytest.approx(0.004)
    book.settle(rid, 0.001)
    assert book.spent() == pytest.approx(0.001)
    assert book.spent("a") == pytest.approx(0.001) and book.spent("b") == 0.0


def test_a_reservation_past_the_global_cap_is_refused(tmp_path: Path) -> None:
    book = ledger(tmp_path, cap=0.01)
    assert book.reserve(0.008, batch="a") is not None
    assert book.reserve(0.003, batch="b") is None
    assert book.reserve(0.002, batch="b") is not None
    assert book.spent() == pytest.approx(0.010)


def test_a_batch_cap_holds_inside_the_global_one(tmp_path: Path) -> None:
    book = ledger(tmp_path, cap=1.0)
    assert book.reserve(0.004, batch="a", batch_cap_usd=0.005) is not None
    assert book.reserve(0.002, batch="a", batch_cap_usd=0.005) is None
    assert book.reserve(0.002, batch="b", batch_cap_usd=0.005) is not None


def test_the_ledger_is_shared_through_its_file(tmp_path: Path) -> None:
    ledger(tmp_path, cap=0.01).reserve(0.009, batch="a")
    assert ledger(tmp_path, cap=0.01).reserve(0.002, batch="b") is None


def test_concurrent_reservations_never_pass_the_cap(tmp_path: Path) -> None:
    book = ledger(tmp_path, cap=0.01)
    granted: list[str | None] = []

    def take() -> None:
        granted.append(book.reserve(0.001, batch="a"))

    threads = [threading.Thread(target=take) for _ in range(25)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sum(r is not None for r in granted) == 10
    assert book.spent() == pytest.approx(0.010)


def test_a_lock_it_cannot_take_refuses_rather_than_spends(tmp_path: Path) -> None:
    book = ledger(tmp_path, wait_s=0.05)
    lock = book.path.with_name(book.path.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("held", encoding="utf-8")
    assert book.reserve(0.001, batch="a") is None


def test_a_line_it_cannot_read_is_skipped_not_fatal(tmp_path: Path) -> None:
    book = ledger(tmp_path)
    book.reserve(0.002, batch="a")
    with book.path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    assert book.spent() == pytest.approx(0.002)


def test_the_ledger_holds_amounts_only(tmp_path: Path) -> None:
    book = ledger(tmp_path)
    book.settle(book.reserve(0.002, batch="a") or "", 0.001)
    rows = [json.loads(line) for line in book.path.read_text(encoding="utf-8").splitlines()]
    assert {key for row in rows for key in row} <= {"id", "batch", "reserved", "settled", "at"}


@pytest.mark.parametrize("cap", [0.0, -1.0, float("nan"), float("inf")])
def test_a_cap_must_be_a_positive_finite_number(tmp_path: Path, cap: float) -> None:
    with pytest.raises(ValueError):
        ledger(tmp_path, cap=cap)


def test_a_negative_reservation_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ledger(tmp_path).reserve(-0.001, batch="a")


# --- the strict lock -----------------------------------------------------------------------


def test_the_strict_lock_raises_and_the_lenient_one_runs_anyway(tmp_path: Path) -> None:
    target = tmp_path / "f"
    lock = tmp_path / "f.lock"
    lock.write_text("", encoding="utf-8")
    with (
        pytest.raises(_lockfile.LockTimeout),
        _lockfile.locked(target, wait_s=0.02, strict=True),
    ):
        pass
    ran = False
    with _lockfile.locked(target, wait_s=0.02):
        ran = True
    assert ran and lock.exists()  # the lenient path never deletes a lock it did not take


def test_a_stale_lock_is_taken_over(tmp_path: Path) -> None:
    lock = tmp_path / "f.lock"
    lock.write_text("", encoding="utf-8")
    old = lock.stat().st_mtime - 3600
    os.utime(lock, (old, old))
    with _lockfile.locked(tmp_path / "f", wait_s=0.02, stale_s=10.0, strict=True):
        assert lock.exists()
    assert not lock.exists()


# --- the decider ---------------------------------------------------------------------------


def fixed() -> FixedDecider:
    return FixedDecider({"q": Answer("truth", 0.8, truth=0.9)}, cost_usd=0.00004)


def test_under_the_cap_the_call_goes_and_the_ledger_settles_its_cost(tmp_path: Path) -> None:
    inner, book = fixed(), ledger(tmp_path)
    capped = CappedDecider(inner, ledger=book, batch="a", max_usd=0.005)
    decision = asyncio.run(capped.decide("p", "state", QS))
    assert inner.calls == 1 and decision.answer("q").truth == 0.9
    assert book.spent("a") == pytest.approx(0.00004)
    assert capped.meter.decisions == 1 and capped.meter.cost_usd == pytest.approx(0.00004)
    assert capped.name == "fixed"


def test_over_the_cap_nothing_is_called_and_the_refusal_is_unavailable(tmp_path: Path) -> None:
    inner = fixed()
    book = ledger(tmp_path, cap=0.001)
    book.reserve(0.001, batch="other")
    capped = CappedDecider(inner, ledger=book, batch="a", max_usd=0.005)
    with pytest.raises(SpendCapReached) as raised:
        asyncio.run(capped.decide("p", "state", QS))
    assert isinstance(raised.value, DeciderUnavailable)
    assert inner.calls == 0 and "cap" in str(raised.value)


def test_the_batch_cap_refuses_too(tmp_path: Path) -> None:
    inner = fixed()
    capped = CappedDecider(inner, ledger=ledger(tmp_path, cap=1.0), batch="a", max_usd=1e-7)
    with pytest.raises(SpendCapReached):
        asyncio.run(capped.decide("p", "state", QS))
    assert inner.calls == 0


def test_a_failed_call_is_settled_at_nothing(tmp_path: Path) -> None:
    book = ledger(tmp_path)
    capped = CappedDecider(BrokenDecider(), ledger=book, batch="a", max_usd=0.005)
    with pytest.raises(DeciderUnavailable):
        asyncio.run(capped.decide("p", "state", QS))
    assert book.spent() == 0.0


def test_the_squire_falls_to_its_default_at_the_cap(tmp_path: Path) -> None:
    from sanchopanza import Squire

    book = ledger(tmp_path, cap=1e-9)
    squire = Squire(CappedDecider(fixed(), ledger=book, batch="a", max_usd=1.0))
    decision = asyncio.run(squire.decide("p", "state", QS))
    assert decision.failed and "cap" in (decision.error or "")


def test_the_estimate_is_pessimistic_and_counts_images() -> None:
    text = estimate_usd({"text": "x" * 3000}, QS, price_per_mtok=0.042)
    assert text >= 1000 * 0.042 / 1e6  # at least one token per three characters
    pictured = estimate_usd({"s": image(data=b"\x89PNG")}, QS, price_per_mtok=0.042)
    assert pictured > estimate_usd({"s": "x"}, QS, price_per_mtok=0.042) + 0.0002


def test_a_given_estimator_is_used(tmp_path: Path) -> None:
    book = ledger(tmp_path, cap=0.01)
    capped = CappedDecider(fixed(), ledger=book, batch="a", max_usd=1.0,
                           estimate=lambda state, questions: 0.02)  # fmt: skip
    with pytest.raises(SpendCapReached):
        asyncio.run(capped.decide("p", "s", QS))


def test_the_wrapper_keeps_what_the_inner_decider_declares(tmp_path: Path) -> None:
    class Seeing:
        name = "seeing"
        accepts_attachments = True

        async def decide(self, point: str, state: Any, questions: Any) -> Decision:
            return Decision(point, {}, self.name, "m")

    capped = CappedDecider(Seeing(), ledger=ledger(tmp_path), batch="a", max_usd=1.0)
    assert capped.accepts_attachments is True


def test_a_call_that_may_have_reached_the_server_is_settled_at_its_estimate(
    tmp_path: Path,
) -> None:
    """A timeout after sending may still be billed: the ledger keeps the estimate, not 0."""

    class Unreachable:
        name = "jev"

        async def decide(self, point: str, state: Any, questions: Any) -> Decision:
            raise DeciderUnavailable("jev unreachable: ReadTimeout")

    book = ledger(tmp_path)
    capped = CappedDecider(Unreachable(), ledger=book, batch="a", max_usd=0.005)
    with pytest.raises(DeciderUnavailable):
        asyncio.run(capped.decide("p", "state", QS))
    assert book.spent() == pytest.approx(estimate_usd("state", QS, price_per_mtok=0.042))
    assert book.spent() > 0
