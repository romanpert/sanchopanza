"""Analysis of lot memgate-long (benchmarks/memgate_long/memgate_long.py), as registered in
docs/results/2026-10-15-memgate-long/prereg.md. Pure functions over the scored rows, no I/O.

The gate's reading of a row, its recall, the paired bootstrap and the Holm family are lot L6's
(`l6_analysis`, `l4_stats`), imported, not copied. One model: jev-1.13.0 (`j13r`), two windows.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from statistics import NormalDist
from typing import Any

import l4_stats as st
import l6_analysis as an

CELL_L, CELL_S = "j13r-L", "j13r-S"
LIVE = (CELL_S, CELL_L)
BM25 = "bm25@3"
REFERENCE = "rec13-S"  # the gate recorded on 2026-09-28 (jev-1.13.0), replayed free
CELLS = (BM25, REFERENCE, CELL_S, CELL_L)
PRIMARY = "recall_window_j13r"  # recall L - S on 1.13: the confirmation, a Holm family of one
MIN_QUESTIONS = 20  # L6's A7_MIN_QUESTIONS: fewer complete questions give "n bajo"
ALCANZA = -0.03  # L6: "alcanza" when recall minus bm25@3 >= -0.03 (criteria H and C's margin)
Z95 = 1.959964
Z80 = 0.841621


def complete_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The questions where both live cells (and the look) answered."""
    return [r for r in rows if all(an.a7_chosen(r, c) is not None for c in LIVE)]


def _failed(row: Mapping[str, Any], cell: str) -> bool:
    return an.a7_chosen(row, cell) is None


def errors_by_class(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Per cell (and the look), how many questions failed with each class (`ReadTimeout`,
    `HTTP400`...): the rows' `errors`, the class of each cell's first failed call."""
    out: dict[str, dict[str, int]] = {}
    for row in rows:
        for cell, label in (row.get("errors") or {}).items():
            counts = out.get(cell, {})
            out = out | {cell: counts | {label: counts.get(label, 0) + 1}}
    return {c: dict(sorted(v.items())) for c, v in sorted(out.items())}


def window_diff(complete: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Recall L - S on the same questions: paired bootstrap over questions (L4/L6's)."""
    return an.paired_stat(lambda i: an._recall(complete, CELL_L, i),
                          lambda i: an._recall(complete, CELL_S, i), len(complete))  # fmt: skip


def bm25_diff(complete: Sequence[Mapping[str, Any]], cell: str) -> dict[str, Any]:
    return an.paired_stat(lambda i: an._recall(complete, cell, i),
                          lambda i: an._recall(complete, BM25, i), len(complete))  # fmt: skip


def confirmation_verdict(result: Mapping[str, Any], gap: float, n: int,
                         min_questions: int = MIN_QUESTIONS) -> str:  # fmt: skip
    """The registered rule (1): "confirmado" iff the paired 95 % CI of recall L - S has its
    lower bound above 0, on at least `min_questions` complete questions, and L failed on no
    more than 2 % more questions than S (L6's failure-gap rule)."""
    if n < min_questions:
        return "no concluyente (n bajo)"
    ci = result.get("ci95")
    if result.get("diff") is None or ci is None:
        return "no medido"
    if gap > st.FAILURE_GAP:
        return "no confirmado (fallos)"
    return "confirmado" if ci[0] > 0 else "no confirmado"


def bm25_verdict(result: Mapping[str, Any], n: int, min_questions: int = MIN_QUESTIONS) -> str:
    """The registered rule (2), L6's definitions: "bate" when the paired CI of recall minus
    bm25@3 is above 0 (the original criterion 1); else "alcanza" when the point estimate is
    >= -0.03; else "no alcanza"."""
    if n < min_questions:
        return "no concluyente (n bajo)"
    ci, diff = result.get("ci95"), result.get("diff")
    if diff is None or ci is None:
        return "no medido"
    if ci[0] > 0:
        return "bate"
    return "alcanza" if diff >= ALCANZA else "no alcanza"


def describe(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per cell over the complete questions: recall (primary), any-hit, all-hit, characters
    injected, precision (L6's `a7_cell`); and the L - S and against-BM25 differences."""
    complete = complete_rows(rows)
    present = [c for c in CELLS if any(an.a7_chosen(r, c) is not None for r in complete)
               or c == BM25]  # fmt: skip
    return {
        "launched": len(rows), "complete": len(complete),
        "cells": {c: an.a7_cell(complete, c) for c in present},
        "window_L_minus_S": window_diff(complete),
        "against_bm25@3": {c: bm25_diff(complete, c) for c in LIVE},
    }  # fmt: skip


def analyse(rows: Sequence[Mapping[str, Any]], *, min_questions: int = MIN_QUESTIONS,
            l6_rows: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:  # fmt: skip
    """The registered reading of the 84 questions, and (with `l6_rows`) the pooled 120,
    descriptive only."""
    complete = complete_rows(rows)
    n = len(complete)
    out: dict[str, Any] = describe(rows)
    out["excerpt_ceiling"] = [sum(r["excerpt_seen"] for r in complete),
                              sum(r["excerpt_total"] for r in complete)]  # fmt: skip
    out["look_rate"] = an._r(sum(bool(r.get("j13r-look")) for r in complete) / max(1, n))
    out["failures"] = {c: sum(_failed(r, c) for r in rows) for c in (*LIVE, REFERENCE)}
    out["errors_by_class"] = errors_by_class(rows)
    out["recall_failure_as_empty"] = {
        c: an._r(an._recall(rows, c, range(len(rows)), empty_on_failure=True)) for c in CELLS
    }
    gap = an.failure_rate(rows, CELL_L, _failed) - an.failure_rate(rows, CELL_S, _failed)
    family = an.family({PRIMARY: out["window_L_minus_S"]}, {PRIMARY: gap})  # Holm over one
    out["family"] = family
    out["confirmation"] = {
        "comparison": PRIMARY, "n": n, "failure_gap": round(gap, 4),
        "diff": family[PRIMARY]["diff"], "ci95": family[PRIMARY]["ci95"],
        "p_holm": family[PRIMARY]["p_holm"], "l6_rule": family[PRIMARY]["verdict"],
        "verdict": confirmation_verdict(family[PRIMARY], gap, n, min_questions),
    }  # fmt: skip
    out["bm25_verdicts"] = {
        c: bm25_verdict(out["against_bm25@3"][c], n, min_questions) for c in LIVE
    }
    if l6_rows is not None:
        pooled = [*l6_rows, *rows]
        out["pooled_120_descriptive"] = describe(pooled) | {
            "note": "descriptive: the 36 of L6 generated the hypothesis; no verdict"
        }
    return out


# ---- power, from L6's 36 questions ------------------------------------------------------------


def projected_se(result: Mapping[str, Any], n_from: int, n_to: int) -> float | None:
    """The standard error a paired difference would have on `n_to` questions, from the 95 % CI
    it had on `n_from` (normal approximation, SE shrinking with the square root of n)."""
    ci = result.get("ci95")
    if ci is None or n_from == 0:
        return None
    return (ci[1] - ci[0]) / (2 * Z95) * (n_from / n_to) ** 0.5


def power(l6_rows: Sequence[Mapping[str, Any]], n: int) -> dict[str, Any]:
    """What `n` questions resolve, given L6's j13r effect on its 36: the chance that the CI's
    lower bound clears 0 for the L6 effect and for half of it, the effect 80 % power detects,
    and the chance that "alcanza" reads true at L6's -3.08 points and at 0."""
    complete = complete_rows(l6_rows)
    window = window_diff(complete)
    versus = bm25_diff(complete, CELL_L)
    se_w = projected_se(window, len(complete), n)
    se_b = projected_se(versus, len(complete), n)
    if not se_w or not se_b or window["diff"] is None:  # none, or a degenerate zero spread
        return {"n": n, "from": len(complete), "se": None}
    phi = NormalDist().cdf
    effect = window["diff"]
    return {
        "n": n, "from": len(complete),
        "l6_window": {k: window[k] for k in ("diff", "ci95")},
        "l6_against_bm25": {k: versus[k] for k in ("diff", "ci95")},
        "se_window": round(se_w, 4), "se_against_bm25": round(se_b, 4),
        "power_at_l6_effect": round(phi(effect / se_w - Z95), 3),
        "power_at_half": round(phi(effect / 2 / se_w - Z95), 3),
        "mde80": round((Z95 + Z80) * se_w, 4),
        "p_alcanza_at_l6_diff": round(phi((versus["diff"] - ALCANZA) / se_b), 3),
        "p_alcanza_at_0": round(phi((0 - ALCANZA) / se_b), 3),
    }  # fmt: skip
