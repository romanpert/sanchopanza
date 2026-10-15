"""Which paragraphs of one document reach the sentence stage of `Squire.select_passages`.

Two rules, both about calls, not about what is kept:

- A paragraph the tournament did not answer (`p is None`) is kept whole and never asked about
  its sentences. Until 2026-10-15 it went to the sentence stage like a confident one, so a
  decider that fell mid-document spent one more failing call per paragraph: a consumer counted
  90 on one document. Kept whole is what that sentence call returned anyway once it failed.
- `max_calls` bounds the calls of one document, tournament included. Its reserve is taken
  synchronously, before any `await`, so two documents judged at once never share one margin.
  The sentence stage gets what the tournament left, the surest paragraphs first; the others
  past the gate are kept whole, unjudged. `None`, the default, is no cap: the published runs.

And one opt-in step, a candidate (roadmap B4, `docs/results/2026-10-16-b4-order/`), for when
what the two stages keep is longer than the caller can deliver (`fit_chars`): a Score of four
levels per delivered paragraph, all in view, orders them, and the ones that do not fit in that
order are dropped. A yes or no cannot rank inside a budget; an agent with its own harness
orders its approved paragraphs this way, and a second Truth pass did not discriminate there.
Ties, and every paragraph whose score did not come back, go by the tournament's probability,
then page order: a down decider orders by what the tournament already said.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..contract import Question, Score
from ..text import truncate

FIT_PER_CALL = 12
FIT_LIMIT = 900
FIT_TITLE_LIMIT = 120
FIT_QUESTION_LIMIT = 1_200

FIT_LEVELS: tuple[Mapping[str, Any], ...] = (
    {
        "what": "Nothing the answer uses: another subject, or the words of `question` without "
        "a fact about them",
        "examples": [
            "(asked how full a reservoir was at year end) The committee met four times.",
        ],
    },
    {
        "what": "Background only: the same subject as `question`, but no fact its answer "
        "would state (the setting, a definition, the motivation, what others did)",
        "examples": [
            "(asked how full a reservoir was at year end) Levels are read weekly by the "
            "basin authority.",
        ],
    },
    {
        "what": "Part of the answer: a fact the answer would use for one part or one step of "
        "it, or a detail that supports it",
        "examples": [
            "(asked how full a reservoir was at year end) Inflows fell by a third after the "
            "dry spring.",
        ],
    },
    {
        "what": "The answer or its core: the passage states what `question` asks for (the "
        "value, the method, the result, the reason)",
        "examples": [
            "(asked how full a reservoir was at year end) On 31 December it held 41 % of its "
            "capacity.",
        ],
    },
)


class CallReserve:
    """The decider calls one document may still make; `None` is unlimited."""

    def __init__(self, limit: int | None) -> None:
        if limit is not None and limit < 1:
            raise ValueError("max_calls must be >= 1 (or None for no cap)")
        self._limit = limit
        self._used = 0

    def take(self) -> bool:
        """Claim one call. Synchronous, so concurrent claims cannot both get the last one."""
        if self._limit is not None and self._used >= self._limit:
            return False
        self._used += 1
        return True

    @property
    def left(self) -> int | None:
        return None if self._limit is None else self._limit - self._used


def sentence_stage(
    verdicts: Sequence[tuple[bool, float | None]], gate: float, left: int | None
) -> tuple[frozenset[int], frozenset[int]]:
    """`(judged, whole)`: the paragraphs that get a sentence call, and those kept whole.

    Judged: kept, answered at or above `gate`, the surest first while `left` lasts (ties in
    page order). Whole: kept but unanswered, or past the gate with no call left.
    """
    confident = [i for i, (keep, p) in enumerate(verdicts) if keep and p is not None and p >= gate]
    unanswered = [i for i, (keep, p) in enumerate(verdicts) if keep and p is None]
    if left is not None and len(confident) > left:
        surest = sorted(confident, key=lambda i: -(verdicts[i][1] or 0.0))[: max(0, left)]
        rest = set(confident) - set(surest)
        return frozenset(surest), frozenset(unanswered) | frozenset(rest)
    return frozenset(confident), frozenset(unanswered)


def fit_id(index: int) -> str:
    return f"P{index + 1:02d}"


def fit_questions(
    *, purpose: str, paragraphs: Sequence[tuple[str, str]]
) -> tuple[Mapping[str, Any], dict[str, Question]]:
    """One four-level Score per delivered paragraph (`(title, delivered text)`), all in view.

    The question has its own field, not cut to the 400 characters of `purpose` elsewhere: the
    compaction guard lost its request that way (`points.keep`)."""
    paragraphs = list(paragraphs)[:FIT_PER_CALL]
    body = "\n\n".join(
        f"{fit_id(i)}| {truncate(t, FIT_TITLE_LIMIT)}\n{truncate(x, FIT_LIMIT)}"
        for i, (t, x) in enumerate(paragraphs)
    )
    state = {"question": truncate(purpose, FIT_QUESTION_LIMIT), "passages": body}
    qs: dict[str, Question] = {
        fit_id(i): Score(
            f"How much of what `question` asks does passage {fit_id(i)} in `passages` "
            "answer? Read the other passages as context, and score the passage by its most "
            "useful sentence.",
            FIT_LEVELS,
        )
        for i in range(len(paragraphs))
    }
    return state, qs


def best_sentence(sentences: Sequence[tuple[bool, float | None]] | None) -> float | None:
    """The highest probability among a paragraph's judged sentences; None if none was judged."""
    answered = [p for _, p in sentences or () if p is not None]
    return max(answered) if answered else None


def fit_order(
    scores: Sequence[float | None],
    sentences: Sequence[float | None],
    probabilities: Sequence[float | None],
) -> list[int]:
    """Positions by Score (highest first), then the paragraph's best sentence probability,
    then its tournament probability, then page order. Scored paragraphs come before unscored
    ones; a probability that did not come back counts as 0. With no score at all this is the
    free order (`fit_score=False`), replayed against page order in
    `docs/results/2026-10-16-b4-order/`."""

    def zero(p: float | None) -> float:
        return p if p is not None else 0.0

    def key(i: int) -> tuple[bool, float, float, float, int]:
        s = scores[i]
        return (s is None, -zero(s), -zero(sentences[i]), -zero(probabilities[i]), i)

    return sorted(range(len(scores)), key=key)


def fit(order: Sequence[int], sizes: Sequence[int], budget: int) -> frozenset[int]:
    """The items taken in `order` while they fit in `budget`; one that does not fit is skipped
    and the next is tried, so a long paragraph never blocks the shorter ones after it."""
    if budget < 1:
        raise ValueError("fit_chars must be >= 1 (or None for no fitting)")
    taken: list[int] = []
    used = 0
    for i in order:
        if used + sizes[i] <= budget:
            taken.append(i)
            used += sizes[i]
    return frozenset(taken)
