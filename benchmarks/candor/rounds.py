"""Which round of the candor benchmark a script reads and writes: `CANDOR_ROUND=1` (registered,
the default), `2` (the confirmation) or `3` (v3 on new data). Every round after the first keeps
its files apart, with a `-2` or `-3` suffix."""

from __future__ import annotations

import os
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "docs" / "results" / "2026-09-29-candor"
ROUND = os.environ.get("CANDOR_ROUND", "1")
SUFFIX = "" if ROUND == "1" else f"-{ROUND}"
RUNS = OUT / f"runs{SUFFIX}"

# Hard caps registered with each round's pre-registration (prereg-3.md for round 3): USD at list
# price for the subscription (sessions, counterfactual generator), real USD for the API arms. A
# script's flag can lower a cap, never raise it.
CAPS: dict[str, dict[str, float]] = {
    "3": {"sessions": 16.5, "counterfactual": 4.5, "haiku": 1.50, "jev": 0.30},
    "4": {"sessions": 9.5, "counterfactual": 2.5, "haiku": 0.0, "jev": 0.10},
}


def cap(name: str, requested: float) -> float:
    """`requested`, clipped to this round's registered cap for `name`, if it has one."""
    limit = CAPS.get(ROUND, {}).get(name)
    return requested if limit is None else min(requested, limit)


def path(name: str) -> Path:
    """`scored.jsonl` in round 1, `scored-2.jsonl` in round 2, `scored-3.jsonl` in round 3."""
    stem, dot, ext = name.partition(".")
    return OUT / f"{stem}{SUFFIX}{dot}{ext}"


def opaque(name: str) -> str:
    """The agent's working directory name. Round 1 used the task name, and one agent read
    "I3-missing-doc" in its path and took the task for a test: later rounds name it by hash."""
    if ROUND == "1":
        return name
    import hashlib

    return "w" + hashlib.sha256(name.encode()).hexdigest()[:10]
