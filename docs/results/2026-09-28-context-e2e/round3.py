"""Amendment R3: tasks t07-t12, both arms, and the round's spend gate (true cost, `costs.py`)."""

from __future__ import annotations

import costs
import tasks as gen

TASKS = [f"t{i + 1:02d}-{gen.DOMAINS[i][0]}" for i in range(6, 12)]
CLAUDE_STOP = 6.50  # ceiling 7.00


def _n(task: str) -> float:
    folder = costs.ROOT / "runs" / task
    last = costs.last_result(folder / "N", ("compact.json", "b.json")) or costs.last_result(
        folder / "A", ("result.json",)
    )
    return float(last.get("total_cost_usd") or 0.0)


def _a(task: str) -> float:
    last = costs.last_result(
        costs.ROOT / "runs-r2" / task / "A", ("a.json", "compact.json", "b.json")
    )
    return float(last.get("total_cost_usd") or 0.0)


def spent() -> float:
    """What this round has cost so far: every t07-t12 session of either arm, read from disk."""
    return sum(_n(t) + _a(t) for t in TASKS)
