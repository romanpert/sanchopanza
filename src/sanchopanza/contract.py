"""The contract between an agent harness and a decision model.

A *decider* answers closed questions about a piece of text state: pick one option,
place on a scale, or say how likely a proposition is. It never generates text. It
returns probabilities and a confidence; code turns those into actions with thresholds.

Nothing in this module knows which model is behind the contract. TypeSafe's Jev, a local
classifier, a vision model, or an LLM forced into a schema all fit behind `Decider`. That
is what makes the squire swappable.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

QuestionKind = Literal["choice", "score", "truth"]
# A state is text, a mapping or a sequence, and any leaf of it may be a
# `sanchopanza.media.Attachment`. Whether a provider can read one is a property of the
# provider, declared by `Decider.accepts_attachments`; the contract only has to admit it.
State = str | Mapping[str, Any] | Sequence[Any] | Any


@dataclass(frozen=True, slots=True)
class Choice:
    """One option among several, mutually exclusive. `options` maps name to criteria."""

    instructions: str | Mapping[str, Any]
    options: Mapping[str, Any]
    kind: QuestionKind = field(default="choice", init=False)

    def __post_init__(self) -> None:
        if len(self.options) < 2:
            raise ValueError("a choice needs at least two options")


@dataclass(frozen=True, slots=True)
class Score:
    """A position on a scale of 2 to 10 levels, each described as a situation."""

    instructions: str | Mapping[str, Any]
    levels: Sequence[str | Mapping[str, Any]]
    kind: QuestionKind = field(default="score", init=False)

    def __post_init__(self) -> None:
        if not 2 <= len(self.levels) <= 10:
            raise ValueError("a score has between 2 and 10 levels")


@dataclass(frozen=True, slots=True)
class Truth:
    """A yes or no. Optional `criteria` describe the boundary of `true` and `false`."""

    instructions: str | Mapping[str, Any]
    criteria: Mapping[str, Any] | None = None
    kind: QuestionKind = field(default="truth", init=False)


Question = Choice | Score | Truth


@dataclass(frozen=True, slots=True)
class Answer:
    """The calibrated answer to one question. Immutable: it is evidence of why code acted."""

    kind: QuestionKind
    confidence: float
    choice: str | None = None
    score: float | None = None
    truth: float | None = None
    probabilities: Mapping[str, float] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        """False when a number in it is one no threshold can be compared against.

        Every comparison against NaN is False, so a guard written `p < t -> refuse` lets a
        NaN through as permission. A truth, probability or confidence must be finite and in
        [0, 1]; a score (a position on a 0..n-1 scale) must be finite.
        """
        if not is_probability(self.confidence):
            return False
        if self.truth is not None and not is_probability(self.truth):
            return False
        if self.score is not None and not _finite(self.score):
            return False
        return all(is_probability(p) for p in self.probabilities.values())

    @property
    def empty(self) -> bool:
        """True when the decider did not answer, or answered a number that is not one:
        code must use its default. An unreadable answer is an absent answer."""
        unanswered = self.choice is None and self.score is None and self.truth is None
        return unanswered or not self.valid

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "confidence": self.confidence,
            "choice": self.choice,
            "score": self.score,
            "truth": self.truth,
            "probabilities": dict(self.probabilities),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Answer:
        confidence = as_number(raw.get("confidence", 0.0))
        return usable(
            cls(
                kind=raw.get("kind", "truth"),
                confidence=math.nan if confidence is None else confidence,
                choice=raw.get("choice"),
                score=raw.get("score"),
                truth=raw.get("truth"),
                probabilities=dict(raw.get("probabilities") or {}),
            )
        )


@dataclass(frozen=True, slots=True)
class Decision:
    """A batch of answers to one state, with what it cost to obtain them."""

    point: str
    answers: Mapping[str, Answer]
    provider: str
    model: str
    input_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    error: str | None = None

    def answer(self, key: str) -> Answer:
        """The answer to one question, or an empty one if the provider did not return it
        or returned a number that is not one (see `Answer.valid`). Every point reads here,
        so whatever the provider, a NaN never reaches a threshold."""
        found = self.answers.get(key)
        return usable(found) if found is not None else Answer(kind="truth", confidence=0.0)

    @property
    def failed(self) -> bool:
        return self.error is not None


class DeciderUnavailable(RuntimeError):
    """The provider cannot answer. Callers continue with their default; they never stop."""


@runtime_checkable
class Decider(Protocol):
    """The only thing a harness knows about a decision provider."""

    name: str
    #: Whether this provider can read a `media.Attachment` in the state. Text-only
    #: providers leave it False and refuse loudly rather than dropping the attachment:
    #: answering a question about an image that was never sent is worse than not answering.
    accepts_attachments: bool = False

    async def decide(self, point: str, state: State, questions: Mapping[str, Question]) -> Decision:
        """Answer every question about the state in one call.

        Raises `DeciderUnavailable` when it cannot. Never returns made-up answers.
        """
        ...


def truth_confidence(value: float) -> float:
    """Confidence of a yes/no: 1 at the extremes, 0 at 0.5."""
    return abs(2.0 * value - 1.0)


def empty_answer(kind: QuestionKind) -> Answer:
    return Answer(kind=kind, confidence=0.0)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(value)
    except TypeError:
        return False


def is_probability(value: Any) -> bool:
    """A finite number in [0, 1]. NaN, infinities and out-of-range values are not."""
    return _finite(value) and 0.0 <= value <= 1.0


def as_number(value: Any) -> float | None:
    """A wire value as a float: None stays None, anything unparseable becomes NaN, which
    `Answer.valid` then rejects. Never raises: a malformed field is an absent answer."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan


def usable(answer: Answer) -> Answer:
    """The answer itself if it is valid, else a clean empty answer of the same kind.

    Built as a new value, never by mutating the frozen one: callers that go past `.empty`
    to `.truth` then see None and fall to their default instead of reading a NaN.
    """
    return answer if answer.valid else empty_answer(answer.kind)


def empty_decision(point: str, provider: str = "none", error: str | None = None) -> Decision:
    return Decision(point=point, answers={}, provider=provider, model="-", error=error)
