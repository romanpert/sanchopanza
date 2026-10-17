"""Lot longdoc-free's dev reading: the rules fixed in prereg-dev.md applied to the dev rows, and
what they set for the confirmation. Free: reads public rows only.

    python benchmarks/longdoc_free/dev_read.py    # docs/results/2026-10-16-longdoc-free/dev.json

Inputs (public, no answer text): jev-dev.jsonl (phase J: the gate's p per question),
dev-sonnet-rows.jsonl and dev-haiku-rows.jsonl (the sessions' F1 and cost), and phase J's spend
(`JEV_SPENT`, from its ledger, passed in). Per question a stats row (stats.py): F1 of N, H, H0;
the cost of each; Jev's cost as the phase's spend over its questions (the asker counts calls
per phase, not per question).

What it decides, by rules written before any dev data:
- whether the dev is read at all: at least MIN_COMPLETE questions with every arm;
- the cut: `stats.dev_cut` (the lowest of 0.5-0.9 covering at least 29 % and 8 questions whose
  covered questions have H - N >= -2 F1 points), None when none does (then the router is not
  confirmed: no confirmation is sealed);
- memory: HC's mean F1 within MEMORY_GAP points of N's means the set measures what Haiku
  remembers, and no confirmation is sealed on it;
- n for the confirmation: 80 % power for R - N against -5 at one-sided 2.5 %, with the dev's
  SD of the per-question difference, the design effect of its novel clusters (at least
  DEFF_FLOOR, since 8 clusters estimate it poorly), and
  the dev's R - N as the true difference (at most 0: a dev gain is not banked); refused (no seal
  on En.QA) when above the 310 confirmation questions;
- the confirmation's money: per Claude phase, CONFIRM_ITEMS sessions per arm at the larger of
  1.5 times the arm's dev mean and its dev 95th percentile, plus one worst turn and the floor;
  Jev fits when the confirmation's dry-run pessimistic estimate is under its 12.50 cap (what
  `paid` requires) and its expected cost (that estimate times the dev's settled over pessimistic
  ratio) times JEV_MARGIN is too. Claude fits when the dev's real spend (every session and open
  reservation of its phases, the smoke included) plus the confirmation's ceilings is at most 105.
  Otherwise the owner decides.
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

MIN_COMPLETE = 35  # of the dev's 41 questions
MEMORY_GAP = 10.0  # F1 points: HC this close to N means the answers come from memory
DEFF_FLOOR = 1.5
CLAUDE_CAP_USD = 105.0
JEV_CONFIRM_CAP_USD = 12.50
JEV_MARGIN = 1.2
WORST_TURN = {"SONNET": 4.32, "HAIKU": 2.16}
FLOOR = {"SONNET": 0.50, "HAIKU": 0.30}
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


def confirm_money(
    money: Mapping[str, Mapping[str, float]],
    dev_claude_usd: float,
    jev_ratio: float | None,
    jev_confirm_pessimistic: float,
) -> dict[str, Any]:
    """The confirmation's ceilings by the registered formula, and whether they fit."""

    def per(arm: str) -> float:
        got = money.get(arm, {})
        return max(1.5 * float(got.get("mean_usd", 0.0)), float(got.get("p95_usd", 0.0)))

    sonnet = CONFIRM_ITEMS * per("N") + WORST_TURN["SONNET"] + FLOOR["SONNET"]
    haiku = CONFIRM_ITEMS * (per("H") + per("H0")) + WORST_TURN["HAIKU"] + FLOOR["HAIKU"]
    expected = jev_confirm_pessimistic * (jev_ratio if jev_ratio is not None else 1.0)
    jev_fits = (jev_confirm_pessimistic <= JEV_CONFIRM_CAP_USD
                and expected * JEV_MARGIN <= JEV_CONFIRM_CAP_USD)  # fmt: skip
    claude_total = dev_claude_usd + sonnet + haiku
    return {"sonnet_ceiling": round(sonnet, 2), "haiku_ceiling": round(haiku, 2),
            "jev_cap": JEV_CONFIRM_CAP_USD, "jev_expected": round(expected, 2),
            "jev_fits": jev_fits, "claude_with_dev": round(claude_total, 2),
            "fits": claude_total <= CLAUDE_CAP_USD and jev_fits}  # fmt: skip


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
            "mean_f1_short": round(
                100 * statistics.fmean(float(r.get("f1_short") or 0) for r in mine), 2
            ),
        }
    return out


def read(jev: Sequence[Mapping[str, Any]], sessions: Sequence[Mapping[str, Any]],
         jev_spent: float, jev_pessimistic: float,
         jev_confirm_pessimistic: float = 12.32,
         dev_claude_usd: float | None = None) -> dict[str, Any]:  # fmt: skip
    rows = stats_rows(jev, sessions, jev_spent)
    complete = len(rows) >= MIN_COMPLETE
    cut = stats.dev_cut(rows) if complete else None
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
    money_now = out["money"]
    dev_claude = (sum(float(r["usd"]) for r in sessions) if dev_claude_usd is None
                  else dev_claude_usd)  # fmt: skip
    ratio = out["jev"]["settled_over_pessimistic"]
    out["confirm_money"] = confirm_money(money_now, dev_claude, ratio, jev_confirm_pessimistic)
    hc = out["answers"].get("HC", {}).get("mean_f1")
    n_f1 = out["answers"].get("N", {}).get("mean_f1")
    memory = hc is not None and n_f1 is not None and hc >= n_f1 - MEMORY_GAP
    out["memory_answers"] = memory
    if not complete:
        why = f"{len(rows)} complete questions, under {MIN_COMPLETE}: the dev is not read"
        out.update({"n_needed": None, "seal_confirmation": False, "why": why})
        return out
    if memory:
        why = f"HC {hc} within {MEMORY_GAP:g} points of N {n_f1}: memory answers"
        out.update({"n_needed": None, "seal_confirmation": False, "why": why})
        return out
    if cut is None:
        out["n_needed"] = None
        out["seal_confirmation"] = False
        out["why"] = "no cut meets the dev rule: the router is not confirmed"
        return out

    def diff(r: Mapping[str, Any]) -> float:
        return 100.0 * (stats.router_f1(r, cut) - r["f1"]["N"])

    values = [diff(r) for r in rows]
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    deff = max(DEFF_FLOOR, design_effect(rows, diff))
    observed = statistics.fmean(values) if values else 0.0
    n = n_needed(sd, deff, observed)
    out.update({"router_minus_n": round(observed, 2), "sd_points": round(sd, 2),
                "design_effect": round(deff, 3), "n_needed": n,
                "seal_confirmation": n <= CONFIRM_ITEMS and out["confirm_money"]["fits"],
                "saving": round(stats.saving(cut)(rows), 4) if rows else None})  # fmt: skip
    if n > CONFIRM_ITEMS:
        out["why"] = f"{n} questions needed, {CONFIRM_ITEMS} left: not sealed on En.QA alone"
    elif not out["confirm_money"]["fits"]:
        out["why"] = "the confirmation's money does not fit the owner's caps: the owner decides"
    return out


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--jev-pessimistic", type=float, default=1.4425, help="dev's dry run")
    ap.add_argument("--jev-confirm-pessimistic", type=float, default=12.3211)
    args = ap.parse_args(argv)
    jev_phase = _load("lf_jev_phase", HERE / "jev_phase.py")
    spent = jev_phase.paid_once.spent(jev_phase.lot("dev"))  # phase J's ledger, settled
    h2h = _load("lf_h2h", HERE.parent / "h2h" / "h2h_lfree.py")
    claude = h2h.stage_spent("dev")  # every session and open reservation, the smoke's too
    lot_dir = HERE.parents[1] / "docs" / "results" / "2026-10-16-longdoc-free"
    sessions = [*read_jsonl(lot_dir / "dev-sonnet-rows.jsonl"),
                *read_jsonl(lot_dir / "dev-haiku-rows.jsonl")]  # fmt: skip
    got = read(read_jsonl(lot_dir / "jev-dev.jsonl"), sessions, spent, args.jev_pessimistic,
               args.jev_confirm_pessimistic, claude)  # fmt: skip
    (lot_dir / "dev.json").write_text(json.dumps(got, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(got, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
