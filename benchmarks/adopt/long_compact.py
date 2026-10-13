"""The context close-out read as its prereg says (docs/results/2026-10-13-long-compact/prereg.md):
N-early-low (Nl, compacts near 67k) against N-early (Ne, near 160k), one run per arm and chain.
Free: it reads rows, grades and diffs under the root (`long_compare.arm_line`).

    python benchmarks/adopt/long_compact.py [--root C:\\sp-runs\\L-compact] [--json out.json]

Per chain, on the calls both arms ran (`common_calls`: a run stopped by its cap ran fewer):
- cost of each arm over those calls (owner USD, cut calls at their caps) and Nl/Ne;
- resolved bugs of each arm on the bugs both ran and both graded;
- compactions (count and their `pre` tokens), peak context, unresolved give-ups.
Over chains (the unit is the run, never the bug):
- primary: `long_report.cost_ratio` of Nl/Ne, the paired mean of ln(Nl/Ne) with its 95 % t interval;
- quality: `long_report.cluster_bootstrap` of Nl - Ne in resolved rate (whole chains resampled),
  and its one-sided 95 % lower bound against the margin `MARGIN` (10 points);
- the verdict by `RULE`, written before any run.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import long_compare  # noqa: E402
import long_report  # noqa: E402

ROOT = Path(r"C:\sp-runs\L-compact")
MODEL = "sonnet"
TREATED, CONTROL = "Nl", "Ne"
MARGIN = 0.10  # non-inferiority in resolved rate, one-sided 95 % (prereg, fixed before any run)
MIN_CHAINS = 5  # chains with both arms read; fewer: no verdict
MIN_COMMON = 30  # calls both arms ran, for a chain to count
RULE = (
    "wins: the cost ratio's 95 % interval lies below 1 and quality is non-inferior (one-sided "
    "95 % lower bound of Nl - Ne above -10 points); cheaper, quality not shown: the interval "
    "below 1, non-inferiority not shown; no difference shown: the interval holds 1; dearer: the "
    "interval above 1; no verdict: fewer than 5 chains with 30 common calls"
)


def ran_calls(row: Mapping[str, Any]) -> list[int]:
    """Request numbers of the calls that ran or were charged (anything but NOT RUN)."""
    return sorted(int(c["request"]) for c in row.get("calls") or []
                  if not str(c.get("status", "")).startswith("NOT RUN"))  # fmt: skip


def common_calls(treated: Mapping[str, Any], control: Mapping[str, Any]) -> int:
    """The last call k such that both arms ran calls 1..k."""
    def prefix(calls: list[int]) -> int:
        k = 0
        for r in calls:
            if r != k + 1:
                break
            k = r
        return k

    return min(prefix(ran_calls(treated)), prefix(ran_calls(control)))


def cost_upto(row: Mapping[str, Any], k: int) -> float:
    return round(sum(float(c.get("owner_usd") or 0.0) for c in row.get("calls") or []
                     if int(c.get("request") or 0) <= k), 4)  # fmt: skip


def _row(evidence: Path) -> dict[str, Any] | None:
    try:
        return json.loads((evidence / "row.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def compaction_pres(row: Mapping[str, Any]) -> list[int]:
    return [int(c.get("pre") or 0) for call in row.get("calls") or []
            for c in call.get("compactions") or []]  # fmt: skip


def chain_line(root: Path, chain: str) -> dict[str, Any] | None:
    """Both arms of one chain, or None when either has no row."""
    base = root / "runs" / f"{chain}-{MODEL}"
    rows = {a: _row(base / a) for a in (TREATED, CONTROL)}
    lines = {a: long_compare.arm_line(base / a) for a in (TREATED, CONTROL)}
    if any(v is None for v in (*rows.values(), *lines.values())):
        return None
    k = common_calls(rows[TREATED], rows[CONTROL])
    cost = {a: cost_upto(rows[a], k) for a in rows}
    x, y = lines[TREATED], lines[CONTROL]
    both = [i for i in long_compare._ran_both(x, y)
            if x["per_bug"][i]["request"] <= k and y["per_bug"][i]["request"] <= k
            and x["per_bug"][i]["resolved"] is not None
            and y["per_bug"][i]["resolved"] is not None]  # fmt: skip
    pairs = [(bool(x["per_bug"][i]["resolved"]), bool(y["per_bug"][i]["resolved"])) for i in both]
    arms = {a: {"cost_common": cost[a], "cost_total": lines[a]["cost_usd"],
                "calls_ran": len(ran_calls(rows[a])), "stopped": lines[a]["stopped"],
                "resolved_common": sum(t if a == TREATED else c for t, c in pairs),
                "resolved_total": lines[a]["resolved"],
                "compactions": compaction_pres(rows[a]),
                "peak_context": lines[a]["peak_context"],
                "gave_up_unresolved": lines[a]["gave_up_unresolved"],
                "cost_per_resolved_common": (round(cost[a] / r, 4) if (r := sum(
                    t if a == TREATED else c for t, c in pairs)) else None)}
            for a in rows}  # fmt: skip
    return {"common_calls": k, "common_bugs": len(pairs),
            "ratio": round(cost[TREATED] / cost[CONTROL], 4) if cost[CONTROL] else None,
            "arms": arms, "pairs": pairs}


def verdict(cost: Mapping[str, Any], low: float | None, chains: int) -> str:
    """`RULE`, applied."""
    if chains < MIN_CHAINS or "high" not in cost:
        return "no verdict"
    if cost["high"] < 1.0:
        return "wins" if low is not None and low > -MARGIN else "cheaper, quality not shown"
    if cost["low"] > 1.0:
        return "dearer"
    return "no difference shown"


def read(root: Path, chains: Sequence[str]) -> dict[str, Any]:
    found = {c: line for c in chains if (line := chain_line(root, c)) is not None}
    counted = {c: v for c, v in found.items() if v["common_calls"] >= MIN_COMMON and v["ratio"]}
    pairs = [(v["arms"][TREATED]["cost_common"], v["arms"][CONTROL]["cost_common"])
             for v in counted.values()]  # fmt: skip
    cost = long_report.cost_ratio(pairs)
    clusters = [v["pairs"] for v in counted.values() if v["pairs"]]
    quality = None
    if clusters:
        diff, lo, hi = long_report.cluster_bootstrap(clusters)
        quality = {"difference": round(diff, 4), "ci95": [round(lo, 4), round(hi, 4)],
                   "one_sided_low": round(long_report.one_sided_low(clusters), 4)}  # fmt: skip
    low = quality["one_sided_low"] if quality else None
    lines = {c: {k: v for k, v in line.items() if k != "pairs"} for c, line in found.items()}
    return {"rule": RULE, "margin": MARGIN, "chains_read": len(found),
            "chains_counted": sorted(counted), "cost": cost, "quality": quality,
            "verdict": verdict(cost, low, len(counted)), "chains": lines}


def main(argv: list[str] | None = None) -> int:
    import long_run

    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--chains", default=",".join(long_run.PROFILES["compact"].chains))
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)
    data = read(Path(args.root), [c for c in args.chains.split(",") if c])
    text = json.dumps(data, indent=1)
    print(text)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
