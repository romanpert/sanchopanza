"""The HotpotQA triage numbers, replayed from `fixtures/triage-sets.jsonl`. No network.

HotpotQA is not redistributed: set SANCHO_HOTPOT to a local JSONL export of the validation
parquet (see `benchmarks/triage_sets/run.py`) or these tests skip. What they pin is
`docs/results/2026-09-25-triage/README.md`.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "triage_sets"))

# Two benches ship a `run.py`: loaded by path under its own name, or whichever test
# imports first hands the other its module.
_spec = importlib.util.spec_from_file_location(
    "triage_sets_run", ROOT / "benchmarks" / "triage_sets" / "run.py"
)
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)

HOTPOT = os.environ.get("SANCHO_HOTPOT", "")
pytestmark = pytest.mark.skipif(
    not HOTPOT or not pathlib.Path(HOTPOT).exists(), reason="SANCHO_HOTPOT not set"
)


class Counting:
    name = "recorded"

    def __init__(self) -> None:
        self._inner = run.RecordedDecider.from_file(run.FIXTURE)
        self.missing = 0

    async def decide(self, point, state, qs):
        d = await self._inner.decide(point, state, qs)
        self.missing += not d.answers
        return d


@pytest.fixture(scope="module")
def first():
    decider = Counting()
    questions = run.load(pathlib.Path(HOTPOT))
    rows = asyncio.run(run.answers(questions, decider))
    assert decider.missing == 0
    return rows


@pytest.fixture(scope="module")
def confirm(first):
    decider = Counting()
    exclude = frozenset(r["id"] for r in first)
    questions = run.load(pathlib.Path(HOTPOT), seed=run.CONFIRM_SEED, exclude=exclude)
    rows = asyncio.run(run.answers(questions, decider, ask_set=False))
    assert decider.missing == 0
    return rows


def test_first_run_verdict_is_the_registered_negative(first):
    report = run.analyze(first)
    assert report["verdict"] == "negative"
    assert report["arms"]["shipped"]["held_out"]["joint_recall"] == 0.1589
    assert report["arms"]["contribution"]["held_out"]["joint_recall"] == 0.9603


def test_the_confirmatory_cut_is_the_one_derived_on_the_first_run(first):
    assert run.derive(first, "contribution") == run.CONFIRM_CUT


def test_confirmed_on_new_questions(confirm):
    report = run.confirm(confirm)
    assert report["verdict"] == "confirmed"
    assert report["contribution"]["joint_recall"] == 0.9333
    assert report["bm25"]["joint_recall"] == 0.8033
    assert report["shipped_045"]["joint_recall"] == 0.1967
