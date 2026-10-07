"""The pilot of bet A against the gate's N, per chain: free, it only reads rows and grades.

    python benchmarks/adopt/pilot_a_compare.py [--gate C:\\sp-runs\\L]
        [--pilot C:\\sp-runs\\L-pilot-a] [--pilot10 C:\\sp-runs\\L-pilot-a10] [--json <out.json>]

The same chains (`long_run.GATE_CHAINS`), Sonnet 5.5 and caps: arm N from the gate's root
(`runs/<chain>-sonnet/N`), A (and A10 when it ran) from the pilot's. Per chain and arm: total cost
(owner USD, cut calls at their caps), cost per resolved bug, per-bug F2P (from `grade.json`; None
until graded), requests, peak context, compactions, give-ups (from the root's `report.json`), how
the arm ended, and for the passages arms the cuts and the re-request rates `r` and `r_whole`.
A/N ratios of cost and of cost per resolved bug.

k=1 per chain and arm: descriptive only, no inferential statistics (no interval, no test). A
difference here is a reason to run more, not a finding.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

CHAINS = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1")  # long_run.GATE_CHAINS
MODEL = "sonnet"
DECLARED = ("k=1 per chain and arm (one run each): descriptive, no inferential statistics; "
            "N is the gate's arm on the same chains, Sonnet 5.5 and caps")


def _json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _ratio(a: float | None, b: float | None) -> float | None:
    return round(a / b, 4) if a is not None and b else None


def arm_line(root: Path, chain: str, arm: str) -> dict[str, Any] | None:
    """One arm of one chain as its row, grade and the root's report say (None: it never ran)."""
    evidence = root / "runs" / f"{chain}-{MODEL}" / arm
    row = _json(evidence / "row.json")
    if row is None:
        return None
    calls = row.get("calls") or []
    grade = _json(evidence / "grade.json") or {}
    report = ((_json(root / "report.json") or {}).get("arms") or {})
    line = next((v for k, v in report.items() if k.startswith(f"{chain}/") and
                 k.endswith(f"/{arm}")), {})  # fmt: skip
    cost = round(sum(float(c.get("owner_usd") or 0.0) for c in calls), 4)
    resolved = grade.get("resolved")
    total = grade.get("bugs_total") or row.get("bugs")
    passages = row.get("passages") or {}
    return {"model": row.get("model"), "stopped": row.get("stopped") or "",
            "partial": bool(row.get("partial")), "cost_usd": cost,
            "calls_ran": sum(1 for c in calls if c.get("status") == "ran"),
            "calls_planned": row.get("requests_planned"), "resolved": resolved, "bugs": total,
            "f2p": round(resolved / total, 4) if resolved is not None and total else None,
            "cost_per_resolved": _ratio(cost, resolved) if resolved else None,
            "requests": sum(int(c.get("requests") or 0) for c in calls),
            "peak_context": max((int(c.get("peak_context") or 0) for c in calls), default=0),
            "compactions": sum(len(c.get("compactions") or []) for c in calls),
            "give_ups": (line.get("give_ups") or {}).get("give_ups"),
            "cuts": passages.get("cuts"), "r": passages.get("r"),
            "r_whole": passages.get("r_whole"), "chars_in": passages.get("chars_in"),
            "chars_out": passages.get("chars_out")}  # fmt: skip


def compare(gate: Path, pilots: Mapping[str, Path]) -> dict[str, Any]:
    chains: dict[str, Any] = {}
    for chain in CHAINS:
        arms = {"N": arm_line(gate, chain, "N"),
                **{a: arm_line(root, chain, a) for a, root in pilots.items()}}  # fmt: skip
        found = {a: v for a, v in arms.items() if v is not None}
        n = found.get("N")
        ratios = {f"{a}_vs_N": {"cost": _ratio(v["cost_usd"], n["cost_usd"]),
                                "cost_per_resolved": _ratio(v["cost_per_resolved"],
                                                            n["cost_per_resolved"])}
                  for a, v in found.items() if a != "N" and n}  # fmt: skip
        chains = {**chains, chain: {**found, **ratios}}
    models = {v["model"] for c in chains.values() for k, v in c.items() if "_vs_" not in k}
    warn = [] if len(models) <= 1 else [f"different models in the rows: {sorted(models)}"]
    return {"declared": DECLARED, "warnings": warn, "chains": chains}


COLUMNS = ("cost_usd", "cost_per_resolved", "f2p", "resolved", "requests", "peak_context",
           "compactions", "give_ups", "cuts", "r", "r_whole", "stopped")  # fmt: skip


def table(data: Mapping[str, Any]) -> list[str]:
    out = [data["declared"], *(f"WARNING {w}" for w in data["warnings"])]
    for chain, arms in data["chains"].items():
        out.append(chain)
        for arm, v in arms.items():
            if "_vs_" in arm:
                out.append(f"  {arm}: cost x{v['cost']}, "
                           f"per resolved bug x{v['cost_per_resolved']}")
            else:
                out.append(f"  {arm}: " + ", ".join(f"{k} {v.get(k)}" for k in COLUMNS))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gate", default=r"C:\sp-runs\L")
    parser.add_argument("--pilot", default=r"C:\sp-runs\L-pilot-a")
    parser.add_argument("--pilot10", default=r"C:\sp-runs\L-pilot-a10")
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)
    data = compare(Path(args.gate), {"A": Path(args.pilot), "A10": Path(args.pilot10)})
    for line in table(data):
        print(line)
    if args.json:
        Path(args.json).write_text(json.dumps(data, indent=1), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
