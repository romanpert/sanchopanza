"""The `memory_write` fourth-question numbers, reproduced from the recordings. No network.

`docs/results/2026-09-25-window/memory.md` reports them. A missing recording makes the
`common` policies answer None, which fails the counts below rather than passing silently.
"""

from __future__ import annotations

import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

import memory_common  # noqa: E402

ROWS = asyncio.run(memory_common.run(offline=True))


def _score(batch: str, policy: str) -> tuple[int, int, int]:
    sub = [r for r in ROWS if r["batch"] == batch]
    agree = sum(r[policy] == r["expected"] for r in sub)
    costly = sum(r[policy] == "store" and r["expected"] == "skip" for r in sub)
    return agree, costly, sum(r[policy] is None for r in sub)


def test_every_case_was_answered_from_the_recording():
    assert all(r["P1"] is not None for r in ROWS)


def test_the_pre_registered_question_passes_on_the_batch_written_first():
    assert _score("new", "shipped") == (37, 1, 0)  # 25 / 3 at the old 0.70 / 0.75
    assert _score("new", "P1") == (45, 1, 0)


def test_the_floor_variants_as_published():
    assert _score("new2", "P1") == (28, 8, 0)
    assert _score("new2", "P3") == (32, 3, 0)
    assert _score("new3", "P1") == (20, 3, 0)
    assert _score("new3", "P4") == (22, 0, 0)


def test_the_shipped_policy_stores_few_standing_instructions_in_the_new_batches():
    instructions = [
        r for r in ROWS if r["family"] in ("A instructions", "F instructions", "F2 instructions")
    ]
    assert len(instructions) == 36
    assert sum(r["shipped"] == "store" for r in instructions) == 4  # 0 at 0.70 / 0.75
    assert sum(r["P1"] == "store" for r in instructions) == 35
