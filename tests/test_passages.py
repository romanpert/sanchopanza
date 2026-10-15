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


class Counting:
    """Answers every page and sentence question; `missing` page indexes go unanswered, and
    from call `down_after` on the decider is down (no answers at all)."""

    name = "counting"

    def __init__(self, page_probs, *, sentence_p=0.9, missing=(), down_after=None):
        self.page_probs = page_probs
        self.sentence_p = sentence_p
        self.missing = set(missing)
        self.down_after = down_after
        self.calls: list[str] = []

    async def decide(self, point, state, questions):
        self.calls.append(point)
        if self.down_after is not None and len(self.calls) > self.down_after:
            return Decision(point, {}, "counting", "-", error="down")
        if point == "triage_pages":  # each line of the state is "<id>| <title>: <text>"
            titles = [
                int(line.split("| ", 1)[1].split(":", 1)[0]) for line in state["pages"].splitlines()
            ]
            answers = {
                key: Answer("truth", 0.8, truth=self.page_probs[title])
                for key, title in zip(questions, titles, strict=True)
                if title not in self.missing
            }
        else:
            answers = {key: Answer("truth", 0.8, truth=self.sentence_p) for key in questions}
        return Decision(point, answers, "counting", "m")


def _document(n):
    return [(str(i), f"Sentence one of {i}. Sentence two of {i}.") for i in range(n)]


def test_an_unanswered_paragraph_skips_the_sentence_stage_and_is_kept_whole():
    pages = _document(3)
    decider = Counting([0.9, 0.9, 0.1], missing={1})
    out = asyncio.run(Squire(decider).select_passages(purpose="p", pages=pages))
    assert decider.calls.count("select_sentences") == 1  # paragraph 0 only
    assert out[1] == [(True, None), (True, None)]  # in doubt, text enters, at no call
    assert out[2] is None
    assert [k for k, _ in out[0]] == [True, True]


def test_a_decider_down_after_the_tournament_spends_no_sentence_calls():
    pages = _document(90)
    decider = Counting([0.9] * 90, down_after=0)  # every call fails
    out = asyncio.run(Squire(decider).select_passages(purpose="p", pages=pages))
    assert decider.calls.count("select_sentences") == 0
    assert all(got == [(True, None), (True, None)] for got in out)


def test_by_default_every_confident_paragraph_gets_its_sentence_call():
    pages = _document(50)
    decider = Counting([0.9] * 50)
    asyncio.run(Squire(decider).select_passages(purpose="p", pages=pages))
    assert decider.calls.count("select_sentences") == 50


def test_max_calls_caps_one_document_and_spends_on_the_surest_paragraphs():
    probs = [0.8] * 50
    probs[7], probs[31], probs[44] = 0.99, 0.97, 0.95
    decider = Counting(probs)
    out = asyncio.run(
        Squire(decider).select_passages(purpose="p", pages=_document(50), max_calls=5)
    )
    # two groups of 25, nothing pruned at round one: two tournament calls, three left
    assert decider.calls == ["triage_pages"] * 2 + ["select_sentences"] * 3
    judged = [i for i, got in enumerate(out) if got and got[0][1] is not None]
    assert judged == [7, 31, 44]  # the three surest paragraphs got the calls left
    # the rest past the gate are kept whole, unjudged: what the decider being down returns
    assert all(out[i] == [(True, None), (True, None)] for i in range(50) if i not in judged)


def test_max_calls_also_bounds_the_tournament():
    decider = Counting([0.9] * 200)
    out = asyncio.run(
        Squire(decider).select_passages(purpose="p", pages=_document(200), max_calls=2)
    )
    assert len(decider.calls) == 2
    assert decider.calls.count("select_sentences") == 0
    assert len(out) == 200


def test_two_documents_at_once_each_keep_their_own_reserve():
    decider = Counting([0.9] * 40)
    squire = Squire(decider)

    async def both():
        return await asyncio.gather(
            squire.select_passages(purpose="p", pages=_document(40), max_calls=5),
            squire.select_passages(purpose="q", pages=_document(40), max_calls=5),
        )

    first, second = asyncio.run(both())
    assert len(decider.calls) == 10
    assert sum(1 for got in first if got and got[0][1] is not None) == 3
    assert sum(1 for got in second if got and got[0][1] is not None) == 3


def test_max_calls_must_be_positive():
    import pytest

    with pytest.raises(ValueError):
        asyncio.run(
            Squire(Counting([0.9])).select_passages(purpose="p", pages=_document(1), max_calls=0)
        )
