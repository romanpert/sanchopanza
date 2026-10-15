"""Ask Jev once for what a recording lacks, under a hard cap; or count it, for free.

Shared by the B4 and A5 runners (`benchmarks/passage_fit/run.py`, `benchmarks/facts_gate/
run.py`). A query is `(point, state, questions)`. `plan` reads the recording and prices what
is missing two ways: the measured median of a real request (71 micro-USD) and the pessimistic
estimate `CappedDecider` reserves. `ask_missing` asks only what is missing, one call per
query, never again on failure: every call goes through `CappedDecider` on a ledger file, is
recorded as it answers, and the first refusal, failure or empty answer stops the run.
"""

from __future__ import annotations

import asyncio
import hashlib
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.budget import SpendLedger  # noqa: E402
from sanchopanza.providers.capped import (  # noqa: E402
    DEFAULT_PRICE_PER_MTOK,
    CappedDecider,
    estimate_usd,
)
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider  # noqa: E402

MEDIAN_REQUEST_USD = 71e-6  # a real Jev request, median (CLAUDE.md); a short question is ~29
Query = tuple[str, Any, Any]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_sealed(prereg: Path) -> None:
    sealed = prereg.with_suffix(".sha256")
    if not sealed.exists() or sealed.read_text(encoding="utf-8").strip() != digest(prereg):
        raise SystemExit(f"{prereg.name} is not sealed, or changed since: nothing spent")


def seal(prereg: Path) -> str:
    """Write the prereg's sha256 once; a different hash already there is refused, never
    overwritten (a prereg edited after its seal is an amendment, not a new seal)."""
    value = digest(prereg)
    sealed = prereg.with_suffix(".sha256")
    if sealed.exists() and sealed.read_text(encoding="utf-8").strip() not in ("", value):
        raise SystemExit(f"{sealed.name} already holds a different hash: nothing written")
    sealed.write_text(value + "\n", encoding="utf-8")
    return value


def require_file(path: Path, sha256: str) -> None:
    """The exact bytes (LF) the prereg names, or nothing is spent or scored."""
    if digest(path) != sha256:
        raise SystemExit(f"{path.name} is not the sealed file: nothing spent or scored")


async def _missing(queries: Sequence[Query], fixture: Path) -> list[Query]:
    recorded = RecordedDecider.from_file(fixture)
    out = []
    for point, state, qs in queries:
        if not (await recorded.decide(point, state, qs)).answers:
            out.append((point, state, qs))
    return out


def plan(queries: Sequence[Query], fixture: Path) -> dict[str, Any]:
    missing = asyncio.run(_missing(queries, fixture))
    pessimistic = sum(
        estimate_usd(s, q, price_per_mtok=DEFAULT_PRICE_PER_MTOK) for _, s, q in missing
    )
    return {
        "calls": len(queries),
        "recorded": len(queries) - len(missing),
        "to_ask": len(missing),
        "usd_at_median_request": round(len(missing) * MEDIAN_REQUEST_USD, 6),
        "usd_pessimistic_estimate": round(pessimistic, 6),
    }


def require_room(plan_: dict[str, Any], cap_usd: float) -> None:
    """Refuse a run whose higher estimate does not fit under its cap."""
    most = max(plan_["usd_at_median_request"], plan_["usd_pessimistic_estimate"])
    if most > cap_usd:
        raise SystemExit(f"estimated {most:.4f} USD does not fit under {cap_usd}: nothing spent")


async def ask_missing(
    queries: Sequence[Query],
    fixture: Path,
    *,
    live: Any,
    ledger: Path,
    batch: str,
    cap_usd: float,
) -> dict[str, Any]:
    """Ask `live` (a Jev decider) for each missing query, in order, one at a time."""
    todo = await _missing(queries, fixture)
    capped = CappedDecider(
        live, ledger=SpendLedger(ledger, cap_usd=cap_usd), batch=batch, max_usd=cap_usd
    )
    recorder = RecordingDecider(capped, fixture)
    asked, spent = 0, 0.0
    for point, state, qs in todo:
        try:
            decision = await recorder.decide(point, state, qs)
        except Exception as error:  # noqa: BLE001 - any refusal or failure stops the run
            stopped = f"{type(error).__name__}: {str(error)[:200]}"
            return {"asked": asked, "usd": round(spent, 6), "stopped": stopped}
        asked += 1
        spent += decision.cost_usd
        if decision.failed or not decision.answers:
            return {"asked": asked, "usd": round(spent, 6), "stopped": "failed or empty answer"}
    return {"asked": asked, "usd": round(spent, 6), "stopped": None}


def preflight(model: str) -> None:  # pragma: no cover - one real decision, ~13 micro-USD
    from sanchopanza.providers.jev import apreflight

    result = asyncio.run(apreflight(model=model))
    if not result.ok or result.model != model:
        raise SystemExit(f"preflight {model}: {result.reason}, served {result.model}")
