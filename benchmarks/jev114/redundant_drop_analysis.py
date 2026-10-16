"""The verdict of lot jev114-redundant-drop, free: `drop-scored.jsonl` in, `analysis.json` out.

    python benchmarks/jev114/redundant_drop_analysis.py
    python benchmarks/jev114/redundant_drop_analysis.py --power   # the registration's figures

The rule is docs/results/2026-10-16-redundant-drop/prereg.md:

1. Derivation (rule D of the recalibration): `thresholds.derive` at a 90 % target on the 95 %
   Wilson lower bound, on the calibration part (retrieval-c plus the 15 calibration records),
   for each arm. 1.14's is the candidate `adds_nothing`; 1.13's is descriptive (it keeps 0.59).
   The target precision is met on that mix, not on hand-written pages alone.
2. Stability: the derivation re-run without each calibration case in turn. It "does not hinge on
   one page" when every one of those cuts is reachable and they span at most 0.05.
3. Primary, stratified: right decisions of 1.14 at its derived cut minus 1.13 at 0.59, the mean
   of the hand-written stratum (retrieval + retrieval-b, 50) and the template stratum (the 30
   evaluation records, 270), equal weights. 95 % interval by a stratified bootstrap: events in
   the hand stratum, records and families crossed in the template stratum. `lot_stats.verdict_of`.
4. Hand-written stratum: a count guard. 1.14 loses at most one more case than it wins there,
   and catches at least as many of its 18 `drop` pages as 1.13. (Its own interval verdict is
   reported, not required: on 50 cases "no peor" would demand agreement on all 50.)
5. Costly drops: 1.14 drops at most two more `keep` pages of the evaluation part than 1.13.
6. No verdict unless the last launch completed; no proposal when more than 2 % of the cases lack
   an answer from either arm, or 1.14 leaves 2 points more unanswered than 1.13.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(HERE))

import l4_stats  # noqa: E402
import lot_stats  # noqa: E402
import thresholds  # noqa: E402

from sanchopanza.policy import Thresholds  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-10-16-redundant-drop"
ROWS = OUT / "drop-scored.jsonl"
TARGET = 0.90
SPAN = 0.05
COSTLY_GAP = 2
NET_LOSS = 1  # hand-written: losses minus wins of 1.14 at most this
SHIPPED_13 = Thresholds().adds_nothing  # 0.59
PROFILE_14 = Thresholds.for_model("jev-1.14.0").adds_nothing  # 0.61, what this lot re-derives
POINT = "redundant_page"
BOOT, BOOT_SEED = l4_stats.BOOT, l4_stats.BOOT_SEED


def derive(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    usable = [{"expected": r["expected"], "probability": r[f"p_{arm}"]}
              for r in rows if r[f"p_{arm}"] is not None]  # fmt: skip
    return thresholds.derive(usable, POINT, TARGET)


def leave_one_out(rows: Sequence[Mapping[str, Any]], arm: str) -> dict[str, Any]:
    whole = derive(rows, arm)
    cuts = {r["id"]: derive([x for x in rows if x is not r], arm) for r in rows}
    reached = [c for c in cuts.values() if c is not None]
    unreachable = sorted(i for i, c in cuts.items() if c is None)
    span = round(max(reached) - min(reached), 2) if reached else None
    moved = {i: c for i, c in cuts.items() if c != whole}
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
            "drops": len(dropped), "hits": hits, "costly_drops": len(dropped) - hits,
            "precision": round(hits / len(dropped), 4) if dropped else None,
            "recall": round(hits / positives, 4) if positives else None}  # fmt: skip


def deltas(rows: Sequence[Mapping[str, Any]], c13: float, c14: float) -> list[int]:
    """Per case: +1 when only 1.14 is right, -1 when only 1.13 is, else 0."""
    return [int(right(r, "14", c14)) - int(right(r, "13r", c13)) for r in rows]


def _mean(values: Sequence[float], weights: Sequence[float]) -> float:
    total = sum(weights)
    return sum(v * w for v, w in zip(values, weights, strict=True)) / total if total else 0.0


def _counts(keys: Sequence[str], rng: random.Random) -> dict[str, int]:
    picked: dict[str, int] = {}
    distinct = sorted(set(keys))
    for _ in distinct:
        k = distinct[rng.randrange(len(distinct))]
        picked[k] = picked.get(k, 0) + 1
    return picked


def stratified(
    hand: Sequence[Mapping[str, Any]], tmpl: Sequence[Mapping[str, Any]], c13: float, c14: float,
    *, replicas: int = BOOT, seed: int = BOOT_SEED,
) -> dict[str, Any]:  # fmt: skip
    """Equal-weight mean of the two strata's differences, with its 95 % interval: events
    resampled in the hand stratum; records and families resampled independently in the template
    stratum, each case weighted by how often its record times its family was drawn."""
    dh, dt = deltas(hand, c13, c14), deltas(tmpl, c13, c14)
    observed = 0.5 * _mean(dh, [1] * len(dh)) + 0.5 * _mean(dt, [1] * len(dt))
    rng, values = random.Random(seed), []
    events = [r["cluster"] for r in hand]
    records, families = [r["scenario"] for r in tmpl], [r["family"] for r in tmpl]
    for _ in range(replicas):
        ce, cs, cf = _counts(events, rng), _counts(records, rng), _counts(families, rng)
        wh = [ce.get(e, 0) for e in events]
        wt = [cs.get(s, 0) * cf.get(f, 0) for s, f in zip(records, families, strict=True)]
        if sum(wh) and sum(wt):
            values.append(0.5 * _mean(dh, wh) + 0.5 * _mean(dt, wt))
    ci = l4_stats.ci95(values)
    wins = sum(d > 0 for d in dh + dt)
    losses = sum(d < 0 for d in dh + dt)
    p = l4_stats.mcnemar_exact(wins, losses)
    return {"diff": round(observed, 4), "ci95": ci, "p_unclustered": round(p, 4),
            "hand_diff": round(_mean(dh, [1] * len(dh)), 4) if dh else None,
            "template_diff": round(_mean(dt, [1] * len(dt)), 4) if dt else None,
            "verdict": lot_stats.verdict_of(observed, ci, p)}  # fmt: skip


def hand_stratum(rows: Sequence[Mapping[str, Any]], c13: float, c14: float) -> dict[str, Any]:
    new = [right(r, "14", c14) for r in rows]
    old = [right(r, "13r", c13) for r in rows]
    result = l4_stats.paired_binary(new, old, [r["cluster"] for r in rows])
    result["verdict"] = lot_stats.verdict_of(result.get("diff"), result.get("ci95_cluster"),
                                             result.get("p", 1.0))  # fmt: skip
    drop_rows = [r for r in rows if r["expected"] == "drop"]
    hits = {arm: sum(drops(r[f"p_{arm}"], c) for r in drop_rows)
            for arm, c in (("13r", c13), ("14", c14))}  # fmt: skip
    net_loss = result.get("only_old", 0) - result.get("only_new", 0)
    result.update({"drop_pages": len(drop_rows), "drop_hits": hits, "net_loss": net_loss,
                   "count_guard": net_loss <= NET_LOSS and hits["14"] >= hits["13r"]})  # fmt: skip
    return result


def by_family(rows: Sequence[Mapping[str, Any]], c13: float, c14: float) -> dict[str, Any]:
    out = {}
    for family in sorted({r["family"] for r in rows}):
        part = [r for r in rows if r["family"] == family]
        out[family] = {"13r": acts(part, "13r", c13), "14": acts(part, "14", c14)}
    return out


def decision(checks: Mapping[str, bool], cut14: float | None) -> dict[str, Any]:
    reasons = [name for name, ok in checks.items() if not ok]
    return {"propose_adds_nothing_14": None if reasons else cut14, "failed_checks": reasons}


def analyse(all_rows: Sequence[Mapping[str, Any]], launch: str | None = None) -> dict[str, Any]:
    launch = lot_stats.launch_status(OUT) if launch is None else launch
    gaps = lot_stats.answer_gaps(all_rows)
    rows = [r for r in all_rows if r["p_13r"] is not None and r["p_14"] is not None]
    hand = lambda r: r["file"] != "generated"  # noqa: E731
    cal = [r for r in rows if r["half"] == "cal"]
    ev = [r for r in rows if r["half"] == "ev"]
    ev_hand, ev_tmpl = [r for r in ev if hand(r)], [r for r in ev if not hand(r)]
    cut14, cut13 = derive(cal, "14"), derive(cal, "13r")
    stability = leave_one_out(cal, "14")
    used14 = PROFILE_14 if cut14 is None else cut14
    primary = stratified(ev_hand, ev_tmpl, SHIPPED_13, used14)
    strat_h = hand_stratum(ev_hand, SHIPPED_13, used14)
    a13, a14 = acts(ev, "13r", SHIPPED_13), acts(ev, "14", used14)
    checks = {
        "last launch complete": launch == "complete",
        "answers: union <= 2 %, 1.14 gap <= 2 points": lot_stats.gaps_allow_favourable(gaps),
        "derivation reachable on 1.14": cut14 is not None,
        "derivation stable": stability["stable"],
        "primary no peor or mejora": primary["verdict"] in lot_stats.FAVOURABLE,
        "hand count guard": strat_h["count_guard"],
        "costly drops guard": a14["costly_drops"] <= a13["costly_drops"] + COSTLY_GAP,
    }
    cal_hand = [r for r in cal if hand(r)]
    return {
        "launch": launch,
        "n": len(all_rows),
        "answered_by_both": len(rows),
        "answers": gaps,
        "parts": {"cal": len(cal), "ev_hand": len(ev_hand), "ev_template": len(ev_tmpl)},
        "cuts": {
            "13r_shipped": SHIPPED_13,
            "14_profile": PROFILE_14,
            "14_derived": cut14,
            "13r_derived": cut13,
            "14_used": used14,
        },  # fmt: skip
        "stability_14": stability,
        "stability_13r": leave_one_out(cal, "13r"),
        "primary_stratified": primary,
        "hand_stratum": strat_h,
        "evaluation": {"13r": a13, "14": a14},
        "checks": checks,
        "decision": decision(checks, cut14),
        "descriptive": {
            "derived_on_retrieval_c_only": {
                "14": derive(cal_hand, "14"),
                "13r": derive(cal_hand, "13r"),
            },  # fmt: skip
            "derived_on_templates_only": {
                "14": derive([r for r in cal if not hand(r)], "14"),
                "13r": derive([r for r in cal if not hand(r)], "13r"),
            },  # fmt: skip
            "hand_written_at_used_cuts": {
                "calibration": {
                    "13r": acts(cal_hand, "13r", SHIPPED_13),
                    "14": acts(cal_hand, "14", used14),
                },  # fmt: skip
                "evaluation": {
                    "13r": acts(ev_hand, "13r", SHIPPED_13),
                    "14": acts(ev_hand, "14", used14),
                },  # fmt: skip
            },
            "14_at_its_profile_cut": stratified(ev_hand, ev_tmpl, SHIPPED_13, PROFILE_14),
            "by_family_all_cases": by_family(rows, SHIPPED_13, used14),
        },
    }


# --- the registration's figures for the hand stratum (free) ----------------------------------


def hand_power(
    clusters: Sequence[str], patterns: Sequence[tuple[int, int]], *, placements: int = 200,
    replicas: int = 2000, seed: int = 20261016, drop: Sequence[bool] | None = None,
) -> list[dict[str, Any]]:  # fmt: skip
    """For each (wins, losses) of 1.14 on the hand-written evaluation cases, placed at random
    among them: how often the hand stratum's own interval reads each verdict (event-cluster
    bootstrap; descriptive now), and how often the count guard holds (`drop` marks the drop
    pages: a win there is a drop only 1.14 catches, a loss one only 1.13 catches)."""
    rng = random.Random(seed)
    drop = [False] * len(clusters) if drop is None else list(drop)
    out = []
    for wins, losses in patterns:
        tally: dict[str, int] = {}
        guard = 0
        for _ in range(placements):
            chosen = rng.sample(range(len(clusters)), wins + losses)
            new, old = [True] * len(clusters), [True] * len(clusters)
            for i in chosen[:wins]:
                old[i] = False
            for i in chosen[wins:]:
                new[i] = False
            ci = _cluster_ci(new, old, clusters, replicas, rng)
            diff = (wins - losses) / len(clusters)
            p = l4_stats.mcnemar_exact(wins, losses)
            found = lot_stats.verdict_of(diff, ci, p)
            tally[found] = tally.get(found, 0) + 1
            hits = sum(drop[i] for i in chosen[:wins]) - sum(drop[i] for i in chosen[wins:])
            guard += losses - wins <= NET_LOSS and hits >= 0
        shares = {k: round(v / placements, 3) for k, v in sorted(tally.items())}
        out.append({"wins": wins, "losses": losses, "verdicts": shares,
                    "count_guard_holds": round(guard / placements, 3)})  # fmt: skip
    return out


def _cluster_ci(new: Sequence[bool], old: Sequence[bool], clusters: Sequence[str], replicas: int,
                rng: random.Random) -> tuple[float, float]:  # fmt: skip
    groups: dict[str, list[int]] = {}
    for i, key in enumerate(clusters):
        groups.setdefault(key, []).append(i)
    units, diffs = list(groups.values()), []
    for _ in range(replicas):
        idx = [i for _ in units for i in units[rng.randrange(len(units))]]
        diffs.append(sum(new[i] - old[i] for i in idx) / len(idx))
    return l4_stats.ci95(diffs)


def power(hand: Callable[[], tuple[Sequence[str], Sequence[bool]]]) -> list[dict[str, Any]]:
    patterns = ((0, 0), (1, 1), (2, 2), (3, 3), (5, 5), (0, 1), (0, 2), (0, 4), (1, 3), (2, 0))
    clusters, drop = hand()
    return hand_power(clusters, patterns, drop=drop)


def _hand_ev() -> tuple[list[str], list[bool]]:
    import redundant_drop

    ev = [c for c in redundant_drop.old_cases() if c["half"] == "ev"]
    return [redundant_drop.cluster_of(c) for c in ev], [c["expected"] == "drop" for c in ev]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--power", action="store_true")
    args = parser.parse_args()
    if args.power:
        for row in power(_hand_ev):
            print(json.dumps(row), flush=True)
        return 0
    rows = [json.loads(x) for x in ROWS.read_text(encoding="utf-8").splitlines() if x.strip()]
    result = analyse(rows)
    ev = [r for r in rows if r["half"] == "ev" and r["p_13r"] is not None and r["p_14"] is not None]
    result["descriptive"]["auc_drop_ev"] = lot_stats.paired_auc(
        [r["expected"] == "drop" for r in ev],
        [r["p_14"] for r in ev],
        [r["p_13r"] for r in ev],
        [r["cluster"] for r in ev],
    )
    (OUT / "analysis.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"cuts": result["cuts"], "primary": result["primary_stratified"]["verdict"],
                      "decision": result["decision"]}))  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
