"""Verdicts of the find end-to-end run (prereg-find-e2e.md), from each session's `row.json`.

Paired by instance: only instances where both arms ran and ended are compared. A session with
no FILES line counts as a miss (the agent did not answer), and is reported apart.
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

FIND_TOOL = "mcp__sanchopanza__find_in_repo"


def _rows(runs: Path) -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(runs.glob("*/row.json"))]


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def summary(runs: Path, out: Path) -> dict[str, Any]:
    rows = _rows(runs)
    by = {(r["instance"], r["arm"]): r for r in rows}
    paired = sorted({i for i, a in by if a == "N" and (i, "F") in by})
    n, f = [by[(i, "N")] for i in paired], [by[(i, "F")] for i in paired]

    def arm(group: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "sessions": len(group),
            "answered": sum(bool(r["claimed"]) for r in group),
            "any@1": sum(bool(r.get("any@1")) for r in group),
            "any@5": sum(bool(r.get("any@5")) for r in group),
            "median_cost_usd": _median([r["cost_usd"] for r in group]),
            "total_cost_usd": round(sum(r["cost_usd"] for r in group), 4),
            "median_reads": _median([r["calls"].get("Read", 0) for r in group]),
            "median_turns": _median([r["turns"] or 0 for r in group]),
            "jev_usd": round(sum(r.get("jev_usd", 0.0) for r in group), 4),
        }

    result: dict[str, Any] = {"paired_instances": len(paired), "N": arm(n), "F": arm(f)}
    result["F_used_find"] = sum(r["calls"].get(FIND_TOOL, 0) > 0 for r in f)
    cost_deltas = [b["cost_usd"] - a["cost_usd"] for a, b in zip(n, f, strict=True)]
    result["median_paired_cost_delta_usd"] = _median(cost_deltas)
    gained = sum(bool(b.get("any@1")) and not a.get("any@1") for a, b in zip(n, f, strict=True))
    lost = sum(bool(a.get("any@1")) and not b.get("any@1") for a, b in zip(n, f, strict=True))
    result["any@1_gained_lost"] = [gained, lost]
    if paired:
        points = (result["F"]["any@1"] - result["N"]["any@1"]) / len(paired)
        delta = result["median_paired_cost_delta_usd"] or 0.0
        reads = (result["F"]["median_reads"] or 0) <= (result["N"]["median_reads"] or 0)
        result["verdicts"] = {
            "E1_F_any1_ge_N_plus_10_points": points >= 0.10,
            "E2_F_median_paired_cost_le_N": delta <= 0.0,
            "E3_F_median_reads_le_N": reads,
        }
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result
