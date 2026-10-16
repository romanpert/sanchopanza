"""The shared Jev budget of the C4, C5 and C6 lots: one ledger file, one cap over all three.

Each lot reserves and settles every call in this file under its own batch name and its own batch
cap (`SpendLedger.reserve(batch=..., batch_cap_usd=...)` through `CappedDecider`), and the file
refuses any call that would take the three together past `CAP_USD`. The path is fixed: no
variable moves it. The `jev-preflight` call each lot makes before its first call is outside
the ledger (about 13 micro-USD).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sanchopanza.budget import SpendLedger  # noqa: E402

LEDGER = Path("C:/sp-runs/w17-jev/ledger.json")
CAP_USD = 6.00  # the round's Jev budget, over every lot
BATCH_CAPS = {"c4-written": 0.15, "c5-free": 2.00, "c6-window": 4.50}  # the round cap binds first


def ledger(path: Path = LEDGER) -> SpendLedger:
    return SpendLedger(path, cap_usd=CAP_USD)


def room(batch: str, path: Path = LEDGER) -> float:
    """What `batch` may still spend: its cap less its spend, and no more than the round leaves."""
    if not path.exists():
        return min(BATCH_CAPS[batch], CAP_USD)
    book = ledger(path)
    return min(BATCH_CAPS[batch] - book.spent(batch), CAP_USD - book.spent())
