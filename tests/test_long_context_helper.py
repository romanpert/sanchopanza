"""`providers.long_context.long_context_twin`: the one place that asks a decider for its
long-context twin (used by `harness.memory_window` and `points.longdoc`)."""

from __future__ import annotations

from sanchopanza.providers.long_context import long_context_twin


class Plain:
    name = "plain"


class Twin:
    name = "jev"

    def __init__(self) -> None:
        self.asked: list[float] = []

    def with_long_context(self, *, timeout_s: float) -> str:
        self.asked.append(timeout_s)
        return "twin"


class Raises:
    name = "clm"

    def with_long_context(self, **_: object) -> None:
        raise AttributeError("clm at http://localhost:8000 has no long-context mode")


def test_a_decider_with_the_mode_gives_its_twin_at_the_timeout():
    decider = Twin()
    assert long_context_twin(decider, 7.5) == ("twin", "")
    assert decider.asked == [7.5]


def test_no_mode_is_a_reason_not_an_error():
    assert long_context_twin(Plain(), 1.0) == (
        None, "the decider 'plain' has no long-context mode"
    )  # fmt: skip
    assert long_context_twin(Raises(), 1.0) == (
        None, "the decider 'clm' has no long-context mode (AttributeError)"
    )  # fmt: skip


def test_a_nameless_decider_is_named_by_a_question_mark():
    assert long_context_twin(object(), 1.0) == (None, "the decider '?' has no long-context mode")
