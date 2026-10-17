"""Lot longdoc-free's statistics: the router composed from per-arm rows, the bootstrap by novel,
the dev rule for the cut and the fixed sequence of the confirmation. Pure; no model, no network.

A row is one item with every arm's score and cost and Jev's gate:

    {"id", "novel", "f1": {"N", "H", "H0"}, "cost": {"N", "H", "H0", "J"}, "p": Truth's p or None}

The router R at cut c answers with H where p >= c and with N elsewhere; Jev (passages + Truth) is
paid on every item: cost_R = J + (H if covered else N). A p of None (Jev gave no usable answer)
is not covered. F1 is ∞Bench's `qa_f1_score` in [0, 1]; differences are reported in points.

Questions on one novel are not independent: every interval resamples novels, with all of a
novel's items, 10,000 draws, seeded. One-sided 2.5 % is the 2.5th percentile of the draws.
"""

from __future__ import annotations

import random
import statistics
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

DRAWS = 10_000
SEED = 20261017
MARGIN = -5.0  # F1 points, both hypotheses
DEV_TOLERANCE = -2.0  # F1 points on the covered dev items
# A cut must also cover enough to be worth confirming (review of 2026-10-17): the design's
# break-even coverage (the router saves nothing below about 29 %), and at least 8 questions.
DEV_MIN_COVERAGE = 0.29
DEV_MIN_COVERED = 8
CUTS = (0.5, 0.6, 0.7, 0.8, 0.9)
MIN_COVERAGE = 0.20
ALPHA_ONE_SIDED = 0.025

Row = dict
Statistic = Callable[[Sequence[Row]], float]


def covered(row: Row, cut: float) -> bool:
    p = row.get("p")
    return p is not None and p >= cut


def router_f1(row: Row, cut: float) -> float:
    return row["f1"]["H"] if covered(row, cut) else row["f1"]["N"]


def router_cost(row: Row, cut: float) -> float:
    return row["cost"]["J"] + (row["cost"]["H"] if covered(row, cut) else row["cost"]["N"])


def mean_diff(a: Callable[[Row], float], b: Callable[[Row], float]) -> Statistic:
    """Mean of a - b over the rows, in F1 points."""

    def stat(rows: Sequence[Row]) -> float:
        return 100.0 * sum(a(r) - b(r) for r in rows) / len(rows)

    return stat


def saving(cut: float) -> Statistic:
    """Share of N's cost the router saves: 1 - sum(cost_R) / sum(cost_N)."""

    def stat(rows: Sequence[Row]) -> float:
        n = sum(r["cost"]["N"] for r in rows)
        return 1.0 - sum(router_cost(r, cut) for r in rows) / n if n else 0.0

    return stat


def coverage(rows: Sequence[Row], cut: float) -> float:
    return sum(covered(r, cut) for r in rows) / len(rows) if rows else 0.0


def by_novel(rows: Sequence[Row]) -> list[list[Row]]:
    groups: dict[str, list[Row]] = defaultdict(list)
    for row in rows:
        groups[row["novel"]].append(row)
    return [groups[k] for k in sorted(groups)]


@dataclass(frozen=True)
class Interval:
    estimate: float
    low: float  # 2.5th percentile of the draws
    high: float  # 97.5th percentile
    draws: int
    clusters: int


def bootstrap(rows: Sequence[Row], stat: Statistic, draws: int = DRAWS,
              seed: int = SEED) -> Interval:  # fmt: skip
    """Percentile interval of `stat`, resampling novels with replacement."""
    groups = by_novel(rows)
    rng = random.Random(seed)
    values = []
    for _ in range(draws):
        sample = [row for _ in groups for row in rng.choice(groups)]
        values.append(stat(sample))
    values.sort()
    low = values[int(ALPHA_ONE_SIDED * draws)]
    high = values[min(draws - 1, int((1 - ALPHA_ONE_SIDED) * draws))]
    return Interval(stat(rows), low, high, draws, len(groups))


def dev_cut(rows: Sequence[Row], cuts: Sequence[float] = CUTS) -> float | None:
    """The lowest cut that covers at least DEV_MIN_COVERAGE of the items and DEV_MIN_COVERED
    of them, and whose covered items have H - N >= DEV_TOLERANCE points (point estimate); None
    when no cut meets all three."""
    for cut in sorted(cuts):
        chosen = [r for r in rows if covered(r, cut)]
        if len(chosen) < DEV_MIN_COVERED or coverage(rows, cut) < DEV_MIN_COVERAGE:
            continue
        if mean_diff(lambda r: r["f1"]["H"], lambda r: r["f1"]["N"])(chosen) >= DEV_TOLERANCE:
            return cut
    return None


@dataclass(frozen=True)
class Verdict:
    cut: float
    router: Interval  # R - N, points
    haiku: Interval | None  # H - N, read only when the router passes
    saving: Interval
    coverage: float
    router_passes: bool
    haiku_passes: bool | None
    substitutes: bool  # router passes, coverage >= MIN_COVERAGE, saving's low bound > 0


def verdict(rows: Sequence[Row], cut: float, draws: int = DRAWS, seed: int = SEED) -> Verdict:
    """The confirmation's fixed sequence, each step one-sided at 2.5 % against MARGIN."""
    router = bootstrap(rows, mean_diff(lambda r: router_f1(r, cut), lambda r: r["f1"]["N"]),
                       draws, seed)  # fmt: skip
    saved = bootstrap(rows, saving(cut), draws, seed)
    share = coverage(rows, cut)
    router_passes = router.low > MARGIN
    haiku = haiku_passes = None
    if router_passes:
        haiku = bootstrap(rows, mean_diff(lambda r: r["f1"]["H"], lambda r: r["f1"]["N"]),
                          draws, seed)  # fmt: skip
        haiku_passes = haiku.low > MARGIN
    substitutes = router_passes and share >= MIN_COVERAGE and saved.low > 0
    return Verdict(cut, router, haiku, saved, share, router_passes, haiku_passes, substitutes)


def secondary(rows: Sequence[Row], cut: float, draws: int = DRAWS, seed: int = SEED) -> dict:
    """Registered secondaries: attribution against H0, and the plain means."""

    def f1(arm: str) -> Callable[[Row], float]:
        return lambda r: r["f1"][arm]

    return {
        "R_minus_H0": bootstrap(
            rows, mean_diff(lambda r: router_f1(r, cut), f1("H0")), draws, seed
        ),
        "H_minus_H0": bootstrap(rows, mean_diff(f1("H"), f1("H0")), draws, seed),
        "mean_f1": {
            arm: 100.0 * statistics.fmean(r["f1"][arm] for r in rows) for arm in ("N", "H", "H0")
        },  # fmt: skip
        "mean_f1_R": 100.0 * statistics.fmean(router_f1(r, cut) for r in rows),
        "cost": {arm: sum(r["cost"][arm] for r in rows) for arm in ("N", "H", "H0", "J")},
    }
