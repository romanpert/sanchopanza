"""`triage_pages` and `select_sentences`: one probability per item, doubt keeps."""

from __future__ import annotations

import asyncio

from sanchopanza import Squire, Thresholds
from sanchopanza.contract import Answer, Decision
from sanchopanza.points import chunks


class Fixed:
    name = "fixed"

    def __init__(self, probabilities):
        self.probabilities = probabilities
        self.questions = []

    async def decide(self, point, state, questions):
        self.questions.append(list(questions))
        answers = {
            key: Answer("truth", abs(2 * p - 1), truth=p)
            for key, p in zip(questions, self.probabilities, strict=False)
            if p is not None
        }
        return Decision(point, answers, "fixed", "m")


def test_the_cuts_are_the_derived_ones():
    t = Thresholds()
    assert (t.pages_in_context, t.sentences) == (0.40, 0.28)


def test_triage_pages_asks_once_and_keeps_by_page():
    decider = Fixed([0.9, 0.1, None, 0.45])
    pages = [(f"t{i}", f"x{i}") for i in range(4)]
    out = asyncio.run(Squire(decider).triage_pages(purpose="p", pages=pages))
    assert [keep for keep, _ in out] == [True, False, True, True]
    assert decider.questions == [["P01", "P02", "P03", "P04"]]


def test_pages_past_the_cap_are_kept_unjudged():
    decider = Fixed([0.0] * chunks.PAGE_MAX)
    pages = [(f"t{i}", "x") for i in range(chunks.PAGE_MAX + 2)]
    out = asyncio.run(Squire(decider).triage_pages(purpose="p", pages=pages))
    assert [keep for keep, _ in out[-2:]] == [True, True]
    assert not any(keep for keep, _ in out[: chunks.PAGE_MAX])


def test_select_sentences_keeps_what_contributes():
    decider = Fixed([0.3, 0.2, 0.8])
    out = asyncio.run(
        Squire(decider).select_sentences(purpose="p", title="t", sentences=["a", "b", "c"])
    )
    assert [keep for keep, _ in out] == [True, False, True]


class ByTitle:
    """p by page title: `hit` pages score high, `near` pages pass round one only."""

    name = "by-title"

    def __init__(self, hit, near):
        self.hit, self.near = set(hit), set(near)
        self.calls = []

    async def decide(self, point, state, questions):
        lines = state["pages"].splitlines()
        self.calls.append(len(lines))
        answers = {}
        for key, line in zip(questions, lines, strict=True):
            title = line.split("| ", 1)[1].split(":", 1)[0]
            p = 0.9 if title in self.hit else 0.25 if title in self.near else 0.02
            answers[key] = Answer("truth", abs(2 * p - 1), truth=p)
        return Decision(point, answers, "by-title", "m")


def test_the_tournament_cut_is_the_derived_one():
    assert Thresholds().pages_first_round == 0.18


def test_triage_many_runs_a_tournament_past_the_cap():
    pages = [(f"t{i}", f"x{i}") for i in range(100)]
    decider = ByTitle(hit={"t3", "t77"}, near={"t40"})
    out = asyncio.run(Squire(decider).triage_many(purpose="p", pages=pages))
    assert decider.calls == [25, 25, 25, 25, 3]
    assert [i for i, (keep, _) in enumerate(out) if keep] == [3, 77]


def test_triage_many_is_triage_pages_under_the_cap():
    pages = [(f"t{i}", f"x{i}") for i in range(12)]
    decider = ByTitle(hit={"t1"}, near=set())
    out = asyncio.run(Squire(decider).triage_many(purpose="p", pages=pages))
    assert decider.calls == [12]
    assert [keep for keep, _ in out] == [i == 1 for i in range(12)]
