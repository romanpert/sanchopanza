"""Derive the `memory_write` cut to a precision target, on one half, report on the other.

    python benchmarks/memory_write_cut.py    # writes docs/results/2026-09-27-memory-write-cut/

Free: it replays recordings. The design, the split and the criterion are fixed in
`docs/results/2026-09-27-memory-write-cut/prereg.md`, written and hashed before this ran.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import random
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "benchmarks"))

import policy_shape  # noqa: E402
from thresholds import wilson_lower  # noqa: E402

from sanchopanza import Squire  # noqa: E402
from sanchopanza.points import memory  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-27-memory-write-cut"
SECONDARY = ("memory-e.jsonl", "memory-f.jsonl", "memory-g.jsonl")
SEED = 20260927
TARGET = 0.80
GRID = [i / 100 for i in range(5, 96)]


def split(rows: list[dict[str, Any]]) -> tuple[list[dict], list[dict]]:
    """Stratified by label, seeded, first half (rounded up) of each label to A."""
    a: list[dict] = []
    b: list[dict] = []
    for label in (True, False):
        ids = sorted(r["id"] for r in rows if r["y"] is label)
        random.Random(SEED).shuffle(ids)
        half = (len(ids) + 1) // 2
        chosen = set(ids[:half])
        a += [r for r in rows if r["y"] is label and r["id"] in chosen]
        b += [r for r in rows if r["y"] is label and r["id"] not in chosen]
    return a, b


def stores(row: dict[str, Any], cut: float) -> bool:
    return policy_shape.margin(row["x"]) >= cut


def score(rows: list[dict[str, Any]], decide) -> dict[str, Any]:
    acted = [r for r in rows if decide(r)]
    true_stores = sum(r["y"] for r in acted)
    positives = sum(r["y"] for r in rows)
    return {
        "n": len(rows),
        "stored": len(acted),
        "hits": sum(decide(r) == r["y"] for r in rows),
        "costly": len(acted) - true_stores,
        "precision": round(true_stores / len(acted), 3) if acted else None,
        "recall": round(true_stores / positives, 3) if positives else None,
    }


def derive(rows: list[dict[str, Any]], target: float = TARGET) -> float | None:
    """Most recall whose Wilson lower bound of precision clears the target; ties: highest cut."""
    best: tuple[float, float] | None = None
    for cut in GRID:
        acted = [r for r in rows if stores(r, cut)]
        if not acted:
            continue
        hits = sum(r["y"] for r in acted)
        if wilson_lower(hits, len(acted)) < target:
            continue
        recall = hits / sum(r["y"] for r in rows)
        if best is None or recall >= best[1]:
            best = (cut, recall)
    return None if best is None else best[0]


def conjunction(row: dict[str, Any]) -> bool:
    return row["shipped"]


def _load(names: tuple[str, ...]) -> list[dict[str, Any]]:
    out = []
    for name in names:
        for line in (ROOT / "benches" / name).read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#"):
                row = json.loads(line)
                if row["point"] == "memory_write":
                    out.append(row)
    return out


async def secondary_rows() -> list[dict[str, Any]]:
    squire = Squire(policy_shape._repository_recordings(), thresholds=policy_shape.CONJUNCTION)
    rows = []
    for case in _load(SECONDARY):
        state, qs = memory.write_questions(fact=case["input"]["fact"])
        decision = await squire.decide("memory_write", state, qs)
        keys = ("durable", "specific", "derivable")
        if decision.failed or any(decision.answer(k).empty for k in keys):
            raise SystemExit(f"{case['id']}: no recording; this analysis is replay-only")
        w = memory.decide_write(decision, squire.thresholds)
        rows.append(
            {
                "id": case["id"],
                "x": [w.durable, w.specific, w.derivable],
                "y": case["expected"] == "store",
                "shipped": w.store,
            }
        )
    return rows


def resampled(rows: list[dict[str, Any]], folds: list[list[int]]) -> dict[str, Any]:
    """The whole procedure (derive on the rest, score the fold), summed over the folds."""
    hits = costly = stored = true_stores = unreachable = 0
    cuts: list[float] = []
    for test in folds:
        held = set(test)
        cut = derive([r for i, r in enumerate(rows) if i not in held])
        if cut is None:
            unreachable += 1
            continue
        cuts.append(cut)
        for i in test:
            s = stores(rows[i], cut)
            hits += s == rows[i]["y"]
            stored += s
            true_stores += s and rows[i]["y"]
            costly += s and not rows[i]["y"]
    return {
        "hits": hits,
        "costly": costly,
        "precision": round(true_stores / stored, 3) if stored else None,
        "cut_min": min(cuts) if cuts else None,
        "cut_max": max(cuts) if cuts else None,
        "unreachable_folds": unreachable,
    }


def descriptive(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    kfold = [resampled(rows, policy_shape.folds(n, 10, seed=100 + r)) for r in range(5)]
    return {
        "kfold_10x5_mean_hits": sum(k["hits"] for k in kfold) / 5,
        "kfold_10x5_mean_costly": sum(k["costly"] for k in kfold) / 5,
        "kfold_cut_range": [min(k["cut_min"] for k in kfold), max(k["cut_max"] for k in kfold)],
        "kfold_unreachable_folds": sum(k["unreachable_folds"] for k in kfold),
        "loo": resampled(rows, [[i] for i in range(n)]),
    }


async def run() -> dict[str, Any]:
    rows = await policy_shape.memory_rows()
    a, b = split(rows)
    cut = derive(a)
    second = await secondary_rows()
    out: dict[str, Any] = {
        "target": TARGET,
        "split": {"A": len(a), "B": len(b), "A_ids": sorted(r["id"] for r in a)},
        "cut": cut,
        "conjunction_on_A": score(a, conjunction),
        "conjunction_on_B": score(b, conjunction),
        "conjunction_on_secondary": score(second, conjunction),
    }
    if cut is not None:
        out["derived_on_A"] = score(a, lambda r: stores(r, cut))
        out["derived_on_B"] = score(b, lambda r: stores(r, cut))
        out["derived_on_secondary"] = score(second, lambda r: stores(r, cut))
        db, sb = out["derived_on_B"], out["conjunction_on_B"]
        checks = {
            "precision_B_ge_target": db["precision"] is not None and db["precision"] >= TARGET,
            "costly_B_le_conjunction": db["costly"] <= sb["costly"],
            "hits_B_gt_conjunction": db["hits"] > sb["hits"],
            "costly_secondary_le_conjunction": out["derived_on_secondary"]["costly"]
            <= out["conjunction_on_secondary"]["costly"],
        }
        out["checks"] = checks
        out["holds"] = all(checks.values())
    else:
        out["holds"] = False
    reverse = derive(b)
    out["reverse"] = {
        "cut": reverse,
        "on_A": None if reverse is None else score(a, lambda r: stores(r, reverse)),
    }
    out["descriptive"] = descriptive(rows)
    out["descriptive_secondary_plain_0.5"] = score(second, lambda r: stores(r, 0.5))
    out["secondary_by_batch"] = {
        name: {
            "conjunction": score([r for r in second if r["id"].startswith(prefix)], conjunction),
            "derived": score(
                [r for r in second if r["id"].startswith(prefix)], lambda r: stores(r, cut or 1.0)
            ),
        }
        for name, prefix in (("memory-e", "mw-2"), ("memory-f", "mw-3"), ("memory-g", "mw-4"))
    }
    return out


def main() -> int:
    result = asyncio.run(run())
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "analysis.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    sys.stdout.write(json.dumps({k: v for k, v in result.items() if k != "split"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
