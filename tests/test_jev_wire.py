"""What Jev actually sends, from one raw response recorded as the wire returned it
(`benchmarks/jev_wire/record.py`, re-recorded when the pinned model changes). Every other
recording stores answers after `from_wire`, so only this file can check a claim about the wire."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sanchopanza.providers.jev import from_wire

RAW = Path(__file__).resolve().parents[1] / "fixtures" / "jev-wire-raw.json"


@pytest.fixture(scope="module")
def answers() -> dict:
    if not RAW.exists():
        pytest.skip("no raw recording present")
    return json.loads(RAW.read_text(encoding="utf-8"))["response"]["answers"]


def test_a_truth_answer_on_the_wire_carries_only_its_probability(answers: dict) -> None:
    """If this fails after a re-recording, Jev has started sending a Truth confidence of its
    own: `from_wire` ignores it (and warns once), and the policies built on |2p - 1| deserve a
    second look."""
    truth = answers["paid"]
    assert truth["type"] == "noul" and set(truth) == {"type", "noul"}
    assert from_wire(truth).confidence == pytest.approx(abs(2 * truth["noul"] - 1))


def test_choice_and_score_confidence_come_from_the_provider(answers: dict) -> None:
    for key in ("when", "urgency"):
        raw = answers[key]
        assert "confidence" in raw
        assert from_wire(raw).confidence == pytest.approx(raw["confidence"])
