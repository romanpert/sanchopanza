"""Lot A10: what the registered comparison can tell apart at n = 950. Free arithmetic.

    python benchmarks/a10_local/power.py     # -> docs/results/2026-10-16-a10-local/power.json

The test set's clusters are checkdone114's (`checkdone114_analysis.SIZES`: 40 workspace tasks x
15 runs, 16 banking x 10, 20 travel x 8, 30 injection tasks once: 106 clusters of plain mean
size 8.96; the size-weighted mean sum(m^2)/sum(m), which sets the design effect, is 12.5). For a
true accuracy difference `delta` (local minus Jev 1.14) and a rate `rate` of stops where exactly
one arm is right, each cluster draws its own disagreement rate (mean `rate`) and the share of
disagreements the local arm wins (mean (rate + delta) / (2 rate)), both beta with intra-cluster
correlation `icc`. The verdict is the registered one (`a10_analysis.verdict`) on a cluster
bootstrap of `replicas`; the analysis itself uses 10,000.

The analytic half-width beside it is 1.96 * sqrt(rate / n * (1 + (12.5 - 1) * icc)), the normal
approximation to a paired difference with that design effect.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import a10_analysis as analysis  # noqa: E402
import checkdone114_analysis as cd  # noqa: E402

OUT = HERE.parents[1] / "docs" / "results" / "2026-10-16-a10-local" / "power.json"
DELTAS = (0.0, -0.025, -0.05, -0.10)
RATES = (0.15, 0.25, 0.35)  # 0.35: Jev 1.14 blocks 250 of the 950
ICCS = (0.0, 0.3)
SEED = 20261016
WEIGHTED_SIZE = sum(m * m for m in cd.SIZES) / sum(cd.SIZES)  # 12.5: the design effect's m
PLAIN_SIZE = sum(cd.SIZES) / len(cd.SIZES)  # 8.96


def simulate(delta: float, rate: float, icc: float, *, sims: int = 150, replicas: int = 400,
             seed: int = SEED) -> dict[str, Any]:  # fmt: skip
    rng = random.Random(seed)
    share = min(0.999, max(0.001, (rate + delta) / (2 * rate)))
    tally = {"mejor": 0, "no peor": 0, "peor": 0, "no concluyente": 0}
    widths = []
    for _ in range(sims):
        sums = []
        for m in cd.SIZES:
            p, q = cd._beta(rng, rate, icc), cd._beta(rng, share, icc)
            s = 0
            for _ in range(m):
                if rng.random() < p:
                    s += 1 if rng.random() < q else -1
            sums.append(s)
        diffs = []
        for _ in range(replicas):
            picked = [rng.randrange(len(cd.SIZES)) for _ in cd.SIZES]
            diffs.append(sum(sums[i] for i in picked) / sum(cd.SIZES[i] for i in picked))
        diffs.sort()
        low, high = diffs[int(0.025 * (replicas - 1))], diffs[int(0.975 * (replicas - 1))]
        widths.append((high - low) / 2)
        found = {"diff": sum(sums) / sum(cd.SIZES), "ci95_cluster": (low, high)}
        tally[analysis.verdict(found)] += 1
    n = sum(cd.SIZES)
    return {
        "delta": delta, "rate": rate, "icc": icc, "sims": sims,
        "p_no_peor_or_mejor": round((tally["no peor"] + tally["mejor"]) / sims, 3),
        "p_peor": round(tally["peor"] / sims, 3),
        "p_no_concluyente": round(tally["no concluyente"] / sims, 3),
        "mean_half_width_points": round(100 * sum(widths) / sims, 2),
        "analytic_half_width_points": round(
            100 * 1.96 * math.sqrt(rate / n * (1 + (WEIGHTED_SIZE - 1) * icc)), 2),
    }  # fmt: skip


def main() -> int:
    table = [simulate(d, r, i) for d in DELTAS for r in RATES for i in ICCS]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = {"size_weighted_mean_cluster_size": WEIGHTED_SIZE,
            "plain_mean_cluster_size": PLAIN_SIZE, "table": table}  # fmt: skip
    OUT.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8", newline="\n")
    for row in table:
        print(json.dumps(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
