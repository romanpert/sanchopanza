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
"""

from __future__ import annotations

from collections.abc import Sequence


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
