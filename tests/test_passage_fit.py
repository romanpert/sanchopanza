"""`select_passages(fit_chars=...)`: approved paragraphs that do not fit, ordered by a Score.

Opt-in (roadmap B4): without `fit_chars` nothing changes, no call is added. With it, and only
when what the two stages kept is longer than `fit_chars`, one four-level Score per delivered
paragraph (all in view, `passages.FIT_PER_CALL` per call) orders them, and the paragraphs that
do not fit in that order are dropped. A failed or missing score falls back to the tournament's
probability, so a down decider still returns text.
"""

from __future__ import annotations

import asyncio

import pytest

from sanchopanza import Squire
from sanchopanza.contract import Answer, Decision, Score
from sanchopanza.points import passages


class Staged:
    """Pages, sentences and fit scores, each from its own table; `fit_down` fails the Score."""

    name = "staged"

    def __init__(self, page_probs, *, scores=None, fit_down=False):
        self.page_probs = page_probs
        self.scores = scores or {}
        self.fit_down = fit_down
        self.calls: list[str] = []
        self.fit_states: list[dict] = []

    async def decide(self, point, state, questions):
        self.calls.append(point)
        if point == "triage_pages":
            titles = [
                int(line.split("| ", 1)[1].split(":", 1)[0]) for line in state["pages"].splitlines()
            ]
            answers = {
                key: Answer("truth", 0.8, truth=self.page_probs[t])
                for key, t in zip(questions, titles, strict=True)
            }
        elif point == "passage_fit":
            self.fit_states.append(dict(state))
            if self.fit_down:
                return Decision(point, {}, "staged", "-", error="down")
            titles = [
                int(block.split("| ", 1)[1].split("\n", 1)[0])
                for block in state["passages"].split("\n\n")
            ]
            answers = {
                key: Answer("score", 0.9, score=float(self.scores.get(t, 0)))
                for key, t in zip(questions, titles, strict=True)
            }
        else:
            answers = {key: Answer("truth", 0.8, truth=0.9) for key in questions}
        return Decision(point, answers, "staged", "m")


def _doc(n, words=4):
    body = " ".join(f"Word{j}." for j in range(words))
    return [(str(i), body) for i in range(n)]


def _delivered(out):
    return [i for i, e in enumerate(out) if e and any(k for k, _ in e)]


def test_the_fit_order_is_score_then_best_sentence_then_probability_then_page():
    scores = [1.0, 3.0, None, 3.0, 0.0, 3.0]
    best = [0.5, 0.9, 0.99, 0.9, None, 0.95]
    probs = [0.9, 0.8, 0.99, 0.95, None, 0.1]
    assert passages.fit_order(scores, best, probs) == [5, 3, 1, 0, 4, 2]


def test_without_scores_the_order_is_the_free_one():
    best = [0.6, 0.6, None]
    assert passages.fit_order([None, None, None], best, [0.8, 0.9, 0.95]) == [1, 0, 2]


def test_the_best_sentence_is_the_highest_answered_probability():
    assert passages.best_sentence([(True, 0.2), (False, None), (True, 0.7)]) == 0.7
    assert passages.best_sentence([(True, None)]) is None
    assert passages.best_sentence(None) is None


def test_fit_takes_in_order_and_skips_what_does_not_fit():
    # sizes by item; order 2, 0, 1, 3: 50 fits, 60 fits (110), 30 does not (140), 10 does (120)
    assert passages.fit([2, 0, 1, 3], [60, 30, 50, 10], 120) == frozenset({2, 0, 3})


def test_fit_refuses_a_budget_below_one():
    with pytest.raises(ValueError):
        passages.fit([0], [10], 0)


def test_the_fit_question_is_a_four_level_score_per_paragraph_all_in_view():
    state, qs = passages.fit_questions(
        purpose="What was measured?", paragraphs=[("Intro", "A."), ("Results", "B.")]
    )
    assert list(qs) == ["P01", "P02"]
    assert all(isinstance(q, Score) and len(q.levels) == 4 for q in qs.values())
    assert state["question"] == "What was measured?"
    assert state["passages"].startswith("P01| Intro\nA.")


def test_by_default_nothing_changes_and_no_fit_call_is_made():
    pages = _doc(6)
    plain = Staged([0.9] * 6)
    out = asyncio.run(Squire(plain).select_passages(purpose="p", pages=pages))
    assert "passage_fit" not in plain.calls
    assert _delivered(out) == list(range(6))


def test_what_fits_is_left_alone_with_no_call():
    pages = _doc(3)  # each paragraph delivers 4 sentences of 6 characters: 24
    decider = Staged([0.9] * 3)
    out = asyncio.run(Squire(decider).select_passages(purpose="p", pages=pages, fit_chars=72))
    assert "passage_fit" not in decider.calls
    assert _delivered(out) == [0, 1, 2]


def test_what_does_not_fit_is_cut_by_the_score_and_kept_in_page_order():
    pages = _doc(5)
    decider = Staged([0.9] * 5, scores={0: 0, 1: 1, 2: 3, 3: 0, 4: 2})
    out = asyncio.run(Squire(decider).select_passages(purpose="p", pages=pages, fit_chars=50))
    assert decider.calls.count("passage_fit") == 1
    assert _delivered(out) == [2, 4]  # the two best fit (48 of 50); output stays in page order
    assert all(out[i] is None for i in (0, 1, 3))


def test_a_failed_score_falls_back_to_the_tournament_probability():
    pages = _doc(4)
    decider = Staged([0.80, 0.99, 0.85, 0.95], fit_down=True)
    out = asyncio.run(Squire(decider).select_passages(purpose="p", pages=pages, fit_chars=50))
    assert _delivered(out) == [1, 3]


def test_without_the_score_the_free_order_cuts_and_no_call_is_made():
    pages = _doc(4)
    decider = Staged([0.80, 0.99, 0.85, 0.95], scores={0: 3, 2: 3})
    out = asyncio.run(
        Squire(decider).select_passages(purpose="p", pages=pages, fit_chars=50, fit_score=False)
    )
    assert "passage_fit" not in decider.calls
    assert _delivered(out) == [1, 3]  # every sentence at 0.9: the tournament decides


def test_many_paragraphs_are_scored_in_groups():
    n = passages.FIT_PER_CALL + 3
    decider = Staged([0.9] * n)
    asyncio.run(Squire(decider).select_passages(purpose="p", pages=_doc(n), fit_chars=30))
    assert decider.calls.count("passage_fit") == 2


def test_the_fit_calls_count_against_max_calls():
    pages = _doc(3)
    decider = Staged([0.9] * 3, scores={0: 0, 1: 0, 2: 3})
    # one tournament call and three sentence calls use the four: no score, probability order
    out = asyncio.run(
        Squire(decider).select_passages(purpose="p", pages=pages, fit_chars=30, max_calls=4)
    )
    assert "passage_fit" not in decider.calls
    assert _delivered(out) == [0]


def test_fit_chars_must_be_positive():
    with pytest.raises(ValueError):
        asyncio.run(Squire(Staged([0.9])).select_passages(purpose="p", pages=_doc(1), fit_chars=0))
