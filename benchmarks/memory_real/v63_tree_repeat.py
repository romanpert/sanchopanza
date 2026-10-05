"""Why two recordings of the same chain differ (records that changed nothing: 0.030 against 0.034
on B2, HANDOFF-2026-10-01-memoria-v62). Records each arm's chain through the hook several times
(`v6_chain_real.record_chain`, tree on) and compares what each record says it changed, with
every git call and every file read past the snapshot's byte budget logged. Local, free, read-only
on `adopt/runs`.

    python benchmarks/memory_real/v63_tree_repeat.py --arms pydantic__pydantic-long40-1/S:15-40 \
        [--times 2] [--out FILE]
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import v6_chain as vc  # noqa: E402
import v6_chain_real as vr  # noqa: E402

from sanchopanza.context import worktree  # noqa: E402

LOG: list[dict[str, Any]] = []


def instrument() -> None:
    """Log each git call's time and outcome, and each read that fell back to size and time."""
    run, read = worktree._run, worktree._read

    def timed(cwd: str, *args: str, data: bytes | None = None) -> bytes | None:
        start = time.monotonic()
        try:
            out = run(cwd, *args, data=data)
        except Exception as error:
            LOG.append({"git": args[:2], "s": round(time.monotonic() - start, 3),
                        "error": error.__class__.__name__})  # fmt: skip
            raise
        LOG.append({"git": args[:2], "s": round(time.monotonic() - start, 3),
                    "ok": out is not None})  # fmt: skip
        return out

    def logged(path: Path, budget: list[int]) -> tuple[bytes | None, str]:
        data, key = read(path, budget)
        if data is None:
            LOG.append({"read": path.name, "key": key, "budget_left": budget[0]})
        return data, key

    worktree._run, worktree._read = timed, logged


def recorded(arm: Path, chain: dict[str, Any]) -> dict[int, list[str]]:
    with tempfile.TemporaryDirectory() as tmp:
        rec = vr.record_chain(arm, chain, Path(tmp), tree=True)
        return {i: sorted(e.changed_raw or e.changed) for i, e in rec["records"].items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arms", required=True)
    parser.add_argument("--times", type=int, default=2)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    instrument()
    report: dict[str, Any] = {}
    for spec in args.arms.split(","):
        name, _, span = spec.partition(":")
        hi = int(span.split("-")[1]) if span else 10**6
        arm = vc.RUNS / name
        chain = vc.chain(arm)
        if chain is None:
            continue
        chain = {**chain, "requests": [r for r in chain["requests"] if r["i"] <= hi]}
        runs, logs = [], []
        for _ in range(args.times):
            LOG.clear()
            runs.append(recorded(arm, chain))
            logs.append(list(LOG))
        differ = {i: [r.get(i) for r in runs] for i in runs[0]
                  if any(r.get(i) != runs[0].get(i) for r in runs[1:])}  # fmt: skip
        empty = [sum(not v for v in r.values()) for r in runs]
        report[name] = {
            "records": [len(r) for r in runs],
            "changing_nothing": empty,
            "differ": {str(k): v for k, v in differ.items()},
            "git_max_s": [max((x["s"] for x in lg if "git" in x), default=0) for lg in logs],
            "git_failed": [sum(1 for x in lg if "git" in x and not x.get("ok")) for lg in logs],
            "reads_past_budget": [sum(1 for x in lg if "read" in x) for lg in logs],
        }
        print(name, json.dumps(report[name]), flush=True)
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
