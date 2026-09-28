"""Shared helpers for the tests. No test here calls a paid provider."""

from __future__ import annotations

from typing import Any

from sanchopanza import Answer, Decision, Thresholds, _env, truth
from sanchopanza.journal import MemoryJournal
from sanchopanza.squire import Squire


def decision(point: str, **answers: Answer) -> Decision:
    return Decision(point=point, answers=answers, provider="test", model="t")


def score(value: float, confidence: float) -> Answer:
    return Answer(kind="score", score=value, confidence=confidence)


def choice(value: str, confidence: float, **probabilities: float) -> Answer:
    return Answer(kind="choice", choice=value, confidence=confidence, probabilities=probabilities)


def yes(p: float) -> Answer:
    return truth(p)


def thresholds(**changes: Any) -> Thresholds:
    return Thresholds().with_(**changes)


def squire(decider: Any, **changes: Any) -> tuple[Squire, MemoryJournal]:
    journal = MemoryJournal()
    return Squire(
        decider, thresholds=thresholds(**changes), journal=journal, brief="brief"
    ), journal


DATASET_FILES = {
    "HOTPOT": "hotpot.jsonl",
    "QASPER": "qasper-test.jsonl",
    "CODEX": "atbench-codex-test.json",
}


def dataset(name: str) -> str:
    """A local dataset that is not redistributed: `SANCHOPANZA_<name>` (or the old
    `SANCHO_<name>`), else its file in `~/.cache/sanchopanza` (or the old `~/.cache/sancho`)
    when it is there, else "" and the test skips."""
    value = _env.get(name)
    if value:
        return value
    candidate = _env.cache_dir() / DATASET_FILES[name]
    return str(candidate) if candidate.exists() else ""
