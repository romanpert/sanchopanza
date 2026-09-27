"""Long documents: the sentence window, `select_passages`, and a tournament that never re-asks.

The rule is the one confirmed on 219 new QASPER questions
(docs/results/2026-09-28-lateral-wholedocs/): only paragraphs the tournament scores at 0.75 or
more reach the sentence stage, and each kept sentence brings two neighbours. The re-asked group
was found replaying the tournaments (docs/results/2026-09-28-lateral-memo/).
"""

from __future__ import annotations

import asyncio

from sanchopanza import Squire, Thresholds
from sanchopanza.contract import Answer, Decision
from sanchopanza.points import hierarchy
from sanchopanza.text import split_sentences


class Fixed:
    name = "fixed"

    def __init__(self, probabilities):
        self.probabilities = probabilities

    async def decide(self, point, state, questions):
        answers = {
            key: Answer("truth", abs(2 * p - 1), truth=p)
            for key, p in zip(questions, self.probabilities, strict=False)
            if p is not None
        }
        return Decision(point, answers, "fixed", "m")


def test_the_document_rule_is_the_confirmed_one():
    t = Thresholds()
    assert (t.document_paragraphs, t.document_window) == (0.75, 2)


def test_the_window_keeps_neighbours_of_a_kept_sentence():
    decider = Fixed([0.0, 0.0, 0.0, 0.9, 0.0, 0.0, 0.0])
    sentences = [f"s{i}" for i in range(7)]
    squire = Squire(decider)
    plain = asyncio.run(squire.select_sentences(purpose="p", sentences=sentences))
    wide = asyncio.run(squire.select_sentences(purpose="p", sentences=sentences, window=2))
    assert [k for k, _ in plain] == [False, False, False, True, False, False, False]
    assert [k for k, _ in wide] == [False, True, True, True, True, True, False]
    assert [p for _, p in wide] == [p for _, p in plain]  # probabilities are not rewritten


def test_a_negative_window_is_refused():
    import pytest

    with pytest.raises(ValueError):
        asyncio.run(Squire(Fixed([0.9])).select_sentences(purpose="p", sentences=["a"], window=-1))


class ByStage:
    """Pages first (one call for the set), then one call per paragraph for its sentences."""

    name = "stage"

    def __init__(self, pages, sentences):
        self.pages = pages
        self.sentences = sentences
        self.sentence_calls = 0

    async def decide(self, point, state, questions):
        if point == "triage_pages":
            probs = self.pages
        else:
            probs = self.sentences[self.sentence_calls]
            self.sentence_calls += 1
        answers = {
            key: Answer("truth", abs(2 * p - 1), truth=p)
            for key, p in zip(questions, probs, strict=False)
        }
        return Decision(point, answers, "stage", "m")


def test_select_passages_sends_only_confident_paragraphs_to_the_sentence_stage():
    pages = [
        ("Intro", "One. Two. Three."),
        ("Method", "Alpha. Beta. Gamma. Delta."),
        ("Related", "Other work."),
    ]
    # paragraph 0 kept at 0.9, paragraph 1 kept at 0.5 (below the 0.75 gate), 2 dropped
    decider = ByStage([0.9, 0.5, 0.1], [[0.0, 0.9, 0.0]])
    out = asyncio.run(Squire(decider).select_passages(purpose="p", pages=pages))
    assert decider.sentence_calls == 1
    assert out[1] is None and out[2] is None
    assert [k for k, _ in out[0]] == [True, True, True]  # window 2 around "Two."


def test_split_sentences_is_the_bench_splitter():
    assert split_sentences("One. Two!  Three? 4 more. (a) b.") == [
        "One.",
        "Two!",
        "Three?",
        "4 more.",
        "(a) b.",
    ]
    assert split_sentences("") == []


def test_the_tournament_never_asks_the_same_group_twice():
    # 10 pages in groups of 4 -> [0-3] [4-6] [7-9]; pages 8 and 9 fall at round one, and the
    # 8 survivors regroup as [0-3] [4-7]: the first group is the same as before.
    probs = [0.9] * 8 + [0.1, 0.1]
    asked: list[tuple[int, ...]] = []

    async def judge(ids):
        asked.append(tuple(ids))
        return [probs[i] for i in ids]

    result = asyncio.run(hierarchy.tournament(10, judge, size=4, first_cut=0.18, final_cut=0.40))
    assert len(asked) == len(set(asked))
    assert result.calls == len(asked) == 4
    assert [v.keep for v in result.pages] == [True] * 8 + [False, False]
