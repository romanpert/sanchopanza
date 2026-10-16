"""Lot A10: what the registered comparisons can tell apart at n = 950. Free arithmetic.

    python benchmarks/a10_local/power.py     # -> docs/results/2026-10-16-a10-local/power.json

THE PRIMARY, the paired AUC difference (`simulate_auc`), is simulated on checkdone114's own 950
stops: their published labels (795 done) and 106 user-task clusters, no Jev answer. See its
docstring for the score model.

THE SECONDARY, accuracy at the cuts (`simulate`). The test set's clusters are checkdone114's
(`checkdone114_analysis.SIZES`: 40 workspace tasks x 15 runs, 16 banking x 10, 20 travel x 8,
30 injection tasks once: 106 clusters of plain mean size 8.96; the size-weighted mean
sum(m^2)/sum(m), which sets the design effect, is 12.5). For a
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
from statistics import NormalDist
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import a10_analysis as analysis  # noqa: E402
import checkdone114_analysis as cd  # noqa: E402

OUT = HERE.parents[1] / "docs" / "results" / "2026-10-16-a10-local" / "power.json"
CD_ROWS = HERE.parents[1] / "docs" / "results" / "2026-10-16-checkdone114" / "done-scored.jsonl"
# The primary: Jev 1.14's AUC on the 950 as checkdone114 published it; the local arm at
# JEV_AUC + delta. +0.13 is the local arm keeping its out-of-fold 0.944 on the test suites.
JEV_AUC = 0.814
AUC_DELTAS = (0.13, 0.0, -0.025, -0.05, -0.10)
RHOS = (0.3, 0.6)
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


def test_design() -> tuple[list[bool], list[int]]:
    """Label (done) and cluster index of each of checkdone114's 950 stops: its published labels
    and user-task clusters, nothing of Jev's answers."""
    rows = [json.loads(x) for x in CD_ROWS.read_text(encoding="utf-8").splitlines() if x.strip()]
    names = sorted({r["cluster"] for r in rows})
    index = {name: i for i, name in enumerate(names)}
    return [r["label"] == "done" for r in rows], [index[r["cluster"]] for r in rows]


def weighted_auc(order: list[int], done: list[bool], weight: list[int]) -> float:
    """Mann-Whitney AUC with integer weights, `order` sorted by score (no ties: continuous)."""
    below = pos = 0.0
    total = 0.0
    for i in order:
        w = weight[i]
        if not w:
            continue
        if done[i]:
            total += w * below
            pos += w
        else:
            below += w
    neg = below
    return total / (pos * neg) if pos and neg else math.nan


def simulate_auc(delta: float, rho: float, icc: float, *, sims: int = 200, replicas: int = 500,
                 seed: int = SEED) -> dict[str, Any]:  # fmt: skip
    """The primary at n = 950. Each arm's score is mu * done + cluster effect + noise, the noise
    of unit variance (a share `icc` of it per cluster), the two arms' cluster effects and noises
    correlated `rho`; mu = sqrt(2) * Phi^-1(AUC) gives the arm its AUC. Jev 1.14 at JEV_AUC,
    the local arm at JEV_AUC + delta. A cluster bootstrap of `replicas` (the analysis: 10,000)
    and the registered verdict (`a10_analysis.verdict` at AUC_MARGIN)."""
    rng = random.Random(seed)
    done, cluster = test_design()
    k, n = max(cluster) + 1, len(done)
    mu = {arm: math.sqrt(2) * NormalDist().inv_cdf(auc)
          for arm, auc in (("jev", JEV_AUC), ("local", JEV_AUC + delta))}  # fmt: skip
    tally = {"mejor": 0, "no peor": 0, "peor": 0, "no concluyente": 0}
    widths, seen = [], []

    def pair() -> tuple[float, float]:
        z1, z2 = rng.gauss(0, 1), rng.gauss(0, 1)
        return z1, rho * z1 + math.sqrt(1 - rho * rho) * z2

    for _ in range(sims):
        effects = [pair() for _ in range(k)]
        orders = {}
        for a, arm in enumerate(("local", "jev")):
            score = []
            for i in range(n):
                noise = pair()[a]
                shared = effects[cluster[i]][a]
                score.append(mu[arm] * done[i] + math.sqrt(icc) * shared
                             + math.sqrt(1 - icc) * noise)  # fmt: skip
            orders[arm] = sorted(range(n), key=score.__getitem__)
        ones = [1] * n
        diff = weighted_auc(orders["local"], done, ones) - weighted_auc(orders["jev"], done, ones)
        seen.append(diff)
        diffs = []
        for _ in range(replicas):
            picks = [0] * k
            for _ in range(k):
                picks[rng.randrange(k)] += 1
            weight = [picks[c] for c in cluster]
            d = weighted_auc(orders["local"], done, weight) - weighted_auc(
                orders["jev"], done, weight
            )
            if not math.isnan(d):
                diffs.append(d)
        diffs.sort()
        low = diffs[int(0.025 * (len(diffs) - 1))]
        high = diffs[int(0.975 * (len(diffs) - 1))]
        widths.append((high - low) / 2)
        found = {"diff": diff, "ci95_cluster": (low, high)}
        tally[analysis.verdict(found, analysis.AUC_MARGIN)] += 1
    return {
        "delta_auc": delta, "local_auc": round(JEV_AUC + delta, 3), "jev_auc": JEV_AUC,
        "rho": rho, "icc": icc, "sims": sims,
        "mean_observed_diff": round(sum(seen) / sims, 4),
        "p_no_peor_or_mejor": round((tally["no peor"] + tally["mejor"]) / sims, 3),
        "p_mejor": round(tally["mejor"] / sims, 3),
        "p_peor": round(tally["peor"] / sims, 3),
        "p_no_concluyente": round(tally["no concluyente"] / sims, 3),
        "mean_half_width_auc": round(sum(widths) / sims, 4),
    }  # fmt: skip


def main() -> int:
    auc_table = [simulate_auc(d, r, i) for d in AUC_DELTAS for r in RHOS for i in ICCS]
    for row in auc_table:
        print(json.dumps(row), flush=True)
    table = [simulate(d, r, i) for d in DELTAS for r in RATES for i in ICCS]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = {"size_weighted_mean_cluster_size": WEIGHTED_SIZE,
            "plain_mean_cluster_size": PLAIN_SIZE,
            "primary_auc": auc_table, "secondary_accuracy": table}  # fmt: skip
    OUT.write_text(json.dumps(body, indent=1) + "\n", encoding="utf-8", newline="\n")
    for row in table:
        print(json.dumps(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
