"""The memory cell's sealed reading (`docs/results/2026-10-13-memory-cell/prereg.md`): N against S
on one model and one scene family, pair by pair.

A pair is (scene, model, repetition) with both arms run (`analyze.ran`); a pair where either arm
is NOT RUN is listed and left out. A **break** is the gate's: the fact not kept with the task
not failed (`analyze.broke`). The primary is a one-sided exact McNemar on breaks, S better than
N. The rest are no-harm criteria fixed before the data:

- tests and task: S passes in no more than `floor(MARGIN * pairs)` fewer pairs than N (3 of 24);
- false send-backs: S's last sessions sent back by a rule that is not the scene's own (a decoy, or
  in family ii the older rule), at most `floor(FALSE_MAX * pairs)` (1 of 24);
- cost: the median over pairs of S's cost over N's (Claude Code's list price plus S's decisions)
  at most `COST_MAX` (1.15).

Verdict: "gana" when the primary and every no-harm criterion hold; "no gana" otherwise, with
each criterion that failed named; "sin veredicto" when fewer than `MIN_PAIRS` pairs ran. Reported
beside it, never deciding: the two-sided reading (S breaks more), the variants of family iii apart,
a bootstrap interval of the cost ratio by scene, and every break and send-back by name.

    python benchmarks/memory_carry/cell.py RUN_DIR [RUN_DIR ...] [--a S] [--b N] [--json]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from analyze import broke, folders, mcnemar, ran, rows  # noqa: E402
from carry import SCENES  # noqa: E402
from sendbacks import sendbacks  # noqa: E402

MARGIN = 0.125  # tests and task: 3 of 24 (v8's 2 of 16)
FALSE_MAX = 0.05  # v8's rate: 1 of 24
COST_MAX = 1.15
MIN_PAIRS = 20
ALPHA = 0.05
BOOT = 10_000
SEED = 20261013

Pair = tuple[str, str, int]


def total(row: dict[str, Any]) -> float:
    return float(row.get("cost") or 0.0) + float(row.get("jev_usd") or 0.0)


def paired(all_rows: list[dict[str, Any]], a: str, b: str) -> tuple[dict[Pair, dict], list]:
    pairs: dict[Pair, dict[str, dict[str, Any]]] = {}
    for r in all_rows:
        pairs.setdefault((r["scene"], r["model"], r["repeat"]), {})[r["arm"]] = r
    done = {k: p for k, p in pairs.items() if ran(p.get(a)) and ran(p.get(b))}
    not_run = sorted(f"{k[0]} r{k[2]}" for k in pairs if k not in done)
    return done, not_run


def false_sendbacks(row: dict[str, Any], run_dir: Path) -> list[str]:
    """Rules other than the scene's own that sent the row's last session back."""
    pair = run_dir / f"{row['scene']}-{row['model']}-{row['arm']}-{row['repeat']}"
    last = len(row.get("planned") or [None, None])
    return [str(f["rule"]) for f in sendbacks(pair) if not f["own"] and f["session"] == last]


def boot_ratio(done: dict[Pair, dict], a: str, b: str) -> tuple[float, float] | None:
    """95 % interval of the geometric mean of S/N cost, resampling scenes (pairs of one scene
    are not independent)."""
    by_scene: dict[str, list[float]] = {}
    for (scene, _, _), p in done.items():
        if total(p[a]) > 0 and total(p[b]) > 0:
            by_scene.setdefault(scene, []).append(math.log(total(p[a]) / total(p[b])))
    if not by_scene:
        return None
    scenes, rng, means = sorted(by_scene), random.Random(SEED), []
    for _ in range(BOOT):
        logs = [x for s in rng.choices(scenes, k=len(scenes)) for x in by_scene[s]]
        means.append(statistics.fmean(logs))
    means.sort()
    return math.exp(means[int(0.025 * BOOT)]), math.exp(means[int(0.975 * BOOT) - 1])


def counts(done: dict[Pair, dict], arm: str) -> dict[str, int]:
    found = [p[arm] for p in done.values()]
    return {"broken": sum(broke(r) for r in found),
            "not_kept": sum(not r["fact_kept"] for r in found),
            "tests": sum(bool(r["tests_pass"]) for r in found),
            "task": sum(bool(r["task_pass"]) for r in found)}  # fmt: skip


def variants(done: dict[Pair, dict], a: str, b: str) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for (scene, _, _), p in done.items():
        name = "worktree" if SCENES.get(scene, {}).get("worktree") else "same checkout"
        cell = out.setdefault(name, {"pairs": 0, f"{a}_broken": 0, f"{b}_broken": 0})
        cell["pairs"] += 1
        cell[f"{a}_broken"] += broke(p[a])
        cell[f"{b}_broken"] += broke(p[b])
    return out


def criteria(done: dict[Pair, dict], a: str, b: str, sent: dict[str, list[str]],
             a_only: int, b_only: int) -> dict[str, Any]:  # fmt: skip
    n = len(done)
    ca, cb = counts(done, a), counts(done, b)
    margin = math.floor(MARGIN * n)
    ratios = [total(p[a]) / total(p[b]) for p in done.values() if total(p[b]) > 0]
    median = statistics.median(ratios) if ratios else None
    return {
        "primary": {"p": mcnemar(a_only, b_only), "holds": mcnemar(a_only, b_only) < ALPHA},
        "tests": {"a": ca["tests"], "b": cb["tests"], "margin": margin,
                  "holds": ca["tests"] >= cb["tests"] - margin},
        "task": {"a": ca["task"], "b": cb["task"], "margin": margin,
                 "holds": ca["task"] >= cb["task"] - margin},
        "false_sendbacks": {"sessions": len(sent), "max": math.floor(FALSE_MAX * n),
                            "holds": len(sent) <= math.floor(FALSE_MAX * n)},
        "cost": {"median_ratio": median, "max": COST_MAX,
                 "holds": median is not None and median <= COST_MAX},
    }  # fmt: skip


def verdict(n: int, checks: dict[str, Any]) -> str:
    if n < MIN_PAIRS:
        return f"sin veredicto ({n} pares corridos, hacen falta {MIN_PAIRS})"
    failed = [name for name, c in checks.items() if not c["holds"]]
    return "gana" if not failed else "no gana (" + ", ".join(failed) + ")"


def cell(all_rows: list[dict[str, Any]], run_dirs: dict[str, Path], a: str = "S",
         b: str = "N") -> dict[str, Any]:  # fmt: skip
    done, not_run = paired(all_rows, a, b)
    a_only = sum(1 for p in done.values() if broke(p[b]) and not broke(p[a]))
    b_only = sum(1 for p in done.values() if broke(p[a]) and not broke(p[b]))
    sent = {f"{k[0]} r{k[2]}": found for k, p in sorted(done.items())
            if (found := false_sendbacks(p[a], run_dirs[p[a]["run"]]))}  # fmt: skip
    checks = criteria(done, a, b, sent, a_only, b_only)
    return {"pairs": len(done), "not_run": not_run, "a": a, "b": b,
            "count": {a: counts(done, a), b: counts(done, b)},
            "a_only_kept": a_only, "b_only_kept": b_only,
            "p_a_better": mcnemar(a_only, b_only), "p_a_worse": mcnemar(b_only, a_only),
            "criteria": checks, "verdict": verdict(len(done), checks),
            "cost": {a: round(sum(total(p[a]) for p in done.values()), 4),
                     b: round(sum(total(p[b]) for p in done.values()), 4),
                     "jev": round(sum(float(p[a].get("jev_usd") or 0) for p in done.values()), 6),
                     "ratio_ci95": boot_ratio(done, a, b)},
            "variants": variants(done, a, b), "false_sendbacks": sent,
            "broken": {arm: sorted(f"{k[0]} r{k[2]}" for k, p in done.items() if broke(p[arm]))
                       for arm in (a, b)}}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--a", default="S")
    parser.add_argument("--b", default="N")
    args = parser.parse_args(argv)
    dirs = folders(args.runs)
    found = rows(dirs)
    print(json.dumps(cell(found, {d.name: d for d in dirs}, args.a, args.b), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
