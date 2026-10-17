"""A10 with labels from the target environment: the splits, the cross-fitting and the analysis.
Pure functions, no I/O. Planned in docs/results/2026-10-17-a10-target/plan.md.

THE STOPS are AgentDojo's published runs in banking, travel and workspace, labelled by AgentDojo's
`utility`. A stop's id is its path, `runs/<agent>/<suite>/<task dir>/<attack>/<file>.json`; its
cluster is `<suite>/<task dir>` (the user task, pooled across agents); its injection group is
`<suite>/injection_task_M`, read from the file name when attacked or from the task directory when
the injection task was run as a user task, and none for a benign user-task stop.

THE PLANS are lists of (fit, score) index lists, one per fit:
- `primary_plan`: five folds of whole user-task clusters, assigned within each suite by A10's
  rule (`greedy_folds`, the rule of `train.folds`); fit on four, score the fifth.
- `strict_plan`: the same user-task folds and five folds of injection groups. A fold scores the
  stops whose user task and injection group (if any) both sit in it, and fits on the stops whose
  user task and injection group both sit outside it.
- `agent_plan`: the primary's folds within each agent: a fit sees only the scored stops' agent.

`cross_fit` fits A10's fixed configuration (`CONFIG`, chosen by A10's CV on slack) once per plan
entry, on `a10_data.Example`s only: their `task` and `record` strings and AgentDojo's label. Jev's
recorded probabilities are joined by `jev_scores` for the comparison and never reach a fit.

THE ANALYSIS is A10's: rank AUC, the paired difference with a bootstrap over user-task clusters
(`a10_analysis.paired_auc`: `l4_stats.bootstrap`, 10,000 replicas, seed 20261015) and the rule at
-0.05 AUC.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import a10_analysis as analysis
import a10_model as model
import l4_stats
import lot_stats
from a10_data import Example

FOLDS = 5
CONFIG = model.Config(("w", "c", "l", "s"), 2, 1.0, 2)  # A10's view B, C=1, min_df 2
JEV = "14"  # jev-1.14.0's recorded p(done): `p_14` (checkdone114), `p_old` (checkdone-w17)
ARMS = ("target", "strict", "agent", "a10")

Plan = list[tuple[list[int], list[int]]]


# --- groups ------------------------------------------------------------------------------------


def _parts(stop_id: str) -> list[str]:
    parts = stop_id.split("/")
    return parts[parts.index("runs") :]


def agent_of(stop_id: str) -> str:
    return _parts(stop_id)[1]


def injection_group(stop_id: str) -> str | None:
    _, _, suite, task_dir, _, file = _parts(stop_id)
    if file.startswith("injection_task_"):
        return f"{suite}/{file.removesuffix('.json')}"
    if task_dir.startswith("injection_task_"):
        return f"{suite}/{task_dir}"
    return None


def suite_of(key: str) -> str:
    return key.split("/", 1)[0]


def greedy_folds(sizes: Mapping[str, int], k: int) -> dict[str, int]:
    """A10's rule (`train.folds`): largest group first (ties by name) to the lightest fold."""
    load = [0] * k
    fold_of: dict[str, int] = {}
    for key in sorted(sizes, key=lambda c: (-sizes[c], c)):
        target = min(range(k), key=lambda f: (load[f], f))
        fold_of[key] = target
        load[target] += sizes[key]
    return fold_of


def _stratified(keys: Sequence[str], k: int) -> dict[str, int]:
    """`greedy_folds` within each suite, so every fold holds about 1/k of every suite."""
    out: dict[str, int] = {}
    for suite in sorted({suite_of(key) for key in keys}):
        sizes: dict[str, int] = {}
        for key in keys:
            if suite_of(key) == suite:
                sizes[key] = sizes.get(key, 0) + 1
        out.update(greedy_folds(sizes, k))
    return out


def cluster_folds(examples: Sequence[Example], k: int = FOLDS) -> dict[str, int]:
    return _stratified([e.cluster for e in examples], k)


def injection_folds(examples: Sequence[Example], k: int = FOLDS) -> dict[str, int]:
    groups = [g for g in (injection_group(e.id) for e in examples) if g is not None]
    return _stratified(groups, k)


# --- plans ---------------------------------------------------------------------------------------


def primary_plan(examples: Sequence[Example], k: int = FOLDS) -> Plan:
    fold = cluster_folds(examples, k)
    return [
        ([i for i, e in enumerate(examples) if fold[e.cluster] != f],
         [i for i, e in enumerate(examples) if fold[e.cluster] == f])
        for f in range(k)
    ]  # fmt: skip


def _strict_folds(e: Example, ufold: Mapping[str, int], ifold: Mapping[str, int]) -> set[int]:
    """The folds a stop belongs to: its user task's and its injection group's."""
    group = injection_group(e.id)
    if e.cluster.split("/", 1)[1].startswith("injection_task_"):
        return {ifold[group]}  # an injection task run as a user task: one group, one fold
    return {ufold[e.cluster]} | ({ifold[group]} if group is not None else set())


def strict_plan(examples: Sequence[Example], k: int = FOLDS) -> Plan:
    ufold, ifold = cluster_folds(examples, k), injection_folds(examples, k)
    folds = [_strict_folds(e, ufold, ifold) for e in examples]
    return [
        ([i for i, s in enumerate(folds) if f not in s],
         [i for i, s in enumerate(folds) if s == {f}])
        for f in range(k)
    ]  # fmt: skip


def agent_plan(examples: Sequence[Example], k: int = FOLDS) -> Plan:
    fold = cluster_folds(examples, k)
    plan: Plan = []
    for agent in sorted({e.agent for e in examples}):
        mine = [i for i, e in enumerate(examples) if e.agent == agent]
        for f in range(k):
            score = [i for i in mine if fold[examples[i].cluster] == f]
            if score:
                plan.append(([i for i in mine if fold[examples[i].cluster] != f], score))
    return plan


# --- fitting -------------------------------------------------------------------------------------


def cross_fit(
    examples: Sequence[Example], plan: Plan, config: model.Config = CONFIG
) -> list[float | None]:
    """p(done) for each scored stop from the fit that did not see it; None if never scored."""
    counts = model.counts_of(examples, config)
    p: list[float | None] = [None] * len(examples)
    for fit, score in plan:
        if not fit or set(fit) & set(score):
            raise ValueError("a fit must be non-empty and disjoint from what it scores")
        vec, w, b, _ = model.fit([examples[i] for i in fit], config, [counts[i] for i in fit])
        rows = vec.transform_all([counts[i] for i in score])
        for i, value in zip(score, model.logreg.predict(rows, w, b), strict=True):
            if p[i] is not None:
                raise ValueError(f"stop {examples[i].id} scored twice")
            p[i] = value
    return p


# --- Jev's recorded scores: for the comparison only ---------------------------------------------


def jev_scores(
    checkdone114: Sequence[Mapping[str, Any]], w17: Sequence[Mapping[str, Any]]
) -> dict[str, tuple[str, float]]:
    """id -> (label, jev-1.14.0's p(done)) from checkdone114 (`p_14`) and checkdone-w17's
    confirmation rows (`p_old`, the same record builder). An id in both is refused."""
    out = {r["id"]: (r["label"], r["p_14"]) for r in checkdone114}
    for r in w17:
        if r["set"] != "confirm":
            continue
        if r["id"] in out:
            raise SystemExit(f"stop in both lots: {r['id']}")
        out[r["id"]] = (r["label"], r["p_old"])
    return out


# --- the analysis --------------------------------------------------------------------------------


def _auc(rows: Sequence[Mapping[str, Any]], arm: str) -> float | None:
    found = lot_stats.rank_auc([r[f"p_{arm}"] for r in rows], [r["label"] == "done" for r in rows])
    return None if found is None else round(found, 4)


def per_fold(rows: Sequence[Mapping[str, Any]], arms: Sequence[str]) -> dict[str, Any]:
    folds = sorted({r["fold"] for r in rows})
    table = {str(f): {a: _auc([r for r in rows if r["fold"] == f], a) for a in arms} for f in folds}
    mean = {}
    for a in arms:
        values = [t[a] for t in table.values() if t[a] is not None]
        mean[a] = round(sum(values) / len(values), 4) if values else None
    return {"folds": table, "mean": mean}


def analyse(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    needed = (JEV, "target", "agent", "a10")
    missing = [r["id"] for r in rows if any(r[f"p_{a}"] is None for a in needed)]
    if missing:
        raise SystemExit(f"{len(missing)} stops without a probability, first {missing[:3]}")
    strict = [r for r in rows if r["p_strict"] is not None]
    suites = sorted({suite_of(r["cluster"]) for r in rows})
    agents = sorted({r["agent"] for r in rows})
    primary = analysis.paired_auc(rows, "target", JEV)
    return {
        "n": len(rows),
        "done": sum(r["label"] == "done" for r in rows),
        "clusters": len({r["cluster"] for r in rows}),
        "auc": {a: _auc(rows, a) for a in (JEV, "target", "agent", "a10")},
        "primary": primary,
        "strict": analysis.paired_auc(strict, "strict", JEV),
        "strict_done": sum(r["label"] == "done" for r in strict),
        "agent": analysis.paired_auc(rows, "agent", JEV),
        "by_suite": {
            s: analysis.paired_auc([r for r in rows if suite_of(r["cluster"]) == s], "target", JEV)
            for s in suites
        },
        "by_agent": {
            a: {
                arm: analysis.paired_auc([r for r in rows if r["agent"] == a], arm, JEV)
                for arm in ("target", "agent")
            }
            for a in agents
        },  # fmt: skip
        "a10_vs_jev": analysis.paired_auc(rows, "a10", JEV),
        "target_vs_a10": analysis.paired_auc(rows, "target", "a10"),
        "per_fold": per_fold(rows, (JEV, "target", "agent", "a10")),
        "replicas": l4_stats.BOOT,
        "verdict": primary["verdict"],
    }
