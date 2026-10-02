"""Paired analysis of carry runs: fact kept, tests, task and cost, arm against arm.

Pairs are (scene, model, repeat). Excluded, and listed as NOT RUN: a pair where either arm hit
the usage limit or a session ended without a result. The primary test of every prereg in
`docs/results/2026-10-02-memory-carry/` is a one-sided exact McNemar on `fact_kept`.

    python benchmarks/memory_carry/analyze.py RUN_DIR [RUN_DIR ...] --a M --b N [--scenes x,y]
"""

from __future__ import annotations

import argparse
import json
import statistics
from math import comb
from pathlib import Path
from typing import Any


def rows(dirs: list[Path]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in dirs:
        path = d / "carry.json"
        if path.exists():
            out += [{**r, "run": d.name} for r in json.loads(path.read_text(encoding="utf-8"))]
    return out


def ran(row: dict[str, Any] | None) -> bool:
    if not row or row.get("limit_hit") or not row.get("second"):
        return False
    return not (row["first"].get("returncode") or row["second"].get("returncode"))


def mcnemar(a_only: int, b_only: int) -> float:
    """One-sided exact p that A keeps the fact more often than B."""
    k = a_only + b_only
    return sum(comb(k, i) for i in range(a_only, k + 1)) / 2**k if k else 1.0


def compare(all_rows: list[dict[str, Any]], a: str, b: str,
            scenes: set[str] | None = None) -> dict[str, Any]:  # fmt: skip
    pairs: dict[tuple[str, str, int], dict[str, dict[str, Any]]] = {}
    for r in all_rows:
        if scenes and r["scene"] not in scenes:
            continue
        pairs.setdefault((r["scene"], r["model"], r["repeat"]), {})[r["arm"]] = r
    done = {k: p for k, p in pairs.items() if ran(p.get(a)) and ran(p.get(b))}
    not_run = sorted(k for k, p in pairs.items() if a in p and b in p and k not in done)
    count = {arm: {"fact": 0, "tests": 0, "task": 0, "task_n": 0} for arm in (a, b)}
    a_only = b_only = 0
    ratios = []
    for p in done.values():
        for arm in (a, b):
            r = p[arm]
            count[arm]["fact"] += bool(r["fact_kept"])
            count[arm]["tests"] += bool(r["tests_pass"])
            if r["task_pass"] is not None:
                count[arm]["task"] += bool(r["task_pass"])
                count[arm]["task_n"] += 1
        a_only += bool(p[a]["fact_kept"]) and not p[b]["fact_kept"]
        b_only += bool(p[b]["fact_kept"]) and not p[a]["fact_kept"]
        if p[b]["cost"]:
            ratios.append(p[a]["cost"] / p[b]["cost"])
    return {"pairs": len(done), "not_run": not_run, "count": count, "a_only": a_only,
            "b_only": b_only, "p": mcnemar(a_only, b_only),
            "cost_ratio": statistics.median(ratios) if ratios else None,
            "broken": {arm: sorted(f"{k[0]} r{k[2]}" for k, p in done.items()
                                   if not p[arm]["fact_kept"]) for arm in (a, b)}}  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--a", required=True)
    parser.add_argument("--b", required=True)
    parser.add_argument("--scenes", default="")
    args = parser.parse_args(argv)
    scenes = set(args.scenes.split(",")) if args.scenes else None
    out = compare(rows([Path(r) for r in args.runs]), args.a, args.b, scenes)
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
