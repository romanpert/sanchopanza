"""The tournament numbers, replayed from `fixtures/hierarchy.jsonl`. No network.

Needs the local HotpotQA export in SANCHOPANZA_HOTPOT (not redistributed), or skips. Pins
`docs/results/2026-09-27-hierarchy/README.md`.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

import pytest

from .helpers import dataset

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOTPOT = dataset("HOTPOT")
pytestmark = pytest.mark.skipif(
    not HOTPOT or not pathlib.Path(HOTPOT).exists(), reason="SANCHOPANZA_HOTPOT not set"
)


def test_the_tournament_replays_confirmed():
    out = subprocess.run(
        [sys.executable, str(ROOT / "benchmarks/hierarchy/run.py"), "--hotpot", HOTPOT],
        capture_output=True,
        text=True,
        cwd=ROOT,
        timeout=1200,
    )
    assert out.returncode == 0, out.stderr
    report = json.loads(out.stdout)
    held = report["held_out"]
    assert report["r1_from_derivation"] == 0.18
    assert (held["TOUR"]["page_joint"], held["TOUR"]["kept_share"]) == (0.965, 0.031)
    assert (held["FLAT"]["page_joint"], held["FLAT"]["kept_share"]) == (0.94, 0.0428)
    assert held["BM25_top4"]["page_joint"] == 0.505
    assert report["verdict"] == "confirmed"
    assert "live calls 0" in out.stderr


class _AsBenched:
    """The bench asked under the point name `hierarchy_context`; `triage_many` asks under
    `triage_pages`. Same question and state, so the recording answers both."""

    name = "recorded"

    def __init__(self, recorded):
        self._recorded = recorded

    async def decide(self, point, state, questions):
        return await self._recorded.decide("hierarchy_context", state, questions)


def test_the_shipped_method_keeps_exactly_what_the_bench_measured():
    # The bench wrote its two rounds by hand; this replays every question through
    # `Squire.triage_many` itself, with the derived cut, and demands the same pages kept.
    import asyncio
    import importlib.util
    from dataclasses import replace

    from sanchopanza import Squire, Thresholds
    from sanchopanza.providers.recorded import RecordedDecider

    spec = importlib.util.spec_from_file_location(
        "hierarchy_run", ROOT / "benchmarks/hierarchy/run.py"
    )
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    rows = bench.build(pathlib.Path(HOTPOT))
    recorded = RecordedDecider.from_file(bench.FIXTURE)
    asyncio.run(bench.round_one(rows, recorded))
    asyncio.run(bench.final_round(rows, recorded, 0.18))
    squire = Squire(
        _AsBenched(recorded),
        thresholds=replace(Thresholds(), max_decisions=1_000_000, max_usd=50.0),
    )

    async def shipped(row):
        out = await squire.triage_many(purpose=row["question"], pages=row["pages"])
        return [keep for keep, _ in out]

    async def every():
        return await asyncio.gather(*(shipped(r) for r in rows))

    kept = asyncio.run(every())
    benched = [bench.keep(r, "TOUR") for r in rows]
    # Every held-out question, the ones the verdict rests on, matches exactly. One derivation
    # question had 32 survivors: the bench judged them as a final in two groups, the shipped
    # method prunes once more first (more than 30 is another round). It is the only one.
    held = bench.DERIVATION
    assert benched[held:] == kept[held:]
    assert [i for i in range(held) if benched[i] != kept[i]] == [54]
