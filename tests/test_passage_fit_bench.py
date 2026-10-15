"""B4 replay helpers (`benchmarks/passage_fit/orders.py`): pure, on a made-up row."""

from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
from dataclasses import replace

import pytest

from sanchopanza import Squire, Thresholds
from sanchopanza.providers.recorded import RecordedDecider

from .helpers import dataset

ROOT = pathlib.Path(__file__).resolve().parents[1]
QASPER = dataset("QASPER")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


od = _load("passage_fit_orders", ROOT / "benchmarks" / "passage_fit" / "orders.py")


def _row():
    paras = ["Aa one. Bb two.", "Cc three.", "Dd four. Ee five."]
    return {
        "question": "five",
        "pages": [("S0", paras[0]), ("S1", paras[1]), ("S2", paras[2])],
        "paras": paras,
        "sentences": [[(0, 7), (8, 15)], [(0, 9)], [(0, 8), (9, 17)]],
        "gold_s": [[False, False], [False], [False, True]],
        "para_final": [0.9, 0.8, 0.95],
        "p_s": [[0.9, 0.1], [0.5], [0.2, 0.3]],
    }


MASK = [[True, False], [True], [True, True]]


def test_delivered_counts_only_kept_sentences():
    items = od.delivered(_row(), MASK)
    assert [(it.index, it.size, it.text) for it in items] == [
        (0, 7, "Aa one."),
        (1, 9, "Cc three."),
        (2, 16, "Dd four. Ee five."),
    ]
    assert od.total(items) == 32


def test_the_arms_order_the_same_items():
    row = _row()
    items = od.delivered(row, MASK)
    by = od.orders(row, items, scores=[0.0, 1.0, 3.0])
    assert by["PAGE"] == [0, 1, 2]
    assert by["PROB"] == [2, 0, 1]
    assert by["FREE"] == [0, 1, 2]  # best sentence 0.9, 0.5, 0.3
    assert by["BM25"][0] == 2  # the only paragraph with "five"
    assert by["L4"] == [2, 1, 0]
    assert by["GOLD"][0] == 2


def test_under_budget_empties_what_does_not_fit_and_scores_gold():
    row = _row()
    items = od.delivered(row, MASK)
    page = od.under_budget(MASK, items, [0, 1, 2], 20)
    assert page == [[True, False], [True], [False, False]]
    assert od.gold_kept(row, page) == (0, 1)
    best = od.under_budget(MASK, items, [2, 1, 0], 20)
    assert od.gold_kept(row, best) == (1, 1)


def test_the_budget_is_the_median_rounded_down():
    assert od.budget_from([1000, 3456, 9000]) == 3400
    assert od.budget_from([10, 20, 30]) == 100


@pytest.mark.skipif(
    not QASPER or not pathlib.Path(QASPER).exists(), reason="SANCHOPANZA_QASPER not set"
)
def test_the_free_arm_is_what_the_library_delivers_on_the_219():
    """`select_passages(fit_chars=B, fit_score=False)` on the recording, against the FREE arm
    of the replay: the free result is the library's behaviour, not a model of it."""
    run = _load("passage_fit_run_test", ROOT / "benchmarks" / "passage_fit" / "run.py")
    derivation, rows = run.rows_of(pathlib.Path(QASPER))
    confirm = sys.modules["wholedocs_confirm"]
    budget = od.budget_from([od.total(r["items"]) for r in derivation])
    assert budget == 3400
    squire = Squire(
        RecordedDecider.from_file(confirm.FIXTURE),
        thresholds=replace(Thresholds(), max_decisions=10**7, max_usd=50.0),
    )

    async def library(row):
        out = await squire.select_passages(
            purpose=row["question"], pages=row["pages"], fit_chars=budget, fit_score=False
        )
        return [
            [False] * len(ranges) if got is None else [keep for keep, _ in got]
            for got, ranges in zip(out, row["sentences"], strict=True)
        ]

    async def everything():
        return await asyncio.gather(*(library(r) for r in rows))

    shipped = asyncio.run(everything())
    replayed = [
        od.under_budget(r["mask"], r["items"], od.orders(r, r["items"])["FREE"], budget)
        for r in rows
    ]
    assert shipped == replayed


def test_the_report_summarises_rows_that_fit_beside_rows_that_were_scored():
    run = _load("passage_fit_run_summary", ROOT / "benchmarks" / "passage_fit" / "run.py")
    over, fits = _row(), _row()
    for row in (over, fits):
        row["mask"] = MASK
        row["items"] = od.delivered(row, MASK)
    over["scores"] = [0.0, 1.0, 3.0]
    fits["scores"] = [None] * 3  # what `recorded_scores` gives a row that fits: no call
    got = run.summary([over, fits], 20)
    # the scored row keeps its answer; the unscored one falls to the free order, which drops it
    assert got["L4"]["recall"] == 0.5 and got["FREE"]["recall"] == 0.0
    assert set(got["paired"]) >= {"L4-PAGE", "L4-BM25", "L4-FREE", "L4-PROB"}


def test_the_score_calls_are_the_library_ones():
    row = _row()
    items = od.delivered(row, MASK)
    assert od.groups(items) == [[0, 1, 2]]
    state, qs = od.fit_query(row, items, [0, 1, 2])
    assert list(qs) == ["P01", "P02", "P03"]
    assert state["question"] == "five"
    assert state["passages"].startswith("P01| S0\nAa one.")
