"""The context close-out read as its prereg says (docs/results/2026-10-13-long-compact/prereg.md):
N-early-low (Nl, compacts near 67k) against N-early (Ne, near 160k), one run per arm and chain.

    python benchmarks/adopt/long_compact.py grade [--root C:\\sp-runs\\L-compact]  # Docker, free
    python benchmarks/adopt/long_compact.py read  [--root ...] [--json out.json]   # free

Per chain, on the calls both arms ran (`common_calls`: 1..k, both; a run stopped by its cap ran
fewer; a superseded row, a call asked again after a 429 or a dead runner, does not count):
- cost of each arm over those calls (owner USD as the runner charged them: a cut call at its
  4.50 cap, as in every earlier long run) and Nl/Ne; the whole-run ratio too when both finished;
- `grade`: each arm graded at its own snapshot after call k (`diff-<k>.patch`, `perbug.grade`),
  written as `grade-common.json`, so the arm that ran on is not graded on calls the other never
  made. Quality is read on the bugs both arms were asked within those calls;
- compactions (their `pre` tokens), peak context, unresolved give-ups (`long_compare.arm_line`).
Over chains (the unit is the run, never the bug), counting a chain only with >= `MIN_COMMON`
common calls AND its common grade for both arms:
- primary: `long_report.cost_ratio` of Nl/Ne (paired mean of ln(Nl/Ne), 95 % t interval);
- quality: `long_report.cluster_bootstrap` of Nl - Ne in resolved rate (whole chains resampled)
  and its one-sided 95 % lower bound against `MARGIN`;
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
MIN_CHAINS = 5  # chains counted (cost and quality); fewer: no verdict
MIN_COMMON = 30  # calls both arms ran, for a chain to count
COMMON_GRADE = "grade-common.json"
RULE = (
    "wins: the cost ratio's 95 % interval lies below 1 and quality is non-inferior (one-sided "
    "95 % lower bound of Nl - Ne above -10 points); cheaper, quality not shown: the interval "
    "below 1, non-inferiority not shown; no difference shown: the interval holds 1; dearer: the "
    "interval above 1; no verdict: fewer than 5 chains with 30 common calls and both arms graded "
    "at them"
)


def ran_calls(row: Mapping[str, Any]) -> list[int]:
    """Request numbers of the calls that ran or were charged: not NOT RUN, not superseded (a call
    asked again leaves its first row superseded), each number once."""
    return sorted({int(c["request"]) for c in row.get("calls") or []
                   if not str(c.get("status", "")).startswith("NOT RUN")
                   and not c.get("superseded")})  # fmt: skip


def prefix(calls: Sequence[int]) -> int:
    """The largest k with calls 1..k all present."""
    k = 0
    for r in calls:
        if r != k + 1:
            break
        k = r
    return k


def common_calls(treated: Mapping[str, Any], control: Mapping[str, Any]) -> int:
    """The last call k such that both arms ran calls 1..k."""
    return min(prefix(ran_calls(treated)), prefix(ran_calls(control)))


def cost_upto(row: Mapping[str, Any], k: int) -> float:
    """Owner USD of calls 1..k, every row charged (a superseded call was paid too)."""
    return round(sum(float(c.get("owner_usd") or 0.0) for c in row.get("calls") or []
                     if int(c.get("request") or 0) <= k), 4)  # fmt: skip


def _json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def compaction_pres(row: Mapping[str, Any]) -> list[int]:
    return [int(c.get("pre") or 0) for call in row.get("calls") or []
            for c in call.get("compactions") or []]  # fmt: skip


def bugs_within(row: Mapping[str, Any], k: int) -> list[str]:
    """Instance ids of the bug requests 1..k (the bugs the arm had been asked by then)."""
    return list(dict.fromkeys(c["instance_id"] for c in row.get("calls") or []
                              if c.get("kind") == "bug" and int(c.get("request") or 0) <= k))


def chain_line(root: Path, chain: str) -> dict[str, Any] | None:
    """Both arms of one chain, or None when either has no row."""
    base = root / "runs" / f"{chain}-{MODEL}"
    rows = {a: _json(base / a / "row.json") for a in (TREATED, CONTROL)}
    lines = {a: long_compare.arm_line(base / a) for a in (TREATED, CONTROL)}
    if any(v is None for v in (*rows.values(), *lines.values())):
        return None
    k = common_calls(rows[TREATED], rows[CONTROL])
    cost = {a: cost_upto(rows[a], k) for a in rows}
    grades = {a: _json(base / a / COMMON_GRADE) for a in rows}
    graded = all(g is not None and g.get("common_calls") == k for g in grades.values())
    pairs: list[tuple[bool, bool]] = []
    if graded:
        asked = set(bugs_within(rows[TREATED], k)) & set(bugs_within(rows[CONTROL], k))
        res = {a: {b["instance_id"]: bool(b["resolved"]) for b in grades[a]["bugs"]}
               for a in rows}  # fmt: skip
        pairs = [(res[TREATED][i], res[CONTROL][i]) for i in sorted(asked)
                 if i in res[TREATED] and i in res[CONTROL]]  # fmt: skip
    finished = all(not lines[a]["stopped"] and prefix(ran_calls(rows[a])) ==
                   int(rows[a].get("requests_planned") or 0) for a in rows)  # fmt: skip
    arms = {a: {"cost_common": cost[a], "cost_total": lines[a]["cost_usd"],
                "calls_ran": len(ran_calls(rows[a])), "stopped": lines[a]["stopped"],
                "resolved_common": (sum(t if a == TREATED else c for t, c in pairs)
                                    if graded else None),
                "resolved_final": lines[a]["resolved"],
                "compactions": compaction_pres(rows[a]),
                "peak_context": lines[a]["peak_context"],
                "gave_up_unresolved": lines[a]["gave_up_unresolved"]}
            for a in rows}  # fmt: skip
    for a, v in arms.items():
        r = v["resolved_common"]
        v["cost_per_resolved_common"] = round(cost[a] / r, 4) if r else None
    total = (round(lines[TREATED]["cost_usd"] / lines[CONTROL]["cost_usd"], 4)
             if finished and lines[CONTROL]["cost_usd"] else None)  # fmt: skip
    return {"common_calls": k, "graded_common": graded, "common_bugs": len(pairs),
            "ratio": round(cost[TREATED] / cost[CONTROL], 4) if cost[CONTROL] else None,
            "ratio_whole_runs": total, "arms": arms, "pairs": pairs}


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
    counted = {c: v for c, v in found.items()
               if v["common_calls"] >= MIN_COMMON and v["ratio"] and v["pairs"]}  # fmt: skip
    pairs = [(v["arms"][TREATED]["cost_common"], v["arms"][CONTROL]["cost_common"])
             for v in counted.values()]  # fmt: skip
    cost = long_report.cost_ratio(pairs)
    clusters = [v["pairs"] for v in counted.values()]
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


# ---- the grade at the common calls (Docker, free) ------------------------------------------------


def grade_common(root: Path, chain: str, known: Mapping[str, Any]) -> list[str]:
    """Each arm graded at its snapshot after the last common call, beside its evidence."""
    import long_run
    import perbug

    base = root / "runs" / f"{chain}-{MODEL}"
    rows = {a: _json(base / a / "row.json") for a in (TREATED, CONTROL)}
    if any(r is None for r in rows.values()):
        return []
    k = common_calls(rows[TREATED], rows[CONTROL])
    done = []
    for arm, row in rows.items():
        snapshot = base / arm / f"diff-{k}.patch"
        if k < 1 or not snapshot.exists():
            continue
        asked = long_run.with_control(known[chain], row["token"], row["bugs"])
        result = {**perbug.grade(asked, snapshot.read_text(encoding="utf-8")),
                  "common_calls": k, "snapshot": snapshot.name}  # fmt: skip
        (base / arm / COMMON_GRADE).write_text(json.dumps(result, indent=1), encoding="utf-8")
        done.append(f"{chain} {arm}: graded at call {k}, {result.get('resolved')} resolved")
    return done


def default_chains() -> list[str]:
    import long_run

    return [*long_run.PROFILES["compact"].chains, *long_run.PROFILES["compact-extra"].chains]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("grade", "read"))
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--chains", default="", help="comma-separated; default compact + extra")
    parser.add_argument("--json", default="")
    args = parser.parse_args(argv)
    chains = [c for c in args.chains.split(",") if c] or default_chains()
    if args.action == "grade":
        import run

        known = run.chains()
        for chain in chains:
            for line in grade_common(Path(args.root), chain, known):
                print(line, flush=True)
        return 0
    data = read(Path(args.root), chains)
    text = json.dumps(data, indent=1)
    print(text)
    if args.json:
        Path(args.json).write_text(text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
