"""A number a policy cannot compare is not an answer.

`float("nan")` and httpx's JSON parser both accept NaN, and every comparison against NaN is
False. So a NaN probability walked straight past the guards written as `p < threshold ->
refuse`: `decide_write` stored on all-NaN answers, `decide_collision` overwrote a stored fact
on `contradicts=NaN`, and `routing.decide` sent a task light on `person_risk=NaN`. The old
`answers.truth(nan)` was worse still: it clamped NaN to 0.0 at confidence 1.0, a confident no.

The rule: a truth, probability or confidence that is not finite or not in [0, 1], or a score
that is not finite, makes the whole answer EMPTY - the same as the provider not answering -
so every existing "absent answer" guard applies. Recorded answers are all finite and in
range, so no shipped recording changes.

No test here calls a paid provider.
"""

from __future__ import annotations

import asyncio
import json
import math

import pytest

from sanchopanza import Answer, Decision, answers
from sanchopanza.contract import Truth
from sanchopanza.points import memory, routing
from sanchopanza.policy import probability
from sanchopanza.providers.jev import from_wire
from sanchopanza.providers.llm import answers_from
from sanchopanza.providers.local import LocalDecider

from .helpers import decision, score, thresholds, yes

NAN = float("nan")
INF = float("inf")
BAD_UNIT = [NAN, INF, -INF, -0.5, 1.5]
BAD_REAL = [NAN, INF, -INF]
T = thresholds()


def raw_truth(p: float, confidence: float | None = None) -> Answer:
    """What a provider that does not validate hands over: the raw number, no clamping."""
    c = confidence if confidence is not None else (abs(2 * p - 1) if math.isfinite(p) else p)
    return Answer(kind="truth", truth=p, confidence=c)


def wire(template: str, bad: str) -> dict:
    """A JSON body as the network delivers it; `json` accepts NaN and Infinity like httpx."""
    return json.loads(template.replace("BAD", bad))


# --- the contract: construction ----------------------------------------------------------


@pytest.mark.parametrize("bad", BAD_UNIT)
def test_a_truth_outside_the_unit_interval_is_empty(bad):
    assert Answer(kind="truth", truth=bad, confidence=0.9).empty


@pytest.mark.parametrize("bad", BAD_UNIT)
def test_a_confidence_outside_the_unit_interval_is_empty(bad):
    assert Answer(kind="truth", truth=0.9, confidence=bad).empty
    assert Answer(kind="choice", choice="a", confidence=bad).empty
    assert Answer(kind="score", score=0.3, confidence=bad).empty


@pytest.mark.parametrize("bad", BAD_REAL)
def test_a_score_that_is_not_finite_is_empty(bad):
    assert Answer(kind="score", score=bad, confidence=0.9).empty


@pytest.mark.parametrize("bad", BAD_UNIT)
def test_a_probability_outside_the_unit_interval_is_empty(bad):
    answer = Answer(kind="choice", choice="a", confidence=0.9, probabilities={"a": bad, "b": 0.1})
    assert answer.empty


def test_valid_edges_and_scale_scores_are_still_answers():
    assert not Answer(kind="truth", truth=0.0, confidence=1.0).empty
    assert not Answer(kind="truth", truth=1.0, confidence=1.0).empty
    # A score is a position on a 0..n-1 scale, not a probability: 1.87 is legitimate.
    assert not Answer(kind="score", score=1.87, confidence=0.6).empty
    assert not Answer(kind="score", score=0.0, confidence=0.0).empty


@pytest.mark.parametrize("bad", BAD_UNIT)
def test_decision_answer_hands_the_policy_a_clean_empty_answer(bad):
    """Readers that go past `.empty` to `.truth` must see None, never the raw NaN."""
    d = decision("x", q=raw_truth(bad, confidence=0.9))
    got = d.answer("q")
    assert got.empty and got.truth is None and got.confidence == 0.0
    assert got.kind == "truth"
    assert probability(got, default=0.42) == 0.42


def test_decision_answer_leaves_a_valid_answer_untouched():
    good = yes(0.93)
    assert decision("x", q=good).answer("q") is good


# --- the wire: Jev and the recorded file -------------------------------------------------


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "-0.5", "1.5"])
def test_jev_truth_off_the_wire_is_empty(bad):
    raw = wire('{"type": "noul", "noul": BAD}', bad)  # httpx parses NaN the same way
    answer = from_wire(raw)
    assert answer.empty and answer.truth is None and answer.confidence == 0.0


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-0.5", "1.5"])
def test_jev_choice_with_a_bad_confidence_or_probability_is_empty(bad):
    head = '{"type": "choice", "choice": "a", '
    conf = wire(head + '"confidence": BAD, "probabilities": {}}', bad)
    prob = wire(head + '"confidence": 0.8, "probabilities": {"a": BAD}}', bad)
    assert from_wire(conf).empty and from_wire(conf).choice is None
    assert from_wire(prob).empty and from_wire(prob).choice is None


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_jev_score_that_is_not_finite_is_empty(bad):
    raw = wire('{"type": "score", "score": BAD, "confidence": 0.9}', bad)
    answer = from_wire(raw)
    assert answer.empty and answer.score is None


def test_jev_non_numeric_value_is_empty_not_a_crash():
    assert from_wire({"type": "noul", "noul": "yes"}).empty
    assert from_wire({"type": "score", "score": "high", "confidence": 0.9}).empty


def test_jev_valid_answers_are_unchanged():
    t = from_wire({"type": "noul", "noul": 0.9})
    assert t.truth == 0.9 and t.confidence == pytest.approx(0.8)
    s = from_wire({"type": "score", "score": 1.87, "confidence": 0.7, "probabilities": {"0": 0.1}})
    assert s.score == 1.87 and s.confidence == 0.7


@pytest.mark.parametrize("bad", BAD_UNIT)
def test_a_recorded_answer_with_a_bad_number_is_empty(bad):
    answer = Answer.from_dict({"kind": "truth", "truth": bad, "confidence": 0.9})
    assert answer.empty and answer.truth is None


# --- the factories any provider uses -----------------------------------------------------


@pytest.mark.parametrize("bad", BAD_REAL)
def test_answers_truth_of_a_non_finite_number_is_empty_not_a_confident_no(bad):
    answer = answers.truth(bad)
    assert answer.empty and answer.truth is None and answer.confidence == 0.0


def test_answers_truth_still_clamps_finite_rounding():
    """Kept on purpose: `evolve` shifts probabilities and relies on the clamp."""
    assert answers.truth(1.0000001).truth == 1.0
    assert answers.truth(-1e-9).truth == 0.0


@pytest.mark.parametrize("bad", BAD_REAL)
def test_answers_choice_and_score_with_a_non_finite_mass_are_empty(bad):
    assert answers.choice({"a": bad, "b": 0.5}).empty
    assert answers.score([bad, 0.5, 0.2]).empty
    assert answers.choice({"a": 0.9, "b": 0.1}, confidence=bad).empty
    assert answers.score([0.9, 0.1], confidence=bad).empty


@pytest.mark.parametrize("bad", BAD_UNIT)
def test_answers_labelled_with_a_bad_confidence_is_empty(bad):
    assert answers.labelled("a", ["a", "b"], confidence=bad).empty


@pytest.mark.parametrize("bad", BAD_UNIT)
def test_llm_self_reported_bad_confidence_answers_nothing(bad):
    got = answers_from({"q": True, "confidence": bad}, {"q": Truth("is it?")})
    assert all(a.empty for a in got.values())


def test_a_local_handler_returning_nan_leaves_the_question_unanswered():
    local = LocalDecider({"q": lambda state, q: raw_truth(NAN)})
    d = asyncio.run(local.decide("p", "state", {"q": Truth("is it?")}))
    assert "q" not in d.answers and d.answer("q").empty


# --- the points the reviewer broke --------------------------------------------------------


def all_nan_write(**extra: Answer) -> Decision:
    return decision(
        "memory_write",
        durable=raw_truth(NAN),
        specific=raw_truth(NAN),
        derivable=raw_truth(NAN),
        **extra,
    )


def test_decide_write_does_not_store_on_nan():
    assert not memory.decide_write(all_nan_write(), T).store


@pytest.mark.parametrize("field", ["durable", "specific", "derivable"])
@pytest.mark.parametrize("bad", BAD_UNIT)
def test_decide_write_does_not_store_when_any_answer_is_unreadable(field, bad):
    good = {"durable": yes(0.97), "specific": yes(0.96), "derivable": yes(0.02)}
    d = decision("memory_write", **{**good, field: raw_truth(bad)})
    assert memory.decide_write(d, T).store is False
    assert memory.decide_write(decision("memory_write", **good), T).store is True


def test_decide_write_common_does_not_store_on_nan():
    d = all_nan_write(common=raw_truth(NAN))
    assert not memory.decide_write_common(d, T).store
    assert not memory.decide_write_common(d, T, specific_floor=0.1).store


@pytest.mark.parametrize("field", ["durable", "derivable", "common"])
def test_decide_write_common_does_not_store_when_any_answer_is_nan(field):
    good = {
        "durable": yes(0.97),
        "specific": yes(0.9),
        "derivable": yes(0.02),
        "common": yes(0.02),
    }
    d = decision("memory_write", **{**good, field: raw_truth(NAN)})
    assert memory.decide_write_common(d, T).store is False
    assert memory.decide_write_common(decision("memory_write", **good), T).store is True


@pytest.mark.parametrize("bad", BAD_UNIT)
def test_decide_collision_never_replaces_on_an_unreadable_contradiction(bad):
    d = decision("memory_collision", contradicts=raw_truth(bad), adds_nothing=yes(0.03))
    result = memory.decide_collision(d, T, newer=True)
    assert result.action != "replace"
    assert result.action == "keep_both"


def test_decide_collision_never_replaces_on_nan_answers_through_the_old_factory():
    nan = answers.truth(NAN)
    d = decision("memory_collision", contradicts=nan, adds_nothing=nan)
    assert memory.decide_collision(d, T, newer=True).action == "keep_both"


@pytest.mark.parametrize("bad", BAD_UNIT)
def test_routing_never_downgrades_on_an_unreadable_person_check(bad):
    d = decision("routing", complexity=score(0.05, 0.95), person_risk=raw_truth(bad))
    assert routing.decide(d, T).tier != "light"
    control = decision("routing", complexity=score(0.05, 0.95), person_risk=yes(0.02))
    assert routing.decide(control, T).tier == "light"


@pytest.mark.parametrize("bad", BAD_REAL)
def test_routing_ignores_a_non_finite_complexity(bad):
    d = decision("routing", complexity=score(bad, 0.95), person_risk=yes(0.02))
    result = routing.decide(d, T)
    assert result.tier == "default" and result.complexity is None


def test_a_nan_off_the_jev_wire_does_not_store_a_memory_end_to_end():
    raw = json.loads('{"type": "noul", "noul": NaN}')
    d = Decision(
        point="memory_write",
        answers={k: from_wire(raw) for k in ("durable", "specific", "derivable")},
        provider="jev",
        model="jev-1.13.0",
    )
    assert not memory.decide_write(d, T).store
