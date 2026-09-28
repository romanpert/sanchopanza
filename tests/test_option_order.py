"""Option-order sensitivity of the `facts` Choice, reproduced from its recording. No network.

`docs/results/2026-09-25-order/README.md` reports these numbers. The recording carries the
order fingerprint of every arm; a missing entry leaves an answer empty and fails the counts
here instead of passing silently.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

import option_order  # noqa: E402

RESULT = asyncio.run(option_order.run(offline=True))
ARMS = RESULT["summary"]["arms"]


def test_every_arm_was_answered_from_the_recording():
    assert RESULT["summary"]["cases"] == 50
    assert RESULT["summary"]["live_cost_usd"] == 0
    assert all(arm["unanswered"] == 0 for arm in ARMS.values())


def test_reordering_moves_labels_and_re_asking_does_not():
    assert ARMS["shipped"]["flips_vs_shipped"] == 0
    assert ARMS["reversed"]["flips_vs_shipped"] == 3
    assert ARMS["rotated"]["flips_vs_shipped"] == 2
    assert ARMS["today"]["flips_vs_shipped"] == 0
    assert ARMS["today"]["max_delta_p"] == 0.15
    assert ARMS["reversed"]["max_delta_p"] == 0.31


def test_the_policy_absorbs_every_flip_in_its_abstention_band():
    assert (ARMS["shipped"]["hits"], ARMS["shipped"]["decided"]) == (36, 40)
    assert (ARMS["reversed"]["hits"], ARMS["reversed"]["decided"]) == (39, 42)
    assert (ARMS["rotated"]["hits"], ARMS["rotated"]["decided"]) == (38, 41)
    assert (ARMS["today"]["hits"], ARMS["today"]["decided"]) == (36, 40)
    flipped = [
        r
        for r in RESULT["rows"]
        if any(
            r["arms"][a]["choice"] != r["arms"]["shipped"]["choice"]
            for a in ("reversed", "rotated")
        )
    ]
    assert len(flipped) == 3  # five flips over three cases
    assert all(r["arms"]["shipped"]["confidence"] < 0.60 for r in flipped)
