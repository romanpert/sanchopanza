"""Lot longdoc-free's dev reading: the rules fixed in prereg-dev.md applied to the dev rows, and
what they set for the confirmation. Free: reads public rows only.

    python benchmarks/longdoc_free/dev_read.py    # docs/results/2026-10-16-longdoc-free/dev.json

Inputs (public, no answer text): jev-dev.jsonl (phase J: the gate's p per question),
dev-sonnet-rows.jsonl and dev-haiku-rows.jsonl (the sessions' F1 and cost), and phase J's spend
(`JEV_SPENT`, from its ledger, passed in). Per question a stats row (stats.py): F1 of N, H, H0;
the cost of each; Jev's cost as the phase's spend over its questions (the asker counts calls
per phase, not per question).

What it decides, by rules written before any dev data:
- the cut: `stats.dev_cut` (the lowest of 0.5-0.9 whose covered questions have H - N >= -2 F1
  points), None when none does (then the router is not confirmed: no confirmation is sealed);
- n for the confirmation: 80 % power for R - N against -5 at one-sided 2.5 %, with the dev's
  SD of the per-question difference, the design effect of its novel clusters (at least 1), and
  the dev's R - N as the true difference (at most 0: a dev gain is not banked); refused (no seal
  on En.QA) when above the 310 confirmation questions;
- the confirmation's money: each arm's mean and 95th-percentile session cost, Jev's settled
  cost over the dry run's pessimistic estimate.
Reported, not decided: HC's mean F1 (what is answered from memory), median answer words and the
share of replies with an ANSWER line per arm, the gate's coverage at each cut, gold in the kept
passages.
"""

from __future__ import annotations

import importlib.util
import json
import math
import statistics
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _load(name: str, path: Path) -> Any:
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


stats = _load("lf_stats", HERE / "stats.py")

Z_ALPHA = 1.959964  # one-sided 2.5 %
Z_POWER = 0.841621  # 80 %
CONFIRM_ITEMS = 310
ARMS = ("N", "H", "H0")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def by_variant(sessions: Sequence[Mapping[str, Any]]) -> dict[tuple[int, str], Mapping[str, Any]]:
    return {(int(r["id"]), r["variant"]): r for r in sessions}


def stats_rows(jev: Sequence[Mapping[str, Any]], sessions: Sequence[Mapping[str, Any]],
               jev_spent: float) -> list[dict[str, Any]]:  # fmt: skip
    """One row per question with every arm present; a question missing an arm is left out (and
    counted by `missing`)."""
    got = by_variant(sessions)
    j_each = jev_spent / len(jev) if jev else 0.0
    out = []
    for row in jev:
        item = int(row["id"])
        arms = {arm: got.get((item, arm)) for arm in ARMS}
        if any(a is None for a in arms.values()):
            continue
        out.append(
            {
                "id": item,
                "novel": row["novel"],
                "p": row["p"],
                "f1": {arm: float(arms[arm]["f1"] or 0.0) for arm in ARMS},
                "cost": {**{arm: float(arms[arm]["usd"]) for arm in ARMS}, "J": j_each},
            }
        )
    return out


def design_effect(rows: Sequence[Mapping[str, Any]], diff: Any) -> float:
    """Var of the mean by novel clusters over the iid variance, at least 1."""
    values = [diff(r) for r in rows]
    n = len(values)
    if n < 2:
        return 1.0
    mean = statistics.fmean(values)
    iid = statistics.variance(values) / n
    groups = stats.by_novel(rows)
    k = len(groups)
    if k < 2 or iid == 0:
        return 1.0
    totals = [sum(diff(r) - mean for r in g) for g in groups]
    clustered = k / (k - 1) * sum(t * t for t in totals) / (n * n)
    return max(1.0, clustered / iid)


def n_needed(sd: float, deff: float, true_diff: float, margin: float = stats.MARGIN) -> int:
    """80 % power at one-sided 2.5 % for diff > margin; sd, true_diff and margin in points."""
    gap = min(true_diff, 0.0) - margin
    if gap <= 0:
        return 10**9
    return math.ceil(deff * (sd * (Z_ALPHA + Z_POWER) / gap) ** 2)


def percentile(values: Sequence[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def session_money(sessions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out = {}
    for arm in sorted({r["variant"] for r in sessions}):
        usd = [float(r["usd"]) for r in sessions if r["variant"] == arm]
        out[arm] = {"sessions": len(usd), "mean_usd": round(statistics.fmean(usd), 4),
                    "p95_usd": round(percentile(usd, 0.95), 4), "max_usd": round(max(usd), 4),
                    "hit_cap": sum(bool(r.get("hit_cap")) for r in sessions
                                   if r["variant"] == arm)}  # fmt: skip
    return out


def answer_form(sessions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out = {}
    for arm in sorted({r["variant"] for r in sessions}):
        mine = [r for r in sessions if r["variant"] == arm]
        out[arm] = {
            "median_words": statistics.median(int(r.get("answer_words") or 0) for r in mine),
            "answer_line_share": round(
                sum(bool(r.get("has_answer_line")) for r in mine) / len(mine), 3
            ),
            "no_answer": sum(bool(r.get("no_answer")) for r in mine),
            "mean_f1": round(100 * statistics.fmean(float(r.get("f1") or 0) for r in mine), 2),
        }
    return out


def read(jev: Sequence[Mapping[str, Any]], sessions: Sequence[Mapping[str, Any]],
         jev_spent: float, jev_pessimistic: float) -> dict[str, Any]:  # fmt: skip
    rows = stats_rows(jev, sessions, jev_spent)
    cut = stats.dev_cut(rows)
    out: dict[str, Any] = {
        "questions": len(jev),
        "complete": len(rows),
        "missing": len(jev) - len(rows),
        "coverage_by_cut": {str(c): round(stats.coverage(rows, c), 3) for c in stats.CUTS},
        "gold_in_kept": sum(bool(r.get("gold_in_kept")) for r in jev),
        "cut": cut,
        "money": session_money(sessions),
        "jev": {
            "spent_usd": round(jev_spent, 4),
            "pessimistic_usd": round(jev_pessimistic, 4),
            "settled_over_pessimistic": round(jev_spent / jev_pessimistic, 4)
            if jev_pessimistic
            else None,
        },  # fmt: skip
        "answers": answer_form(sessions),
    }
    if cut is None:
        out["n_needed"] = None
        out["seal_confirmation"] = False
        out["why"] = "no cut meets the dev rule: the router is not confirmed"
        return out

    def diff(r: Mapping[str, Any]) -> float:
        return 100.0 * (stats.router_f1(r, cut) - r["f1"]["N"])

    values = [diff(r) for r in rows]
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    deff = design_effect(rows, diff)
    observed = statistics.fmean(values) if values else 0.0
    n = n_needed(sd, deff, observed)
    out.update({"router_minus_n": round(observed, 2), "sd_points": round(sd, 2),
                "design_effect": round(deff, 3), "n_needed": n,
                "seal_confirmation": n <= CONFIRM_ITEMS,
                "saving": round(stats.saving(cut)(rows), 4) if rows else None})  # fmt: skip
    if n > CONFIRM_ITEMS:
        out["why"] = f"{n} questions needed, {CONFIRM_ITEMS} left: not sealed on En.QA alone"
    return out


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jev-spent", type=float, required=True, help="phase J's settled USD")
    ap.add_argument("--jev-pessimistic", type=float, required=True, help="its dry-run estimate")
    args = ap.parse_args(argv)
    lot_dir = HERE.parents[1] / "docs" / "results" / "2026-10-16-longdoc-free"
    sessions = [*read_jsonl(lot_dir / "dev-sonnet-rows.jsonl"),
                *read_jsonl(lot_dir / "dev-haiku-rows.jsonl")]  # fmt: skip
    got = read(read_jsonl(lot_dir / "jev-dev.jsonl"), sessions, args.jev_spent,
               args.jev_pessimistic)  # fmt: skip
    (lot_dir / "dev.json").write_text(json.dumps(got, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(got, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
