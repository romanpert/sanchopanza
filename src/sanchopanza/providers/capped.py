"""`CappedDecider`: a hard dollar cap around any decider, shared through a ledger file.

    ledger = SpendLedger("~/.cache/sanchopanza/jev114-ledger.jsonl", cap_usd=4.50)
    decider = CappedDecider(JevDecider(), ledger=ledger, batch="L1", max_usd=0.30)

Every call is first reserved in the ledger at a pessimistic estimate (`estimate_usd`: a token
per three characters of the request, plus a full-size image per attachment); when it does not
fit under the ledger's cap or the batch's `max_usd`, the inner decider is not called and
`SpendCapReached`, a `DeciderUnavailable`, is raised, so a squire falls to its default and
journals why. After the call the reservation is settled at the decision's `cost_usd` (0 when
the call failed, the estimate when it was cancelled in flight). The in-process `Meter` counts
decisions and dollars for the caller; the ledger is what holds across processes. What can still
overshoot: a call that costs more than its estimate, by the difference.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import Callable, Mapping

from .. import _lockfile
from ..budget import Meter, SpendLedger
from ..contract import Decider, DeciderUnavailable, Decision, Question, State
from ..media import attachments_in, without_attachments

CHARS_PER_TOKEN = 3  # measured 4 to 7.4 on Jev; 3 errs high
IMAGE_TOKENS = 8_200  # a 1568x1568 image at the 640x480 rate measured (about 850 tokens)
DEFAULT_PRICE_PER_MTOK = 0.042

Estimator = Callable[[State, Mapping[str, Question]], float]


class SpendCapReached(DeciderUnavailable):
    """The call was not made: it would not fit under the ledger's cap or the batch's."""


def estimate_usd(
    state: State, questions: Mapping[str, Question], *, price_per_mtok: float
) -> float:
    """A pessimistic price for one call, from the size of what would be sent."""
    asked = {key: repr(question) for key, question in questions.items()}
    sent = {"state": without_attachments(state), "questions": asked}
    text = json.dumps(sent, ensure_ascii=False, default=str)
    tokens = len(text) / CHARS_PER_TOKEN + IMAGE_TOKENS * len(attachments_in(state))
    return tokens * price_per_mtok / 1_000_000


class CappedDecider:
    """Wraps any `Decider`; refuses before calling when the ledger or the batch is full."""

    def __init__(
        self,
        inner: Decider,
        *,
        ledger: SpendLedger,
        batch: str,
        max_usd: float,
        price_per_mtok: float = DEFAULT_PRICE_PER_MTOK,
        estimate: Estimator | None = None,
    ) -> None:
        self._inner = inner
        self._ledger = ledger
        self._batch = batch
        self._max_usd = float(max_usd)
        self._price = price_per_mtok
        self._estimate = estimate
        self.name = inner.name
        self.accepts_attachments = getattr(inner, "accepts_attachments", False)
        self._meter = Meter()

    @property
    def meter(self) -> Meter:
        return self._meter

    @property
    def price_per_mtok(self) -> float:
        return self._price

    def with_long_context(self, **options: object) -> CappedDecider:
        """The inner decider's long-context twin under the same ledger, batch and caps.
        Raises `AttributeError` when the inner decider has none, as it would unwrapped. The
        twin keeps its own in-process `meter`: the ledger holds what both spend, and a squire
        that hands it one call adds that call to its own meter (`Squire.absorb`)."""
        twin = self._inner.with_long_context(**options)  # type: ignore[attr-defined]
        return CappedDecider(
            twin,
            ledger=self._ledger,
            batch=self._batch,
            max_usd=self._max_usd,
            price_per_mtok=self._price,
            estimate=self._estimate,
        )

    def _cost_of(self, state: State, questions: Mapping[str, Question]) -> float:
        if self._estimate is not None:
            return float(self._estimate(state, questions))
        return estimate_usd(state, questions, price_per_mtok=self._price)

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        estimate = self._cost_of(state, questions)
        rid = self._ledger.reserve(estimate, batch=self._batch, batch_cap_usd=self._max_usd)
        if rid is None:
            raise SpendCapReached(
                f"spend cap: a call estimated at {estimate:.6f} USD does not fit (batch "
                f"{self._batch!r} at {self._ledger.spent(self._batch):.4f} of {self._max_usd:g}, "
                f"ledger at {self._ledger.spent():.4f} of {self._ledger.cap_usd:g}); not called"
            )
        self._meter = self._meter.reserve()
        cost = 0.0
        try:
            decision = await self._inner.decide(point, state, questions)
            cost = decision.cost_usd
            return decision
        except asyncio.CancelledError:
            # Cut in flight (a deadline): the server may bill a request it received, and no
            # bill will come back. The reservation stands at its estimate.
            cost = estimate
            raise
        finally:
            self._meter = self._meter.charge(cost)
            # A settle that cannot take the lock leaves the estimate standing: safe side.
            with contextlib.suppress(_lockfile.LockTimeout, OSError):
                self._ledger.settle(rid, cost)
