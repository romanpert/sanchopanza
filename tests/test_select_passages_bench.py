"""`Squire.select_passages` keeps exactly what the whole-document confirmation measured.

The confirmation (docs/results/2026-09-28-lateral-wholedocs/) wrote its rule by hand over
`hierarchy.tournament` and `select_sentences`. This replays each of its 219 questions through
the shipped method, on the same recording, and demands the same sentences kept. Needs the local
QASPER test export in SANCHO_QASPER (not redistributed), or skips. No network.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import pathlib
import sys
from dataclasses import replace

import pytest

from sanchopanza import Squire, Thresholds
from sanchopanza.providers.recorded import RecordedDecider

ROOT = pathlib.Path(__file__).resolve().parents[1]
QASPER = os.environ.get("SANCHO_QASPER", "")
pytestmark = pytest.mark.skipif(
    not QASPER or not pathlib.Path(QASPER).exists(), reason="SANCHO_QASPER not set"
)


def _confirm():
    path = ROOT / "benchmarks" / "lateral" / "wholedocs" / "confirm.py"
    spec = importlib.util.spec_from_file_location("wholedocs_confirm_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["wholedocs_confirm_test"] = module
    spec.loader.exec_module(module)
    return module


def test_the_shipped_method_keeps_what_the_confirmation_measured():
    confirm = _confirm()
    rows = confirm.build(pathlib.Path(QASPER))
    assert len(rows) == 219
    recorded = RecordedDecider.from_file(confirm.FIXTURE)
    squire = Squire(recorded, thresholds=replace(Thresholds(), max_decisions=10**7, max_usd=50.0))

    async def masks_of(row):
        out = await squire.select_passages(purpose=row["question"], pages=row["pages"])
        return [
            [False] * len(ranges) if got is None else [keep for keep, _ in got]
            for got, ranges in zip(out, row["sentences"], strict=True)
        ]

    async def everything():
        return await asyncio.gather(*(masks_of(r) for r in rows))

    shipped = asyncio.run(everything())
    asyncio.run(confirm.data.probe(rows, recorded, recorded))
    bench = confirm.arms(rows)["GW_frozen"]
    assert shipped == bench
    hits = confirm.hits(rows, shipped)
    assert round(sum(hits) / len(hits), 4) == 0.8721
