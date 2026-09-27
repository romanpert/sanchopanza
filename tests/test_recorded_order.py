"""A recording must tell two option orders apart.

Found on 2026-09-25 while measuring option-order sensitivity: `key_of` serialises with
`sort_keys=True`, so a Choice asked as (agree, conflict, unrelated) and the same Choice asked
as (unrelated, conflict, agree) share a key, and a replay of the second silently returned the
answer recorded for the first. The order is part of what the model saw (the same 50 cases
moved 3-4 labels between orders, against 0 when re-asked in the same order), so a recording
carries it. Old recordings have no order and keep matching any order, as before.
"""

from __future__ import annotations

import asyncio
import json

from sanchopanza.contract import Choice, Truth
from sanchopanza.providers.recorded import RecordedDecider, RecordingDecider, key_of, order_of

STATE = {"fact_a": "a", "fact_b": "b"}
ORDERED = {"relation": Choice("How?", {"agree": "x", "conflict": "y", "unrelated": "z"})}
REVERSED = {"relation": Choice("How?", {"unrelated": "z", "conflict": "y", "agree": "x"})}


def _entry(order: str | None, choice: str) -> dict:
    line = {
        "key": key_of("facts", STATE, ORDERED),
        "point": "facts",
        "model": "jev-1.13.0",
        "default": False,
        "answers": {"relation": {"kind": "choice", "choice": choice, "confidence": 0.9}},
    }
    return {**line, "order": order} if order else line


def test_the_key_is_still_blind_to_order_and_the_order_fingerprint_is_not():
    assert key_of("facts", STATE, ORDERED) == key_of("facts", STATE, REVERSED)
    assert order_of(ORDERED) != order_of(REVERSED)
    # a Truth question has no ordered options: its fingerprint is stable
    assert order_of({"q": Truth("Is it?")}) == order_of({"q": Truth("Is it?")})


def test_a_recording_with_an_order_answers_only_that_order():
    recorded = RecordedDecider(
        [_entry(order_of(ORDERED), "agree"), _entry(order_of(REVERSED), "unrelated")]
    )
    first = asyncio.run(recorded.decide("facts", STATE, ORDERED))
    second = asyncio.run(recorded.decide("facts", STATE, REVERSED))
    assert first.answer("relation").choice == "agree"
    assert second.answer("relation").choice == "unrelated"


def test_a_legacy_recording_without_an_order_matches_any_order():
    recorded = RecordedDecider([_entry(None, "agree")])
    decision = asyncio.run(recorded.decide("facts", STATE, REVERSED))
    assert decision.answer("relation").choice == "agree"


def test_an_order_recorded_for_another_order_does_not_answer():
    recorded = RecordedDecider([_entry(order_of(REVERSED), "unrelated")])
    assert asyncio.run(recorded.decide("facts", STATE, ORDERED)).answer("relation").empty


def test_the_recorder_writes_the_order(tmp_path):
    class Fixed:
        name = "fixed"

        async def decide(self, point, state, questions):
            from sanchopanza.contract import Answer, Decision

            answer = Answer(kind="choice", choice="agree", confidence=0.9)
            return Decision(point, {"relation": answer}, "fixed", "m")

    path = tmp_path / "rec.jsonl"
    asyncio.run(RecordingDecider(Fixed(), path).decide("facts", STATE, REVERSED))
    line = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert line["order"] == order_of(REVERSED)
    replay = asyncio.run(RecordedDecider.from_file(path).decide("facts", STATE, ORDERED))
    assert replay.answer("relation").empty
