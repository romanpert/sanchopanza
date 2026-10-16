"""The registered analysis of lot A10 (docs/results/2026-10-16-a10-local/prereg.md): the local
classifier against Jev's recorded decisions on the same stops. Pure functions, no I/O.

A row is {"id", "cluster", "label" ("done" | "not_done"), "p_local", "p_14", "p_13r"}. Every arm
blocks a stop when its p(done) is below its cut: the local one at the cut fixed on the training
set, `jev-1.14.0` at 0.30 and `jev-1.13.0` at 0.5 (the cuts lot checkdone114 scored). Jev's
probabilities are read here only to score Jev's own decisions; nothing of them reaches the
classifier.

The statistics are the jev114 lots': exact McNemar and the paired bootstrap of
`l4_stats.paired_binary` (10,000 replicas, user-task clusters and single stops), Wilson intervals
from `sanchopanza.eval.stats`, rank AUC and its cluster bootstrap from `lot_stats`.
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
MARGIN = -0.05  # non-inferiority: the cluster interval's lower bound above -5 points


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


def verdict(result: Mapping[str, Any]) -> str:
    """The registered rule on the user-task cluster interval of (local - Jev) accuracy."""
    ci = result.get("ci95_cluster")
    if result.get("diff") is None or ci is None:
        return "no medido"
    low, high = ci
    if low > 0:
        return "mejor"
    if low > MARGIN:
        return "no peor"
    if high < 0:
        return "peor"
    return "no concluyente"


def paired(
    rows: Sequence[Mapping[str, Any]],
    new: Callable[[Mapping[str, Any]], bool],
    old: Callable[[Mapping[str, Any]], bool],
) -> dict[str, Any]:
    return l4_stats.paired_binary([new(r) for r in rows], [old(r) for r in rows],
                                  [r["cluster"] for r in rows])  # fmt: skip


def against(rows: Sequence[Mapping[str, Any]], arm: str, cuts: Mapping[str, float]) -> dict:
    """Local minus Jev `arm` on the same stops: right decisions (the verdict), finished stops
    not falsely blocked, unfinished stops caught, and AUC."""
    local, cut = cuts["local"], cuts[arm]
    done = [r for r in rows if r["label"] == "done"]
    unfinished = [r for r in rows if r["label"] == "not_done"]
    accuracy = paired(rows, lambda r: right(r, "local", local), lambda r: right(r, arm, cut))
    accuracy["verdict"] = verdict(accuracy)
    return {
        "accuracy": accuracy,
        "not_falsely_blocked": paired(done, lambda r: not blocks(r["p_local"], local),
                                      lambda r: not blocks(r[f"p_{arm}"], cut)),
        "caught": paired(unfinished, lambda r: blocks(r["p_local"], local),
                         lambda r: blocks(r[f"p_{arm}"], cut)),
        "auc": lot_stats.paired_auc([r["label"] == "done" for r in rows],
                                    [r["p_local"] for r in rows], [r[f"p_{arm}"] for r in rows],
                                    [r["cluster"] for r in rows]),
    }  # fmt: skip


def analyse(rows: Sequence[Mapping[str, Any]], local_cut: float) -> dict[str, Any]:
    missing = [r["id"] for r in rows if None in (r["p_local"], r["p_14"], r["p_13r"])]
    if missing:
        raise SystemExit(f"{len(missing)} stops without a probability, first {missing[:3]}")
    cuts = {"local": local_cut, **jev_cuts()}
    suites = sorted({r["cluster"].split("/")[0] for r in rows})
    by_suite = {
        s: {arm: arm_table([r for r in rows if r["cluster"].startswith(s + "/")], arm, cut)
            for arm, cut in cuts.items()}
        for s in suites
    }  # fmt: skip
    primary = against(rows, "14", cuts)
    return {
        "n": len(rows),
        "done": sum(r["label"] == "done" for r in rows),
        "clusters": len({r["cluster"] for r in rows}),
        "cuts": cuts,
        "arms": {arm: arm_table(rows, arm, cut) for arm, cut in cuts.items()},
        "primary_vs_14": primary,
        "secondary_vs_13r": against(rows, "13r", cuts),
        "by_suite": by_suite,
        "verdict": primary["accuracy"]["verdict"],
    }
