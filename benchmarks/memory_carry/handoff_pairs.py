"""W17's analysis (docs/results/2026-10-16-memory-w17/prereg.md): pairs of N0 and S' (arm `S` in
the rows) on F2's scenes, per model, with the sealed rules of each lot.

Pairs are (scene, model, repetition) with both arms run (`handoff_analyze.ran`). "Kept all" is
task and fact and decision. The cost ratio is, per pair, S's cost (Jev included) over N0's; its
statistic is the median over pairs and its interval the percentile bootstrap of that median,
pairs resampled (DRAWS, SEED), as F2's descriptive one (`handoff_cost_ci.bootstrap_median`).

- **Sonnet 5.5** (`w17-sonnet`): S1 S' better than N0 on kept all, one-sided exact McNemar
  p < ALPHA; S2 the cost ratio's upper bound <= COST_BOUND["sonnet"]; S3 no harm (S's tests in
  no more than floor(MARGIN x pairs) fewer pairs than N0's; S's sessions 2 sent back by another
  rule than the scene's own in at most SENDBACK_RATE of the pairs). "gana" when S1, S2 and S3
  hold; "S' better than N0; no gana (cost)" when S1 and S3 hold; "not shown" otherwise.
- **Opus 5.5** (`w17-opus`): O1 the cost ratio's upper bound <= COST_BOUND["opus"]; O2 kept all
  not worse, the one-sided 95 % Tango lower bound of S' - N0 above -MARGIN; O3 no harm as S3.
  "no extra cost" when O1, O2 and O3 hold; "costs extra" when the ratio's lower bound is above
  1; "not determined" otherwise.
- **Scoreboard** (both, `scoreboard`): "sin margen" when N0 failed kept all in fewer than
  HEADROOM of the pairs; "gana (coste)" when the ratio's upper bound is below 1, O2's bound
  holds and there is no harm; "gana (éxito)" when S1 holds, the ratio's upper bound is within
  the lot's COST_BOUND and there is no harm; "no gana" otherwise.
- "sin veredicto" (both) with fewer than MIN_PAIRS pairs run.

The strata (session 2's line "named" or "bare") are reported apart, each with its own McNemar
and cost interval; the bare stratum's McNemar is the prereg's sealed secondary reading.

    python benchmarks/memory_carry/handoff_pairs.py RUN_DIR
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from handoff_analyze import (  # noqa: E402
    ALPHA,
    MARGIN,
    SENDBACK_RATE,
    TOKEN_KINDS,
    compare,
    cut_kind,
    median,
    own_sendbacks,
    ran,
    touched,
    triples,
)
from handoff_cost_ci import bootstrap_median  # noqa: E402

ARMS = ("N0", "S")
SEED = 20261017
DRAWS = 10_000
COST_BOUND = {"sonnet": 1.10, "opus": 1.05}
MIN_PAIRS = {"sonnet": 40, "opus": 30}
HEADROOM = 0.05  # N0 failing in fewer than this share of the pairs: "sin margen"
LINES = ("named", "bare")


def s_cost(t: dict[str, dict[str, Any]]) -> float:
    return float(t["S"]["cost"]) + float(t["S"].get("jev_usd") or 0)


def ratio_interval(values: list[float]) -> dict[str, Any]:
    got = bootstrap_median(values, DRAWS, SEED)
    return {"pairs": got["triples"], "median": got["median"], "ci95": got["ci95"],
            "draws": DRAWS, "seed": SEED}  # fmt: skip


def cost_ratios(done: dict[Any, dict[str, dict[str, Any]]]) -> list[float]:
    return [s_cost(t) / float(t["N0"]["cost"]) for t in done.values() if t["N0"]["cost"]]


def first_session_ratios(done: dict[Any, dict[str, dict[str, Any]]]) -> list[float]:
    """S's session 1 over N0's: the same prompt and the same work, so the install's own cost."""
    out = []
    for t in done.values():
        s, n = (float((t[a].get("sessions") or [{}])[0].get("cost") or 0) for a in ("S", "N0"))
        if n:
            out.append(s / n)
    return out


def harm(done: dict[Any, dict[str, dict[str, Any]]], run: Path | None) -> dict[str, Any]:
    n = len(done)
    tests = {a: sum(bool(t[a].get("tests_pass")) for t in done.values()) for a in ARMS}
    false_sb = sum(own_sendbacks(t["S"], run) for t in done.values())
    return {"tests": tests["S"] >= tests["N0"] - math.floor(MARGIN * n),
            "false_sendbacks": false_sb, "sendbacks": false_sb <= SENDBACK_RATE * n}  # fmt: skip


def stratum(done: dict[Any, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    if not done:
        return {"pairs": 0}
    cmp = compare(done, "S", "N0")
    ratios = cost_ratios(done)
    return {"pairs": len(done), "S_vs_N0": cmp, "better": cmp["p_a_better"] < ALPHA,
            "kept_all": {a: sum(t[a]["kept_all"] for t in done.values()) for a in ARMS},
            "cost_ratio": ratio_interval(ratios) if ratios else None}  # fmt: skip


def scoreboard(n: int, n0_fails: int, ci: list[float], tango_ok: bool, better: bool,
               no_harm: bool, bound: float) -> str:  # fmt: skip
    if n0_fails < HEADROOM * n:
        return "sin margen"
    if ci[1] < 1.0 and tango_ok and no_harm:
        return "gana (coste)"
    if better and ci[1] <= bound and no_harm:
        return "gana (éxito)"
    return "no gana"


def verdict_of(model: str, enough: bool, c: dict[str, Any], ci: list[float]) -> str:
    if not enough:
        return "sin veredicto"
    if model == "sonnet":
        if c["s1_better"] and c["s3_tests"] and c["s3_sendbacks"]:
            return "gana" if c["s2_cost"] else "S' better than N0; no gana (cost)"
        return "not shown"
    if c["o1_cost"] and c["o2_not_worse"] and c["o3_tests"] and c["o3_sendbacks"]:
        return "no extra cost"
    return "costs extra" if ci[0] > 1.0 else "not determined"


def analyse(rows: list[dict[str, Any]], model: str, run: Path | None = None,
            planned: list[tuple[str, str, int]] | None = None) -> dict[str, Any]:  # fmt: skip
    mine = [r for r in rows if r["model"] == model]
    all_t = triples(mine)
    done = {k: t for k, t in all_t.items() if all(ran(t.get(a)) for a in ARMS)}
    keys = set(planned or []) | set(all_t)
    n = len(done)
    cmp = compare(done, "S", "N0")
    ratios = cost_ratios(done)
    cost = ratio_interval(ratios) if ratios else {"median": None, "ci95": [math.inf, math.inf]}
    ci = cost["ci95"]
    no_harm = harm(done, run)
    tango_ok = cmp["tango_lower_95_raw"] > -MARGIN
    bound = COST_BOUND[model]
    if model == "sonnet":
        criteria = {"s1_better": cmp["p_a_better"] < ALPHA, "s2_cost": ci[1] <= bound,
                    "s3_tests": no_harm["tests"], "s3_sendbacks": no_harm["sendbacks"]}  # fmt: skip
    else:
        criteria = {"o1_cost": ci[1] <= bound, "o2_not_worse": tango_ok,
                    "o3_tests": no_harm["tests"], "o3_sendbacks": no_harm["sendbacks"]}  # fmt: skip
    n0_fails = sum(1 for t in done.values() if not t["N0"]["kept_all"])
    board = scoreboard(n, n0_fails, ci, tango_ok, cmp["p_a_better"] < ALPHA,
                       no_harm["tests"] and no_harm["sendbacks"], bound)  # fmt: skip
    enough = n >= MIN_PAIRS[model]
    by_line = {line: {k: t for k, t in done.items() if t["S"].get("line", "named") == line}
               for line in LINES}  # fmt: skip
    first = first_session_ratios(done)
    return {
        "model": model, "pairs": n, "verdict": verdict_of(model, enough, criteria, ci),
        "scoreboard": board if enough else "sin veredicto", "criteria": criteria,
        "cost_bound": bound, "cost_ratio": cost, "S_vs_N0": cmp,
        "false_sendbacks": no_harm["false_sendbacks"], "n0_fails": n0_fails,
        "count": {a: {c: sum(bool(t[a].get(f"{c}_pass")) for t in done.values())
                      for c in ("task", "fact", "decision", "intact", "tests")}
                  | {"kept_all": sum(t[a]["kept_all"] for t in done.values())} for a in ARMS},
        "strata": {line: stratum(sub) for line, sub in by_line.items()},
        "session_1_ratio": ratio_interval(first) if first else None,
        "not_run": sorted(f"{k[0]} r{k[2]}" for k in keys if k not in done),
        "not_run_reasons": dict(Counter(cut_kind(r) for r in mine if r.get("cut"))),
        **reported(done), "touched": touched(mine),
    }  # fmt: skip


def reported(done: dict[Any, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    ts = list(done.values())
    cost = {a: median([float(t[a]["cost"]) + float(t[a].get("jev_usd") or 0) for t in ts])
            for a in ARMS}  # fmt: skip
    tokens = {a: {k: median([float((t[a].get("tokens") or {}).get(k, 0)) for t in ts])
                  for k in TOKEN_KINDS} for a in ARMS}  # fmt: skip
    seconds = {a: median([float(s.get("seconds") or 0) for t in ts
                          for s in (t[a].get("sessions") or [])[1:2]]) for a in ARMS}  # fmt: skip
    return {"cost_median_usd": cost, "tokens_median": tokens, "session_2_seconds_median": seconds,
            "given_in_S": sum(1 for t in ts if t["S"].get("given")),
            "hook_starts_below_2": sum(1 for t in ts if int(t["S"].get("hook_starts") or 0) < 2),
            "native_after_1": {a: sum(1 for t in ts if t[a].get("native_after_1")) for a in ARMS},
            "jev": {k: sum(int(t["S"].get(k) or 0) for t in ts)
                    for k in ("jev_decisions", "jev_failed")},
            "jev_usd": round(sum(float(t["S"].get("jev_usd") or 0) for t in ts), 6),
            "subagents": {a: sum(int(t[a].get("subagents") or 0) for t in ts) for a in ARMS},
            "crossed_midnight": sum(1 for t in ts for a in ARMS
                                    if t[a].get("crossed_midnight"))}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    args = parser.parse_args(argv)
    import handoff

    run = Path(args.run)
    name = run.name if run.name in handoff.RUNS else "w17-sonnet"
    plan = handoff.build_plan(name)
    planned = sorted({(s, m, r) for s, m, _, r in plan})
    result = analyse(handoff.rows_of(run), handoff.RUNS[name]["model"], run, planned)
    print(json.dumps(result, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
