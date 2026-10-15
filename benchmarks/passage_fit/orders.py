"""B4, pure: which approved paragraphs of one paper are delivered under a size budget, by arm.

A row is a QASPER question as `benchmarks/lateral/wholedocs/data.py` fills it (`paras`,
`sentences` as character ranges, `gold_s`, `para_final`), and `mask` the sentence mask of the
shipped document rule (GW: gate 0.75, cut 0.28, window 2). A paragraph is *delivered* when
the mask keeps at least one of its sentences; its size is the characters of those sentences,
as `Squire.select_passages(fit_chars=...)` counts them. Every arm takes the same delivered
paragraphs and only orders them; `passages.fit` then takes them in that order while they fit.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sanchopanza.points import passages
from sanchopanza.text import BM25Index

FREE_ARMS = ("PAGE", "PROB", "BM25", "FREE")  # the order today, then three free orders
PAID_ARM = "L4"
CEILING = "GOLD"  # descriptive only: gold paragraphs first, what no order can beat


@dataclass(frozen=True)
class Item:
    index: int  # the paragraph's position in the paper
    size: int  # characters of its kept sentences
    text: str  # its kept sentences, joined by a space


def delivered(row: dict[str, Any], mask: Sequence[Sequence[bool]]) -> list[Item]:
    out = []
    for i, (keep, ranges) in enumerate(zip(mask, row["sentences"], strict=True)):
        chosen = [row["paras"][i][a:b] for k, (a, b) in zip(keep, ranges, strict=True) if k]
        if chosen:
            out.append(Item(i, sum(len(s) for s in chosen), " ".join(chosen)))
    return out


def total(items: Sequence[Item]) -> int:
    return sum(it.size for it in items)


def budget_from(totals: Sequence[int], step: int = 100) -> int:
    """The registered budget: the median delivered size of the derivation set, rounded down
    to `step` characters. It reads no gold label."""
    return max(step, int(statistics.median(totals)) // step * step)


def bm25_order(question: str, items: Sequence[Item]) -> list[int]:
    scores = BM25Index([it.text for it in items]).scores(question)
    return sorted(range(len(items)), key=lambda j: (-scores[j], j))


def orders(
    row: dict[str, Any],
    items: Sequence[Item],
    *,
    scores: Sequence[float | None] | None = None,
) -> dict[str, list[int]]:
    """Positions in `items` by arm. `scores` (the four-level Score per item) adds `L4`."""
    n = len(items)
    probs = [row["para_final"][it.index] for it in items]
    best = [passages.best_sentence([(True, p) for p in row["p_s"][it.index]]) for it in items]
    gold = [sum(row["gold_s"][it.index]) for it in items]
    out = {
        "PAGE": list(range(n)),
        "PROB": passages.fit_order([None] * n, [None] * n, probs),
        "BM25": bm25_order(row["question"], items),
        "FREE": passages.fit_order([None] * n, best, probs),  # `fit_score=False`
        CEILING: sorted(range(n), key=lambda j: (-gold[j], j)),
    }
    if scores is not None:
        out[PAID_ARM] = passages.fit_order(list(scores), best, probs)  # `fit_score=True`
    return out


def under_budget(
    mask: Sequence[Sequence[bool]], items: Sequence[Item], order: Sequence[int], budget: int
) -> list[list[bool]]:
    """`mask` with every delivered paragraph that does not fit, in `order`, emptied."""
    sizes = [it.size for it in items]
    taken = {items[j].index for j in passages.fit(order, sizes, budget)}
    dropped = {it.index for it in items} - taken
    return [[False] * len(m) if i in dropped else list(m) for i, m in enumerate(mask)]


def gold_kept(row: dict[str, Any], mask: Sequence[Sequence[bool]]) -> tuple[int, int]:
    """(answer sentences kept, answer sentences in the paper)."""
    pairs = [
        (m, g)
        for ms, gs in zip(mask, row["gold_s"], strict=True)
        for m, g in zip(ms, gs, strict=True)
    ]
    return sum(1 for m, g in pairs if m and g), sum(1 for _, g in pairs if g)


def groups(items: Sequence[Item]) -> list[list[int]]:
    """The calls of the Score, as `Squire.select_passages(fit_chars=...)` groups them."""
    size = passages.FIT_PER_CALL
    return [list(range(a, min(a + size, len(items)))) for a in range(0, len(items), size)]


def fit_query(row: dict[str, Any], items: Sequence[Item], group: Sequence[int]) -> tuple:
    """The state and questions of one Score call: the library's own builder."""
    section = [row["pages"][items[j].index][0] for j in group]
    return passages.fit_questions(
        purpose=row["question"],
        paragraphs=[(s, items[j].text) for s, j in zip(section, group, strict=True)],
    )
