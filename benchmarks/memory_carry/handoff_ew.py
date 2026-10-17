"""The equal-work lot's sealed reading (docs/results/2026-10-17-memory-equal-work/prereg.md):
pairs of N0 and S' (arm `S` in the rows) on F2's scenes, Sonnet 5.5, each arm nudged once when
its `task` check failed after session 2 (`handoff_nudge`, rule R3).

Pairs are (scene, model, repetition) with both arms run (`handoff_analyze.ran`) and the checks
after session 2 recorded (`kept_all_s2`).

- **Cost ratio (the estimand):** per pair, S's whole cost (sessions 1 and 2, its nudge if it had
  one, Jev) over N0's whole cost (sessions 1 and 2, its nudge if it had one). Its statistic is
  the median over pairs, its interval the percentile bootstrap 95 % of that median, pairs in
  (scene, repetition) order resampled with replacement, DRAWS draws, SEED (this lot's own).
- **Success:** kept all (task, fact, decision) after the nudge, S' against N0: one-sided exact
  McNemar and the one-sided 95 % Tango lower bound of S' - N0.
- **Verdict, in this order** (the final scoreboard's rule 2.4, as W17 made it exact,
  `handoff_pairs.scoreboard`): "sin veredicto" with fewer than MIN_PAIRS pairs; "sin margen" when
  N0 failed kept all **after session 2, before its nudge** in fewer than HEADROOM of the pairs;
  "gana (coste)" when the ratio's upper bound is below 1.00, Tango's bound above -MARGIN and no
  harm; "gana (éxito)" when McNemar p < ALPHA, the upper bound <= COST_BOUND and no harm; "no
  gana" otherwise. No harm is W17's (`handoff_pairs.harm`), on the checks after the nudge.
- **Sealed secondaries (they do not change the verdict):** W17's reading of the same rows as they
  stood after session 2 (`handoff_pairs.analyse` on `at_s2`: kept all after session 2, the cost
  of sessions 1 and 2 plus Jev, W17's seed); the named and bare strata; the nudge per arm.

    python benchmarks/memory_carry/handoff_ew.py RUN_DIR
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import handoff_pairs as hp  # noqa: E402
from handoff_analyze import ALPHA, MARGIN, compare, cut_kind, ran, touched, triples  # noqa: E402

ARMS = ("N0", "S")
MODEL = "sonnet"
SEED = 20261021  # fixed in the prereg before any data of this lot
COST_BOUND = hp.COST_BOUND[MODEL]  # 1.10
MIN_PAIRS = hp.MIN_PAIRS[MODEL]  # 40
BUDGET_STOP = "error_max_budget_usd"  # carry.BUDGET_STOP: a call stopped by its own cap
READING = "equal work (R3)"


def whole(row: dict[str, Any]) -> float:
    """The arm's cost: its calls' own costs (a nudge included) and its Jev decisions."""
    return float(row["cost"]) + float(row.get("jev_usd") or 0)


def at_s2(row: dict[str, Any]) -> dict[str, Any]:
    """The row as it stood after session 2: its checks then, sessions 1 and 2's cost."""
    if not isinstance(row.get("kept_all_s2"), bool):
        return row
    first_two = sum(float(s.get("cost") or 0) for s in (row.get("sessions") or [])[:2])
    return {**row, **(row.get("checks_s2") or {}), "kept_all": row["kept_all_s2"],
            "cost": round(first_two, 6)}  # fmt: skip


Pairs = dict[Any, dict[str, dict[str, Any]]]


def pairs_of(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Pairs, Pairs]:
    """(this model's rows, every pair seen, the pairs with both arms run and checked twice)."""
    mine = [r for r in rows if r["model"] == MODEL]
    all_t = triples(mine)
    done = {k: t for k, t in all_t.items() if all(both_checks(t.get(a)) for a in ARMS)}
    return mine, all_t, done


def both_checks(row: dict[str, Any] | None) -> bool:
    return ran(row) and isinstance((row or {}).get("kept_all_s2"), bool)


def interval(done: Pairs) -> dict[str, Any]:
    ratios = [whole(t["S"]) / whole(t["N0"]) for t in hp.by_pair(done) if whole(t["N0"])]
    if not ratios:
        return {"pairs": 0, "median": None, "ci95": [math.inf, math.inf],
                "ci95_raw": [math.inf, math.inf]}  # fmt: skip
    return hp.ratio_interval(ratios, SEED)


def nudges(done: dict[Any, dict[str, dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    """Per arm: how many arms were nudged, how many of those kept all after it, and the rate."""
    out = {}
    for a in ARMS:
        rows = [t[a] for t in done.values()]
        pushed = [r for r in rows if r.get("nudged")]
        out[a] = {"nudged": len(pushed), "kept_after": sum(bool(r["kept_all"]) for r in pushed),
                  "rate": round(len(pushed) / len(rows), 4) if rows else None}  # fmt: skip
    return out


def stratum(done: dict[Any, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    if not done:
        return {"pairs": 0}
    cmp = compare(done, "S", "N0")
    return {"pairs": len(done), "S_vs_N0": cmp, "better": cmp["p_a_better"] < ALPHA,
            "kept_all": {a: sum(t[a]["kept_all"] for t in done.values()) for a in ARMS},
            "kept_all_s2": {a: sum(t[a]["kept_all_s2"] for t in done.values()) for a in ARMS},
            "cost_ratio": interval(done), "nudges": nudges(done)}  # fmt: skip


def nudge_report(done: dict[Any, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    """Reported, not deciding: the nudges' own cost, how it was read, their resumed starts, and
    the calls (sessions and nudges) stopped by their own cap, per arm."""
    out: dict[str, Any] = {}
    for a in ARMS:
        rows = [t[a] for t in done.values()]
        pushed = [r["nudge"] for r in rows if r.get("nudged") and r.get("nudge")]
        costs = [float(p.get("cost") or 0) for p in pushed]
        calls = [s for r in rows for s in [*(r.get("sessions") or []), r.get("nudge") or {}]]
        starts = Counter(s for p in pushed for s in p.get("session_starts") or [])
        at_cap = sum(1 for s in calls if s.get("subtype") == BUDGET_STOP)
        out[a] = {"cost_median_usd": round(statistics.median(costs), 6) if costs else None,
                  "cost_sources": dict(Counter(str(p.get("cost_source")) for p in pushed)),
                  "session_starts": dict(starts), "calls_at_cap": at_cap}  # fmt: skip
    return out


def analyse(rows: list[dict[str, Any]], run: Path | None = None,
            planned: list[tuple[str, str, int]] | None = None) -> dict[str, Any]:  # fmt: skip
    mine, all_t, done = pairs_of(rows)
    keys = set(planned or []) | set(all_t)
    n = len(done)
    cmp = compare(done, "S", "N0")
    cost = interval(done)
    ci = cost["ci95_raw"]
    harm = hp.harm(done, run)
    no_harm = bool(harm["tests"] and harm["sendbacks"])
    tango_ok = cmp["tango_lower_95_raw"] > -MARGIN
    better = cmp["p_a_better"] < ALPHA
    fails_s2 = sum(1 for t in done.values() if not t["N0"]["kept_all_s2"])
    board = hp.scoreboard(n, fails_s2, ci, tango_ok, better, no_harm, COST_BOUND)
    by_line = {line: {k: t for k, t in done.items() if t["S"].get("line", "named") == line}
               for line in hp.LINES}  # fmt: skip
    return {
        "reading": READING, "model": MODEL, "pairs": n,
        "verdict": board if n >= MIN_PAIRS else "sin veredicto",
        "criteria": {"cost_below_1": ci[1] < 1.0, "tango_not_worse": tango_ok, "better": better,
                     "cost_within_bound": ci[1] <= COST_BOUND, "no_harm": no_harm,
                     "tests": harm["tests"], "sendbacks": harm["sendbacks"]},
        "headroom": {"n0_fails_s2": fails_s2, "pairs": n, "room": fails_s2 >= hp.HEADROOM * n},
        "cost_bound": COST_BOUND, "cost_ratio": cost, "S_vs_N0": cmp,
        "false_sendbacks": harm["false_sendbacks"],
        "count": {a: {c: sum(bool(t[a].get(f"{c}_pass")) for t in done.values())
                      for c in ("task", "fact", "decision", "intact", "tests")}
                  | {"kept_all": sum(t[a]["kept_all"] for t in done.values()),
                     "kept_all_s2": sum(t[a]["kept_all_s2"] for t in done.values())}
                  for a in ARMS},
        "nudges": nudges(done), "nudge_report": nudge_report(done),
        "strata": {line: stratum(sub) for line, sub in by_line.items()},
        "w17_reading": hp.analyse([at_s2(r) for r in mine], MODEL, run, planned),
        "not_run": sorted(f"{k[0]} r{k[2]}" for k in keys if k not in done),
        "not_run_reasons": dict(Counter(cut_kind(r) for r in mine if r.get("cut"))),
        **hp.reported(done), "touched": touched([with_nudge(r) for r in mine]),
    }  # fmt: skip


def with_nudge(row: dict[str, Any]) -> dict[str, Any]:
    """The row with its nudge among its calls, for what the agent's tool calls named."""
    push = row.get("nudge") or {}
    return {**row, "sessions": [*(row.get("sessions") or []), *([push] if push else [])]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run")
    args = parser.parse_args(argv)
    import handoff

    run = Path(args.run)
    if run.name not in handoff.RUNS or handoff.lot_of(run.name) != "ew":
        runs = ", ".join(handoff.LOTS["ew"]["sequence"])
        raise SystemExit(f"{run}: not this lot's run folder ({runs})")
    plan = handoff.build_plan(run.name)
    planned = sorted({(s, m, r) for s, m, _, r in plan})
    result = analyse(handoff.rows_of(run), run, planned)
    print(json.dumps(result, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
