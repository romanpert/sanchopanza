"""The cost of H's handoff turn, its own and not the session's (F2).

Claude Code 2.1.287 reports, for a resumed `claude -p` turn, the session's running
`total_cost_usd`: session 1 plus the turn. The turn's own cost is that total minus session 1's,
which equals the turn's own tokens priced at Claude Code's rates (`meter.CLAUDE_CODE_RATES`,
1-hour cache writes). `turn_own` takes whichever reading the numbers support; `own_row` applies
it to a row recorded with the running total.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import meter  # noqa: E402

MODEL_IDS = {"sonnet": meter.SONNET_55, "opus": meter.OPUS_55}
TOL = 1e-6  # USD
RUNNING = "running total minus session 1"
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
             model: str) -> tuple[float, str]:  # fmt: skip
    """(the turn's own cost, how it was read) from the reported total and session 1's cost."""
    if not tokens:
        return total, OWN
    cost = priced(tokens, model)
    if total - first >= 0 and abs(total - first - cost) <= TOL:
        return total - first, RUNNING
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
