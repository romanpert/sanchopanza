"""Which round of the candor benchmark a script reads and writes: `CANDOR_ROUND=1` (registered,
the default) or `2` (the confirmation). Round 2 keeps every file apart, with a `-2` suffix."""

from __future__ import annotations

import os
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "docs" / "results" / "2026-09-29-candor"
ROUND = os.environ.get("CANDOR_ROUND", "1")
SUFFIX = "" if ROUND == "1" else f"-{ROUND}"
RUNS = OUT / f"runs{SUFFIX}"


def path(name: str) -> Path:
    """`scored.jsonl` in round 1, `scored-2.jsonl` in round 2."""
    stem, dot, ext = name.partition(".")
    return OUT / f"{stem}{SUFFIX}{dot}{ext}"


def opaque(name: str) -> str:
    """The agent's working directory name. Round 1 used the task name, and one agent read
    "I3-missing-doc" in its path and took the task for a test: round 2 names it by hash."""
    if ROUND == "1":
        return name
    import hashlib

    return "w" + hashlib.sha256(name.encode()).hexdigest()[:10]
