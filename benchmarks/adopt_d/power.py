"""Point 7: power for a next adoption phase, from phase A's own runs (read-only, no spend).

Variance comes from what is observed: per chain, the runs of N, Sm (first reading) and Sm
(second reading); per single, N, S (first) and S (second). Treating the three as draws of one
distribution is the null (the S arms barely differed: no block, no find call, no prompt
injection), which is the scenario a non-inferiority design must survive.
"""
import json
import math
import os
import random
import statistics as st
from pathlib import Path

R = Path(os.path.expanduser("~/.cache/sanchopanza/adopt"))
CHAINS = ["pygments__pygments-2", "encode__starlette-2", "pydantic__pydantic-1",
          "pydantic__pydantic-2", "conan-io__conan-1", "conan-io__conan-2",
          "pylint-dev__astroid-1", "encode__starlette-rel-2", "pydantic__pydantic-rel-1",
          "iterative__dvc-rel-1"]


def chain_run(d):
    g = json.loads((d / "grade.json").read_text(encoding="utf-8"))
    row = json.loads((d / "row.json").read_text(encoding="utf-8"))
    bugs = [b["resolved"] for b in g["bugs"]]
    cost = sum(c.get("cost_usd") or 0 for c in row["calls"]) + (row.get("jev_usd") or 0)
    return {"bugs": bugs, "cost": cost}


def single_run(d):
    g = json.loads((d / "grade.json").read_text(encoding="utf-8"))
    row = json.loads((d / "row.json").read_text(encoding="utf-8"))
    cost = sum(c.get("cost_usd") or 0 for c in row["calls"]) + (row.get("jev_usd") or 0)
    return {"ok": bool(g.get("resolved")), "cost": cost}


def load():
    chains = {}
    for c in CHAINS:
        runs = {"N": chain_run(R / "runs" / c / "N"), "S2": chain_run(R / "runs" / c / "Sm"),
                "S1": chain_run(R / "runs" / f"{c}-nojev1" / "Sm")}
        chains[c] = runs
    singles = {}
    for d in sorted((R / "singles").iterdir()):
        if d.name.endswith("-nojev1") or not (d / "S" / "grade.json").exists():
            continue
        one = R / "singles" / f"{d.name}-nojev1" / "S"
        if not (d / "N" / "grade.json").exists() or not (one / "grade.json").exists():
            continue
        singles[d.name] = {"N": single_run(d / "N"), "S2": single_run(d / "S"),
                           "S1": single_run(one)}
    return chains, singles


def describe(chains, singles):
    print("chain                      N   Sm1 Sm2  costN  costS1 costS2")
    for c, r in chains.items():
        print(f"{c:26s} {sum(r['N']['bugs'])}   {sum(r['S1']['bugs'])}   {sum(r['S2']['bugs'])}"
              f"   {r['N']['cost']:.2f}   {r['S1']['cost']:.2f}   {r['S2']['cost']:.2f}")
    retest = [sum(r["S2"]["bugs"]) - sum(r["S1"]["bugs"]) for r in chains.values()]
    print("Sm retest diffs", retest, "sd", round(st.stdev(retest), 2),
          "-> per-run sd", round(st.stdev(retest) / math.sqrt(2), 2))
    lr = [math.log(r["S2"]["cost"] / r["S1"]["cost"]) for r in chains.values()]
    print("chain cost ln retest sd", round(st.stdev(lr), 3))
    flips = sum(r["S1"]["ok"] != r["S2"]["ok"] for r in singles.values())
    print(f"singles: {len(singles)} with 3 runs; S1 vs S2 disagree in {flips}")
    lrs = [math.log(r["S2"]["cost"] / r["S1"]["cost"]) for r in singles.values()]
    print("singles cost ln retest sd", round(st.stdev(lrs), 3))


def sim_chain_run(pool, rng, harm):
    """One run of a chain: a whole observed run, bugs flipped to failure with prob `harm`."""
    run = rng.choice(pool)
    return sum(1 for b in run["bugs"] if b and rng.random() >= harm), run["cost"]


def chains_power(chains, n_chains, reps, harm, margin_share=0.05, sims=4000, seed=1):
    """P(H1 'holds') under the sealed point rule and under a one-sided 95 % interval rule."""
    rng = random.Random(seed)
    pools = [[r["N"], r["S1"], r["S2"]] for r in chains.values()]
    point = interval = 0
    for _ in range(sims):
        picked = [rng.choice(pools) for _ in range(n_chains)]
        diffs = []
        for pool in picked:
            n = sum(sim_chain_run(pool, rng, 0.0)[0] for _ in range(reps)) / reps
            s = sum(sim_chain_run(pool, rng, harm)[0] for _ in range(reps)) / reps
            diffs.append(s - n)
        margin = max(1, round(margin_share * 5 * n_chains))
        total = sum(diffs)
        point += total >= -margin
        se = st.stdev(diffs) * math.sqrt(n_chains) if n_chains > 1 else 0
        interval += total - 1.645 * se >= -margin
    return point / sims, interval / sims


def singles_power(singles, n, reps, harm, margin=2, sims=4000, seed=2):
    rng = random.Random(seed)
    p = [sum(r[k]["ok"] for k in ("N", "S1", "S2")) / 3 for r in singles.values()]
    point = interval = 0
    for _ in range(sims):
        diffs = []
        for _ in range(n):
            q = rng.choice(p)
            a = sum(rng.random() < q for _ in range(reps)) / reps
            b = sum(rng.random() < q * (1 - harm) for _ in range(reps)) / reps
            diffs.append(b - a)
        scaled = margin * n / 26
        total = sum(diffs)
        point += total >= -scaled
        se = st.stdev(diffs) * math.sqrt(n)
        interval += total - 1.645 * se >= -scaled
    return point / sims, interval / sims


def cost_ci_halfwidth(sd_ln, n, reps):
    """Half-width of a 95 % interval on the mean ln ratio; reps shrink the sd as if it were all
    run noise, so with reps > 1 this is the optimistic bound."""
    return 1.96 * sd_ln / math.sqrt(reps) / math.sqrt(n)


if __name__ == "__main__":
    chains, singles = load()
    describe(chains, singles)
    print("\nchains: P(H1 holds)  [point rule, interval rule]  margin 5 % of bugs")
    for n, reps in ((10, 1), (10, 2), (10, 3), (20, 2), (40, 2)):
        ok = chains_power(chains, n, reps, 0.0)
        bad = chains_power(chains, n, reps, 0.10)
        print(f"  {n:2d} chains x {reps} reps: true equal {ok[0]:.2f} {ok[1]:.2f} | "
              f"S 10 % worse {bad[0]:.2f} {bad[1]:.2f}")
    print("\nsingles: P(H1 holds)  margin 2 of 26 scaled")
    for n, reps in ((26, 1), (26, 3), (52, 2), (100, 1)):
        ok = singles_power(singles, n, reps, 0.0)
        bad = singles_power(singles, n, reps, 0.15)
        print(f"  {n:3d} x {reps}: true equal {ok[0]:.2f} {ok[1]:.2f} | "
              f"S 15 % worse {bad[0]:.2f} {bad[1]:.2f}")
    sd_c = st.stdev([math.log(r["S2"]["cost"] / r["N"]["cost"]) for r in chains.values()])
    sd_s = st.stdev([math.log(r["S2"]["cost"] / r["N"]["cost"]) for r in singles.values()])
    print(f"\ncost: paired ln(S/N) sd chains {sd_c:.3f}, singles {sd_s:.3f}")
    for n, reps in ((10, 1), (10, 3), (20, 2), (26, 1), (26, 3), (52, 2)):
        print(f"  n={n} reps={reps}: ~95 % half-width chains x{math.exp(cost_ci_halfwidth(sd_c, n, reps)):.3f}"
              f" singles x{math.exp(cost_ci_halfwidth(sd_s, n, reps)):.3f}")
