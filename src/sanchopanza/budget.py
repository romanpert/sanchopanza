"""A cap on decisions and dollars per job (`Meter`), and one shared by a batch (`SpendLedger`).

A decision costs a ten-thousandth of a dollar. A loop without a cap charges anyway. At
the cap every policy falls to its default and the journal gets one warning, not one per
decision.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import _lockfile, durable


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


class SpendLedger:
    """A hard dollar cap shared by every process of an experiment batch, in one JSON-lines file.

    `Meter` caps one job in one process. A batch of experiments runs several processes at once
    against one budget, so the count has to live on disk: every call is reserved before it is
    made, at a pessimistic estimate, and settled at what it cost once it answers. A reservation
    that would take the ledger past `cap_usd`, or the batch past its own cap, is refused, and the
    caller does not call. Reserving reads and appends under an exclusive lock
    (`_lockfile.locked(strict=True)`): a lock it cannot take within `wait_s` is a refusal, never
    a call. A reservation never settled (a process killed mid-call) keeps counting at its
    estimate: the cap errs towards spending less.

    Lines hold amounts only: `{"id", "batch", "reserved", "at"}` and `{"id", "settled"}`.
    """

    def __init__(self, path: Path | str, *, cap_usd: float, wait_s: float = 5.0) -> None:
        if not (math.isfinite(cap_usd) and cap_usd > 0):
            raise ValueError("cap_usd must be a positive, finite number of dollars")
        self.path = Path(path)
        self.cap_usd = float(cap_usd)
        self._wait_s = wait_s
        self.busy = False  # the last `reserve` refused because the lock was not had in time

    def _rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and "id" in row:
                rows.append(row)
        return rows

    @staticmethod
    def _totals(rows: list[dict[str, Any]]) -> dict[str, tuple[str, float]]:
        """Per reservation id: (batch, dollars), settled amount over reserved estimate."""
        out: dict[str, tuple[str, float]] = {}
        for row in rows:
            rid = str(row["id"])
            if "reserved" in row:
                out[rid] = (str(row.get("batch", "")), float(row["reserved"]))
            elif "settled" in row and rid in out:
                out[rid] = (out[rid][0], float(row["settled"]))
        return out

    def spent(self, batch: str | None = None) -> float:
        """Dollars committed so far: settled calls at their cost, open ones at their estimate."""
        totals = self._totals(self._rows()).values()
        return sum(usd for name, usd in totals if batch is None or name == batch)

    def _append(self, row: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        durable.append_text(self.path, json.dumps(row) + "\n")  # a line kept through a crash

    def reserve(self, usd: float, *, batch: str, batch_cap_usd: float | None = None) -> str | None:
        """A reservation id when `usd` fits under both caps, else None (do not call)."""
        if not (math.isfinite(usd) and usd >= 0):
            raise ValueError("a reservation is a non-negative, finite number of dollars")
        self.busy = False
        try:
            with _lockfile.locked(self.path, wait_s=self._wait_s, strict=True):
                totals = self._totals(self._rows()).values()
                spent = sum(amount for _, amount in totals)
                in_batch = sum(amount for name, amount in totals if name == batch)
                if spent + usd > self.cap_usd + 1e-12:
                    return None
                if batch_cap_usd is not None and in_batch + usd > batch_cap_usd + 1e-12:
                    return None
                import uuid  # here, not at the top: a hook imports this module

                rid = uuid.uuid4().hex
                self._append({"id": rid, "batch": batch, "reserved": usd, "at": time.time()})
                return rid
        except (_lockfile.LockTimeout, OSError):
            self.busy = True  # not the cap: another process held the ledger
            return None

    def settle(self, rid: str, usd: float) -> None:
        """What a reserved call cost (0 when it failed). Raises when the lock cannot be had:
        an unsettled reservation keeps its estimate, which only errs towards spending less."""
        with _lockfile.locked(self.path, wait_s=self._wait_s, strict=True):
            self._append({"id": rid, "settled": max(float(usd), 0.0)})
