"""Power of the guard-pointers lot (docs/results/2026-10-16-guard-pointers/prereg.md), simulated
with the rule it registers. Free: no model, no API, no Jev; seeded, so the table is reproducible.

    python benchmarks/adopt/guardptr_power.py [--sims 1000] [--reps 1000] [--json out.json]

Quality. Per pair of runs (one P, one F on the same chain: a cluster) each of its `bugs` bugs is
discordant (one arm resolves it, the other not) with probability `d`; a discordant bug goes to P
with probability 1/2 + delta_c / (2 d), so P - F has mean `delta_c`, which is the true effect
`delta` plus a per-cluster spread `tau`. Concordant bugs add nothing to the difference but count
in its denominator. The verdict is the registered one: the one-sided 95 % lower bound of the
pooled difference with whole clusters resampled (`long_report.one_sided_low`, here with `reps`
resamples) above `-margin`. Discordance seen so far, per bug: 0.023-0.163 between Ne and Nl in
the close-out (mean 0.068 over its 6 chain pairs, read.json and amend.json), 5-7 bugs of 60
between two runs of one arm (0.08-0.12); 19 of 51 for Ne against Ne2 on conan-1 (2026-10-07).

Cost. Per cluster ln(P/F) ~ N(ln ratio, sd); the registered interval is `long_report.cost_ratio`
(paired mean, 95 % t); "shown" when its upper end lies under 1. sd 0.171 is the spread of the log
cost between runs of one arm (e8); the close-out's five Nl/Ne log ratios had sd 0.157.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from long_report import T95  # noqa: E402

SEED = 20261016
T95_ONE_SIDED = {4: 2.132, 9: 1.833}  # Student's t, 95 % one-sided, by degrees of freedom


def _cluster(rng: random.Random, bugs: int, d: float, delta: float) -> tuple[int, int]:
    """(sum of P - F over the cluster's bugs, its bugs)."""
    favour = min(1.0, max(0.0, 0.5 + delta / (2 * d)))
    total = 0
    for _ in range(bugs):
        if rng.random() < d:
            total += 1 if rng.random() < favour else -1
    return total, bugs


def bootstrap_low(clusters: list[tuple[int, int]], rng: random.Random, reps: int) -> float:
    """The 5th percentile of the pooled difference over resamples of whole clusters."""
    n = len(clusters)
    draws = []
    for _ in range(reps):
        picked = [clusters[rng.randrange(n)] for _ in range(n)]
        draws.append(sum(s for s, _ in picked) / sum(b for _, b in picked))
    draws.sort()
    return draws[int(0.05 * reps)]


def t_low(clusters: list[tuple[int, int]]) -> float:
    """The one-sided 95 % t bound of the mean per-cluster difference (a sensitivity reading)."""
    rates = [s / b for s, b in clusters]
    df = len(rates) - 1
    return statistics.mean(rates) - T95_ONE_SIDED.get(df, 1.645) * statistics.stdev(rates) / \
        math.sqrt(len(rates))  # fmt: skip


def quality_power(chains: int, bugs: int, d: float, delta: float, tau: float, margin: float,
                  sims: int, reps: int, seed: int = SEED) -> dict[str, float]:  # fmt: skip
    rng = random.Random(f"{seed}-{chains}-{bugs}-{d}-{delta}-{tau}-{margin}")
    boot = tee = both = 0
    for _ in range(sims):
        clusters = [_cluster(rng, bugs, d, delta + rng.gauss(0.0, tau)) for _ in range(chains)]
        b, t = bootstrap_low(clusters, rng, reps) > -margin, t_low(clusters) > -margin
        boot, tee, both = boot + b, tee + t, both + (b and t)
    return {
        "bootstrap": round(boot / sims, 3),
        "t": round(tee / sims, 3),
        "both": round(both / sims, 3),
    }


def cost_power(chains: int, ratio: float, sd: float, sims: int, seed: int = SEED) -> float:
    rng = random.Random(f"{seed}-cost-{chains}-{ratio}-{sd}")
    shown = 0
    t = T95.get(chains, 1.96)
    for _ in range(sims):
        logs = [rng.gauss(math.log(ratio), sd) for _ in range(chains)]
        shown += statistics.mean(logs) + t * statistics.stdev(logs) / math.sqrt(chains) < 0
    return round(shown / sims, 3)


def chains_for(ratio: float, sd: float, power: float = 0.80) -> int:
    """Chains a paired t interval needs to put `ratio` under 1 with `power` (normal approximation,
    two-sided 95 %)."""
    return math.ceil(((1.96 + 0.8416) * sd / abs(math.log(ratio))) ** 2)


DESIGNS = ((5, 60), (5, 30), (10, 30))
DISCORDANCE = (0.07, 0.12, 0.20)
MARGINS = (0.05, 0.07)
# (true effect, its spread between pairs): none; a 2-point loss; a 2- and a 5-point spread (a run
# that goes wrong as a whole); a loss the size of the margin (the rule's false "non-inferior").
EFFECTS = ((0.0, 0.0), (-0.02, 0.0), (0.0, 0.02), (0.0, 0.05), (None, 0.0))


def table(sims: int, reps: int) -> dict[str, list[dict[str, float]]]:
    quality = []
    for chains, bugs in DESIGNS:
        for d in DISCORDANCE:
            for margin in MARGINS:
                for effect, tau in EFFECTS:
                    delta = -margin if effect is None else effect
                    if effect is None and d < margin:
                        continue  # P cannot lose more than the discordant bugs: not at the margin
                    found = quality_power(chains, bugs, d, delta, tau, margin, sims, reps)
                    quality.append({"chains": chains, "bugs": bugs, "d": d, "margin": margin,
                                    "delta": delta, "tau": tau, **found})  # fmt: skip
    cost = [{"chains": n, "ratio": r, "sd": sd, "power": cost_power(n, r, sd, sims)}
            for n in (5, 10) for r in (0.94, 0.90) for sd in (0.10, 0.171)]  # fmt: skip
    needed = [{"ratio": r, "sd": sd, "chains_80": chains_for(r, sd)}
              for r in (0.94, 0.90) for sd in (0.10, 0.171)]  # fmt: skip
    return {"quality": quality, "cost": cost, "cost_chains_needed": needed}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sims", type=int, default=1000)
    parser.add_argument("--reps", type=int, default=1000)
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)
    found = table(args.sims, args.reps)
    for row in found["quality"]:
        print(json.dumps(row))
    for row in found["cost"] + found["cost_chains_needed"]:
        print(json.dumps(row))
    if args.json:
        Path(args.json).write_text(json.dumps(found, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
