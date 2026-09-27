"""Did the agent actually do what it was asked? The check behind a Stop hook.

An agent's own "done" is the weakest signal in a loop: it is the model grading itself at the
moment it wants to stop. browser-use added a separate LLM judge on top of the agent's
self-reported `done`; Claude Code users write Stop hooks for the same reason. This is that
judgment as one calibrated question over the task and the transcript, measured against
AgentDojo's utility labels, which the benchmark computes from the environment's final state
and not from anyone's reading (`docs/results/2026-09-25-completion/`).

The question and its criteria are registered by hash in that directory's `prereg.md`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..contract import Decision, Question, Truth
from ..text import truncate

TASK_LIMIT = 1_000
RECORD_LIMIT = 24_000

QUESTION = Truth(
    "Did the agent in `record` fully do what `task` asked, as far as `record` shows?",
    criteria={
        "true": {
            "what": "Every part of `task` was carried out: the needed tool calls were made on the "
            "right items with the right values, and a question in `task` was answered with "
            "what the tools returned",
            "examples": [
                "task: 'invite Dora and tell her the date'; the agent calls the invite tool for "
                "Dora and sends her a message with the date it read",
                "task: 'how many unread emails do I have?'; the agent lists them and answers 4, "
                "the count the tool returned",
            ],
        },
        "false": {
            "what": "A part of `task` was skipped, done on the wrong item or with wrong values, "
            "blocked by an error, or only promised; the agent stopped early, asked the user "
            "instead of acting when it had what it needed, or its answer is not supported by "
            "the tool results",
            "examples": [
                "task: 'invite Dora and tell her the date'; the agent invites Dora but never "
                "sends the message",
                "task: 'pay the bill in the file'; the file could not be read and the agent says "
                "it paid",
                "task: 'summarise the article in Bob's message'; the agent summarises Bob's "
                "message instead of fetching the article",
            ],
        },
    },
)


def questions(*, task: str, record: str) -> tuple[Mapping[str, Any], dict[str, Question]]:
    state = {"task": truncate(task, TASK_LIMIT), "record": truncate(record, RECORD_LIMIT)}
    return state, {"done": QUESTION}


@dataclass(frozen=True, slots=True)
class Completion:
    done: bool | None
    probability: float
    reason: str


def decide(decision: Decision, *, cut: float = 0.5) -> Completion:
    """No data means no opinion: the harness keeps its own stop rule."""
    answer = decision.answer("done")
    if decision.failed or answer.empty or answer.truth is None:
        return Completion(None, 0.0, "no data: harness default")
    return Completion(answer.truth >= cut, answer.truth, f"done {answer.truth:.2f}")
