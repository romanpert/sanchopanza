"""A threshold profile for Jev 1.14, recalibrated on the recordings of lots L1, L2 and L4. Free.

    python benchmarks/jev114/jev114_recal.py --extract-done --runs-root PATH   # once, replay
    python benchmarks/jev114/jev114_recal.py                                   # analysis

Pre-registered in docs/results/2026-10-15-jev114-recal/prereg.md (sealed in 671546e, before
any cut was computed on a 1.14 answer). Nothing here calls a model:

- the six L1 points read `docs/results/2026-10-15-jev114-l1/rows/rows-bench.jsonl`;
- check_done reads `done-scored.jsonl`, which `--extract-done` builds once by replaying the L2
  fixtures over the AgentDojo trajectories (`--runs-root` names the checkout that holds the
  untracked `runs/` directories);
- the candor holistic cut reads the L4 `errata-scored.jsonl`.

Rule D re-runs a cut's original derivation (`thresholds.derive`, `memory_write_cut.derive`).
Rule T transfers 1.13's operating point: the strictest cut at which 1.14 acts on at least as
many calibration cases as 1.13 does at its shipped cut. No label is read by T.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import random
import sys
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))
sys.path.insert(0, str(HERE))

import jev114_paired as paired  # noqa: E402
import memory_write_cut  # noqa: E402
import policy_shape  # noqa: E402
import thresholds  # noqa: E402

from sanchopanza.candor.judge import HOLISTIC_CUT  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402

OUT = ROOT / "docs" / "results" / "2026-10-15-jev114-recal"
L1_ROWS = ROOT / "docs" / "results" / "2026-10-15-jev114-l1" / "rows" / "rows-bench.jsonl"
ERRATA = ROOT / "docs" / "results" / "2026-10-15-jev114-l4" / "errata-scored.jsonl"
MEMORY_CUT = ROOT / "docs" / "results" / "2026-09-27-memory-write-cut" / "analysis.json"
DONE = OUT / "done-scored.jsonl"
ARMS = ("13r", "14")
GRID = [round(i / 100, 2) for i in range(1, 100)]
CV_FOLDS, CV_SEEDS = 5, (1, 2, 3, 4, 5)
_T = Thresholds()


def _ge(p: float, c: float) -> bool:
    return p >= c


def _le(p: float, c: float) -> bool:
    return p <= c


def _lt(p: float, c: float) -> bool:
    return p < c


# point -> rule, knob, shipped cut, act(p, cut), strict ("high": a higher cut acts less),
# calibration files, evaluation files, label that means "act", D target.
POINTS: dict[str, dict[str, Any]] = {
    "redundant_page": dict(rule="D", knob="adds_nothing", shipped=_T.adds_nothing, act=_ge,
                           strict="high", cal=("retrieval-c",), ev=("retrieval", "retrieval-b"),
                           label="drop", target=0.90),
    "memory_write": dict(rule="D", knob="remember", shipped=_T.remember, act=_ge, strict="high",
                         cal="A", ev="B+efg", label="store", target=0.80),
    "goal_met": dict(rule="T", knob="goal_met", shipped=_T.saturated, act=_ge, strict="high",
                     cal=("loop-b",), ev=("loop",), label=True, target=0.80),
    "repeats_check": dict(rule="T", knob="repeats_check", shipped=_T.saturated, act=_ge,
                          strict="high", cal=("loop-b",), ev=("loop",), label=True, target=0.80),
    "extract_gate": dict(rule="T", knob="extract_skip", shipped=round(1.0 - _T.act, 2), act=_le,
                         strict="low", cal=("graph-build-b",), ev=("graph-build",), label="skip",
                         target=0.80),
    "recall": dict(rule="T", knob="recall_skip", shipped=round(1.0 - _T.act, 2), act=_le,
                   strict="low", cal=("memory-b",), ev=("memory",), label="skip", target=0.80),
    "check_done": dict(rule="T", knob="done", shipped=_T.done, act=_lt,
                       strict="low", cal="derivation", ev="held_out", label="not_done",
                       target=0.90),
    "holistic": dict(rule="T", knob="holistic", shipped=HOLISTIC_CUT, act=_ge, strict="high",
                     cal=0, ev=1, label=True, target=0.05),
}  # fmt: skip
L1_POINTS = ("redundant_page", "memory_write", "goal_met", "repeats_check", "extract_gate",
             "recall")  # fmt: skip


# --- items: one per case, {"id", "part", "y" (label says act), "p": {arm: float | None}} -----


def _read(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _margin(row: Mapping[str, Any]) -> float | None:
    answers = row["calls"][0]["answers"] if row.get("calls") else {}
    x = [(answers.get(k) or {}).get("truth") for k in ("durable", "specific", "derivable")]
    return None if None in x else policy_shape.margin(x)


def l1_items(point: str) -> list[dict[str, Any]]:
    spec = POINTS[point]
    a_ids = set(json.loads(MEMORY_CUT.read_text(encoding="utf-8"))["split"]["A_ids"])
    by_id: dict[str, dict[str, Any]] = {}
    for row in _read(L1_ROWS):
        if row["point"] != point:
            continue
        if point == "memory_write":
            first = row["file"] in ("memory", "memory-b", "memory-c")
            part = ("cal" if row["id"] in a_ids else "ev") if first else "ev"
            p = _margin(row)
        else:
            in_cal, in_ev = row["file"] in spec["cal"], row["file"] in spec["ev"]
            part = "cal" if in_cal else "ev" if in_ev else None
            p = row.get("probability")
        item = by_id.setdefault(
            row["id"],
            {
                "id": row["id"],
                "part": part,
                "file": row["file"],
                "y": row["expected"] == spec["label"],
                "p": {},
            },
        )
        item["p"][row["arm"]] = p
    return [i for i in by_id.values() if i["part"]]


def done_items() -> list[dict[str, Any]]:
    return [{"id": r["id"], "part": "cal" if r["half"] == "derivation" else "ev",
             "y": r["label"] == "not_done", "p": {a: r[f"p_{a}"] for a in ARMS}}
            for r in _read(DONE)]  # fmt: skip


def errata_half(task: str) -> int:
    return int(hashlib.sha256(f"errata:{task}".encode()).hexdigest()[:8], 16) % 2


def holistic_items() -> list[dict[str, Any]]:
    return [{"id": r["id"], "part": "cal" if errata_half(r["task"]) == 0 else "ev",
             "y": bool(r["positive"]), "p": {"13r": r.get("j13r"), "14": r.get("j14")}}
            for r in _read(ERRATA)]  # fmt: skip


def items_of(point: str) -> list[dict[str, Any]]:
    if point == "check_done":
        return done_items()
    if point == "holistic":
        return holistic_items()
    return l1_items(point)


def paired_items(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cases both arms answered; the others are left out of both."""
    return [i for i in items if all(i["p"].get(a) is not None for a in ARMS)]


# --- the rules -----------------------------------------------------------------------------


def acts_count(ps: Iterable[float], cut: float, act: Callable[[float, float], bool]) -> int:
    return sum(1 for p in ps if act(p, cut))


def transfer(cal: list[dict[str, Any]], point: str) -> float:
    """Rule T: the strictest grid cut at which 14 acts on at least as many cases as 13r does
    at the shipped cut. Labels are not read."""
    spec = POINTS[point]
    n13 = acts_count((i["p"]["13r"] for i in cal), spec["shipped"], spec["act"])
    if n13 == 0:
        return spec["shipped"]
    ok = [c for c in GRID if acts_count((i["p"]["14"] for i in cal), c, spec["act"]) >= n13]
    if not ok:
        return spec["shipped"]
    return max(ok) if spec["strict"] == "high" else min(ok)


def _as_threshold_rows(cal: list[dict[str, Any]], point: str, arm: str) -> list[dict[str, Any]]:
    label = POINTS[point]["label"]
    return [{"point": point, "probability": i["p"][arm], "expected": label if i["y"] else None}
            for i in cal]  # fmt: skip


def derive_target(cal: list[dict[str, Any]], point: str, arm: str) -> float | None:
    """Rule D, the derivation on record for this point, on one arm's answers."""
    spec = POINTS[point]
    if point == "memory_write":
        # `memory_write_cut.stores` reads margin(x) = min(x0, x1, 1 - x2): x = [m, 1, 0] is m.
        rows = [{"x": [i["p"][arm], 1.0, 0.0], "y": i["y"]} for i in cal]
        return memory_write_cut.derive(rows, spec["target"])
    if point in thresholds.ACTION:
        return thresholds.derive(_as_threshold_rows(cal, point, arm), point, spec["target"])
    if point == "holistic":
        negatives = [i["p"][arm] for i in cal if not i["y"]]
        ok = [c for c in GRID if acts_count(negatives, c, _ge) <= spec["target"] * len(negatives)]
        return min(ok) if ok else None
    return _derive_generic(cal, arm, spec)


def _derive_generic(cal: list[dict[str, Any]], arm: str, spec: Mapping[str, Any]) -> float | None:
    """`thresholds.derive`'s rule for an acting direction it does not list (p < cut)."""
    positives = sum(i["y"] for i in cal)
    best: tuple[float, float] | None = None
    for cut in GRID:
        acted = [i for i in cal if spec["act"](i["p"][arm], cut)]
        if not acted:
            continue
        hits = sum(i["y"] for i in acted)
        if thresholds.wilson_lower(hits, len(acted)) < spec["target"]:
            continue
        recall = hits / positives if positives else 0.0
        if best is None or recall > best[1]:
            best = (cut, recall)
    return None if best is None else best[0]


def profile_cut(cal: list[dict[str, Any]], point: str) -> float | None:
    spec = POINTS[point]
    return derive_target(cal, point, "14") if spec["rule"] == "D" else transfer(cal, point)


def rederived_13(cal: list[dict[str, Any]], point: str) -> float | None:
    spec = POINTS[point]
    return derive_target(cal, point, "13r") if spec["rule"] == "D" else spec["shipped"]


# --- scoring --------------------------------------------------------------------------------


def right(items: list[dict[str, Any]], arm: str, cut: float, point: str) -> dict[str, bool]:
    act = POINTS[point]["act"]
    return {i["id"]: act(i["p"][arm], cut) == i["y"] for i in items}


def operating(items: list[dict[str, Any]], arm: str, cut: float | None, point: str) -> dict:
    if cut is None:
        return {"cut": None}
    act = POINTS[point]["act"]
    acted = [i for i in items if act(i["p"][arm], cut)]
    hits = sum(i["y"] for i in acted)
    positives = sum(i["y"] for i in items)
    return {"cut": cut, "n": len(items), "right": sum(right(items, arm, cut, point).values()),
            "acted": len(acted), "costly": len(acted) - hits,
            "precision": round(hits / len(acted), 4) if acted else None,
            "recall": round(hits / positives, 4) if positives else None}  # fmt: skip


def _stratified_folds(items: list[dict[str, Any]], seed: int) -> list[set[str]]:
    folds: list[set[str]] = [set() for _ in range(CV_FOLDS)]
    for label in (True, False):
        ids = sorted(i["id"] for i in items if i["y"] is label)
        random.Random(seed).shuffle(ids)
        for k, ident in enumerate(ids):
            folds[k % CV_FOLDS].add(ident)
    return folds


def cross_validated(point: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive: the profile's rule fitted on four folds, scored on the fifth, 5 seeds."""
    shipped = POINTS[point]["shipped"]
    base = sum(right(items, "13r", shipped, point).values())
    per_seed: dict[str, list[int]] = {"14": [], "13r": []}
    for seed in CV_SEEDS:
        totals = {"14": 0, "13r": 0}
        for fold in _stratified_folds(items, seed):
            test = [i for i in items if i["id"] in fold]
            train = [i for i in items if i["id"] not in fold]
            for arm, fit in (("14", profile_cut), ("13r", rederived_13)):
                cut = fit(train, point)
                cut = shipped if cut is None else cut
                totals[arm] += sum(right(test, arm, cut, point).values())
        for arm, total in totals.items():
            per_seed[arm].append(total)
    return {"n": len(items), "13r_shipped": base,
            "14_profile_rule_by_seed": per_seed["14"],
            "14_profile_rule_mean": sum(per_seed["14"]) / len(CV_SEEDS),
            "13r_same_rule_by_seed": per_seed["13r"],
            "13r_same_rule_mean": sum(per_seed["13r"]) / len(CV_SEEDS)}  # fmt: skip


def analyse_point(point: str) -> tuple[dict[str, Any], dict[str, bool], dict[str, bool]]:
    spec = POINTS[point]
    items = paired_items(items_of(point))
    cal = [i for i in items if i["part"] == "cal"]
    ev = [i for i in items if i["part"] == "ev"]
    cut14 = profile_cut(cal, point)
    cut13 = rederived_13(cal, point)
    other = "T" if spec["rule"] == "D" else "D"
    alt14 = transfer(cal, point) if other == "T" else derive_target(cal, point, "14")
    alt13 = spec["shipped"] if other == "T" else derive_target(cal, point, "13r")
    used14 = spec["shipped"] if cut14 is None else cut14
    base = right(ev, "13r", spec["shipped"], point)
    new = right(ev, "14", used14, point)
    out = {
        "rule": spec["rule"], "knob": spec["knob"], "shipped": spec["shipped"],
        "n_cal": len(cal), "n_ev": len(ev), "cut_14": cut14, "cut_13r_rederived": cut13,
        "descriptive_other_rule": {"rule": other, "cut_14": alt14, "cut_13r": alt13},
        "ev": {"13r_shipped": operating(ev, "13r", spec["shipped"], point),
               "14_profile": operating(ev, "14", used14, point),
               "14_shipped": operating(ev, "14", spec["shipped"], point),
               "13r_rederived": operating(ev, "13r", cut13, point)},
        "test": paired.compare(base, new),
    }  # fmt: skip
    if point in L1_POINTS:
        out["cv"] = cross_validated(point, items)
    return out, base, new


def analyse() -> dict[str, Any]:
    report: dict[str, Any] = {"prereg_sha256": prereg_sha(), "points": {}}
    pooled: dict[str, dict[str, dict[str, bool]]] = {
        "all": {"b": {}, "n": {}},
        "l1": {"b": {}, "n": {}},
    }
    for point in POINTS:
        out, base, new = analyse_point(point)
        report["points"][point] = out
        for scope in ("all", "l1") if point in L1_POINTS else ("all",):
            pooled[scope]["b"].update({f"{point}:{k}": v for k, v in base.items()})
            pooled[scope]["n"].update({f"{point}:{k}": v for k, v in new.items()})
    adjusted = paired.holm({p: o["test"]["p"] for p, o in report["points"].items()})
    for point, out in report["points"].items():
        t = out["test"]
        t["p_holm"] = adjusted[point]
        t["verdict"] = paired.verdict(t["diff"], t["low"], t["high"], adjusted[point])
    for scope, both in pooled.items():
        t = paired.compare(both["b"], both["n"])
        t["verdict"] = paired.verdict(t["diff"], t["low"], t["high"], t["p"])
        report[f"pooled_{scope}"] = t
    report["profile"] = profile_of(report)
    return report


def profile_of(report: Mapping[str, Any]) -> dict[str, float]:
    """The knobs whose 1.14 cut differs from 1.13's; `remember` brings `derivable` along."""
    out: dict[str, float] = {}
    for out_point in report["points"].values():
        cut = out_point["cut_14"]
        if cut is None or cut == out_point["shipped"]:
            continue
        out[out_point["knob"]] = cut
        if out_point["knob"] == "remember":
            out["derivable"] = round(1.0 - cut, 2)
    return out


def prereg_sha() -> str:
    return hashlib.sha256((OUT / "prereg.md").read_bytes()).hexdigest()


# --- one-off extraction of the check_done answers (replay of the L2 fixtures) ---------------


def extract_done(runs_root: Path) -> int:
    path = ROOT / "benchmarks" / "cascade" / "jev114.py"
    spec = importlib.util.spec_from_file_location("jev114_l2", path)
    l2 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(l2)
    l2.completion.ROOT = runs_root  # the trajectories live in an untracked `runs/` tree
    cases = l2.completion.load()
    if len(cases) != 655:
        raise SystemExit(f"{len(cases)} trajectories under {runs_root}, expected 655")
    rows = {arm: asyncio.run(l2.jev_rows(cases, arm)) for arm in ARMS}
    lines = []
    for k, case in enumerate(cases):
        r13, r14 = rows["13r"][k], rows["14"][k]
        assert r13["id"] == r14["id"] == case["id"]
        lines.append(json.dumps({"id": case["id"], "half": r13["half"], "label": case["label"],
                                 "p_13r": r13["jev_p"], "p_14": r14["jev_p"]}))  # fmt: skip
    DONE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extract-done", action="store_true")
    parser.add_argument("--runs-root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.extract_done:
        return extract_done(args.runs_root)
    report = analyse()
    (OUT / "analysis.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    for point, out in report["points"].items():
        t = out["test"]
        print(
            f"{point:15} {out['rule']} {out['shipped']} -> {out['cut_14']} "
            f"(13r re-derived {out['cut_13r_rederived']}) | ev n={t['n']} "
            f"{t['base']} -> {t['new']} [{t['low']:+.3f}, {t['high']:+.3f}] {t['verdict']}"
        )
    for scope in ("all", "l1"):
        t = report[f"pooled_{scope}"]
        print(
            f"pooled {scope}: n={t['n']} {t['base']} -> {t['new']} "
            f"[{t['low']:+.3f}, {t['high']:+.3f}] {t['verdict']}"
        )
    print("profile:", report["profile"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
