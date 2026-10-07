"""N, S0 and S1 side by side on one suite's dev tasks, from the phases' private rows.

python benchmarks/h2h/compare_lines.py gaia|bcp|longdoc [--out report.json]   # free

Each arm comes from a (phase, arm) pair of the private cache: N is a phase's CC rows, S0 and S1
the SP rows of the phase that ran that line. Rows marked `invalid` (Jev out of credit, S failed
open) are left out, and a task counts only where every arm has a valid row. Grades: GAIA's
official scorer, BrowseComp-Plus' exact match or judge with hand verdicts first, LongBench's
letter. Counts, costs and task ids only.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import components as comp_mod  # noqa: E402
import h2h_bcp as bcp  # noqa: E402
import offline_common as common  # noqa: E402

gaia, stats = common.gaia, common.stats
CACHE = pathlib.Path.home() / ".cache" / "sanchopanza"
KNOWLEDGE = ("search", "read", "pick")
SUITES: dict[str, dict[str, tuple[str, str]]] = {
    "gaia": {"N": ("gaia/h2h/dev-s1", "SONNET-CC"), "S0": ("gaia/h2h/dev-s0", "SONNET-SP"),
             "S1": ("gaia/h2h/dev-s1", "SONNET-SP")},
    "bcp": {"N": ("bcp/h2h/bcp-dev", "SONNET-CC"), "S0": ("bcp/h2h/bcp-dev", "SONNET-SP"),
            "S1": ("bcp/h2h/bcp-dev-s1", "SONNET-SP")},
    "longdoc": {"N": ("longdoc/h2h/longdoc-dev", "SONNET-CC"),
                "S0": ("longdoc/h2h/longdoc-dev", "SONNET-SP"),
                "S1": ("longdoc/h2h/longdoc-dev-s1", "SONNET-SP")},
}  # fmt: skip


def rows_of(suite: str, folder: str, arm: str) -> list[dict[str, Any]]:
    own = CACHE / folder
    rows = [r for r in gaia.read_rows(own / "sessions.jsonl")
            if r.get("arm") == arm and not r.get("invalid")]  # fmt: skip
    hand = gaia.hand_verdicts(own / "hand.jsonl")
    if suite == "bcp":
        rows = bcp.with_grades(rows, own / "graded.jsonl")
        return [{**r, "ok_final": bcp.graded_ok(r, hand)} for r in rows]
    return [{**r, "ok_final": bool(hand.get((r["task"], r["arm"], r["run"]), r["ok_oficial"]))}
            for r in rows]  # fmt: skip


def knowledge_uses(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in KNOWLEDGE:
        tool = f"mcp__sanchopanza-knowledge__{name}"
        calls = [int((r.get("tools") or {}).get(tool, 0)) for r in rows]
        out[name] = {"calls": sum(calls), "sessions": sum(c > 0 for c in calls)}
    web = [int((r.get("tools") or {}).get(t, 0)) for r in rows for t in ("WebSearch", "WebFetch")]
    out["web_tools_calls"] = sum(web)
    return out


def cell(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    usd = [stats.cost(r) for r in rows]
    tokens = {k: sum(int((r.get("tokens") or {}).get(k, 0)) for r in rows)
              for k in stats.TOKEN_KINDS}  # fmt: skip
    comps = comp_mod.summary([{**r, "arm": "x"} for r in rows]).get("x", {})
    return {
        "sessions": len(rows),
        "right_official": sum(bool(r.get("ok_oficial") if "em" not in r else r.get("em")
                                   or r.get("judged")) for r in rows),
        "right_final": sum(bool(r["ok_final"]) for r in rows),
        "usd_total": round(sum(usd), 4), "usd_mean": round(statistics.mean(usd), 4),
        "usd_median": round(statistics.median(usd), 4),
        "turns_mean": round(statistics.mean(int(r.get("turns") or 0) for r in rows), 1),
        "wall_mean_s": round(statistics.mean(float(r["wall_s"]) for r in rows), 1),
        "tokens": tokens,
        "knowledge": knowledge_uses(rows),
        "jev_calls": sum(int(r.get("jev_calls") or 0) for r in rows),
        "jev_by_point": stats._sum_maps([r.get("jev_by_point") or {} for r in rows]),
        "jev_usd": round(sum(float(r.get("jev_usd") or 0.0) for r in rows), 6),
        "components": {k: comps.get(k, {}) for k in ("calls", "outputs", "sessions_with_output",
                                                     "returns", "turns_after", "usd_after")},
        "leak": sorted(r["task"] for r in rows if r.get("leak")),
        "hit_cap": sum(bool(r.get("hit_cap")) for r in rows),
    }  # fmt: skip


def paired(a: Mapping[str, Mapping], b: Mapping[str, Mapping], tasks: Sequence[str]) -> dict:
    ga = [bool(a[t]["ok_final"]) for t in tasks]
    gb = [bool(b[t]["ok_final"]) for t in tasks]
    only_a, only_b, p = stats.mcnemar(ga, gb)
    return {
        "a_only": [t for t, x, y in zip(tasks, ga, gb, strict=True) if x and not y],
        "b_only": [t for t, x, y in zip(tasks, ga, gb, strict=True) if y and not x],
        "p": round(p, 4),
        "cost": stats.bootstrap_cost(
            [stats.cost(a[t]) for t in tasks], [stats.cost(b[t]) for t in tasks]
        ),  # fmt: skip
    }


def compare(suite: str) -> dict[str, Any]:
    arms = {name: {r["task"]: r for r in rows_of(suite, *where)}
            for name, where in SUITES[suite].items()}  # fmt: skip
    tasks = sorted(set.intersection(*(set(v) for v in arms.values())))
    out: dict[str, Any] = {"suite": suite, "tasks": len(tasks), "task_ids": tasks}
    out["by_arm"] = {name: cell([rows[t] for t in tasks]) for name, rows in arms.items()}
    out["paired"] = {f"{a}-{b}": paired(arms[a], arms[b], tasks)
                     for a, b in (("S1", "N"), ("S1", "S0"), ("S0", "N"))}  # fmt: skip
    s1_n = sorted(set(arms["S1"]) & set(arms["N"]))
    if len(s1_n) > len(tasks):
        s1, n = arms["S1"], arms["N"]
        out["s1_vs_n_all_valid"] = {
            "tasks": len(s1_n),
            **paired(s1, n, s1_n),
            "S1_right": sum(bool(s1[t]["ok_final"]) for t in s1_n),
            "N_right": sum(bool(n[t]["ok_final"]) for t in s1_n),
            "S1_usd": round(sum(stats.cost(s1[t]) for t in s1_n), 4),
            "N_usd": round(sum(stats.cost(n[t]) for t in s1_n), 4),
        }
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("suite", choices=sorted(SUITES))
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    result = compare(args.suite)
    text = json.dumps(result, indent=1)
    if args.out:
        pathlib.Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
