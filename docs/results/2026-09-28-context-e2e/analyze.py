"""Tables and the registered hypotheses from `phase-a.jsonl` and `runs.jsonl`. Free.

python analyze.py            # prints the tables, writes analysis.json
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from statistics import mean, median
from typing import Any

HERE = Path(__file__).resolve().parent
ARMS = ("N", "R", "S", "F")


ROUND1 = {f"t0{i}-{d}" for i, d in enumerate(
    ("orders", "shipments", "invoices", "sensors", "tickets", "bookings"), start=1)}  # fmt: skip


def rows(name: str) -> list[dict[str, Any]]:
    """Round 1's rows only (t01-t06); amendment R3's t07-t12 rows share the files."""
    path = HERE / name
    if not path.exists():
        return []
    out = [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]
    return [r for r in out if r["task"] in ROUND1]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def b_input(r: dict[str, Any]) -> int:
    u = r["b"].get("usage") or {}
    return sum(int(u.get(k) or 0) for k in (
        "input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))  # fmt: skip


def per_arm(runs: list[dict[str, Any]], arm: str, tasks: set[str]) -> dict[str, Any] | None:
    rs = sorted(
        (r for r in runs if r["arm"] == arm and r["task"] in tasks), key=lambda r: r["task"]
    )
    if not rs:
        return None
    n = len(rs)
    k = sum(r["success"] for r in rs)
    after = [r.get("after") or {} for r in rs]
    kinds: dict[str, int] = {}
    for r in rs:
        kind = (r.get("compaction") or {}).get("kind", "missing")
        kinds[kind] = kinds.get(kind, 0) + 1
    hooks = [r["hook"] for r in rs if r.get("hook")]
    return {
        "n": n,
        "success": k,
        "success_ci": wilson(k, n),
        "facts": {
            f: sum(bool(r["facts"].get(f)) for r in rs)
            for f in ("token", "probe", "window", "visible")
        },  # noqa: E501
        "b_input_tokens_sum": sum(b_input(r) for r in rs),
        "b_input_tokens_median": median(b_input(r) for r in rs),
        "b_output_tokens_sum": sum(
            int((r["b"].get("usage") or {}).get("output_tokens") or 0) for r in rs
        ),  # noqa: E501
        "b_first_context_median": median(a.get("first_context_tokens", 0) for a in after),
        "compact_usd": round(sum(r["compact"]["cost_usd"] for r in rs), 4),
        "b_usd": round(sum(r["b"]["cost_usd"] for r in rs), 4),
        "usd_per_task": round(mean(r["compact"]["cost_usd"] + r["b"]["cost_usd"] for r in rs), 4),
        "jev_usd": round(sum(r.get("jev_usd", 0.0) for r in rs), 5),
        "re_reads_mean": round(mean(a.get("re_reads", 0) for a in after), 2),
        "re_reads_total": sum(a.get("re_reads", 0) for a in after),
        "archive_reads": sum(a.get("archive_reads", 0) for a in after),
        "greps_mean": round(mean(a.get("greps", 0) for a in after), 2),
        "one_shot_reruns": sum(a.get("one_shot_reruns", 0) for a in after),
        "b_turns_median": median(a.get("turns", 0) for a in after),
        "compaction_kinds": kinds,
        "summary_keeps": {
            k: sum(bool((r.get("summary_keeps") or {}).get(k)) for r in rs)
            for k in ("token", "code", "tolerance", "helper", "window_home")
        },
        "window_constants": sorted(str(r.get("window_constant")) for r in rs),
        "leftover_hits": sum(a.get("leftover_hits", 0) for a in after),
        "fallbacks": sum(bool(h["fallback"]) for h in hooks),
        "pruned": sum(h["pruned"] > 0 and not h["fallback"] for h in hooks),
        "fallback_reasons": sorted({x[:120] for h in hooks for x in h["fallback_reasons"]}),
        "compact_seconds_median": median(r["compact"]["seconds"] for r in rs),
        "b_seconds_median": median(r["b"].get("seconds", 0) for r in rs),
        "b_capped_or_error": sum(r["b"].get("subtype") not in ("success",) for r in rs),
    }


def hypothesis(
    runs: list[dict[str, Any]], x: str, y: str, tasks: set[str]
) -> dict[str, Any] | None:
    """`x` holds against `y` if successes(x) >= successes(y) - 1 and tokens(x) <= tokens(y),
    over the tasks both arms ran."""
    by = {(r["task"], r["arm"]): r for r in runs}
    both = sorted(t for t in tasks if (t, x) in by and (t, y) in by)
    if not both:
        return None
    sx = sum(by[(t, x)]["success"] for t in both)
    sy = sum(by[(t, y)]["success"] for t in both)
    tx = sum(b_input(by[(t, x)]) for t in both)
    ty = sum(b_input(by[(t, y)]) for t in both)
    rx = [(by[(t, x)].get("after") or {}).get("re_reads", 0) for t in both]
    ry = [(by[(t, y)].get("after") or {}).get("re_reads", 0) for t in both]
    return {
        "tasks": len(both),
        f"success_{x}": sx, f"success_{y}": sy,
        "success_part": sx >= sy - 1,
        f"b_input_{x}": tx, f"b_input_{y}": ty,
        "token_part": tx <= ty,
        "holds": sx >= sy - 1 and tx <= ty,
        "discordant": {f"{x}_only": sum(by[(t, x)]["success"] and not by[(t, y)]["success"] for t in both),  # noqa: E501
                       f"{y}_only": sum(by[(t, y)]["success"] and not by[(t, x)]["success"] for t in both)},  # noqa: E501
        "re_reads_mean_diff": round(mean(a - b for a, b in zip(rx, ry, strict=True)), 2),
    }  # fmt: skip


def failures(runs: list[dict[str, Any]], tasks: set[str]) -> list[dict[str, Any]]:
    out = []
    for r in sorted(runs, key=lambda r: (r["task"], r["arm"])):
        if r["task"] not in tasks or r["success"]:
            continue
        out.append({
            "task": r["task"], "arm": r["arm"],
            "failed": [f for f, ok in r["facts"].items() if not ok],
            "compaction": (r.get("compaction") or {}).get("kind"),
            "fallback": (r.get("hook") or {}).get("fallback"),
            "b_subtype": r["b"].get("subtype"),
            "b_said": r["b"].get("result_text", "")[:240],
        })  # fmt: skip
    return out


def analyse() -> dict[str, Any]:
    a_rows = rows("phase-a.jsonl")
    runs = rows("runs.jsonl")
    valid = {r["task"] for r in a_rows if r["valid"]}
    return {
        "phase_a": {
            "tasks": len(a_rows),
            "valid": len(valid),
            "excluded": [
                {"task": r["task"], "subtype": r["subtype"], "consumed": r["consumed"]}
                for r in a_rows
                if not r["valid"]
            ],  # fmt: skip
            "usd": round(sum(r["cost_usd"] for r in a_rows), 4),
            "usd_mean": round(mean(r["cost_usd"] for r in a_rows), 4) if a_rows else 0,
            "seconds_median": median(r["seconds"] for r in a_rows) if a_rows else 0,
            "last_context_median": median(
                (r.get("transcript") or {}).get("last_context_tokens", 0) for r in a_rows
            )
            if a_rows
            else 0,  # fmt: skip
            "visible_pass_after_a": sum(bool(r.get("visible_pass")) for r in a_rows),
        },
        "arms": {arm: per_arm(runs, arm, valid) for arm in ARMS},
        "H1_S_vs_N": hypothesis(runs, "S", "N", valid),
        "H2_S_vs_F": hypothesis(runs, "S", "F", valid),
        "H2_F_vs_S": hypothesis(runs, "F", "S", valid),
        "H3_R_vs_N": hypothesis(runs, "R", "N", valid),
        "failures": failures(runs, valid),
        "spend": {
            "claude_usd": round(
                sum(r["cost_usd"] for r in a_rows)
                + sum(r["compact"]["cost_usd"] + r["b"]["cost_usd"] for r in runs),
                4,
            ),
            "jev_usd": round(sum(r.get("jev_usd", 0.0) for r in runs), 5),
        },  # fmt: skip
    }


def main() -> int:
    result = analyse()
    (HERE / "analysis.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
