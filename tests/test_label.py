"""Corpus labelling: rubric, cache with an age, budget, abstention reasons, files."""

from __future__ import annotations

import json

import pytest

from sanchopanza import answers
from sanchopanza.label import (
    Item,
    LabelCache,
    Row,
    Rubric,
    label,
    margin_of,
    read_items,
    summary,
    write_rows,
)
from sanchopanza.policy import Thresholds
from sanchopanza.providers.chain import CascadeDecider
from sanchopanza.providers.fixed import BrokenDecider
from sanchopanza.providers.local import LocalDecider
from sanchopanza.squire import Squire

RUBRIC = Rubric("topic", {"sports": "games and athletes", "business": "companies, markets"})


def by_word(state, question):
    text = state["text"].lower()
    if "goal" in text:
        return answers.choice({"sports": 0.9, "business": 0.05, "other": 0.05})
    if "shares" in text:
        return answers.choice({"sports": 0.1, "business": 0.85, "other": 0.05})
    if "weather" in text:
        return answers.choice({"sports": 0.05, "business": 0.05, "other": 0.9})
    return answers.choice({"sports": 0.45, "business": 0.4, "other": 0.15})


def squire(decider=None, **thresholds):
    return Squire(
        decider if decider is not None else LocalDecider(by_word, cost_usd_per_call=0.001),
        thresholds=Thresholds(**thresholds) if thresholds else None,
    )


ITEMS = [
    Item("a", "A late goal won the cup"),
    Item("b", "Shares fell after the report"),
    Item("c", "Heavy weather tomorrow"),
    Item("d", "Something in between"),
]


async def test_labels_abstentions_and_their_reasons():
    rows = await label(ITEMS, RUBRIC, squire=squire())
    got = {r.key: (r.label, r.reason) for r in rows}
    assert got == {
        "a": ("sports", ""),
        "b": ("business", ""),
        "c": (None, "other"),
        "d": (None, "below threshold"),
    }
    assert [r.key for r in rows] == ["a", "b", "c", "d"], "input order is kept"
    assert rows[0].p == pytest.approx(0.9)
    assert rows[0].margin == pytest.approx(0.85)
    assert rows[0].provider == "local"


async def test_a_broken_decider_leaves_every_row_unlabelled_and_says_so():
    rows = await label(ITEMS, RUBRIC, squire=squire(BrokenDecider()))
    assert all(r.label is None for r in rows)
    assert {r.reason for r in rows} == {"no answer"}


async def test_the_budget_stops_spending_and_the_rest_says_budget():
    rows = await label(ITEMS, RUBRIC, squire=squire(max_decisions=2), concurrency=1)
    assert sum(r.label is not None or r.reason in ("other", "below threshold") for r in rows) == 2
    assert [r.reason for r in rows][2:] == ["budget", "budget"]


async def test_the_cache_answers_repeats_for_free_until_it_is_stale(tmp_path):
    cache = LabelCache(tmp_path / "cache.jsonl")
    first = squire()
    await label(ITEMS[:2], RUBRIC, squire=first, cache=cache)
    spent = first.meter.decisions
    second = squire()
    rows = await label(ITEMS[:2], RUBRIC, squire=second, cache=LabelCache(cache.path))
    assert second.meter.decisions == 0, "a cached item is not paid twice"
    assert all(r.cached for r in rows) and spent == 2
    key = LabelCache.key("local", RUBRIC, ITEMS[0])
    stale = LabelCache(cache.path, max_age_days=1)
    assert stale.get(key, now=10**12) is None, "an entry past its age is not served"


async def test_a_new_rubric_is_a_new_cache(tmp_path):
    cache = LabelCache(tmp_path / "cache.jsonl")
    await label(ITEMS[:1], RUBRIC, squire=squire(), cache=cache)
    edited = Rubric("topic", {"sports": "games", "business": "companies, markets"})
    fresh = squire()
    await label(ITEMS[:1], edited, squire=fresh, cache=cache)
    assert fresh.meter.decisions == 1


async def test_a_failed_answer_is_never_cached(tmp_path):
    cache = LabelCache(tmp_path / "cache.jsonl")
    await label(ITEMS[:1], RUBRIC, squire=squire(BrokenDecider()), cache=cache)
    assert not cache.path.exists() or not cache.path.read_text().strip()


async def test_a_cascade_reports_which_stage_paid():
    unsure = LocalDecider(
        lambda s, q: answers.choice({"sports": 0.5, "business": 0.3, "other": 0.2})
    )
    unsure.name = "cheap"
    sure = LocalDecider(
        lambda s, q: answers.choice({"sports": 0.05, "business": 0.9, "other": 0.05})
    )
    sure.name = "dear"
    cascade = CascadeDecider(unsure, sure, tau={"choice": 0.6})
    rows = await label(ITEMS[:1], RUBRIC, squire=squire(cascade))
    assert rows[0].label == "business"
    assert rows[0].provider == "cheap>dear"


def test_margin_is_the_lead_over_the_runner_up():
    assert margin_of({"a": 0.52, "b": 0.46, "c": 0.02}) == pytest.approx(0.06)
    assert margin_of({"a": 1.0}) == 0.0


def test_rubric_from_a_list_and_validation():
    rubric = Rubric.from_mapping({"field": "tone", "labels": ["calm", "angry"]})
    assert dict(rubric.options) == {"calm": "calm", "angry": "angry"}
    with pytest.raises(ValueError):
        Rubric.from_mapping({"field": "", "labels": ["a", "b"]})
    with pytest.raises(ValueError):
        Rubric.from_mapping({"field": "x", "labels": ["only"]})


def test_files_round_trip(tmp_path):
    jsonl = tmp_path / "in.jsonl"
    jsonl.write_text('{"id": 7, "text": "hello"}\n{"text": "bye", "context": "c"}\n')
    assert read_items(jsonl) == [Item("7", "hello"), Item("1", "bye", "c")]
    csv_in = tmp_path / "in.csv"
    csv_in.write_text("key,text\nx,one\ny,two\n")
    assert [i.key for i in read_items(csv_in)] == ["x", "y"]
    txt = tmp_path / "in.txt"
    txt.write_text("one\n\ntwo\n")
    assert [i.text for i in read_items(txt)] == ["one", "two"]
    rows = [Row("x", "sports", 0.9, 0.8, "jev"), Row("y", None, 0.4, 0.1, "jev", "below threshold")]
    write_rows(tmp_path / "out.csv", rows)
    assert (tmp_path / "out.csv").read_text().splitlines()[
        2
    ] == "y,,0.4000,0.1000,jev,below threshold"
    write_rows(tmp_path / "out.jsonl", rows)
    assert json.loads((tmp_path / "out.jsonl").read_text().splitlines()[0])["label"] == "sports"
    assert summary(rows)["abstained"] == {"below threshold": 1}
