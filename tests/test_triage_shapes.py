"""The two triage shapes for multi-part purposes: contribution per page, and one call per set."""

from __future__ import annotations

from sanchopanza.contract import Answer, Decision
from sanchopanza.points import triage


def test_contribution_asks_one_question_over_the_page():
    state, qs = triage.contribution_questions(purpose="p", title="t", text="x" * 5000)
    assert list(qs) == ["contributes"]
    assert len(state["text"]) <= triage.TEXT_LIMIT + len(" [...] ")


def test_set_questions_number_the_pages_and_cap_them():
    pages = [(f"title {i}", f"text {i}") for i in range(50)]
    state, qs = triage.set_questions(purpose="p", pages=pages)
    options = list(qs["needed"].options)
    assert options[0] == "P01" and len(options) == triage.SET_MAX
    assert "P01| title 0: text 0" in state["pages"]


def test_keep_from_set_keeps_by_share_and_everything_on_no_data():
    answer = Answer(
        kind="choice",
        confidence=0.6,
        choice="P02",
        probabilities={"P01": 0.3, "P02": 0.6, "P03": 0.1},
    )
    decision = Decision("triage_set", {"needed": answer}, "jev", "m")
    assert triage.keep_from_set(decision, 3, share=0.2) == [True, True, False]
    empty = Decision("triage_set", {}, "jev", "m", error="down")
    assert triage.keep_from_set(empty, 3, share=0.2) == [True, True, True]


def test_triage_part_keeps_on_contribution_and_in_doubt():
    import asyncio

    from sanchopanza import Squire, Thresholds

    class Fixed:
        name = "fixed"

        def __init__(self, p):
            self.p = p

        async def decide(self, point, state, questions):
            answers = (
                {}
                if self.p is None
                else {"contributes": Answer("truth", abs(2 * self.p - 1), truth=self.p)}
            )
            return Decision(point, answers, "fixed", "m")

    t = Thresholds()
    assert t.contributes == 0.28
    keep = asyncio.run(Squire(Fixed(0.30), thresholds=t).triage_part(purpose="p", text="x"))
    drop = asyncio.run(Squire(Fixed(0.10), thresholds=t).triage_part(purpose="p", text="x"))
    none = asyncio.run(Squire(Fixed(None), thresholds=t).triage_part(purpose="p", text="x"))
    assert keep.keep and not drop.keep and none.keep
