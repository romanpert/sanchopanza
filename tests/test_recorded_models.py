"""Recordings of two Jev versions side by side without touching a single existing key.

`key_of` had no model in it, and 38 fixtures of jev-1.13.0 answers depend on that. From 1.14
on the model enters the key, and a replay for one model never answers from the other's lines.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from sanchopanza.contract import Answer, Decision, Truth
from sanchopanza.harness.claude_code import decider_from_env
from sanchopanza.providers import create
from sanchopanza.providers.recorded import (
    RecordedDecider,
    RecordingDecider,
    fixture_path,
    key_of,
)

STATE, QS = {"task": "t"}, {"q": Truth("Is it?")}
LEGACY_KEY = "2e2d6af86d168381"  # key_of("routing", STATE, QS) before models were keyed


class Answering:
    name = "jev"

    def __init__(self, model: str, truth: float) -> None:
        self.model, self.truth = model, truth

    async def decide(self, point: str, state: Any, questions: Any) -> Decision:
        return Decision(point, {"q": Answer("truth", 0.8, truth=self.truth)}, self.name,
                        self.model, 300, 1e-5)  # fmt: skip


def record(path: Path, model: str, truth: float) -> None:
    asyncio.run(RecordingDecider(Answering(model, truth), path).decide("routing", STATE, QS))


def replay(path: Path, model: str | None = None) -> Decision:
    return asyncio.run(RecordedDecider.from_file(path, model=model).decide("routing", STATE, QS))


@pytest.mark.parametrize("model", [None, "jev-1.13.0", "jev-1.13", "jev-latest", "claude-x"])
def test_existing_keys_do_not_change(model: str | None) -> None:
    assert key_of("routing", STATE, QS) == LEGACY_KEY
    assert key_of("routing", STATE, QS, model=model) == LEGACY_KEY


def test_from_1_14_on_the_model_is_in_the_key() -> None:
    k14 = key_of("routing", STATE, QS, model="jev-1.14.0")
    assert k14 != LEGACY_KEY
    assert k14 != key_of("routing", STATE, QS, model="jev-1.15.0")


def test_a_1_13_recording_replays_as_before(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    record(path, "jev-1.13.0", 0.9)
    assert '"key": "' + LEGACY_KEY + '"' in path.read_text(encoding="utf-8")
    assert replay(path).answer("q").truth == 0.9
    assert replay(path, "jev-1.13.0").answer("q").truth == 0.9


def test_a_1_14_replay_never_answers_from_1_13_lines(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    record(path, "jev-1.13.0", 0.9)
    assert replay(path, "jev-1.14.0").answer("q").empty


def test_a_1_14_recording_is_invisible_to_a_replay_that_names_no_model(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    record(path, "jev-1.14.0", 0.2)
    assert replay(path).answer("q").empty
    assert replay(path, "jev-1.14.0").answer("q").truth == 0.2


def test_both_versions_in_one_file_each_answer_their_own(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    record(path, "jev-1.13.0", 0.9)
    record(path, "jev-1.14.0", 0.2)
    assert replay(path).answer("q").truth == 0.9
    assert replay(path, "jev-1.14.0").answer("q").truth == 0.2
    assert replay(path, "jev-1.14.0").model == "jev-1.14.0"


def test_a_1_13_default_entry_does_not_answer_for_1_14() -> None:
    entries = [{"key": "other", "point": "routing", "model": "jev-1.13.0", "default": True,
                "answers": {"q": {"kind": "truth", "confidence": 0.8, "truth": 0.9}}}]  # fmt: skip
    for_14 = RecordedDecider(entries, model="jev-1.14.0")
    replayed = asyncio.run(for_14.decide("routing", STATE, QS))
    assert replayed.answer("q").empty
    legacy = asyncio.run(RecordedDecider(entries).decide("routing", STATE, QS))
    assert legacy.answer("q").truth == 0.9


def test_fixture_path_puts_each_keyed_model_in_its_own_directory() -> None:
    base = Path("fixtures") / "chunks.jsonl"
    assert fixture_path(base, "jev-1.13.0") == base
    assert fixture_path(base, None) == base
    assert fixture_path(base, "jev-latest") == base
    assert fixture_path(base, "jev-1.14.0") == Path("fixtures") / "jev114" / "chunks.jsonl"
    assert fixture_path(str(base), "jev-1.14.2") == Path("fixtures") / "jev114" / "chunks.jsonl"


def test_create_and_the_harness_pass_the_model_to_a_replay(tmp_path: Path) -> None:
    path = tmp_path / "r.jsonl"
    record(path, "jev-1.14.0", 0.2)
    made = create("recorded", path=path, model="jev-1.14.0")
    assert asyncio.run(made.decide("routing", STATE, QS)).answer("q").truth == 0.2
    env = {"SANCHOPANZA_PROVIDER": "recorded", "SANCHOPANZA_FIXTURE": str(path),
           "SANCHOPANZA_JEV_MODEL": "jev-1.14.0"}  # fmt: skip
    built = decider_from_env(env)
    assert asyncio.run(built.decide("routing", STATE, QS)).answer("q").truth == 0.2
    assert len(create("recorded", path=path)) == 0  # no model named: the 1.14 line is not seen
