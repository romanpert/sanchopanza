"""Free within-result baselines for the arrival cut, each given the same characters per result.

For one tool result and a budget of characters (what the arrival cut kept of it, markers
included, or the whole result when the cut passed it through), each baseline returns the text
the agent would have got:

- `head_tail`: the first half of the budget and the last half, as a truncation keeps them.
  Issue #99 of fast-jev-compaction found head+tail hard to beat for trimming inside a result.
- `bm25`: the result split into the same blocks as the arrival cut (`blocks.split`), ranked by
  BM25 against the same purpose, taken best first while they fit, then put back in order.
- `random`: the same blocks in a seeded random order, taken while they fit.

No marker text is charged to the baselines, which gives them a few characters the arrival
cut spends on omission markers: the comparison leans, slightly, their way.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from typing import Any

from sanchopanza.context import blocks
from sanchopanza.text import bm25_scores

NAMES = ("head_tail", "bm25", "random")


def head_tail(text: str, budget: int) -> str:
    if budget >= len(text):
        return text
    head = budget // 2
    tail = budget - head
    return text[:head] + text[len(text) - tail :] if tail else text[:head]


def _fill(text: str, found: Sequence[Any], order: Sequence[int], budget: int) -> str:
    chosen: set[int] = set()
    used = 0
    for i in order:
        size = found[i].end - found[i].start
        if used + size <= budget:
            chosen.add(i)
            used += size
    return "".join(found[i].of(text) for i in sorted(chosen))


def by_bm25(text: str, found: Sequence[Any], purpose: str, budget: int) -> str:
    scores = bm25_scores(purpose, [b.of(text) for b in found])
    order = sorted(range(len(found)), key=lambda i: (-scores[i], i))
    return _fill(text, found, order, budget)


def by_random(text: str, found: Sequence[Any], budget: int, seed: str) -> str:
    order = list(range(len(found)))
    rng = random.Random(int(hashlib.sha256(seed.encode()).hexdigest()[:12], 16))
    rng.shuffle(order)
    return _fill(text, found, order, budget)


def all_of(call: Any, purpose: str, budget: int, *, seed: str) -> dict[str, str]:
    """The three baselines' texts for one call's result at `budget` characters."""
    text = call.result
    if budget >= len(text):
        return dict.fromkeys(NAMES, text)
    found = blocks.split(text, blocks.kind_of(call.tool, call.input, text))
    return {
        "head_tail": head_tail(text, budget),
        "bm25": by_bm25(text, found, purpose, budget),
        "random": by_random(text, found, budget, seed),
    }
