"""The cost of a resumed turn, its own and not the session's: H's handoff turn (F2) and the
equal-work lot's nudge.

Claude Code 2.1.287 reports, for a resumed `claude -p` turn, the session's running
`total_cost_usd`: the resumed session plus the turn. The turn's own cost is that total minus the
resumed session's (session 1 for H's handoff, session 2 for the nudge), which equals the turn's
own tokens priced at Claude Code's rates (`meter.CLAUDE_CODE_RATES`, 1-hour cache writes).
`turn_own` takes whichever reading the numbers support, and names the running reading after the
session it subtracts (`RUNNING`, `RUNNING_S2`); `own_row` applies it to a row recorded with the
running total.

The equal-work lot's recorded rows (sealed d1c39af) carry `RUNNING` for their nudges: that run's
code named every running reading after session 1, while it subtracted session 2.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import meter  # noqa: E402

MODEL_IDS = {"sonnet": meter.SONNET_55, "opus": meter.OPUS_55}
TOL = 1e-6  # USD
RUNNING = "running total minus session 1"  # H's handoff turn resumes session 1
RUNNING_S2 = "running total minus session 2"  # the nudge resumes session 2
OWN = "the turn's own report"
PRICED = "its tokens at Claude Code's rates"


def priced(tokens: dict[str, int], model: str) -> float:
    r = meter.rates_of(meter.CLAUDE_CODE_RATES, MODEL_IDS[model])
    n = {k: int(tokens.get(k) or 0) for k in ("input", "output", "cache_read", "cache_write")}
    return (
        n["input"] * r.input
        + n["output"] * r.output
        + n["cache_read"] * r.read
        + n["cache_write"] * r.write_1h
    ) / 1e6


def turn_own(total: float, first: float, tokens: dict[str, int] | None,
             model: str, running: str = RUNNING) -> tuple[float, str]:  # fmt: skip
    """(the turn's own cost, how it was read) from the reported total and the resumed session's
    cost; `running` names the running reading (the session subtracted)."""
    if not tokens:
        return total, OWN
    cost = priced(tokens, model)
    if total - first >= 0 and abs(total - first - cost) <= TOL:
        return total - first, running
    if abs(total - cost) <= TOL:
        return total, OWN
    return cost, PRICED


def own_row(row: dict[str, Any]) -> dict[str, Any]:
    """An H row with its handoff turn at its own cost (and the arm's cost with it); a row
    already recorded that way, or of another arm, is returned as it is."""
    hand = row.get("handoff") or {}
    if row.get("arm") != "H" or not hand or "cost_reported_total" in hand:
        return row
    total = float(hand.get("cost") or 0.0)
    first = float((row.get("sessions") or [{}])[0].get("cost") or 0.0)
    own, source = turn_own(total, first, hand.get("tokens"), row["model"])
    return {**row, "cost": round(float(row["cost"]) - (total - own), 6),
            "handoff": {**hand, "cost": own, "cost_reported_total": total,
                        "cost_source": source}}  # fmt: skip
