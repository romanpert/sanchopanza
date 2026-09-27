"""The numeric regularizers of an RRSI-style loop: noise floor, admission, edit budget.

**Noise floor.** A candidate is admitted only if it beats the incumbent by more than `delta`:

    sampling = (high - low) / 2       the half-width of the 95 % Wilson interval of the
                                      incumbent's accuracy at the split size n
    drift    = flips / n              the share of the split whose correctness changes when
                                      every Truth answer moves by +/- m, m being a high
                                      quantile of measured re-ask deltas (`drift_magnitude`)
    delta    = min(1, max(sampling + drift, 1 / n))      and delta = 1 when n = 0

Summing the two terms is deliberately conservative. Sampling noise and provider drift are
different sources and either one alone can manufacture a gain of that size. The Wilson width
is the *unpaired* one even though a candidate and its incumbent are scored on the same cases;
a paired test (`eval.stats.mcnemar`) would admit more. The unpaired width is kept because an
outer loop compares many candidates against the same split, round after round, and that
reuse inflates false admissions in a way no single paired test accounts for. RRSI's finding is
that the loop which gains less on its evolution set transfers better; this is the cheap way to
gain less. The floor never drops below one case: with n = 100 a one-case gain is 0.01 and
the floor is at least that.

**Cost rule.** Extra cost is admitted only if `cost_delta <= beta0 + beta1 * gain`, with gain
in accuracy points (0..1) and cost in whatever unit the caller uses (USD per case, tokens).

**Edit budget.** `b(r) = b_min + (b_max - b_min) * (1 + cos(pi * r / (T - 1))) / 2`, rounded
half up: wide early, one edit at a time at the end, when a joint edit is hardest to attribute.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from ..eval.stats import wilson
from .knobs import Edit


@dataclass(frozen=True, slots=True)
class NoiseFloor:
    delta: float
    sampling: float
    drift: float
    n: int
    magnitude: float = 0.0  # the drift magnitude m the flips were counted at
    drift_flips: int = 0


def drift_magnitude(deltas: Sequence[float], *, quantile: float = 0.95) -> float:
    """Nearest-rank quantile of |delta| over measured re-asks of the same input. 0 if none.

    With a handful of re-asks (the repository has six, `docs/results/2026-09-25-window/` s.7)
    the 95 % nearest rank is the maximum, which is the honest reading of a small sample.
    """
    if not 0.0 < quantile <= 1.0:
        raise ValueError("quantile must be in (0, 1]")
    if not deltas:
        return 0.0
    ordered = sorted(abs(float(d)) for d in deltas)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return ordered[rank - 1]


def noise_floor(
    n: int, accuracy: float, *, drift_flips: int = 0, magnitude: float = 0.0, z: float = 1.96
) -> NoiseFloor:
    """The gain a candidate must exceed on a split of `n` cases. See the module docstring."""
    if not 0.0 <= accuracy <= 1.0:
        raise ValueError("accuracy must be in [0, 1]")
    if n < 0 or drift_flips < 0:
        raise ValueError("n and drift_flips are non-negative")
    if n == 0:
        return NoiseFloor(1.0, 1.0, 0.0, 0, magnitude, drift_flips)
    _, low, high = wilson(round(accuracy * n), n, z)
    sampling = (high - low) / 2
    drift = drift_flips / n
    delta = min(1.0, max(sampling + drift, 1.0 / n))
    return NoiseFloor(delta, sampling, drift, n, magnitude, drift_flips)


@dataclass(frozen=True, slots=True)
class Admission:
    admitted: bool
    gain: float
    delta: float
    cost_delta: float
    cost_allowance: float
    edits: int
    budget: int
    reasons: tuple[str, ...]  # every condition that failed; empty when admitted


def admit(
    candidate_score: float,
    incumbent_score: float,
    *,
    delta: float,
    cost_delta: float,
    beta0: float,
    beta1: float,
    edits: Sequence[Edit],
    budget: int,
) -> Admission:
    """Admit only if gain > delta AND the cost rule holds AND len(edits) <= budget."""
    gain = candidate_score - incumbent_score
    allowance = beta0 + beta1 * gain
    reasons: list[str] = []
    if not edits:
        reasons.append("no edits: nothing to admit")
    if not gain > delta:
        reasons.append(f"gain {gain:+.4f} does not exceed the noise floor {delta:.4f}")
    if cost_delta > allowance:
        reasons.append(
            f"cost delta {cost_delta:.6g} exceeds the allowance {allowance:.6g} "
            f"(beta0 {beta0:.6g} + beta1 {beta1:.6g} x gain {gain:+.4f})"
        )
    if len(edits) > budget:
        reasons.append(f"{len(edits)} edits exceed this round's edit budget of {budget}")
    return Admission(
        admitted=not reasons,
        gain=gain,
        delta=delta,
        cost_delta=cost_delta,
        cost_allowance=allowance,
        edits=len(edits),
        budget=budget,
        reasons=tuple(reasons),
    )


def edit_budget(round: int, total_rounds: int, b_max: int, b_min: int) -> int:
    """Maximum atomic edits per candidate in `round` (0-based), cosine-annealed."""
    if total_rounds < 1:
        raise ValueError("total_rounds must be at least 1")
    if not 0 <= round < total_rounds:
        raise ValueError(f"round must be in [0, {total_rounds})")
    if not 1 <= b_min <= b_max:
        raise ValueError("need 1 <= b_min <= b_max")
    if total_rounds == 1:
        return b_max
    progress = round / (total_rounds - 1)
    value = b_min + (b_max - b_min) * (1 + math.cos(math.pi * progress)) / 2
    return math.floor(value + 0.5)
