"""A bench must score the policy that ships, not a 0.5 cut the policy never applies.

`points/loop.decide` speaks only from `Thresholds.saturated` (0.70) and `points/injection`
flags only above `Thresholds.injection` (0.70); the bench scorer must apply the same cuts, or
"under the policy" figures describe a policy that does not ship. Also: a falsy-but-present
decider or journal must be kept, not swapped for the null one.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sanchopanza import MemoryJournal, Squire, Thresholds
from sanchopanza.eval.bench import load_cases, run_bench
from sanchopanza.providers import RecordedDecider

ROOT = Path(__file__).resolve().parents[1]


def _rows(bench: str, fixture: str) -> list:
    files = [ROOT / "benches" / bench]
    if not all(f.exists() for f in files) or not (ROOT / "fixtures" / fixture).exists():
        pytest.skip("bench or fixture not present")
    cases = load_cases(files)
    return asyncio.run(run_bench(cases, RecordedDecider.from_file(ROOT / "fixtures" / fixture)))


def test_the_loop_bench_scores_the_policy_in_force():
    t = Thresholds()
    rows = [r for r in _rows("loop-b.jsonl", "new-points-50-v2.jsonl") if r.probability is not None]
    assert rows
    assert [r.id for r in rows if r.predicted != (r.probability >= t.saturated)] == []


def test_the_injection_bench_scores_the_policy_in_force():
    t = Thresholds()
    rows = [r for r in _rows("safety.jsonl", "public-benches.jsonl") if r.point == "injection"]
    rows = [r for r in rows if r.probability is not None]
    assert rows
    assert [r.id for r in rows if r.predicted != (r.probability > t.injection)] == []


class _EmptyButPresent:
    """A decider whose container protocol says empty: `RecordedDecider` with only defaults."""

    name = "present"

    def __len__(self) -> int:
        return 0

    async def decide(self, point, state, questions):  # pragma: no cover - never reached
        raise AssertionError


def test_a_falsy_decider_is_kept_not_swapped_for_the_null_one():
    decider = _EmptyButPresent()
    assert Squire(decider).provider == "present"


def test_an_empty_journal_is_kept_not_swapped_for_the_null_one():
    journal = MemoryJournal()
    squire = Squire(journal=journal)
    squire.journal.record("x", {})
    assert len(journal.events) == 1
