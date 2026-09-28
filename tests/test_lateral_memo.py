"""Remembering a group the tournament already judged: same pages kept, fewer calls. No network.

Pins `docs/results/2026-09-28-lateral-memo/README.md`. The candidate is tested without data; the
replays need SANCHOPANZA_QASPER (and SANCHOPANZA_HOTPOT for the 100-page sets), or skip.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import subprocess
import sys

import pytest

from sanchopanza.points import hierarchy

from .helpers import dataset

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "benchmarks" / "lateral" / "memo" / "run.py"
QASPER = dataset("QASPER")
HOTPOT = dataset("HOTPOT")

_spec = importlib.util.spec_from_file_location("lateral_memo_test", SCRIPT)
memo = importlib.util.module_from_spec(_spec)
sys.modules["lateral_memo_test"] = memo
_spec.loader.exec_module(memo)


def test_a_group_already_judged_is_not_asked_again():
    asked: list[tuple[int, ...]] = []

    # 38 pages: round one judges 0-18 and 19-37. Page 37 falls, 37 survive and regroup as 19 +
    # 18, so the next round's first group is 0-18 again: the same state, asked twice.
    async def judge(ids):
        asked.append(tuple(ids))
        return [0.1 if i == 37 else 0.9 for i in ids]

    async def run(fn):
        return await hierarchy.tournament(38, fn, size=30, first_cut=0.18, final_cut=0.40)

    # Before the fix the shipped tournament asked group 0-18 twice (4 calls, 60 repeats over the
    # 2026-09-27 QASPER recordings, README). It now reuses the first answers.
    shipped = asyncio.run(run(judge))
    assert len(asked) == 3 and len(set(asked)) == 3
    asked.clear()
    remembered = asyncio.run(run(memo.memoize(judge)))
    assert len(asked) == 3
    assert [v.keep for v in shipped.pages] == [v.keep for v in remembered.pages]


def test_a_repeated_group_gets_its_first_answers():
    answers = iter([[0.9, 0.1], [0.2, 0.8]])

    async def judge(ids):
        return next(answers)

    wrapped = memo.memoize(judge)

    async def twice():
        return await wrapped([0, 1]), await wrapped([0, 1]), await wrapped([1, 2])

    first, again, other = asyncio.run(twice())
    assert first == again == [0.9, 0.1]
    assert other == [0.2, 0.8]


@pytest.mark.skipif(
    not QASPER or not pathlib.Path(QASPER).exists(), reason="SANCHOPANZA_QASPER not set"
)
def test_every_recorded_tournament_keeps_the_same_pages_with_fewer_calls():
    argv = [sys.executable, str(SCRIPT), "--qasper", QASPER]
    if HOTPOT and pathlib.Path(HOTPOT).exists():
        argv += ["--hotpot", HOTPOT]
    out = subprocess.run(argv, capture_output=True, text=True, cwd=ROOT, timeout=1200)
    assert out.returncode == 0, out.stderr
    report = json.loads(out.stdout)
    # The shipped tournament memoizes since this finding, so it now makes exactly the calls of
    # the memoized one: 1,299 on the 2026-09-27 recordings, where it made 1,359 before (60
    # repeats in 36 questions, README), with the same pages kept.
    assert report["longdocs_2026_09_27"] == {
        "questions": 300,
        "calls_as_shipped": 1299,
        "calls_memoized": 1299,
        "repeated_calls": 0,
        "questions_with_a_repeat": 0,
        "same_pages_kept": 300,
    }
    assert report["wholedocs_2026_09_28"]["repeated_calls"] == 0
    assert report["wholedocs_2026_09_28"]["same_pages_kept"] == 219
    if "hierarchy_2026_09_27_held_out" in report:
        assert report["hierarchy_2026_09_27_held_out"]["repeated_calls"] == 0
        assert report["hierarchy_2026_09_27_held_out"]["same_pages_kept"] == 200
