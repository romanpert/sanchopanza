"""H1's bootstrap rule, simulated exactly on phase A's resolve profile. Free, read-only, seeded.

    python benchmarks/adopt_d/sim_h1.py [--sims 2000]

Why: `power.py` judged H1 with a normal approximation. The verdict (`confirm_d.h1`) is a
percentile bootstrap over 26 instances whose differences take a few discrete values; at n = 26
such an interval undercovers, so the one-sided 5 % rule (draws[500] of 10,000) lets a design that
sits exactly at the margin pass more often than 5 %. This simulates the rule as `confirm_d` applies
it and prints, for draws[100] (1 %) and draws[500] (5 %):

- **type I at the margin**: S's chance of resolving is the instance's times (1 - h), h chosen so
  that the expected D over the profile is -2/26 (the margin); P(H1 holds) should be <= 5 %;
- **power at equality**: both arms with the instance's chance; P(H1 holds).

The profile is `power.py`'s: per phase A single, the share resolved over its three runs (N and the
two readings of S), instances drawn with replacement. Each simulated study: 26 instances x 3
repetitions per arm, D = mean over instances of res_S - res_N, then 10,000 bootstrap resamples of
the instances, as `confirm_d.resample` (`random.choices` here: the same distribution, faster). D
is a multiple of 1/78, so the rule is compared on integer sums: draw >= -6/78 = -2/26 exactly.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import power  # noqa: E402  (phase A's runs, read only)

SEED = 20261005
INSTANCES, REPS, RESAMPLES = 26, 3, 10_000
MARGIN_SUM = -2 * REPS  # -2/26 of a share, as a sum of (s - n) over 26 instances x 3 repetitions
INDICES = {"draws[100] (1 %)": 100, "draws[500] (5 %)": 500}


def profile() -> list[float]:
    _, singles = power.load()
    return [sum(r[k]["ok"] for k in ("N", "S1", "S2")) / 3 for r in singles.values()]


def study(rng: random.Random, chances: list[float], harm: float) -> list[int]:
    """Per instance, S's resolved repetitions minus N's (an integer in -3..3)."""
    out = []
    for _ in range(INSTANCES):
        p = rng.choice(chances)
        n = sum(rng.random() < p for _ in range(REPS))
        s = sum(rng.random() < p * (1 - harm) for _ in range(REPS))
        out.append(s - n)
    return out


def holds(rng: random.Random, diffs: list[int]) -> dict[str, bool]:
    draws = sorted(sum(rng.choices(diffs, k=len(diffs))) for _ in range(RESAMPLES))
    return {label: draws[i] >= MARGIN_SUM for label, i in INDICES.items()}


def rate(chances: list[float], harm: float, sims: int, seed: int) -> dict[str, float]:
    rng = random.Random(seed)
    counts = dict.fromkeys(INDICES, 0)
    for _ in range(sims):
        for label, ok in holds(rng, study(rng, chances, harm)).items():
            counts[label] += ok
    return {label: n / sims for label, n in counts.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sims", type=int, default=2000)
    args = parser.parse_args(argv)
    chances = profile()
    mean = sum(chances) / len(chances)
    harm = (2 / INSTANCES) / mean  # expected D over the profile = -2/26
    print(f"profile: {len(chances)} phase A singles, mean resolve {mean:.4f}; margin harm "
          f"h = {harm:.4f}; {args.sims} studies per scenario, seed {SEED}")  # fmt: skip
    margin = rate(chances, harm, args.sims, SEED)
    equal = rate(chances, 0.0, args.sims, SEED + 1)
    for label in INDICES:
        se = (margin[label] * (1 - margin[label]) / args.sims) ** 0.5
        print(f"{label}: type I at the margin {margin[label]:.4f} (MC se {se:.4f}); "
              f"power at equality {equal[label]:.4f}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
