"""The verdict of lot jev114-redundant-drop, free: `drop-scored.jsonl` in, `analysis.json` out.

    python benchmarks/jev114/redundant_drop_analysis.py

The rule is docs/results/2026-10-16-redundant-drop/prereg.md:

1. Derivation (rule D of the recalibration): `thresholds.derive` at a 90 % target on the 95 %
   Wilson lower bound, on the calibration part (retrieval-c plus the 15 calibration scenarios),
   for each arm. 1.14's is the candidate `adds_nothing`; 1.13's is descriptive (it keeps 0.59).
2. Stability: the derivation re-run without each calibration case in turn. It "does not hinge on
   one page" when every one of those cuts is reachable and they span at most 0.05.
3. Evaluation part (retrieval, retrieval-b and the 30 evaluation scenarios): right decisions of
   1.14 at its derived cut against 1.13 at 0.59, exact McNemar and a 95 % paired bootstrap over
   clusters (cases sharing a `known`); `jev114_paired.verdict` on that interval.
4. Guards: on the 50 hand-written evaluation cases alone the same comparison is not "peor", and
   1.14 drops at most two more `keep` pages of the evaluation part than 1.13.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(HERE))

import jev114_paired as paired  # noqa: E402
import l4_stats  # noqa: E402
import lot as lots  # noqa: E402
import thresholds  # noqa: E402

from sanchopanza.policy import Thresholds  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-10-16-redundant-drop"
ROWS = OUT / "drop-scored.jsonl"
TARGET = 0.90
SPAN = 0.05
COSTLY_GAP = 2
SHIPPED_13 = Thresholds().adds_nothing  # 0.59
PROFILE_14 = Thresholds.for_model("jev-1.14.0").adds_nothing  # 0.61, what this lot re-derives
POINT = "redundant_page"


def derive(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    usable = [{"expected": r["expected"], "probability": r[f"p_{arm}"]}
              for r in rows if r[f"p_{arm}"] is not None]  # fmt: skip
    return thresholds.derive(usable, POINT, TARGET)


def leave_one_out(rows: Sequence[Mapping[str, Any]], arm: str) -> dict[str, Any]:
    cuts = {r["id"]: derive([x for x in rows if x is not r], arm) for r in rows}
    reached = [c for c in cuts.values() if c is not None]
    unreachable = sorted(i for i, c in cuts.items() if c is None)
    span = round(max(reached) - min(reached), 2) if reached else None
    moved = {i: c for i, c in cuts.items() if c != derive(rows, arm)}
    return {"min": min(reached, default=None), "max": max(reached, default=None), "span": span,
            "unreachable_without": unreachable, "cases_that_move_it": dict(sorted(moved.items())),
            "stable": not unreachable and span is not None and span <= SPAN}  # fmt: skip


def drops(p: float, cut: float) -> bool:
    return p >= cut


def right(row: Mapping[str, Any], arm: str, cut: float) -> bool:
    return drops(row[f"p_{arm}"], cut) == (row["expected"] == "drop")


def acts(rows: Sequence[Mapping[str, Any]], arm: str, cut: float) -> dict[str, Any]:
    dropped = [r for r in rows if drops(r[f"p_{arm}"], cut)]
    positives = sum(r["expected"] == "drop" for r in rows)
    hits = sum(r["expected"] == "drop" for r in dropped)
    return {"cut": cut, "right": sum(right(r, arm, cut) for r in rows), "n": len(rows),
            "drops": len(dropped), "costly_drops": len(dropped) - hits,
            "precision": round(hits / len(dropped), 4) if dropped else None,
            "recall": round(hits / positives, 4) if positives else None}  # fmt: skip


def compare(rows: Sequence[Mapping[str, Any]], c13: float, c14: float) -> dict[str, Any]:
    new = [right(r, "14", c14) for r in rows]
    old = [right(r, "13r", c13) for r in rows]
    result = l4_stats.paired_binary(new, old, [r["cluster"] for r in rows])
    ci = result.get("ci95_cluster")
    result["verdict"] = (
        "no medido" if ci is None else paired.verdict(result["diff"], ci[0], ci[1], result["p"])
    )
    return result


def by_family(rows: Sequence[Mapping[str, Any]], c13: float, c14: float) -> dict[str, Any]:
    out = {}
    for family in sorted({r["family"] for r in rows}):
        part = [r for r in rows if r["family"] == family]
        out[family] = {"n": len(part), "13r": sum(right(r, "13r", c13) for r in part),
                       "14": sum(right(r, "14", c14) for r in part)}  # fmt: skip
    return out


def decision(cut14: float | None, stability: Mapping[str, Any], pooled: Mapping[str, Any],
             hand: Mapping[str, Any], costly_ok: bool) -> dict[str, Any]:  # fmt: skip
    reasons = []
    if cut14 is None:
        reasons.append("the 90 % derivation is unreachable on 1.14")
    if not stability["stable"]:
        reasons.append("the derivation hinges on single cases")
    if pooled.get("verdict") not in ("no peor", "mejora"):
        reasons.append(f"pooled evaluation is {pooled.get('verdict')}")
    if hand.get("verdict") == "peor":
        reasons.append("the 50 hand-written evaluation cases are peor")
    if not costly_ok:
        reasons.append("1.14 drops more than two extra keep pages")
    return {"propose_adds_nothing_14": None if reasons else cut14, "reasons_not": reasons}


def analyse(all_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [r for r in all_rows if r["p_13r"] is not None and r["p_14"] is not None]
    cal = [r for r in rows if r["half"] == "cal"]
    ev = [r for r in rows if r["half"] == "ev"]
    hand_ev = [r for r in ev if r["file"] != "generated"]
    cut14, cut13 = derive(cal, "14"), derive(cal, "13r")
    stability = leave_one_out(cal, "14")
    used14 = PROFILE_14 if cut14 is None else cut14
    pooled = compare(ev, SHIPPED_13, used14)
    hand = compare(hand_ev, SHIPPED_13, used14)
    a13, a14 = acts(ev, "13r", SHIPPED_13), acts(ev, "14", used14)
    costly_ok = a14["costly_drops"] <= a13["costly_drops"] + COSTLY_GAP
    old_cal = [r for r in cal if r["file"] != "generated"]
    return {
        "n": len(all_rows),
        "answered_by_both": len(rows),
        "parts": {"cal": len(cal), "ev": len(ev), "hand_ev": len(hand_ev)},
        "cuts": {
            "13r_shipped": SHIPPED_13,
            "14_profile": PROFILE_14,
            "14_derived": cut14,
            "13r_derived": cut13,
            "14_used": used14,
        },  # fmt: skip
        "stability_14": stability,
        "stability_13r": leave_one_out(cal, "13r"),
        "evaluation": {
            "13r": a13,
            "14": a14,
            "pooled": pooled,
            "hand_written": hand,
            "costly_guard_holds": costly_ok,
        },  # fmt: skip
        "decision": decision(cut14, stability, pooled, hand, costly_ok),
        "descriptive": {
            "derived_on_retrieval_c_only": {
                "14": derive(old_cal, "14"),
                "13r": derive(old_cal, "13r"),
            },  # fmt: skip
            "14_at_its_profile_cut": {
                "arm": acts(ev, "14", PROFILE_14),
                "against_13r": compare(ev, SHIPPED_13, PROFILE_14),
            },  # fmt: skip
            "by_family_ev": by_family(ev, SHIPPED_13, used14),
        },
    }


def main() -> int:
    rows = [json.loads(x) for x in ROWS.read_text(encoding="utf-8").splitlines() if x.strip()]
    result = analyse(rows)
    ev = [r for r in rows if r["half"] == "ev" and r["p_13r"] is not None and r["p_14"] is not None]
    result["descriptive"]["auc_drop_ev"] = lots.paired_auc(
        [r["expected"] == "drop" for r in ev],
        [r["p_14"] for r in ev],
        [r["p_13r"] for r in ev],
        [r["cluster"] for r in ev],
    )
    (OUT / "analysis.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"cuts": result["cuts"], "stable": result["stability_14"]["stable"],
                      "pooled": result["evaluation"]["pooled"]["verdict"],
                      "decision": result["decision"]}))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
