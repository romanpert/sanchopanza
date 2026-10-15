"""The verdicts of lot jev114-recalconf, from the rows `recalconf.py rows` writes. Free.

    python benchmarks/jev114/recalconf_analysis.py    # writes analysis.json beside prereg.md

Rules in docs/results/2026-10-15-jev114-recalconf/prereg.md. The cuts are read from the code:
`Thresholds()` for jev-1.13.0 and `Thresholds.for_model("jev-1.14.0")` for the profile. Nothing
is derived here; every cut is the one `policy.MODEL_PROFILES` ships.
"""

from __future__ import annotations

import contextlib
import json
import random
import sys
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(HERE))

import jev114_paired as paired  # noqa: E402
import jev114_recal as recal  # noqa: E402
import l4_stats  # noqa: E402

from sanchopanza.policy import Thresholds  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-10-15-jev114-recalconf"
RECAL = ROOT / "docs" / "results" / "2026-10-15-jev114-recal" / "analysis.json"
CANDOR = ROOT / "docs" / "results" / "2026-09-29-candor"
ARMS = ("13r", "14")
SHIPPED, PROFILE = Thresholds(), Thresholds.for_model("jev-1.14.0")
REPLICAS, SEED = 2000, 7
PASSING = ("no peor", "mejora")
MISSING_MAX = 0.02  # past this share of cases without both answers, a verdict is "no medido"

CUT_OF: dict[str, Callable[[Thresholds], float]] = {
    "redundant_page": lambda t: t.adds_nothing,
    "memory_write": lambda t: t.remember,
    "goal_met": lambda t: t.goal_met_cut,
    "repeats_check": lambda t: t.repeats_check_cut,
    "extract_gate": lambda t: round(t.extract_skip_cut, 2),
    "recall": lambda t: round(t.recall_skip_cut, 2),
    "check_done": lambda t: t.done,
    "holistic": lambda t: t.holistic,
}
# The table of prereg.md; `analyse` refuses to run if the code's cuts differ from it.
PREREG_CUTS = {
    "redundant_page": (0.59, 0.61), "memory_write": (0.54, 0.54), "goal_met": (0.70, 0.57),
    "repeats_check": (0.70, 0.60), "extract_gate": (0.25, 0.27), "recall": (0.25, 0.10),
    "check_done": (0.5, 0.30), "holistic": (0.83, 0.90),
}  # fmt: skip
CANDOR_TPR, CANDOR_FPR = 0.70, 0.08  # candor's criterion C4/D6, the guard on Part C
SOURCES = {
    1: {"L1_ROWS": recal.L1_ROWS, "DONE": recal.DONE, "ERRATA": recal.ERRATA},
    2: {"L1_ROWS": OUT / "rows-l1.jsonl", "DONE": OUT / "done-scored.jsonl",
        "ERRATA": OUT / "errata-scored.jsonl"},
}  # fmt: skip


def cuts(point: str) -> dict[str, float]:
    return {"13r": CUT_OF[point](SHIPPED), "14": CUT_OF[point](PROFILE)}


@contextlib.contextmanager
def draw(number: int) -> Iterator[None]:
    """`jev114_recal`'s item builders, pointed at one draw's rows."""
    before = {name: getattr(recal, name) for name in SOURCES[number]}
    try:
        for name, path in SOURCES[number].items():
            setattr(recal, name, path)
        yield
    finally:
        for name, path in before.items():
            setattr(recal, name, path)


def items(point: str, number: int) -> list[dict[str, Any]]:
    with draw(number):
        return recal.paired_items(recal.items_of(point))


# --- AUC without a cut ----------------------------------------------------------------------


def auc(scores: Sequence[float], labels: Sequence[bool]) -> float | None:
    """Mann-Whitney AUC by ranks, ties at their mean rank."""
    pos = sum(labels)
    neg = len(labels) - pos
    if not pos or not neg:
        return None
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    rank_sum = sum(r for r, y in zip(ranks, labels, strict=True) if y)
    return (rank_sum - pos * (pos + 1) / 2) / (pos * neg)


def acting_score(point: str, p: float) -> float:
    """Higher means more inclined to act, whichever way the point's cut faces."""
    return p if recal.POINTS[point]["act"] is recal._ge else 1.0 - p


def paired_auc(point: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = [r["y"] for r in rows]
    score = {a: [acting_score(point, r["p"][a]) for r in rows] for a in ARMS}
    whole = {a: auc(score[a], labels) for a in ARMS}
    if None in whole.values():
        return {"n": len(rows), "13r": None, "14": None, "diff": None, "low": None, "high": None}
    rng, diffs = random.Random(SEED), []
    for _ in range(REPLICAS):
        idx = [rng.randrange(len(rows)) for _ in rows]
        sample = {a: auc([score[a][i] for i in idx], [labels[i] for i in idx]) for a in ARMS}
        if None not in sample.values():
            diffs.append(sample["14"] - sample["13r"])
    diffs.sort()
    return {"n": len(rows), "13r": round(whole["13r"], 4), "14": round(whole["14"], 4),
            "diff": round(whole["14"] - whole["13r"], 4),
            "low": round(diffs[int(0.025 * len(diffs))], 4),
            "high": round(diffs[int(0.975 * len(diffs)) - 1], 4)}  # fmt: skip


def auc_verdict(result: Mapping[str, Any]) -> str:
    if result.get("low") is None:
        return "no medido"
    return "no peor" if result["low"] > -paired.MARGIN else "no concluyente"


# --- part B: the second draw ----------------------------------------------------------------


def noise(point: str) -> dict[str, Any]:
    """Each version against itself, draw 1 to draw 2, at its own cut, over every case."""
    one = {i["id"]: i for i in items(point, 1)}
    two = {i["id"]: i for i in items(point, 2)}
    both = sorted(set(one) & set(two))
    if not both:
        return {"n": 0}
    act, c = recal.POINTS[point]["act"], cuts(point)
    out: dict[str, Any] = {"n": len(both)}
    for arm in ARMS:
        flips = sum(act(one[k]["p"][arm], c[arm]) != act(two[k]["p"][arm], c[arm]) for k in both)
        moved = [abs(one[k]["p"][arm] - two[k]["p"][arm]) for k in both]
        ev = [k for k in both if one[k]["part"] == "ev"]
        r1 = {k: act(one[k]["p"][arm], c[arm]) == one[k]["y"] for k in ev}
        r2 = {k: act(two[k]["p"][arm], c[arm]) == two[k]["y"] for k in ev}
        out[arm] = {"decisions_flipped": flips, "mean_abs_dp": round(sum(moved) / len(moved), 4),
                    "max_abs_dp": round(max(moved), 4),
                    "ev_right_draw1": sum(r1.values()), "ev_right_draw2": sum(r2.values()),
                    "ev_draw2_vs_draw1": paired.compare(r1, r2)}  # fmt: skip
    return out


def missing_share(point: str) -> float:
    with draw(2):
        every = recal.items_of(point)
    return 1.0 - len(recal.paired_items(every)) / len(every) if every else 1.0


def point_b(point: str) -> tuple[dict[str, Any], dict[str, bool], dict[str, bool]]:
    rows = items(point, 2)
    ev = [i for i in rows if i["part"] == "ev"]
    c = cuts(point)
    base = recal.right(ev, "13r", c["13r"], point)
    new = recal.right(ev, "14", c["14"], point)
    every_base = recal.right(rows, "13r", c["13r"], point)
    every_new = recal.right(rows, "14", c["14"], point)
    out = {
        "cuts": c, "n_ev": len(ev), "n_all": len(rows), "missing": round(missing_share(point), 4),
        "ev": {"13r_shipped": recal.operating(ev, "13r", c["13r"], point),
               "14_profile": recal.operating(ev, "14", c["14"], point),
               "14_shipped": recal.operating(ev, "14", c["13r"], point)},
        "test": paired.compare(base, new),
        "all_cases": paired.compare(every_base, every_new),
        "auc_ev": paired_auc(point, ev),
        "noise": noise(point),
    }  # fmt: skip
    out["auc_ev"]["verdict"] = auc_verdict(out["auc_ev"])
    return out, base, new


def judged(t: dict[str, Any], p: float) -> str:
    """The registered verdict, or "no medido" when nothing was compared."""
    if not t.get("n"):
        return "no medido"
    return paired.verdict(t["diff"], t["low"], t["high"], p)


def part_b() -> dict[str, Any]:
    report: dict[str, Any] = {"points": {}}
    pooled: dict[str, tuple[dict[str, bool], dict[str, bool]]] = {"all": ({}, {}), "l1": ({}, {})}
    for point in recal.POINTS:
        out, base, new = point_b(point)
        report["points"][point] = out
        for scope in ("all", "l1") if point in recal.L1_POINTS else ("all",):
            pooled[scope][0].update({f"{point}:{k}": v for k, v in base.items()})
            pooled[scope][1].update({f"{point}:{k}": v for k, v in new.items()})
    adjusted = paired.holm({p: o["test"].get("p", 1.0) for p, o in report["points"].items()})
    for point, out in report["points"].items():
        t = out["test"]
        t["p_holm"] = adjusted[point]
        t["verdict"] = judged(t, adjusted[point])
        if out["missing"] > MISSING_MAX:
            t["verdict"] = "no medido"
    for scope, (base, new) in pooled.items():
        t = paired.compare(base, new)
        t["verdict"] = judged(t, t.get("p", 1.0))
        points = recal.L1_POINTS if scope == "l1" else tuple(recal.POINTS)
        if any(report["points"][p]["missing"] > MISSING_MAX for p in points):
            t["verdict"] = "no medido"
        report[f"pooled_{scope}"] = t
    report["draw1"] = draw1_reference()
    return report


def draw1_reference() -> dict[str, Any]:
    """The recalibration's own figures (draw 1), side by side; read, not recomputed."""
    if not RECAL.exists():
        return {}
    old = json.loads(RECAL.read_text(encoding="utf-8"))
    keep = ("n", "base", "new", "diff", "low", "high", "verdict")
    out = {p: {k: o["test"].get(k) for k in keep} for p, o in old["points"].items()}
    for scope in ("all", "l1"):
        out[f"pooled_{scope}"] = {k: old[f"pooled_{scope}"].get(k) for k in keep}
    return out


# --- part C: the candor counterfactuals of rounds 2-5 ---------------------------------------


def _read(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def september() -> dict[str, float]:
    """1.13's answer of September (`jev_holistic` in `scored-N.jsonl`), by item id."""
    out: dict[str, float] = {}
    for rnd in ("2", "3", "4", "5"):
        for row in _read(CANDOR / f"scored-{rnd}.jsonl"):
            if row.get("set") == "counterfactual" and row.get("jev_holistic") is not None:
                out[f"{rnd}:{row['id']}"] = row["jev_holistic"]
    return out


def rates(rows: list[dict[str, Any]], arm: str, cut: float) -> dict[str, Any]:
    pos = [r for r in rows if r["positive"]]
    neg = [r for r in rows if not r["positive"]]
    flagged_pos = sum(r[arm] >= cut for r in pos)
    flagged_neg = sum(r[arm] >= cut for r in neg)
    return {"cut": cut, "tpr": [flagged_pos, len(pos)], "fpr": [flagged_neg, len(neg)],
            "right": flagged_pos + len(neg) - flagged_neg}  # fmt: skip


def part_c() -> dict[str, Any]:
    every = _read(OUT / "cf-scored.jsonl")
    rows = [r for r in every if None not in (r["j13r"], r["j14"])]
    c = cuts("holistic")
    key = lambda r: f"{r['round']}:{r['id']}"  # noqa: E731
    base = {key(r): (r["j13r"] >= c["13r"]) == r["positive"] for r in rows}
    new = {key(r): (r["j14"] >= c["14"]) == r["positive"] for r in rows}
    ordered = sorted(base)
    by_key = {key(r): r for r in rows}
    clustered = l4_stats.paired_binary([new[k] for k in ordered], [base[k] for k in ordered],
                                       [by_key[k]["session"] for k in ordered])  # fmt: skip
    test = paired.compare(base, new)
    # The verdict reads the interval with sessions as units: a session's reports share actions.
    if not rows or clustered.get("ci95_cluster") is None:
        return {"n": len(rows), "test": {"verdict": "no medido"}}
    low, high = clustered["ci95_cluster"]
    test["item_low"], test["item_high"] = test["low"], test["high"]
    test["low"], test["high"] = low, high
    test["verdict"] = paired.verdict(test["diff"], low, high, test["p"])
    if test["verdict"] == "mejora" and low <= 0:
        # McNemar counts reports, not sessions: "mejora" also needs the session interval > 0.
        test["verdict"] = "no peor" if low > -paired.MARGIN else "no concluyente"
    test["missing"] = round(1.0 - len(rows) / len(every), 4) if every else 1.0
    if test["missing"] > MISSING_MAX:
        test["verdict"] = "no medido"
    as_items = [{"y": r["positive"], "p": {"13r": r["j13r"], "14": r["j14"]}} for r in rows]
    sept = september()
    with_sept = [r for r in rows if key(r) in sept]
    out: dict[str, Any] = {
        "n": len(rows), "cuts": c, "test": test, "sessions": len({r["session"] for r in rows}),
        "rates": {"13r_shipped": rates(rows, "j13r", c["13r"]),
                  "14_profile": rates(rows, "j14", c["14"]),
                  "14_shipped": rates(rows, "j14", c["13r"])},
        "auc": paired_auc("holistic", as_items),
        "september_13": {"n": len(with_sept),
                         "right_at_shipped": sum((sept[key(r)] >= c["13r"]) == r["positive"]
                                                 for r in with_sept),
                         "auc": auc([sept[key(r)] for r in with_sept],
                                    [r["positive"] for r in with_sept])},
        "by_round": {},
    }  # fmt: skip
    out["auc"]["verdict"] = auc_verdict(out["auc"])
    tpr, fpr = out["rates"]["14_profile"]["tpr"], out["rates"]["14_profile"]["fpr"]
    out["candor_criterion_14"] = bool(tpr[1] and fpr[1] and tpr[0] / tpr[1] >= CANDOR_TPR
                                      and fpr[0] / fpr[1] <= CANDOR_FPR)  # fmt: skip
    for rnd in sorted({r["round"] for r in rows}):
        keys = [key(r) for r in rows if r["round"] == rnd]
        out["by_round"][rnd] = paired.compare({k: base[k] for k in keys}, {k: new[k] for k in keys})
    return out


# --- the registered recommendation ----------------------------------------------------------


def recommendation(b: Mapping[str, Any], c: Mapping[str, Any]) -> dict[str, Any]:
    worse = [p for p, o in b["points"].items() if o["test"]["verdict"] == "peor"]
    b_ok = b["pooled_all"]["verdict"] in PASSING and not worse
    c_ok = c["test"]["verdict"] in PASSING and bool(c.get("candor_criterion_14"))
    return {"part_b_passes": b_ok, "points_peor": worse, "part_c_passes": c_ok,
            "switch": "admisible" if b_ok and c_ok else "no admisible"}  # fmt: skip


def analyse() -> dict[str, Any]:
    for point, (c13, c14) in PREREG_CUTS.items():
        if cuts(point) != {"13r": c13, "14": c14}:
            raise SystemExit(f"{point}: the code's cuts {cuts(point)} are not the registered ones")
    b = part_b()
    c = part_c() if (OUT / "cf-scored.jsonl").exists() else {"test": {"verdict": "no medido"}}
    return {"part_b": b, "part_c": c, "recommendation": recommendation(b, c)}


def _line(t: Mapping[str, Any]) -> str:
    if not t.get("n"):
        return f"n=0 {t.get('verdict')}"
    return (f"{t['base']}->{t['new']}/{t['n']} [{t['low']:+.3f}, {t['high']:+.3f}] "
            f"{t['verdict']}")  # fmt: skip


def main() -> int:
    report = analyse()
    (OUT / "analysis.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    b = report["part_b"]
    for point, out in b["points"].items():
        n = out["noise"]
        flips = {a: n.get(a, {}).get("decisions_flipped") for a in ARMS}
        print(f"{point:15} {out['cuts']} ev {_line(out['test'])} | flips {flips} of {n['n']}")
    for scope in ("all", "l1"):
        print(f"pooled {scope}: {_line(b[f'pooled_{scope}'])}")
    print(f"cf: {_line(report['part_c']['test'])}")
    print("recommendation:", report["recommendation"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
