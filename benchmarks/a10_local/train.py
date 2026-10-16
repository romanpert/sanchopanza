"""Lot A10: a local check_done classifier fitted on public labels only. Free: no model is called.

    python benchmarks/a10_local/train.py cv  [--runs-root P]   # grouped 5-fold CV: cv.json, oof
    python benchmarks/a10_local/train.py fit [--runs-root P]   # chosen config on all 393: model
    python benchmarks/a10_local/train.py dry [--runs-root P]   # the eval pipeline on TRAIN only

Registered in docs/results/2026-10-16-a10-local/prereg.md.

THE LABELS are AgentDojo's `utility` on 393 of the 655 slack stops of
docs/results/2026-09-25-completion/ (286 done): the three pipelines Jev did not touch
(`a10_data.load_train` drops the two `squire` ones, whose records and labels are effects of Jev's
injection detector). TypeSafe's MCA 2.3(b) forbids training on Jev's outputs: no Jev probability
or decision is a feature, a label, or a selection criterion here. `dry` reads Jev's recorded
probabilities on these stops (docs/results/2026-10-15-jev114-recal/done-scored.jsonl) only to
exercise the comparison code, after the model is fixed.

THE CV. Folds group the stops by user task (`slack/<task dir>`: 21 user tasks and 5 injection
tasks run as user tasks, each by three pipelines), so a fold never sees a task it is scored on.
They cannot also group by injection task: every user task is run with every injection task, so
grouping by both leaves one group. An injected payload therefore appears in the fitting folds
and in the scored one, under other user tasks: a leak the registration states. Every
configuration in the grid is scored by its pooled out-of-fold AUC; the best wins, ties (to 3
decimals) going to the lower out-of-fold log-loss. When the winner's C is the grid's largest,
the same view at 10x that C is scored too and recorded in cv.json, descriptively: it does not
change the choice. The cut is then derived on the winner's
out-of-fold probabilities by the rule that gave Jev 1.14 its 0.30 on the 655 (lot jev114-recal,
rule D): the cut with the most recall on unfinished stops whose block precision has a 95 % Wilson
lower bound of at least the target, cuts 0.01 to 0.99, block when p(done) < cut. The targets are
tried in order, 0.90 then 0.80 (`PRECISION_TARGETS`); if neither finds a cut, the out-of-fold
accuracy-maximising cut is used.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import a10_analysis as analysis  # noqa: E402
import a10_data as data  # noqa: E402
import a10_model as model  # noqa: E402
import lot_stats  # noqa: E402
import thresholds  # noqa: E402

ROOT = data.ROOT
OUT = ROOT / "docs" / "results" / "2026-10-16-a10-local"
CV_FILE = OUT / "cv.json"
OOF_FILE = OUT / "oof.jsonl"
DRY_FILE = OUT / "dry.json"
MODEL = ROOT / "fixtures" / "a10_local" / "model.json"
RECAL_DONE = ROOT / "docs" / "results" / "2026-10-15-jev114-recal" / "done-scored.jsonl"

FOLDS = 5
GRID_C = (0.1, 1.0, 10.0, 100.0)
VIEWS: dict[str, tuple[tuple[str, ...], int]] = {
    "A": (("w", "l", "s"), 2),  # words 1-2, last message, structure
    "B": (("w", "c", "l", "s"), 2),  # A plus character 3-5-grams
    "C": (("w", "l", "s"), 1),  # A with words 1 only
    "D": (("l", "s"), 1),  # last message and structure only: no task-specific vocabulary
}
# Rule D's targets, tried in order. 0.90 is check_done's; with 107 unfinished training stops no
# cut reaches it (`thresholds.py`: 35 blocks, all right, are the floor), so 0.80, the target
# recal used for its other points, comes next. Fixed on TRAIN, before any test stop was scored.
PRECISION_TARGETS = (0.90, 0.80)
CUT_GRID = tuple(round(i / 100, 2) for i in range(1, 100))


def grid() -> list[model.Config]:
    return [model.Config(fam, n, c) for fam, n in VIEWS.values() for c in GRID_C]


def folds(examples: Sequence[data.Example], k: int = FOLDS) -> list[int]:
    """Fold of each stop: whole clusters, largest first (ties by name) to the lightest fold."""
    sizes: dict[str, int] = {}
    for e in examples:
        sizes[e.cluster] = sizes.get(e.cluster, 0) + 1
    load = [0] * k
    fold_of: dict[str, int] = {}
    for cluster in sorted(sizes, key=lambda c: (-sizes[c], c)):
        target = min(range(k), key=lambda f: (load[f], f))
        fold_of[cluster] = target
        load[target] += sizes[cluster]
    return [fold_of[e.cluster] for e in examples]


def out_of_fold(
    examples: Sequence[data.Example], config: model.Config, fold_of: Sequence[int],
    counts: Sequence[Any],
) -> list[float]:  # fmt: skip
    p = [math.nan] * len(examples)
    for f in sorted(set(fold_of)):
        train = [i for i, g in enumerate(fold_of) if g != f]
        held = [i for i, g in enumerate(fold_of) if g == f]
        vec, w, b, _ = model.fit([examples[i] for i in train], config, [counts[i] for i in train])
        rows = vec.transform_all([counts[i] for i in held])
        for i, value in zip(held, model.logreg.predict(rows, w, b), strict=True):
            p[i] = value
    return p


def log_loss(p: Sequence[float], done: Sequence[bool]) -> float:
    eps = 1e-12
    total = sum(-math.log(max(eps, x if y else 1 - x)) for x, y in zip(p, done, strict=True))
    return total / len(p)


def accuracy_at(p: Sequence[float], done: Sequence[bool], cut: float) -> float:
    return sum((x >= cut) == y for x, y in zip(p, done, strict=True)) / len(p)


def derive_cut(
    p: Sequence[float], done: Sequence[bool], target: float = PRECISION_TARGETS[0]
) -> float | None:
    """Rule D at `target`: the cut with the most recall on unfinished stops whose block
    precision's Wilson lower bound clears the target; the lowest such cut on a tie."""
    unfinished = sum(not y for y in done)
    best: tuple[float, float] | None = None
    for cut in CUT_GRID:
        acted = [y for x, y in zip(p, done, strict=True) if x < cut]
        if not acted:
            continue
        hits = sum(not y for y in acted)
        if thresholds.wilson_lower(hits, len(acted)) < target:
            continue
        recall = hits / unfinished
        if best is None or recall > best[1]:
            best = (cut, recall)
    return None if best is None else best[0]


def max_accuracy_cut(p: Sequence[float], done: Sequence[bool]) -> float:
    """The out-of-fold accuracy-maximising cut (lowest on a tie): the ladder's last rung."""
    return max(CUT_GRID, key=lambda c: (accuracy_at(p, done, c), -c))


def cut_by_ladder(p: Sequence[float], done: Sequence[bool]) -> tuple[float, str]:
    """Rule D at each of PRECISION_TARGETS in turn; the first that finds a cut gives it. When
    none does, the out-of-fold accuracy-maximising cut."""
    for target in PRECISION_TARGETS:
        cut = derive_cut(p, done, target)
        if cut is not None:
            return cut, f"D at {target}"
    return max_accuracy_cut(p, done), "max out-of-fold accuracy"


def summary(p: Sequence[float], done: Sequence[bool], fold_of: Sequence[int]) -> dict[str, Any]:
    per_fold = []
    for f in sorted(set(fold_of)):
        idx = [i for i, g in enumerate(fold_of) if g == f]
        per_fold.append(lot_stats.rank_auc([p[i] for i in idx], [done[i] for i in idx]))
    return {
        "auc": round(lot_stats.rank_auc(p, done), 4),
        "auc_per_fold": [None if a is None else round(a, 4) for a in per_fold],
        "log_loss": round(log_loss(p, done), 4),
        "accuracy_at_0.5": round(accuracy_at(p, done, 0.5), 4),
    }


def select(results: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return min(results, key=lambda r: (-round(r["cv"]["auc"], 3), r["cv"]["log_loss"]))


def cmd_cv(args: argparse.Namespace) -> int:
    examples = data.load_train(args.runs_root)
    done = [e.done for e in examples]
    fold_of = folds(examples)
    counts_by_view: dict[tuple[tuple[str, ...], int], list[Any]] = {}
    results, oof_by_name = [], {}
    for config in grid():
        key = (config.families, config.word_n)
        if key not in counts_by_view:
            counts_by_view[key] = model.counts_of(examples, config)
        p = out_of_fold(examples, config, fold_of, counts_by_view[key])
        results.append({"config": config.name, "cv": summary(p, done, fold_of)})
        oof_by_name[config.name] = p
        print(json.dumps(results[-1]), flush=True)
    best = select(results)
    p = oof_by_name[best["config"]]
    cut, rule = cut_by_ladder(p, done)
    chosen = next(c for c in grid() if c.name == best["config"])
    edge = None
    if chosen.c == max(GRID_C):
        wider = model.Config(chosen.families, chosen.word_n, 10 * chosen.c, chosen.min_df)
        counts = counts_by_view[(chosen.families, chosen.word_n)]
        q = out_of_fold(examples, wider, fold_of, counts)
        edge = {"config": wider.name, "cv": summary(q, done, fold_of), "used": False}
    report = {
        "train_digest": data.digest(examples),
        "n": len(examples),
        "done": sum(done),
        "folds": {
            str(f): {
                "stops": fold_of.count(f),
                "clusters": len(
                    {e.cluster for e, g in zip(examples, fold_of, strict=True) if g == f}
                ),
            }
            for f in range(FOLDS)
        },  # fmt: skip
        "grid": results,
        "chosen": {
            "name": chosen.name,
            "families": list(chosen.families),
            "word_n": chosen.word_n,
            "c": chosen.c,
            "min_df": chosen.min_df,
        },  # fmt: skip
        "grid_edge_descriptive": edge,
        "cut_ladder": {f"D at {t}": derive_cut(p, done, t) for t in PRECISION_TARGETS},
        "cut_rule": rule,
        "cut": cut,
        "at_cut": cut_table(p, done, cut),
        "max_accuracy_cut_descriptive": (mc := max_accuracy_cut(p, done)),
        "at_max_accuracy_cut": cut_table(p, done, mc),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    CV_FILE.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    OOF_FILE.write_text("".join(
        json.dumps({"id": e.id, "cluster": e.cluster, "label": "done" if e.done else "not_done",
                    "p_local": round(x, 6)}) + "\n"
        for e, x in zip(examples, p, strict=True)), encoding="utf-8", newline="\n")  # fmt: skip
    print(json.dumps({k: report[k] for k in ("chosen", "cut", "at_cut")}, indent=1))
    return 0


def cut_table(p: Sequence[float], done: Sequence[bool], cut: float) -> dict[str, Any]:
    blocked = [y for x, y in zip(p, done, strict=True) if x < cut]
    return {"cut": cut, "accuracy": round(accuracy_at(p, done, cut), 4), "blocks": len(blocked),
            "false_blocks": sum(blocked), "caught": len(blocked) - sum(blocked),
            "unfinished": sum(not y for y in done)}  # fmt: skip


def cmd_fit(args: argparse.Namespace) -> int:
    report = json.loads(CV_FILE.read_text(encoding="utf-8"))
    examples = data.load_train(args.runs_root)
    if data.digest(examples) != report["train_digest"]:
        raise SystemExit("the training stops differ from the ones the CV read")
    chosen = report["chosen"]
    config = model.Config(tuple(chosen["families"]), chosen["word_n"], chosen["c"],
                          chosen["min_df"])  # fmt: skip
    vec, w, b, info = model.fit(examples, config)
    best = next(r for r in report["grid"] if r["config"] == config.name)
    meta = {
        "lot": "a10-local",
        "train_digest": report["train_digest"],
        "train_n": len(examples),
        "cut_rule": report["cut_rule"],
        "cv": best["cv"],
        "solver": {k: (round(v, 8) if isinstance(v, float) else v) for k, v in info.items()},
        "terms": len(vec.terms),
    }
    fitted = model.Model(config, vec, tuple(w), b, report["cut"], meta)
    written = model.save(fitted, MODEL)
    print(f"{written.relative_to(ROOT).as_posix()}: {written.stat().st_size} bytes, "
          f"{len(vec.terms)} terms, sha256 {model.file_sha256(MODEL)}; {info}")  # fmt: skip
    return 0


def cmd_dry(args: argparse.Namespace) -> int:
    """The eval pipeline on TRAIN only: out-of-fold p_local against Jev's recorded p on the same
    393 training stops, at every arm's cut. Jev's 0.30 was derived on half of the 655, these
    among them."""
    fitted = model.load(MODEL)
    oof = [json.loads(x) for x in OOF_FILE.read_text(encoding="utf-8").splitlines() if x]
    jev = {}
    for line in RECAL_DONE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            jev[row["id"]] = row
    rows = [{**r, "p_14": jev[r["id"]]["p_14"], "p_13r": jev[r["id"]]["p_13r"]} for r in oof]
    if any(jev[r["id"]]["label"] != r["label"] for r in oof):
        raise SystemExit("labels differ between oof.jsonl and the recal rows")
    report = {"set": "TRAIN (out-of-fold), not the test set", **analysis.analyse(rows, fitted.cut)}
    DRY_FILE.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({k: report[k] for k in ("set", "n", "cuts", "verdict")}, indent=1))
    for arm, table in report["arms"].items():
        print(arm, json.dumps({k: table[k] for k in ("accuracy", "false_blocks", "caught",
                                                     "auc")}))  # fmt: skip
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, fn in (("cv", cmd_cv), ("fit", cmd_fit), ("dry", cmd_dry)):
        p = sub.add_parser(name)
        p.add_argument(
            "--runs-root", type=Path, default=None,
            help="checkout holding docs/results/2026-09-24-agentdojo-*/runs/",
        )  # fmt: skip
        p.set_defaults(fn=fn)
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
