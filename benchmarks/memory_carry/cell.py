"""The memory cell's sealed reading (`docs/results/2026-10-13-memory-cell/prereg.md`): N against S
on one model and one scene family, pair by pair.

A pair is (scene, model, repetition) with both arms run (`analyze.ran`). The planned pairs are the
scene set's scenes at the given repetitions; a pair where either arm is NOT RUN, or never started,
is listed and left out. A **break** is the gate's: the fact not kept with the task not failed
(`analyze.broke`). The primary is a one-sided exact McNemar on breaks, S better than N. The rest
are criteria fixed before the data:

- fact alone: the same McNemar on `fact_kept`, a failed task counting as not kept, also p < ALPHA
  (so S cannot win by failing tasks, which the gate's break forgives);
- tests and task: S passes in no more than `floor(MARGIN * pairs)` fewer pairs than N (3 of 24);
- false send-backs: S's last sessions sent back by a rule that is not the scene's own (a decoy or
  any other rule), at most `floor(FALSE_MAX * pairs)` (1 of 24);
- cost: the median over pairs of S's cost over N's (Claude Code's list price plus S's decisions)
  at most `COST_MAX` (1.15).

Verdict: "gana" when every criterion holds; "no gana" otherwise, with each criterion that failed
named; "sin veredicto" when fewer than `MIN_PAIRS` pairs ran. Reported beside it, never deciding:
the other one-sided p (S breaks more), the variants of family iii apart, a bootstrap interval of
the cost ratio by scene, wall time, every break and send-back by name, S pairs whose hook log does
not show one start per session (their send-backs cannot be placed), and S's hook calls that
ended in an error.

    python benchmarks/memory_carry/cell.py RUN_DIR [RUN_DIR ...] [--a S] [--b N]
        [--scenes parallel] [--repeats 1,2,3] [--model sonnet]
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
from carry import SCENES, SETS  # noqa: E402
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


def wall(row: dict[str, Any]) -> float:
    return sum(float(s.get("seconds") or 0.0) for s in row.get("sessions") or [])


def paired(all_rows: list[dict[str, Any]], a: str, b: str,
           planned: list[Pair] | None = None) -> tuple[dict[Pair, dict], list[str]]:  # fmt: skip
    pairs: dict[Pair, dict[str, dict[str, Any]]] = {k: {} for k in planned or []}
    for r in all_rows:
        pairs.setdefault((r["scene"], r["model"], r["repeat"]), {})[r["arm"]] = r
    done = {k: p for k, p in pairs.items() if ran(p.get(a)) and ran(p.get(b))}
    not_run = sorted(f"{k[0]} r{k[2]}" + ("" if p else " (never started)")
                     for k, p in pairs.items() if k not in done)  # fmt: skip
    return done, not_run


def pair_dir(row: dict[str, Any], run_dir: Path) -> Path:
    return run_dir / f"{row['scene']}-{row['model']}-{row['arm']}-{row['repeat']}"


def false_sendbacks(row: dict[str, Any], run_dir: Path) -> list[str]:
    """Rules other than the scene's own that sent the row's last session back."""
    last = len(row.get("planned") or [None, None])
    return [str(f["rule"]) for f in sendbacks(pair_dir(row, run_dir))
            if not f["own"] and f["session"] == last]  # fmt: skip


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        out += [item] if isinstance(item, dict) else []
    return out


def starts(row: dict[str, Any], run_dir: Path) -> int:
    """Session starts memory logged in the pair (`sendbacks` numbers sessions by them)."""
    log = _jsonl(pair_dir(row, run_dir) / "hook-log.jsonl")
    return sum(1 for r in log if r.get("event") == "SessionStart" and r.get("source") == "startup")


def hook_errors(row: dict[str, Any], run_dir: Path) -> int:
    """S's hook calls that exited non-zero or wrote to stderr."""
    calls = _jsonl(pair_dir(row, run_dir) / "hooks.jsonl")
    return sum(1 for r in calls if r.get("exit") not in (0, None) or r.get("stderr"))


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


def discordant(done: dict[Pair, dict], a: str, b: str, bad: Any) -> tuple[int, int]:
    """(pairs where only B was bad, pairs where only A was bad)."""
    a_only = sum(1 for p in done.values() if bad(p[b]) and not bad(p[a]))
    b_only = sum(1 for p in done.values() if bad(p[a]) and not bad(p[b]))
    return a_only, b_only


def criteria(done: dict[Pair, dict], a: str, b: str, sent: dict[str, list[str]]) -> dict[str, Any]:
    n = len(done)
    ca, cb = counts(done, a), counts(done, b)
    margin = math.floor(MARGIN * n)
    ratios = [total(p[a]) / total(p[b]) for p in done.values() if total(p[b]) > 0]
    median = statistics.median(ratios) if ratios else None
    p_break = mcnemar(*discordant(done, a, b, broke))
    p_fact = mcnemar(*discordant(done, a, b, lambda r: not r["fact_kept"]))
    return {
        "primary": {"p": p_break, "holds": p_break < ALPHA},
        "fact_alone": {"p": p_fact, "holds": p_fact < ALPHA},
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


def named(done: dict[Pair, dict], test: Any) -> list[str]:
    return sorted(f"{k[0]} r{k[2]}" for k, p in done.items() if test(p))


def cell(all_rows: list[dict[str, Any]], run_dirs: dict[str, Path], a: str = "S",
         b: str = "N", planned: list[Pair] | None = None) -> dict[str, Any]:  # fmt: skip
    done, not_run = paired(all_rows, a, b, planned)
    a_only, b_only = discordant(done, a, b, broke)
    where = {k: run_dirs[p[a]["run"]] for k, p in done.items()}
    sent = {f"{k[0]} r{k[2]}": found for k, p in sorted(done.items())
            if (found := false_sendbacks(p[a], where[k]))}  # fmt: skip
    checks = criteria(done, a, b, sent)
    walls = [wall(p[a]) / wall(p[b]) for p in done.values() if wall(p[b]) > 0]
    return {"pairs": len(done), "not_run": not_run, "a": a, "b": b,
            "count": {a: counts(done, a), b: counts(done, b)},
            "a_only_kept": a_only, "b_only_kept": b_only,
            "p_a_better": mcnemar(a_only, b_only), "p_a_worse": mcnemar(b_only, a_only),
            "criteria": checks, "verdict": verdict(len(done), checks),
            "cost": {a: round(sum(total(p[a]) for p in done.values()), 4),
                     b: round(sum(total(p[b]) for p in done.values()), 4),
                     "jev": round(sum(float(p[a].get("jev_usd") or 0) for p in done.values()), 6),
                     "ratio_ci95": boot_ratio(done, a, b)},
            "wall_ratio_median": statistics.median(walls) if walls else None,
            "variants": variants(done, a, b), "false_sendbacks": sent,
            "starts_mismatch": named(done, lambda p: starts(p[a], where_of(p, run_dirs, a))
                                     != len(p[a].get("planned") or [])),
            "hook_errors": {f"{k[0]} r{k[2]}": e for k, p in sorted(done.items())
                            if (e := hook_errors(p[a], where[k]))},
            "broken": {arm: named(done, lambda p, arm=arm: broke(p[arm])) for arm in (a, b)},
            "not_kept": {arm: named(done, lambda p, arm=arm: not p[arm]["fact_kept"])
                         for arm in (a, b)}}  # fmt: skip


def where_of(p: dict[str, dict[str, Any]], run_dirs: dict[str, Path], arm: str) -> Path:
    return run_dirs[p[arm]["run"]]


def planned_pairs(scenes: str, repeats: str, model: str) -> list[Pair]:
    names = SETS[scenes] if scenes in SETS else scenes.split(",")
    return [(n, model, int(r)) for r in repeats.split(",") for n in names]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--a", default="S")
    parser.add_argument("--b", default="N")
    parser.add_argument("--scenes", default="parallel")
    parser.add_argument("--repeats", default="1,2,3")
    parser.add_argument("--model", default="sonnet")
    args = parser.parse_args(argv)
    dirs = folders(args.runs)
    found = rows(dirs)
    planned = planned_pairs(args.scenes, args.repeats, args.model)
    out = cell(found, {d.name: d for d in dirs}, args.a, args.b, planned)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
