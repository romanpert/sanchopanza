"""Paired comparison of two Jev versions on the same cases: items, tests, verdicts.

Pure functions over the per-case rows `jev114_components.py` writes; no network, no files. The rules
are the ones sealed in `docs/results/2026-10-15-jev114-l1/prereg.md`:

- an item is one case (one binary item per question for `memory_collision` without a cut);
- "with thresholds": the item is right when the shipped policy decided it and decided it right
  (an abstention is not right); rows the code layer decided (no model call) are left out;
- "without a threshold": a probability read at 0.5, a Choice read at its argmax, and AUC;
- a pair counts only when both arms answered it (no failed call in either);
- difference = 1.14 minus 1.13r, 95 % CI by paired bootstrap (2000 replicas, seed 7), exact
  McNemar; verdict "mejora" (> 0, Holm p < 0.05), "no peor" (CI low > -0.02), "peor" (CI high
  < 0), else "no concluyente".
"""

from __future__ import annotations

import math
import random
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.eval.bench import BINARY_POINTS, POSITIVE_LABEL  # noqa: E402
from sanchopanza.eval.stats import auc, bootstrap_difference, mcnemar  # noqa: E402

MARGIN = 0.02  # "no peor": the CI's lower bound must clear minus two points
ALPHA = 0.05
CITATION_LABEL = {"supports": "supported", "contradicts": "contradicted",
                  "says_nothing": "unsupported"}  # fmt: skip


def failed(row: Mapping[str, Any]) -> bool:
    """A call errored or came back without answers: the case was not judged by the model."""
    return any(c.get("error") or not c.get("answers") for c in row.get("calls", ()))


def capped(row: Mapping[str, Any]) -> bool:
    return any(c.get("capped") for c in row.get("calls", ()))


def code_only(row: Mapping[str, Any]) -> bool:
    return row.get("provider") == "code" or not row.get("calls")


def _answer(row: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    for call in row.get("calls", ()):
        found = (call.get("answers") or {}).get(key)
        if found is not None:
            return found
    return None


def policy_item(row: Mapping[str, Any]) -> bool | None:
    """Right under the shipped policy; None when the model was not asked."""
    if "correct" not in row or code_only(row):
        return None
    return bool(row.get("decided")) and bool(row.get("correct"))


def collision_truths(expected: str, newer: bool | None) -> dict[str, bool | None]:
    """`benchmarks/collision.py:truths`, the inverse of `decide_collision`."""
    if expected == "duplicate":
        return {"adds_nothing": True, "contradicts": None}
    if expected in ("replace", "flag"):
        return {"adds_nothing": False, "contradicts": True}
    return {"adds_nothing": False, "contradicts": newer is False}


def free_items(row: Mapping[str, Any]) -> list[tuple[str, float, bool]]:
    """(item key, score, truth) read without a threshold; empty where none is defined."""
    if code_only(row) or "point" not in row:
        return []
    point, rid, expected = row["point"], row["id"], row.get("expected")
    positive = POSITIVE_LABEL.get(point)
    if point == "supersede":  # a failed or partial answer sends back: scored 0
        return [(rid, float(row.get("score") or 0.0), expected == 1)]
    if point in BINARY_POINTS and row.get("probability") is not None and point != "steerability":
        truth = bool(expected) if positive is None else expected == positive
        return [(rid, float(row["probability"]), truth)]
    if point in ("triage", "steerability"):
        found = _answer(row, "relevant")
        if found is None or found.get("truth") is None:
            return []
        return [(rid, float(found["truth"]), expected == "keep")]
    if point == "memory_collision":
        out = []
        for name, truth in collision_truths(str(expected), row.get("newer")).items():
            found = _answer(row, name)
            if truth is not None and found is not None and found.get("truth") is not None:
                out.append((f"{rid}:{name}", float(found["truth"]), truth))
        return out
    if point in ("citation", "numeric_citation"):
        found = _answer(row, "relation")
        probs = (found or {}).get("probabilities") or {}
        if not probs:
            return []
        top = max(probs, key=lambda k: probs[k])
        right = CITATION_LABEL.get(top) == expected
        return [(rid, 1.0 if right else 0.0, True)]  # a Choice: right at its argmax or not
    return []


def free_correct(score: float, truth: bool) -> bool:
    return (score >= 0.5) == truth


def holm(pvalues: Mapping[str, float]) -> dict[str, float]:
    """Holm-adjusted p per name (step-down, monotone)."""
    ordered = sorted(pvalues.items(), key=lambda kv: kv[1])
    out, running, m = {}, 0.0, len(ordered)
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * p))
        out[name] = running
    return out


def verdict(diff: float, low: float, high: float, p_adjusted: float) -> str:
    if diff > 0 and p_adjusted < ALPHA:
        return "mejora"
    if low > -MARGIN:
        return "no peor"
    if high < 0:
        return "peor"
    return "no concluyente"


def compare(base: Mapping[str, bool], new: Mapping[str, bool]) -> dict[str, Any]:
    """Paired accuracy of `new` (1.14) against `base` (1.13r) on the keys both have."""
    keys = sorted(set(base) & set(new))
    if not keys:
        return {"n": 0}
    a, b = [base[k] for k in keys], [new[k] for k in keys]
    diff, low, high = bootstrap_difference(b, a)
    only_new, only_base, p = mcnemar(b, a)
    return {"n": len(keys), "base": sum(a), "new": sum(b), "diff": diff, "low": low,
            "high": high, "only_new": only_new, "only_base": only_base, "p": p}  # fmt: skip


def auc_compare(
    base: Mapping[str, tuple[str, float, bool]],
    new: Mapping[str, tuple[str, float, bool]],
    *, replicas: int = 2000, seed: int = 7,
) -> dict[str, Any]:  # fmt: skip
    """Macro AUC over groups (points) with both classes, 1.14 minus 1.13r, paired bootstrap
    resampling items within each group. Values are (group, score, truth) per item key."""
    keys = sorted(set(base) & set(new))
    groups: dict[str, list[str]] = defaultdict(list)
    for k in keys:
        groups[base[k][0]].append(k)
    usable = {g: ks for g, ks in groups.items()
              if len({base[k][2] for k in ks}) == 2}  # fmt: skip
    if not usable:
        return {"groups": 0}

    def macro(sample: Mapping[str, Sequence[str]], arm: Mapping[str, tuple[str, float, bool]]):
        values = []
        for ks in sample.values():
            v = auc([arm[k][1] for k in ks], [arm[k][2] for k in ks])
            if not math.isnan(v):
                values.append(v)
        return sum(values) / len(values) if values else float("nan")

    observed = macro(usable, new) - macro(usable, base)
    rng = random.Random(seed)
    diffs = []
    for _ in range(replicas):
        sample = {g: [ks[rng.randrange(len(ks))] for _ in ks] for g, ks in usable.items()}
        d = macro(sample, new) - macro(sample, base)
        if not math.isnan(d):
            diffs.append(d)
    diffs.sort()
    per_group = {g: {"n": len(ks), "base": auc([base[k][1] for k in ks], [base[k][2] for k in ks]),
                     "new": auc([new[k][1] for k in ks], [new[k][2] for k in ks])}
                 for g, ks in sorted(usable.items())}  # fmt: skip
    return {"groups": len(usable), "base": macro(usable, base), "new": macro(usable, new),
            "diff": observed, "low": diffs[int(0.025 * len(diffs))],
            "high": diffs[int(0.975 * len(diffs)) - 1], "per_group": per_group}  # fmt: skip


def concordance(scores: Sequence[float], levels: Sequence[int]) -> float:
    """Ordinal AUC: over pairs of different level, how often the higher level scores higher."""
    total = wins = 0.0
    for i in range(len(scores)):
        for j in range(len(scores)):
            if levels[i] > levels[j]:
                total += 1
                wins += 1.0 if scores[i] > scores[j] else 0.5 if scores[i] == scores[j] else 0.0
    return wins / total if total else float("nan")
