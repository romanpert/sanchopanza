"""The fifty-cases-per-point bench, replayed from its recording.

No network: every decision comes from `fixtures/new-points-50-v2.jsonl`, which is the
recording of 2026-09-24 plus the re-recording made after that day's two structural fixes.
These tests pin what the bench establishes, so that a change to a question, a threshold or a
label has to be deliberate and shows up as a failing test.

The gap between the shipped policy and a plain 0.5 cut on this bench is explained by two
different causes, established on a third batch large enough to derive a threshold:

- `redundant_page` read `t.redundant`, the knob the *search* point uses for a repeated query,
  on the stated theory that they are "the same reading". Derivation on 75 new cases refuted
  it: 0.80 scores 26/34 here, its own derived 0.59 scores 33/34, with 100 % precision and
  92 % recall held out on a different batch. Fixed, and it is the first threshold in this
  repository that was derived rather than chosen. 26/34 -> 33/34.
- `memory_write` was NOT a threshold. Its losses are one family - standing instructions from
  the client - killed by the `specific` gate while `durable` scores them 0.80 to 0.88. The
  obvious patch (widen `specific`) was tried, measured and reverted: it reaches 88/100 by
  turning 5 costly-direction errors into 8, because the narrow gate had been filtering
  general knowledge as a side effect. `points/memory.py` records the defect and what it
  actually needs. Its cut was then derived on 100 cases to an 80 % precision target and
  checked on a held-out half (`docs/results/2026-09-27-memory-write-cut/`): one cut of 0.54 on
  the weakest margin, 29/34 here, every error still a refusal to store.

Total 200/212 against 202 at a plain cut: the gap is two decisions, and it was twelve.

What the tests pin:

1. the agreement per point on the harder cases;
2. **the gap between what the model orders correctly and what the shipped thresholds act
   on**, which reopened on these cases after the 0.2.0 fix had closed it on the easy ones;
3. that every error the policy makes is still a refusal to act;
4. the sample-size floor, which is the run's actual result: fifty cases per point support a
   precision target of 80 % and nothing above it.

If the benches or the fixture are absent the module is skipped.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from sanchopanza.eval.bench import load_cases, run_bench, summarize
from sanchopanza.providers import RecordedDecider

ROOT = Path(__file__).resolve().parents[1]
BENCHES = ROOT / "benches"
FIXTURE = ROOT / "fixtures" / "new-points-50-v2.jsonl"
FILES = ["loop-b.jsonl", "memory-b.jsonl", "graph-build-b.jsonl", "retrieval-b.jsonl"]
BINARY = ("extract_gate", "goal_met", "memory_write", "recall", "redundant_page", "repeats_check")


@pytest.fixture(scope="module")
def run():
    if not FIXTURE.exists() or not all((BENCHES / f).exists() for f in FILES):
        pytest.skip("fifty-case benches or fixture not present")
    cases = load_cases(BENCHES / f for f in FILES)
    results = asyncio.run(run_bench(cases, RecordedDecider.from_file(FIXTURE)))
    return summarize(results), results


def test_the_recording_covers_the_whole_bench(run):
    summary, _ = run
    assert summary["cases"] == 212
    assert summary["calls"] == 212
    assert summary["cost_usd"] / summary["calls"] < 3e-5  # 28.4 millionths of a dollar


def test_every_binary_point_reaches_fifty_with_the_first_batch(run):
    """The point of this file: 34 to 38 new cases on top of the 12 to 20 already published."""
    counts = {p: run[0]["points"][p]["n"] for p in BINARY}
    assert counts == {
        "extract_gate": 34,
        "goal_met": 36,
        "memory_write": 34,
        "recall": 36,
        "redundant_page": 34,
        "repeats_check": 38,
    }


def test_agreement_per_point_reproduces(run):
    points = run[0]["points"]
    assert points["extract_gate"]["hits"] == 30
    assert points["goal_met"]["hits"] == 34  # at `saturated` 0.70; 35 was the 0.5 cut
    assert points["memory_write"]["hits"] == 29  # 26 at 0.70 / 0.75; derived cut 0.54
    assert points["recall"]["hits"] == 36
    assert points["redundant_page"]["hits"] == 33  # 26 while it shared search's knob
    assert points["repeats_check"]["hits"] == 38  # at 0.70; the 0.5 cut had one false alarm
    assert sum(points[p]["hits"] for p in BINARY) == 200  # 197 before the 0.54 cut


def test_the_gap_against_a_plain_cut_reopened_on_the_hard_cases(run):
    """200 under the policy, 202 at 0.5: the gap is two decisions, and it was twelve.

    This test is the one that caught both structural defects, because it is the only place
    that states the gap as a number instead of describing it. Its previous docstring
    concluded the twelve-decision gap was "two single thresholds declining to act", which
    was the wrong diagnosis and stayed wrong until a bigger sample made a derivation
    possible. Kept here as a warning: a gap between an ordering and a policy is evidence
    that something is mis-specified, not evidence about which thing.
    """
    _, results = run
    binary = [r for r in results if r.point in BINARY and r.probability is not None]
    at_half = sum(1 for r in binary if _predicted_at_half(r) == r.expected)
    assert at_half == 202
    assert at_half - 200 == 2


def test_every_policy_error_is_a_refusal_to_act(run):
    """memory_write only fails by not storing; redundant_page only by not dropping."""
    _, results = run
    for point, action in (("memory_write", "store"), ("redundant_page", "drop")):
        wrong = [r for r in results if r.point == point and r.correct is False]
        assert wrong, "the point is supposed to have errors on these cases"
        assert all(r.expected == action and r.predicted != action for r in wrong)


def test_fifty_cases_support_an_eighty_percent_target_and_no_more():
    """Pure arithmetic, and the run's real finding. See `benchmarks/thresholds.py`."""
    import math

    z = 1.96

    def lower(k: int, n: int) -> float:
        centre = (k + z * z / 2) / (n + z * z)
        half = z / (n + z * z) * math.sqrt(k * (n - k) / n + z * z / 4)
        return max(0.0, centre - half)

    needed = {t: next(n for n in range(1, 1000) if lower(n, n) >= t) for t in (0.80, 0.90, 0.95)}
    assert needed == {0.80: 16, 0.90: 35, 0.95: 73}
    # A point with 50 labelled cases at a balanced mix acts on about 25 of them.
    assert lower(25, 25) >= 0.80
    assert lower(25, 25) < 0.90


def _predicted_at_half(row) -> object:
    """The label a plain 0.5 cut would give, in the row's own vocabulary."""
    high = {
        "memory_write": ("store", "skip"),
        "redundant_page": ("drop", "keep"),
        "goal_met": (True, False),
        "repeats_check": (True, False),
    }
    low = {"extract_gate": ("skip", "extract"), "recall": ("skip", "look")}
    if row.point in high:
        yes, no = high[row.point]
        return yes if row.probability >= 0.5 else no
    yes, no = low[row.point]
    return yes if row.probability <= 0.5 else no
