"""Is the hand-written policy the bottleneck, or the model? Free: it replays recordings.

    python benchmarks/policy_shape.py            # writes docs/results/2026-09-25-policy-shape/

Pre-registered on 2026-09-25 before the first run, on the 100 `memory_write` cases of the
first three batches (`benches/memory.jsonl`, `memory-b.jsonl`, and the third batch in
`memory-c.jsonl` / `memory-d.jsonl`), every one of which has a recorded answer to the three
shipped questions (durable, specific, derivable):

  H1. A logistic regression over the three raw probabilities, cross-validated 10-fold and
      repeated 5 times, beats the shipped conjunction (durable >= 0.70, specific >= 0.70,
      derivable <= 0.75) by at least 5 cases WITHOUT more costly errors (a store when the
      label says skip).
  H2. Platt scaling of the deciding probability, leave-one-out, halves ECE on at least 4 of
      the 6 binary points of the fifty-case benches (`fixtures/new-points-50-v2.jsonl`).

Two shapes are compared with the shipped conjunction, both fitted only on the training folds:
a logistic regression, and the shipped shape itself (one cut on the weakest of the three
margins) with the cut derived per fold to maximum accuracy. The point is not to ship either:
`memory_write` already has a fourth question measured for the family these cases lose
(`benchmarks/memory_common.py`). The point is to know how much of the gap between the model
and the policy the policy's SHAPE explains, on data the policy never saw.

Everything here is plain Python: the regression is gradient descent, the folds are seeded.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import pathlib
import random
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza import Squire, Thresholds  # noqa: E402
from sanchopanza.eval.bench import load_cases, run_bench  # noqa: E402
from sanchopanza.eval.stats import ece, wilson  # noqa: E402
from sanchopanza.points import memory  # noqa: E402
from sanchopanza.providers.recorded import RecordedDecider  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-09-25-policy-shape"
MEMORY_FILES = ("memory.jsonl", "memory-b.jsonl", "memory-c.jsonl", "memory-d.jsonl")
FIFTY_FILES = ("loop-b.jsonl", "memory-b.jsonl", "graph-build-b.jsonl", "retrieval-b.jsonl")
FIFTY_FIXTURE = ROOT / "fixtures" / "new-points-50-v2.jsonl"
# The conjunction this analysis compares against, pinned: the default moved to one derived
# cut on 2026-09-27 (docs/results/2026-09-27-memory-write-cut/).
CONJUNCTION = Thresholds(remember=0.70, derivable=0.75)
ACTS = {
    "memory_write": "store",
    "redundant_page": "drop",
    "goal_met": True,
    "repeats_check": True,
    "extract_gate": "extract",
    "recall": "look",
}


def _repository_recordings() -> RecordedDecider:
    entries: list[dict[str, Any]] = []
    for path in sorted((ROOT / "fixtures").glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entries.append(json.loads(line))
    return RecordedDecider(entries)


# --- the three raw probabilities of memory_write, with the shipped verdict ----------------


async def memory_rows() -> list[dict[str, Any]]:
    every = load_cases(ROOT / "benches" / f for f in MEMORY_FILES)
    cases = [c for c in every if c["point"] == "memory_write"]
    squire = Squire(_repository_recordings(), thresholds=CONJUNCTION)
    rows: list[dict[str, Any]] = []
    for case in cases:
        inp = case["input"]
        state, qs = memory.write_questions(fact=inp["fact"], source=inp.get("source", ""))
        decision = await squire.decide("memory_write", state, qs)
        keys = ("durable", "specific", "derivable")
        if decision.failed or any(decision.answer(k).empty for k in keys):
            raise SystemExit(f"{case['id']}: no recording; this bench is replay-only")
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


# --- plain-Python logistic regression ------------------------------------------------------


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def _dot(w: list[float], x: list[float]) -> float:
    return w[0] + sum(wi * xi for wi, xi in zip(w[1:], x, strict=True))


def fit(
    xs: list[list[float]],
    ys: list[bool],
    *,
    l2: float = 1e-2,
    iters: int = 3000,
    lr: float = 0.5,
) -> list[float]:
    """Weights (bias first) by full-batch gradient descent with L2. Deterministic."""
    width = len(xs[0]) + 1
    w = [0.0] * width
    n = len(xs)
    for _ in range(iters):
        grad = [0.0] * width
        for x, y in zip(xs, ys, strict=True):
            err = _sigmoid(_dot(w, x)) - (1.0 if y else 0.0)
            grad[0] += err
            for j, xi in enumerate(x):
                grad[j + 1] += err * xi
        w = [
            wi - lr * (g / n + (l2 * wi if j else 0.0))
            for j, (wi, g) in enumerate(zip(w, grad, strict=True))
        ]
    return w


def predict(w: list[float], x: list[float]) -> float:
    return _sigmoid(_dot(w, x))


def folds(n: int, k: int, seed: int) -> list[list[int]]:
    idx = list(range(n))
    random.Random(seed).shuffle(idx)
    return [idx[i::k] for i in range(k)]


def margin(x: list[float]) -> float:
    return min(x[0], x[1], 1.0 - x[2])


def cross_validate(
    rows: list[dict[str, Any]], *, repeats: int, k: int = 10, regression: bool = True
) -> dict[str, Any]:
    """Hits and costly errors per run, averaged over repeats, for the fitted shapes.

    `regression=False` skips the slow shape (the replay test pins the derived cut only).
    """
    n = len(rows)
    names = ["derived_cut"] + (["regression"] if regression else [])
    hits = dict.fromkeys(names, 0)
    costly = dict.fromkeys(names, 0)
    cuts: list[float] = []
    for r in range(repeats):
        for test in folds(n, k, seed=100 + r):
            held = set(test)
            train = [i for i in range(n) if i not in held]
            w = None
            if regression:
                w = fit([rows[i]["x"] for i in train], [rows[i]["y"] for i in train])
            best, best_hits = 0.5, -1
            for cut in (i / 100 for i in range(5, 96)):
                h = sum((margin(rows[i]["x"]) >= cut) == rows[i]["y"] for i in train)
                if h > best_hits:
                    best, best_hits = cut, h
            cuts.append(best)
            for i in test:
                shapes = [("derived_cut", margin(rows[i]["x"]) >= best)]
                if w is not None:
                    shapes.append(("regression", predict(w, rows[i]["x"]) >= 0.5))
                for name, store in shapes:
                    hits[name] += store == rows[i]["y"]
                    costly[name] += store and not rows[i]["y"]
    out: dict[str, Any] = {
        name: {"hits_per_run": hits[name] / repeats, "costly_per_run": costly[name] / repeats}
        for name in names
    }
    out["derived_cuts"] = {
        "min": min(cuts),
        "median": sorted(cuts)[len(cuts) // 2],
        "max": max(cuts),
    }
    return out


# --- Platt scaling of a single deciding probability, leave-one-out -------------------------


def _logit(p: float) -> float:
    p = max(1e-4, min(1 - 1e-4, p))
    return math.log(p / (1 - p))


def platt_loo(ps: list[float], ys: list[bool]) -> list[float]:
    out: list[float] = []
    for i in range(len(ps)):
        xs = [[_logit(p)] for j, p in enumerate(ps) if j != i]
        yy = [y for j, y in enumerate(ys) if j != i]
        w = fit(xs, yy, l2=1e-3, iters=1500, lr=0.2)
        out.append(predict(w, [_logit(ps[i])]))
    return out


def _brier(ps: list[float], ys: list[bool]) -> float:
    return sum((p - y) ** 2 for p, y in zip(ps, ys, strict=True)) / len(ps)


async def recalibration() -> dict[str, Any]:
    cases = load_cases(ROOT / "benches" / f for f in FIFTY_FILES)
    results = await run_bench(cases, RecordedDecider.from_file(FIFTY_FIXTURE))
    out: dict[str, Any] = {}
    for point, act in ACTS.items():
        rows = [
            r for r in results if getattr(r, "point", None) == point and r.probability is not None
        ]
        ps = [r.probability for r in rows]
        ys = [r.expected == act for r in rows]
        cal = platt_loo(ps, ys)
        out[point] = {
            "n": len(ps),
            "ece_before": round(ece(ps, ys), 3),
            "ece_after": round(ece(cal, ys), 3),
            "brier_before": round(_brier(ps, ys), 3),
            "brier_after": round(_brier(cal, ys), 3),
        }
    return out


async def run(*, repeats: int = 5) -> dict[str, Any]:
    rows = await memory_rows()
    shipped_hits = sum(r["shipped"] == r["y"] for r in rows)
    shipped_costly = sum(r["shipped"] and not r["y"] for r in rows)
    plain = sum((margin(r["x"]) >= 0.5) == r["y"] for r in rows)
    plain_costly = sum(margin(r["x"]) >= 0.5 and not r["y"] for r in rows)
    _, low, high = wilson(shipped_hits, len(rows))
    on_all = fit([r["x"] for r in rows], [r["y"] for r in rows])
    return {
        "memory_write": {
            "n": len(rows),
            "shipped": {
                "hits": shipped_hits,
                "costly": shipped_costly,
                "wilson95": [round(low, 3), round(high, 3)],
            },
            "plain_0.5": {"hits": plain, "costly": plain_costly},
            "cross_validated": cross_validate(rows, repeats=repeats),
            "regression_on_all": [round(v, 2) for v in on_all],
            "repeats": repeats,
        },
        "recalibration": await recalibration(),
    }


def report(result: dict[str, Any]) -> str:
    m = result["memory_write"]
    cv = m["cross_validated"]
    sh, pl = m["shipped"], m["plain_0.5"]
    dc, lr = cv["derived_cut"], cv.get("regression")
    cuts = cv["derived_cuts"]
    lines = [
        f"## memory_write, {m['n']} cases, three raw probabilities",
        "",
        "| policy | fitted on | hits | costly (store when skip) |",
        "|---|---|---|---|",
        f"| shipped conjunction (0.70 / 0.70 / 0.75) | nothing | {sh['hits']} | {sh['costly']} |",
        f"| plain 0.5 cut on the weakest margin | nothing | {pl['hits']} | {pl['costly']} |",
        "| one cut on the weakest margin, derived per fold | training folds | "
        f"{dc['hits_per_run']:.1f} | {dc['costly_per_run']:.1f} |",
    ]
    if lr is not None:
        lines.append(
            "| logistic regression on the three probabilities | training folds | "
            f"{lr['hits_per_run']:.1f} | {lr['costly_per_run']:.1f} |"
        )
    lines += [
        "",
        f"Cross-validation: 10-fold, {m['repeats']} repeats, hits averaged per run of 100. "
        f"Derived cuts across folds: min {cuts['min']:.2f}, median {cuts['median']:.2f}, "
        f"max {cuts['max']:.2f}. Regression on all cases (bias, durable, specific, "
        f"derivable): {m['regression_on_all']}. Wilson 95 % of the shipped accuracy: "
        f"{sh['wilson95'][0]}-{sh['wilson95'][1]}.",
        "",
        "## Platt scaling, leave-one-out, on the deciding probability of each binary point",
        "",
        "| point | n | ECE before | ECE after | Brier before | Brier after |",
        "|---|---|---|---|---|---|",
    ]
    for point, r in result["recalibration"].items():
        lines.append(
            f"| {point} | {r['n']} | {r['ece_before']} | {r['ece_after']} | "
            f"{r['brier_before']} | {r['brier_after']} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", default=str(RESULTS))
    args = ap.parse_args()
    result = asyncio.run(run(repeats=args.repeats))
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "policy-shape.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    text = report(result)
    (out / "summary.md").write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
