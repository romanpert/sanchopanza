"""Verdict pieces the 2026-10-16 lots share (checkdone114, redundant_drop). Pure functions, no
network; `launch_status` reads the launch log `lot.publish` copied into the results directory.

- `verdict_of`: `jev114_paired.verdict` on a cluster interval, except that "mejora" also needs
  the interval's lower bound above 0 (the exact McNemar p is unclustered, so anticonservative
  when cases cluster);
- `answer_gaps`: the share of cases each arm left unanswered, their union, and 1.14's excess
  over 1.13 (FAILURE_GAP, as in lot L4);
- `launch_status`: no verdict at all unless the last launch completed;
- `paired_auc`: rank AUC of each arm and a cluster interval of the difference, descriptive.
"""

from __future__ import annotations

import json
import random
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import jev114_paired as paired  # noqa: E402

MISSING = 0.02  # union of unanswered cases above this: no favourable verdict
FAILURE_GAP = 0.02  # 1.14 unanswered minus 1.13 unanswered above this: no favourable verdict
FAVOURABLE = ("no peor", "mejora")


def verdict_of(diff: float | None, ci: Sequence[float] | None, p: float) -> str:
    if diff is None or ci is None:
        return "no medido"
    found = paired.verdict(diff, ci[0], ci[1], p)
    if found == "mejora" and ci[0] <= 0:
        return paired.verdict(diff, ci[0], ci[1], 1.0)  # "no peor" or "no concluyente"
    return found


def answer_gaps(rows: Sequence[Mapping[str, Any]], key: str = "p_{}") -> dict[str, float]:
    n = len(rows) or 1
    miss = {arm: sum(r[key.format(arm)] is None for r in rows) / n for arm in ("13r", "14")}
    union = sum(any(r[key.format(a)] is None for a in ("13r", "14")) for r in rows) / n
    return {"missing_13r": round(miss["13r"], 4), "missing_14": round(miss["14"], 4),
            "missing_union": round(union, 4),
            "failure_gap": round(miss["14"] - miss["13r"], 4)}  # fmt: skip


def gaps_allow_favourable(gaps: Mapping[str, float]) -> bool:
    return gaps["missing_union"] <= MISSING and gaps["failure_gap"] <= FAILURE_GAP


def launch_status(out: Path) -> str:
    """'complete' when the last line of the copied launch log says so, else what it says."""
    path = out / "launches.jsonl"
    if not path.exists():
        return "no launch log"
    lines = [x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    try:
        last = json.loads(lines[-1]) if lines else {}
    except ValueError:
        return "unreadable launch log"
    return str(last.get("outcome") or "empty launch log")


def rank_auc(scores: Sequence[float], labels: Sequence[bool]) -> float | None:
    """Mann-Whitney AUC by ranks, ties at their mean rank: `recalconf_analysis.auc`, kept here
    so the sealed analysis does not import a published lot's module (a test pins they agree)."""
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


def paired_auc(
    labels: Sequence[bool], new: Sequence[float], old: Sequence[float], clusters: Sequence[str],
    *, replicas: int = 2000, seed: int = 7,
) -> dict[str, Any]:  # fmt: skip
    """AUC of each arm (`rank_auc`) and the difference's 95 % interval by a paired bootstrap
    over clusters. `l4_stats.paired_auc` counts pairs, too slow here."""

    def area(scores: Sequence[float], idx: Sequence[int]) -> float | None:
        return rank_auc([scores[i] for i in idx], [labels[i] for i in idx])

    everything = list(range(len(labels)))
    whole = {"new": area(new, everything), "old": area(old, everything)}
    if None in whole.values():
        return {"n": len(labels), "new": None, "old": None, "diff": None, "ci95_cluster": None}
    groups: dict[str, list[int]] = {}
    for i, key in enumerate(clusters):
        groups.setdefault(key, []).append(i)
    units, rng, diffs = list(groups.values()), random.Random(seed), []
    for _ in range(replicas):
        idx = [i for _ in units for i in units[rng.randrange(len(units))]]
        a, b = area(new, idx), area(old, idx)
        if a is not None and b is not None:
            diffs.append(a - b)
    diffs.sort()
    ci = (round(diffs[int(0.025 * (len(diffs) - 1))], 4),
          round(diffs[int(0.975 * (len(diffs) - 1))], 4))  # fmt: skip
    return {"n": len(labels), "positives": sum(labels), "new": round(whole["new"], 4),
            "old": round(whole["old"], 4), "diff": round(whole["new"] - whole["old"], 4),
            "ci95_cluster": ci}  # fmt: skip
