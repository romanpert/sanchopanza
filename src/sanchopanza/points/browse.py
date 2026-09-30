"""Which element of a page should the agent act on next? One Truth per element, read in context.

The shape is `chunks.context_questions` moved from pages to page elements: the state carries the
goal, the actions already taken and up to `GROUP_MAX` elements, one line each, and every element
gets its own probability while the model reads the others. A Choice over the group was the
alternative; `chunks` measured that a Choice concentrates its mass on one item, which is right
when exactly one element is the target and wrong for the ranking a harness needs (the target
plus the few that could be).

The question and criteria are registered by hash in
`docs/results/2026-09-30-browse/prereg.md`: changing a string here invalidates the recording.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..contract import Decision, Question, Truth
from ..text import truncate

GROUP_MAX = 30
LINE_LIMIT = 220
DONE_MAX = 8

NEXT = Truth(
    "Is this element of `elements` the one to act on next (click it, type into it, or pick "
    "from it) to carry out `goal`, given the actions in `done`? Read the other elements as "
    "context.",
    criteria={
        "true": {
            "what": "Acting on this element is the next step toward the goal: the link, button, "
            "tab, option or filter to click, or the field to type the needed value into",
            "examples": [
                "goal 'find flights to Paris', nothing done: the destination field",
                "goal 'show only 4-star hotels', filters open: the '4 stars' checkbox",
            ],
        },
        "false": {
            "what": "Unrelated to the goal, a step already in `done`, a step that only makes "
            "sense later, or decoration and navigation that does not move toward the goal",
            "examples": [
                "goal 'find flights to Paris': the 'Careers' link in the footer",
                "the search button before the destination has been typed",
            ],
        },
    },
)


def element_id(index: int) -> str:
    return f"E{index + 1:02d}"


def _ask(label: str) -> Truth:
    return Truth(f"{label}: " + str(NEXT.instructions), criteria=NEXT.criteria)


def questions(
    *, goal: str, done: Sequence[str], lines: Sequence[str]
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """State and questions for up to `GROUP_MAX` element lines."""
    lines = list(lines)[:GROUP_MAX]
    body = "\n".join(
        f"{element_id(i)}| {truncate(line, LINE_LIMIT)}" for i, line in enumerate(lines)
    )
    recent = list(done)[-DONE_MAX:]
    state = {
        "goal": truncate(goal, 400),
        "done": "\n".join(truncate(a, 160) for a in recent) or "(nothing yet)",
        "elements": body,
    }
    qs: dict[str, Question] = {
        element_id(i): _ask(f"Element {element_id(i)}") for i in range(len(lines))
    }
    return state, qs


def probabilities(decision: Decision, n: int) -> list[float | None]:
    """One probability per element line, None where the decider said nothing."""
    return [decision.answer(element_id(i)).truth if i < GROUP_MAX else None for i in range(n)]
