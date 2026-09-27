"""A cap on decisions and dollars per job. Immutable counter, one rule.

A decision costs a ten-thousandth of a dollar. A loop without a cap charges anyway. At
the cap every policy falls to its default and the journal gets one warning, not one per
decision.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Meter:
    decisions: int = 0
    cost_usd: float = 0.0

    def add(self, cost_usd: float) -> Meter:
        return Meter(decisions=self.decisions + 1, cost_usd=self.cost_usd + cost_usd)

    def reserve(self) -> Meter:
        """Count a decision before it is made. Concurrent callers must see it at once: a
        count taken after the await let every call of an `asyncio.gather` pass the cap
        (300 decisions under a cap of 5, review of 2026-09-25)."""
        return Meter(decisions=self.decisions + 1, cost_usd=self.cost_usd)

    def charge(self, cost_usd: float) -> Meter:
        """Settle what a reserved decision cost. The dollar cap can still overshoot by what
        the decisions in flight turn out to cost; the decision cap cannot."""
        return Meter(decisions=self.decisions, cost_usd=self.cost_usd + cost_usd)

    def within(self, max_decisions: int, max_usd: float) -> bool:
        return self.decisions < max_decisions and self.cost_usd < max_usd
