"""More pages than one call holds: a tournament of in-context calls.

`chunks.context_questions` judges up to `PAGE_MAX` pages in one call, each with the others in
view, and that shape is the confirmed one (98.3 % of needed pages at 34 % of the text,
`docs/results/2026-09-27-chunks/`). Past the cap, or past Jev's 32k-token state, a set has to
be split, and a page judged among 25 strangers is not judged among its real rivals.

The tournament keeps the shape at every step. Round one splits the set into balanced groups in
their given order and keeps, from each, the pages at or above a lenient `first_cut`. The
survivors, now few, are judged together at `final_cut`: the second look is the in-context look
that made the single call work. It is the idea of LATTICE (arXiv:2510.13217): navigate a
hierarchy, score each node among siblings and a few references, carry the parent's relevance
down the path. Here the hierarchy is free (the order the pages came in); no summary is written.

Two rules from the rest of the package hold here too: a page the decider did not answer is
kept, and a round that prunes nothing ends the rounds instead of repeating them. `blend` mixes
the round-one probability into the final one, LATTICE's path relevance; 0 uses the final alone.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

Judge = Callable[[Sequence[int]], Awaitable[list[float | None]]]

MAX_ROUNDS = 3


def groups(n: int, size: int) -> list[list[int]]:
    """Indexes 0..n-1 in order, in the fewest groups of at most `size`, sizes within one."""
    if size <= 0:
        raise ValueError("group size must be positive")
    if n <= 0:
        return []
    count = -(-n // size)
    base, extra = divmod(n, count)
    out, start = [], 0
    for g in range(count):
        width = base + (1 if g < extra else 0)
        out.append(list(range(start, start + width)))
        start += width
    return out


@dataclass(frozen=True)
class Verdict:
    keep: bool
    first: float | None = None
    final: float | None = None
    score: float | None = None
    last: float | None = None  # the probability of the last round that judged the page


@dataclass(frozen=True)
class Tournament:
    pages: list[Verdict]
    calls: int
    rounds: int


async def _judge_all(
    ids: list[int], judge: Judge, size: int
) -> tuple[dict[int, float | None], int]:
    parts = [[ids[i] for i in g] for g in groups(len(ids), size)]
    answers = await asyncio.gather(*(judge(part) for part in parts))
    probs: dict[int, float | None] = {}
    for part, ps in zip(parts, answers, strict=True):
        probs.update(zip(part, ps, strict=True))
    return probs, len(parts)


def _passes(p: float | None, cut: float) -> bool:
    return p is None or p >= cut


async def tournament(
    n: int,
    judge: Judge,
    *,
    size: int,
    first_cut: float,
    final_cut: float,
    blend: float = 0.0,
) -> Tournament:
    """Judge `n` pages through `judge(ids) -> probabilities`, at most `size` per call."""
    candidates = list(range(n))
    first: dict[int, float | None] = {}
    last: dict[int, float | None] = {}
    stalled: dict[int, float | None] | None = None
    calls = rounds = 0
    while len(candidates) > size and rounds < MAX_ROUNDS:
        probs, used = await _judge_all(candidates, judge, size)
        calls += used
        rounds += 1
        for i, p in probs.items():
            first.setdefault(i, p)
            last[i] = p
        survivors = [i for i in candidates if _passes(probs[i], first_cut)]
        if len(survivors) == len(candidates):
            # This round already judged every candidate in these same groups. Asking again
            # would buy only the decider's noise (Jev is not deterministic) and made a replay
            # diverge from its recording: its answers are the final ones.
            stalled = probs
            break
        candidates = survivors
    if stalled is not None:
        final, used = stalled, 0
    else:
        final, used = await _judge_all(candidates, judge, size) if candidates else ({}, 0)
    calls += used
    last.update(final)
    pages = []
    for i in range(n):
        if i not in final:
            pages.append(Verdict(keep=False, first=first.get(i), last=last.get(i)))
            continue
        p_final, p_first = final[i], first.get(i)
        score = p_final
        if blend and p_final is not None and p_first is not None:
            score = blend * p_first + (1.0 - blend) * p_final
        pages.append(
            Verdict(
                keep=_passes(score, final_cut),
                first=p_first if rounds else p_final,
                final=p_final,
                score=score,
                last=p_final,
            )
        )
    return Tournament(pages=pages, calls=calls, rounds=rounds)
