"""F2, descriptive and post hoc: paired bootstrap 95 % intervals of the cost ratios S/N0 and S/H.

F2's prereg seals no cost condition, so this is reported, never deciding. The statistic is the
one F2's table gives (`handoff_analyze.reported`): the median over triples of S's cost (Jev
included) over the other arm's cost, H at its handoff turn's own cost. Triples are resampled with
replacement (10,000 draws, seed 20261016) and the interval is the 2.5th and 97.5th percentiles.

    python benchmarks/memory_carry/handoff_cost_ci.py docs/results/2026-10-16-memory-f2
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from handoff_analyze import ARMS, ran, triples  # noqa: E402
from handoff_cost import own_row  # noqa: E402

DRAWS = 10_000
SEED = 20261016
MODELS = ("sonnet", "opus")


def s_cost(t: dict[str, dict[str, Any]]) -> float:
    return float(t["S"]["cost"]) + float(t["S"].get("jev_usd") or 0)


def ratios(rows: list[dict[str, Any]], model: str, other: str) -> list[float]:
    """S's cost over `other`'s, one per triple with all three arms run, as the table pairs them."""
    mine = [own_row(r) for r in rows if r["model"] == model]
    done = [t for t in triples(mine).values() if all(ran(t.get(a)) for a in ARMS)]
    return [s_cost(t) / float(t[other]["cost"]) for t in done if t[other]["cost"]]


def percentile(sorted_values: list[float], q: float) -> float:
    """Linear interpolation between closest ranks (numpy's default)."""
    pos = (len(sorted_values) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def bootstrap_median(values: list[float], draws: int = DRAWS, seed: int = SEED) -> dict[str, Any]:
    """The median and its percentile bootstrap 95 % interval, resampling the values."""
    if not values:
        raise ValueError("no paired triples to resample")
    rng = random.Random(seed)
    n = len(values)
    meds = sorted(statistics.median(rng.choices(values, k=n)) for _ in range(draws))
    return {
        "triples": n,
        "median": round(statistics.median(values), 6),
        "ci95": [round(percentile(meds, 0.025), 4), round(percentile(meds, 0.975), 4)],
        "draws": draws,
        "seed": seed,
    }


def intervals(folder: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for model in MODELS:
        rows = json.loads((folder / f"rows-f2-{model}.json").read_text(encoding="utf-8"))
        out[model] = {f"S/{b}": bootstrap_median(ratios(rows, model, b)) for b in ("N0", "H")}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", type=Path, help="the published F2 folder (rows-f2-*.json)")
    args = ap.parse_args(argv)
    sys.stdout.write(json.dumps(intervals(args.folder), indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
