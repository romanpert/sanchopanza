"""Paired statistics for lot L4 (benchmarks/jev114/l4.py): exact McNemar, AUC, a paired
bootstrap over resampling units (single items, or clusters of items), Holm, and the verdict rule
of docs/results/2026-10-15-jev114-l4/prereg.md. Pure functions, no I/O."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from math import comb
from typing import Any

BOOT = 10_000
BOOT_SEED = 20261015
NOT_WORSE = -0.02  # "no peor": the 95 % CI's lower bound of (j14 - j13r) above -2 points
ALPHA = 0.05
FAILURE_GAP = 0.02  # j14 failing on more than 2 % more items than j13r withholds a verdict

Units = Sequence[Sequence[int]]


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar p: b = only the new arm right, c = only the old one."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(min(b, c) + 1)) / 2**n
    return min(1.0, 2 * tail)


def auc(pos: Sequence[float], neg: Sequence[float]) -> float | None:
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def items_as_units(n: int) -> list[list[int]]:
    return [[i] for i in range(n)]


def clusters_as_units(keys: Sequence[str]) -> list[list[int]]:
    groups: dict[str, list[int]] = {}
    for i, key in enumerate(keys):
        groups.setdefault(key, []).append(i)
    return list(groups.values())


def bootstrap(stat: Callable[[list[int]], float | None], units: Units) -> list[float]:
    """`stat(indices)` over BOOT resamples of `units` with replacement (seeded)."""
    rng = random.Random(BOOT_SEED)
    out = []
    for _ in range(BOOT):
        idx = [i for _ in units for i in units[rng.randrange(len(units))]]
        value = stat(idx)
        if value is not None:
            out.append(value)
    return out


def ci95(values: Sequence[float]) -> tuple[float, float] | None:
    if not values:
        return None
    ordered = sorted(values)
    lo = ordered[int(0.025 * (len(ordered) - 1))]
    hi = ordered[int(0.975 * (len(ordered) - 1))]
    return (round(lo, 4), round(hi, 4))


def paired_binary(new: Sequence[bool], old: Sequence[bool], clusters: Sequence[str]) -> dict:
    """j14 against j13r on the same items: rates, exact McNemar p, and the difference's CI by
    item bootstrap (`ci95`, the registered one) and by cluster bootstrap (`ci95_cluster`)."""
    n = len(new)
    if n == 0:
        return {"n": 0, "diff": None, "p": 1.0, "ci95": None, "ci95_cluster": None}
    b = sum(x and not y for x, y in zip(new, old, strict=True))
    c = sum(y and not x for x, y in zip(new, old, strict=True))

    def diff(idx: list[int]) -> float:
        return sum(new[i] - old[i] for i in idx) / len(idx)

    return {
        "n": n, "new": round(sum(new) / n, 4), "old": round(sum(old) / n, 4),
        "diff": round(diff(list(range(n))), 4), "only_new": b, "only_old": c,
        "p": round(mcnemar_exact(b, c), 4),
        "ci95": ci95(bootstrap(diff, items_as_units(n))),
        "ci95_cluster": ci95(bootstrap(diff, clusters_as_units(clusters))),
    }  # fmt: skip


def paired_auc(
    labels: Sequence[bool], new: Sequence[float], old: Sequence[float], clusters: Sequence[str]
) -> dict[str, Any]:
    """AUC of each arm on the same items; the difference's CI and p by paired bootstrap
    (p = twice the smaller share of resampled differences on either side of 0)."""
    n = len(labels)

    def area(scores: Sequence[float], idx: list[int]) -> float | None:
        return auc([scores[i] for i in idx if labels[i]], [scores[i] for i in idx if not labels[i]])

    def diff(idx: list[int]) -> float | None:
        a, b = area(new, idx), area(old, idx)
        return None if a is None or b is None else a - b

    whole = diff(list(range(n)))
    if whole is None:
        return {"n": n, "diff": None, "p": 1.0, "ci95": None, "ci95_cluster": None}
    diffs = bootstrap(diff, items_as_units(n))
    p = 2 * min(sum(d <= 0 for d in diffs), sum(d >= 0 for d in diffs)) / len(diffs)
    return {
        "n": n, "positives": sum(labels), "new": round(area(new, list(range(n))), 4),
        "old": round(area(old, list(range(n))), 4), "diff": round(whole, 4),
        "p": round(min(1.0, p), 4), "ci95": ci95(diffs),
        "ci95_cluster": ci95(bootstrap(diff, clusters_as_units(clusters))),
    }  # fmt: skip


def holm(pvalues: dict[str, float]) -> dict[str, float]:
    """Holm-adjusted p-values, monotone, capped at 1."""
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    out, running = {}, 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (len(ordered) - rank) * p))
        out[name] = round(running, 4)
    return out


def verdict(result: dict[str, Any], adjusted_p: float, failure_gap: float = 0.0) -> str:
    """The registered rule. A comparison not measured, or one where j14 failed on more than
    FAILURE_GAP more of the items than j13r, gets no favourable verdict."""
    if result.get("diff") is None or result.get("ci95") is None:
        return "no medido"
    if failure_gap > FAILURE_GAP:
        return "no concluyente o peor"
    if result["diff"] > 0 and adjusted_p < ALPHA:
        return "mejora"
    if result["ci95"][0] > NOT_WORSE:
        return "no peor"
    return "no concluyente o peor"
