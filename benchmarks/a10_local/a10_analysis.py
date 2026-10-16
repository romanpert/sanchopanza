"""The registered analysis of lot A10 (docs/results/2026-10-16-a10-local/prereg.md): the local
classifier against Jev's recorded probabilities on the same stops. Pure functions, no I/O.

A row is {"id", "cluster", "label" ("done" | "not_done"), "p_local", "p_14", "p_13r"}.

THE PRIMARY is the paired difference in AUC (finished stops ranked above unfinished ones), local
minus `jev-1.14.0`, with a cluster bootstrap over user tasks (`l4_stats.bootstrap`: 10,000
replicas, seed 20261015), read on its unrounded bounds against a margin of -0.05 AUC. AUC needs
no cut, so an arm cannot score well by blocking little: on checkdone114's 950 stops "never
block" is right on 795, more than either Jev arm at its cut.

SECONDARY: right decisions at the cuts, false blocks and catches. Every arm blocks a stop when
its p(done) is below its cut: the local one at the cut fixed on the training set, `jev-1.14.0`
at 0.30 and `jev-1.13.0` at 0.5 (the cuts lot checkdone114 scored), and a descriptive "never"
arm that blocks nothing. Jev's probabilities are read here only to score Jev; nothing of them
reaches the classifier.

The statistics are the jev114 lots': exact McNemar and the paired bootstrap of `l4_stats` (same
resampling and seed as `paired_binary`), Wilson intervals from `sanchopanza.eval.stats`, rank AUC
from `lot_stats`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import a10_data  # noqa: F401 - puts src/ and benchmarks/jev114 on sys.path
import l4_stats
import lot_stats

from sanchopanza.eval.stats import wilson

MODELS = {"14": "jev-1.14.0", "13r": "jev-1.13.0"}
# The cuts lot checkdone114 scored (`policy.Thresholds.for_model(...).done` on 2026-10-16),
# registered here as numbers so a later profile change cannot move them; a test pins them.
JEV_CUTS = {"14": 0.30, "13r": 0.5}
AUC_MARGIN = -0.05  # the primary: the AUC difference's lower bound above -0.05
MARGIN = -0.05  # secondary, accuracy at the cuts: above -5 points
NEVER = "never"  # the descriptive arm that never blocks (p_never = 1, cut 0)


def jev_cuts() -> dict[str, float]:
    return dict(JEV_CUTS)


def blocks(p: float, cut: float) -> bool:
    return p < cut


def right(row: Mapping[str, Any], arm: str, cut: float) -> bool:
    return blocks(row[f"p_{arm}"], cut) == (row["label"] == "not_done")


def _rate(k: int, n: int) -> dict[str, Any]:
    p, low, high = wilson(k, n)
    return {"k": k, "n": n, "rate": round(p, 4), "wilson95": [round(low, 4), round(high, 4)]}


def arm_table(rows: Sequence[Mapping[str, Any]], arm: str, cut: float) -> dict[str, Any]:
    done = [r for r in rows if r["label"] == "done"]
    unfinished = [r for r in rows if r["label"] == "not_done"]
    blocked = [r for r in rows if blocks(r[f"p_{arm}"], cut)]
    hits = sum(r["label"] == "not_done" for r in blocked)
    return {
        "cut": cut,
        "accuracy": _rate(sum(right(r, arm, cut) for r in rows), len(rows)),
        "false_blocks": _rate(sum(blocks(r[f"p_{arm}"], cut) for r in done), len(done)),
        "caught": _rate(sum(blocks(r[f"p_{arm}"], cut) for r in unfinished), len(unfinished)),
        "blocks": len(blocked),
        "block_precision": round(hits / len(blocked), 4) if blocked else None,
        "auc": _auc(rows, arm),
    }


def _auc(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    found = lot_stats.rank_auc([r[f"p_{arm}"] for r in rows], [r["label"] == "done" for r in rows])
    return None if found is None else round(found, 4)


def verdict(result: Mapping[str, Any], margin: float = MARGIN) -> str:
    """The registered rule on a cluster interval of (local - Jev), read on the unrounded bounds
    when present. The house convention for margin lots: "peor" only when the whole interval
    lies below the margin; an interval wholly below 0 whose lower bound is above the margin is
    "no peor"."""
    ci = result.get("ci95_cluster_raw") or result.get("ci95_cluster")
    if result.get("diff") is None or ci is None:
        return "no medido"
    low, high = ci
    if low > 0:
        return "mejor"
    if low > margin:
        return "no peor"
    if high < margin:
        return "peor"
    return "no concluyente"


def _bounds(values: Sequence[float]) -> tuple[float, float] | None:
    """`l4_stats.ci95`'s percentiles, unrounded."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[int(0.025 * (len(ordered) - 1))], ordered[int(0.975 * (len(ordered) - 1))]


def _rounded(bounds: tuple[float, float] | None) -> tuple[float, float] | None:
    return None if bounds is None else (round(bounds[0], 4), round(bounds[1], 4))


def paired(
    rows: Sequence[Mapping[str, Any]],
    new: Callable[[Mapping[str, Any]], bool],
    old: Callable[[Mapping[str, Any]], bool],
) -> dict[str, Any]:
    """`l4_stats.paired_binary` (same resampling, same seed, so the same intervals), keeping the
    cluster interval's unrounded bounds for the verdict and saying whether it excludes 0."""
    a, b = [new(r) for r in rows], [old(r) for r in rows]
    n = len(a)
    if n == 0:
        return {"n": 0, "diff": None, "p": 1.0, "ci95": None, "ci95_cluster": None}

    def diff(idx: list[int]) -> float:
        return sum(a[i] - b[i] for i in idx) / len(idx)

    only_new = sum(x and not y for x, y in zip(a, b, strict=True))
    only_old = sum(y and not x for x, y in zip(a, b, strict=True))
    item = _bounds(l4_stats.bootstrap(diff, l4_stats.items_as_units(n)))
    cluster = _bounds(
        l4_stats.bootstrap(diff, l4_stats.clusters_as_units([r["cluster"] for r in rows]))
    )
    return {
        "n": n, "new": round(sum(a) / n, 4), "old": round(sum(b) / n, 4),
        "diff": round(diff(list(range(n))), 4), "only_new": only_new, "only_old": only_old,
        "p": round(l4_stats.mcnemar_exact(only_new, only_old), 4),
        "ci95": _rounded(item), "ci95_cluster": _rounded(cluster), "ci95_cluster_raw": cluster,
        # Descriptive, not the verdict: the cluster interval lies wholly below 0.
        "below_zero": cluster is not None and cluster[1] < 0,
    }  # fmt: skip


def paired_auc(rows: Sequence[Mapping[str, Any]], new: str, old: str) -> dict[str, Any]:
    """AUC of p(done) for finished above unfinished stops, arm `new` minus arm `old`, with the
    user-task cluster bootstrap of `l4_stats.bootstrap` (10,000 replicas, its seed) and the
    interval's unrounded bounds for the verdict."""
    labels = [r["label"] == "done" for r in rows]
    a, b = [r[f"p_{new}"] for r in rows], [r[f"p_{old}"] for r in rows]

    def area(scores: Sequence[float], idx: Sequence[int]) -> float | None:
        return lot_stats.rank_auc([scores[i] for i in idx], [labels[i] for i in idx])

    def diff(idx: list[int]) -> float | None:
        x, y = area(a, idx), area(b, idx)
        return None if x is None or y is None else x - y

    everything = list(range(len(rows)))
    whole = diff(everything)
    if whole is None:
        return {"n": len(rows), "diff": None, "ci95_cluster": None, "verdict": "no medido"}
    cluster = _bounds(
        l4_stats.bootstrap(diff, l4_stats.clusters_as_units([r["cluster"] for r in rows]))
    )
    result = {
        "n": len(rows), "positives": sum(labels),
        "new": round(area(a, everything), 4), "old": round(area(b, everything), 4),
        "diff": round(whole, 4), "ci95_cluster": _rounded(cluster), "ci95_cluster_raw": cluster,
        "replicas": l4_stats.BOOT, "seed": l4_stats.BOOT_SEED,
    }  # fmt: skip
    result["verdict"] = verdict(result, AUC_MARGIN)
    return result


def against(rows: Sequence[Mapping[str, Any]], arm: str, cuts: Mapping[str, float]) -> dict:
    """Local minus Jev `arm` on the same stops: AUC (the verdict), then right decisions at the
    cuts, finished stops not falsely blocked and unfinished stops caught."""
    local, cut = cuts["local"], cuts[arm]
    done = [r for r in rows if r["label"] == "done"]
    unfinished = [r for r in rows if r["label"] == "not_done"]
    accuracy = paired(rows, lambda r: right(r, "local", local), lambda r: right(r, arm, cut))
    accuracy["verdict_descriptive"] = verdict(accuracy, MARGIN)
    return {
        "auc": paired_auc(rows, "local", arm),
        "accuracy": accuracy,
        "not_falsely_blocked": paired(done, lambda r: not blocks(r["p_local"], local),
                                      lambda r: not blocks(r[f"p_{arm}"], cut)),
        "caught": paired(unfinished, lambda r: blocks(r["p_local"], local),
                         lambda r: blocks(r[f"p_{arm}"], cut)),
    }  # fmt: skip


def analyse(rows: Sequence[Mapping[str, Any]], local_cut: float) -> dict[str, Any]:
    missing = [r["id"] for r in rows if None in (r["p_local"], r["p_14"], r["p_13r"])]
    if missing:
        raise SystemExit(f"{len(missing)} stops without a probability, first {missing[:3]}")
    rows = [{**r, f"p_{NEVER}": 1.0} for r in rows]
    cuts = {"local": local_cut, **jev_cuts()}
    shown = {**cuts, NEVER: 0.0}
    suites = sorted({r["cluster"].split("/")[0] for r in rows})
    by_suite = {
        s: {arm: arm_table([r for r in rows if r["cluster"].startswith(s + "/")], arm, cut)
            for arm, cut in shown.items()}
        for s in suites
    }  # fmt: skip
    primary = against(rows, "14", cuts)
    return {
        "n": len(rows),
        "done": sum(r["label"] == "done" for r in rows),
        "clusters": len({r["cluster"] for r in rows}),
        "cuts": cuts,
        "arms": {arm: arm_table(rows, arm, cut) for arm, cut in shown.items()},
        "primary_vs_14": primary,
        "secondary_vs_13r": against(rows, "13r", cuts),
        "by_suite": by_suite,
        "verdict": primary["auc"]["verdict"],
    }
