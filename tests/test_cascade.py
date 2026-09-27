"""CascadeDecider: the expensive stage sees only what the cheap stage was unsure of."""

from __future__ import annotations

import asyncio

import pytest

from sanchopanza.contract import Answer, Choice, DeciderUnavailable, Decision, Truth
from sanchopanza.providers import CascadeDecider

QS = {
    "a": Truth("Is a?"),
    "b": Truth("Is b?"),
    "c": Choice("Which?", {"x": "x", "y": "y"}),
}


class Fixed:
    def __init__(self, name, answers, cost=0.0, fail=False):
        self.name = name
        self._answers = answers
        self._cost = cost
        self._fail = fail
        self.asked: list[tuple[str, ...]] = []

    async def decide(self, point, state, questions):
        self.asked.append(tuple(sorted(questions)))
        if self._fail:
            raise DeciderUnavailable("down")
        return Decision(
            point,
            {k: v for k, v in self._answers.items() if k in questions},
            self.name,
            f"{self.name}-model",
            cost_usd=self._cost,
        )


def truth(p: float) -> Answer:
    return Answer(kind="truth", truth=p, confidence=abs(2 * p - 1))


def run(cascade, qs=QS):
    return asyncio.run(cascade.decide("p", {"s": 1}, qs))


def test_confident_answers_never_reach_the_expensive_stage():
    cheap = Fixed("jev", {"a": truth(0.95), "b": truth(0.02), "c": Answer("choice", 0.9, "x")})
    big = Fixed("llm", {})
    decision = run(CascadeDecider(cheap, big, tau=0.5))
    assert big.asked == []
    assert decision.provider == "jev"


def test_only_the_unsure_questions_escalate_and_their_answers_replace_the_cheap_ones():
    cheap = Fixed("jev", {"a": truth(0.6), "b": truth(0.02), "c": Answer("choice", 0.3, "x")}, 1e-5)
    big = Fixed("llm", {"a": truth(0.1), "b": truth(0.99), "c": Answer("choice", 0.8, "y")}, 1e-3)
    decision = run(CascadeDecider(cheap, big, tau=0.5))
    assert big.asked == [("a", "c")]
    assert decision.answer("a").truth == 0.1  # replaced
    assert decision.answer("b").truth == 0.02  # stood: the expensive answer was never asked
    assert decision.answer("c").choice == "y"
    assert decision.provider == "jev>llm"
    assert decision.cost_usd == pytest.approx(1e-5 + 1e-3)


def test_a_threshold_per_kind():
    cheap = Fixed("jev", {"a": truth(0.7), "b": truth(0.7), "c": Answer("choice", 0.5, "x")})
    big = Fixed("llm", {"c": Answer("choice", 0.9, "y")})
    run(CascadeDecider(cheap, big, tau={"truth": 0.3, "choice": 0.6}))
    assert big.asked == [("c",)]


def test_an_empty_answer_always_escalates():
    cheap = Fixed("jev", {"a": truth(0.99), "b": truth(0.01)})
    big = Fixed("llm", {"c": Answer("choice", 0.9, "y")})
    decision = run(CascadeDecider(cheap, big, tau=0.0))
    assert big.asked == [("c",)]
    assert decision.answer("c").choice == "y"


def test_a_failed_expensive_stage_leaves_the_cheap_answers():
    cheap = Fixed("jev", {"a": truth(0.6), "b": truth(0.02), "c": Answer("choice", 0.9, "x")})
    big = Fixed("llm", {}, fail=True)
    decision = run(CascadeDecider(cheap, big, tau=0.5))
    assert decision.answer("a").truth == 0.6
    assert decision.provider == "jev"


def test_a_failed_cheap_stage_sends_everything_to_the_expensive_one():
    cheap = Fixed("jev", {}, fail=True)
    big = Fixed("llm", {"a": truth(0.9), "b": truth(0.1), "c": Answer("choice", 0.9, "x")})
    decision = run(CascadeDecider(cheap, big, tau=0.5))
    assert big.asked == [("a", "b", "c")]
    assert not decision.failed


def test_both_stages_down_raises_like_any_unavailable_decider():
    with pytest.raises(DeciderUnavailable):
        run(CascadeDecider(Fixed("jev", {}, fail=True), Fixed("llm", {}, fail=True), tau=0.5))
