"""Analysis of lot L6 (benchmarks/jev114/l6.py), as registered in
docs/results/2026-10-15-jev114-l6/prereg.md. Pure functions over the scored rows, no I/O.

Each experiment is one family for Holm. The resampling unit is the item (a task, a paper, a
question); the paired bootstrap, McNemar and the verdict rule are lot L4's (`l4_stats`).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import l4_stats as st

MODELS = ("j13r", "j14")
WINDOWS = ("S", "L")
PRIMARY_B3 = "j14-L"  # the cell whose substitution verdict answers the product question


def _r(x: float | None, k: int = 4) -> float | None:
    return None if x is None else round(x, k)


def paired_stat(
    stat_new: Callable[[list[int]], float | None],
    stat_old: Callable[[list[int]], float | None],
    n: int,
) -> dict[str, Any]:
    """new - old for any statistic of a resample of items; CI and p by paired bootstrap
    (p = twice the smaller share of resampled differences on either side of 0)."""

    def diff(idx: list[int]) -> float | None:
        a, b = stat_new(idx), stat_old(idx)
        return None if a is None or b is None else a - b

    whole = list(range(n))
    d = diff(whole) if n else None
    if d is None:
        return {"n": n, "diff": None, "p": 1.0, "ci95": None}
    diffs = st.bootstrap(diff, st.items_as_units(n))
    p = 2 * min(sum(x <= 0 for x in diffs), sum(x >= 0 for x in diffs)) / len(diffs)
    return {"n": n, "new": _r(stat_new(whole)), "old": _r(stat_old(whole)), "diff": _r(d),
            "p": round(min(1.0, p), 4), "ci95": st.ci95(diffs)}  # fmt: skip


def binary(new: Sequence[bool], old: Sequence[bool], ids: Sequence[str]) -> dict[str, Any]:
    out = st.paired_binary(list(new), list(old), list(ids))
    return {k: v for k, v in out.items() if k != "ci95_cluster"}


def family(results: Mapping[str, dict[str, Any]], gaps: Mapping[str, float]) -> dict[str, Any]:
    adjusted = st.holm({k: (v.get("p", 1.0) if v.get("diff") is not None else 1.0)
                        for k, v in results.items()})  # fmt: skip
    return {k: v | {"p_holm": adjusted[k], "verdict": st.verdict(v, adjusted[k], gaps.get(k, 0))}
            for k, v in results.items()}  # fmt: skip


def wilson(k: int, n: int) -> tuple[float, float] | None:
    if n == 0:
        return None
    z = 1.959964
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    return (round(centre - half, 4), round(centre + half, 4))


def failure_rate(rows: Sequence[Mapping[str, Any]], cell: str,
                 failed: Callable[[Mapping[str, Any], str], bool]) -> float:  # fmt: skip
    return sum(failed(r, cell) for r in rows) / len(rows) if rows else 0.0


# ---- B3 ---------------------------------------------------------------------------------------


def _b3_failed(row: Mapping[str, Any], cell: str) -> bool:
    return not row.get(cell) or row[cell].get("letter") is None


def _b3_right(row: Mapping[str, Any], cell: str) -> bool:
    return not _b3_failed(row, cell) and row[cell]["letter"] == row["gold"]


def _b3_auc(rows: Sequence[Mapping[str, Any]], cell: str, idx: Sequence[int]) -> float | None:
    """AUC of the cell's top probability for its own right against its own wrong answers."""
    pos = [rows[i][cell]["p"] for i in idx if _b3_right(rows[i], cell)]
    neg = [rows[i][cell]["p"] for i in idx
           if not _b3_failed(rows[i], cell) and not _b3_right(rows[i], cell)]  # fmt: skip
    return st.auc(pos, neg)


def substitution(rows: Sequence[Mapping[str, Any]], cell: str, cut: float) -> dict[str, Any]:
    """Jev answers alone where its top probability >= cut, Sonnet (recorded) elsewhere."""
    rows = [r for r in rows if r.get("sonnet")]
    n = len(rows)
    covered = [not _b3_failed(r, cell) and r[cell]["p"] >= cut for r in rows]
    jev_right = [_b3_right(r, cell) for r in rows]
    sonnet_right = [bool(r["sonnet"]["ok"]) for r in rows]
    hybrid = [j if c else s for c, j, s in zip(covered, jev_right, sonnet_right, strict=True)]
    k = sum(covered)
    right_cov = sum(j for c, j in zip(covered, jev_right, strict=True) if c)
    sonnet_cov = sum(s for c, s in zip(covered, sonnet_right, strict=True) if c)
    sonnet_usd = sum(r["sonnet"]["usd"] for r in rows)
    saved = sum(r["sonnet"]["usd"] for r, c in zip(rows, covered, strict=True) if c)
    jev_usd = sum((r.get(cell) or {}).get("usd", 0.0) for r in rows)
    out = {
        "cut": cut, "n": n, "covered": k, "coverage": _r(k / n if n else None),
        "precision": _r(right_cov / k if k else None), "precision_wilson95": wilson(right_cov, k),
        "sonnet_on_covered": _r(sonnet_cov / k if k else None),
        "hybrid_vs_sonnet": binary(hybrid, sonnet_right, [r["id"] for r in rows]),
        "sonnet_usd_total": round(sonnet_usd, 4), "sonnet_usd_saved": round(saved, 4),
        "jev_usd": round(jev_usd, 4),
        "net_saving_share": _r((saved - jev_usd) / sonnet_usd if sonnet_usd else None),
    }  # fmt: skip
    return out


def substitution_verdict(sub: Mapping[str, Any], tau: float, min_cov: float,
                         min_prec: float) -> str:  # fmt: skip
    ci = sub["hybrid_vs_sonnet"].get("ci95")
    ok = ((sub["coverage"] or 0) >= min_cov and (sub["precision"] or 0) >= min_prec
          and ci is not None and ci[0] > st.NOT_WORSE)  # fmt: skip
    return "sustituye" if ok else "no sustituye"


def b3_cell(rows: Sequence[Mapping[str, Any]], cell: str, cuts: Sequence[float]) -> dict:
    answered = [r for r in rows if not _b3_failed(r, cell)]
    letters = Counter(r[cell]["letter"] for r in answered)
    return {
        "n": len(rows), "answered": len(answered),
        "accuracy_all": _r(sum(_b3_right(r, cell) for r in rows) / len(rows) if rows else None),
        "accuracy_answered": _r(sum(_b3_right(r, cell) for r in answered) / len(answered)
                                if answered else None),
        "auc": _r(_b3_auc(rows, cell, range(len(rows)))),
        "letters": dict(sorted(letters.items())),
        "usd": round(sum((r.get(cell) or {}).get("usd", 0.0) for r in rows), 4),
        "tokens_mean": round(sum((r.get(cell) or {}).get("tokens", 0) for r in rows)
                             / max(1, len(rows))),
        "sweep": [substitution(rows, cell, c) for c in cuts],
    }  # fmt: skip


def analyse_b3(rows: Sequence[Mapping[str, Any]], *, cuts: Sequence[float], tau: float,
               min_cov: float, min_prec: float) -> dict[str, Any]:  # fmt: skip
    cells = [f"{m}-{w}" for w in WINDOWS for m in MODELS]
    out: dict[str, Any] = {"n": len(rows), "cells": {c: b3_cell(rows, c, cuts) for c in cells}}
    sonnet = [r for r in rows if r.get("sonnet")]
    out["sonnet"] = {
        "n": len(sonnet),
        "right": sum(r["sonnet"]["ok"] for r in sonnet),
        "usd": round(sum(r["sonnet"]["usd"] for r in sonnet), 4),
        "gold_letters": dict(sorted(Counter(r["gold"] for r in rows).items())),
    }
    pairs = {
        "acc_model_S": ("j14-S", "j13r-S"),
        "acc_model_L": ("j14-L", "j13r-L"),
        "acc_window_j13r": ("j13r-L", "j13r-S"),
        "acc_window_j14": ("j14-L", "j14-S"),
    }
    comps, gaps = {}, {}
    for name, (new, old) in pairs.items():
        both = [r for r in rows if not _b3_failed(r, new) and not _b3_failed(r, old)]
        comps[name] = binary([_b3_right(r, new) for r in both], [_b3_right(r, old) for r in both],
                             [r["id"] for r in both])  # fmt: skip
        gaps[name] = failure_rate(rows, new, _b3_failed) - failure_rate(rows, old, _b3_failed)
    for w in WINDOWS:
        new, old = f"j14-{w}", f"j13r-{w}"
        both = [r for r in rows if not _b3_failed(r, new) and not _b3_failed(r, old)]
        comps[f"auc_model_{w}"] = paired_stat(lambda i, c=new, b=both: _b3_auc(b, c, i),
                                              lambda i, c=old, b=both: _b3_auc(b, c, i),
                                              len(both))  # fmt: skip
        gaps[f"auc_model_{w}"] = gaps[f"acc_model_{w}"]
    out["family"] = family(comps, gaps)
    out["substitution"] = {}
    out["substitution_primary"] = PRIMARY_B3
    for cell in cells:
        sub = substitution(rows, cell, tau)
        out["substitution"][cell] = sub | {
            "verdict": substitution_verdict(sub, tau, min_cov, min_prec)
        }
    return out


# ---- A6 ---------------------------------------------------------------------------------------


def _a6_mask(row: Mapping[str, Any], arm: str) -> list[bool] | None:
    got = row.get(arm)
    return None if not got else list(got["keep"])


def _a6_scores(row: Mapping[str, Any], mask: Sequence[bool]) -> tuple[bool, bool, float, int]:
    hits = [m for m, g in zip(mask, row["gold"], strict=True) if g]
    sizes = row["sizes"]
    share = sum(s for s, m in zip(sizes, mask, strict=True) if m) / sum(sizes)
    return all(hits), any(hits), share, sum(mask)


def budget_mask(row: Mapping[str, Any], arm: str, share: float) -> list[bool] | None:
    """Paragraphs by probability (unanswered last, then position), the longest prefix within
    `share` of the paper's characters: the threshold-free reading of P28."""
    got = row.get(arm)
    if not got:
        return None
    sizes, ps = row["sizes"], got["p"]
    order = sorted(range(len(sizes)), key=lambda i: (ps[i] is None, -(ps[i] or 0.0), i))
    room, used, mask = share * sum(sizes), 0.0, [False] * len(sizes)
    for i in order:
        if used + sizes[i] > room:
            break
        used += sizes[i]
        mask[i] = True
    return mask


def _paper_auc(row: Mapping[str, Any], arm: str) -> float | None:
    got = row.get(arm)
    if not got:
        return None
    ps = [p if p is not None else 0.5 for p in got["p"]]
    pos = [p for p, g in zip(ps, row["gold"], strict=True) if g]
    neg = [p for p, g in zip(ps, row["gold"], strict=True) if not g]
    return st.auc(pos, neg)


def a6_arm(rows: Sequence[Mapping[str, Any]], arm: str, share: float) -> dict[str, Any]:
    """Over every paper. A failed paper reads as production does (`triage_pages` keeps an
    unanswered page): every paragraph kept at the cut; within the budget, nothing ranked, so
    no evidence kept."""
    if not rows:
        return {"n": 0}

    def at(row: Mapping[str, Any], mask: list[bool] | None, fallback: bool) -> tuple:
        return _a6_scores(row, mask if mask is not None else [fallback] * len(row["sizes"]))

    at_cut = [at(r, _a6_mask(r, arm), True) for r in rows]
    at_budget = [at(r, budget_mask(r, arm, share), False) for r in rows]
    aucs = [a for a in (_paper_auc(r, arm) for r in rows) if a is not None]
    n = len(rows)
    all_e = sum(x[0] for x in at_cut) / n
    kept = sum(x[2] for x in at_cut) / n
    return {
        "n": n, "failed": sum(not r.get(arm) for r in rows),
        "all_evidence": _r(all_e), "any_evidence": _r(sum(x[1] for x in at_cut) / n),
        "kept_share": _r(kept), "paragraphs_kept": round(sum(x[3] for x in at_cut) / n, 2),
        "P28": all_e >= 0.85 and kept <= 0.25,
        "budget_all_evidence": _r(sum(x[0] for x in at_budget) / n),
        "budget_kept_share": _r(sum(x[2] for x in at_budget) / n),
        "paper_auc_mean": _r(sum(aucs) / len(aucs) if aucs else None),
    }  # fmt: skip


def analyse_a6(rows: Sequence[Mapping[str, Any]], *, share: float) -> dict[str, Any]:
    arms = ("rec13-S", "j13r-L", "j14-L")
    out: dict[str, Any] = {"n": len(rows), "arms": {a: a6_arm(rows, a, share) for a in arms}}
    comps, gaps = {}, {}
    for tag, (new, old) in {"model": ("j14-L", "j13r-L"), "window": ("j13r-L", "rec13-S")}.items():
        both = [r for r in rows if r.get(new) and r.get(old)]
        ids = [r["id"] for r in both]
        gap = (sum(not r.get(new) for r in rows) - sum(not r.get(old) for r in rows)) / len(rows)
        cut = {a: [_a6_scores(r, _a6_mask(r, a)) for r in both] for a in (new, old)}
        bud = {a: [_a6_scores(r, budget_mask(r, a, share)) for r in both] for a in (new, old)}
        comps[f"{tag}_all_evidence"] = binary([x[0] for x in cut[new]], [x[0] for x in cut[old]],
                                              ids)  # fmt: skip
        comps[f"{tag}_budget_all_evidence"] = binary(
            [x[0] for x in bud[new]], [x[0] for x in bud[old]], ids
        )
        # Less text is better: the difference is old - new, the share of the paper saved.
        comps[f"{tag}_text_saved"] = paired_stat(
            lambda i, c=cut[old]: sum(c[k][2] for k in i) / len(i),
            lambda i, c=cut[new]: sum(c[k][2] for k in i) / len(i),
            len(both),
        )
        for k in ("all_evidence", "budget_all_evidence", "text_saved"):
            gaps[f"{tag}_{k}"] = gap
    out["family"] = family(comps, gaps)
    return out


# ---- A7 ---------------------------------------------------------------------------------------


def a7_chosen(row: Mapping[str, Any], cell: str) -> set[int] | None:
    """The gate's sessions: the triage when `needs_recall` looked, none when it did not; None
    when the triage or the recall step failed."""
    if cell == "bm25@3":
        return set(row["bm25@3"])
    model = cell.split("-")[0]
    kept, look = row.get(cell), row.get(f"{model}-look")
    if kept is None or look is None:
        return None
    return set(kept) if look else set()


def _recall(rows: Sequence[Mapping[str, Any]], cell: str, idx: Sequence[int],
            empty_on_failure: bool = False) -> float | None:  # fmt: skip
    def chosen(row: Mapping[str, Any]) -> set[int]:
        got = a7_chosen(row, cell)
        return set() if got is None and empty_on_failure else got

    hit = sum(len(chosen(rows[i]) & set(rows[i]["gold"])) for i in idx)
    total = sum(len(rows[i]["gold"]) for i in idx)
    return hit / total if total else None


def a7_cell(rows: Sequence[Mapping[str, Any]], cell: str) -> dict[str, Any]:
    got = [r for r in rows if a7_chosen(r, cell) is not None]
    if not got:
        return {"n": 0}
    sets = [(a7_chosen(r, cell), set(r["gold"]), r["sizes"]) for r in got]
    chosen_n = sum(len(c) for c, _, _ in sets)
    return {
        "n": len(got), "recall": _r(_recall(got, cell, range(len(got)))),
        "any_hit": _r(sum(bool(c & g) for c, g, _ in sets) / len(got)),
        "all_hit": _r(sum(g <= c for c, g, _ in sets) / len(got)),
        "chars": round(sum(sum(s[i] for i in c) for c, _, s in sets) / len(got)),
        "precision": _r(sum(len(c & g) for c, g, _ in sets) / chosen_n if chosen_n else None),
    }  # fmt: skip


def analyse_a7(rows: Sequence[Mapping[str, Any]], *, min_questions: int) -> dict[str, Any]:
    cells = ["bm25@3", "rec13-S", *(f"{m}-{w}" for w in WINDOWS for m in MODELS)]
    live = [f"{m}-{w}" for w in WINDOWS for m in MODELS]
    complete = [r for r in rows if all(a7_chosen(r, c) is not None for c in live)]
    out: dict[str, Any] = {
        "launched": len(rows), "complete": len(complete),
        "cells": {c: a7_cell(complete, c) for c in cells},
        "excerpt_ceiling": [sum(r["excerpt_seen"] for r in complete),
                            sum(r["excerpt_total"] for r in complete)],
        "look_rate": {m: _r(sum(bool(r.get(f"{m}-look")) for r in complete)
                            / max(1, len(complete))) for m in MODELS},
    }  # fmt: skip
    pairs = {
        "recall_model_S": ("j14-S", "j13r-S"),
        "recall_model_L": ("j14-L", "j13r-L"),
        "recall_window_j13r": ("j13r-L", "j13r-S"),
        "recall_window_j14": ("j14-L", "j14-S"),
    }
    comps, gaps = {}, {}
    n = len(complete)

    def failed(row: Mapping[str, Any], cell: str) -> bool:
        return a7_chosen(row, cell) is None

    for name, (new, old) in pairs.items():
        comps[name] = paired_stat(lambda i, c=new: _recall(complete, c, i),
                                  lambda i, c=old: _recall(complete, c, i), n)  # fmt: skip
        gaps[name] = failure_rate(rows, new, failed) - failure_rate(rows, old, failed)
    out["family"] = family(comps, gaps)
    low = n < min_questions
    if low:
        out["family"] = {k: v | {"verdict": "no concluyente (n bajo)"}
                         for k, v in out["family"].items()}  # fmt: skip
    out["failures"] = {c: sum(failed(r, c) for r in rows) for c in [*live, "rec13-S"]}
    # The original runner's reading: a failed triage injects nothing (recall 0 on it).
    out["recall_failure_as_empty"] = {
        c: _r(_recall(rows, c, range(len(rows)), empty_on_failure=True)) for c in cells
    }
    out["against_bm25@3"] = {}
    for cell in live:
        res = paired_stat(
            lambda i, c=cell: _recall(complete, c, i), lambda i: _recall(complete, "bm25@3", i), n
        )
        ci = res.get("ci95")
        res["beats"] = bool(ci and ci[0] > 0) and not low  # the original's criterion 1
        res["within_3_points"] = res["diff"] is not None and res["diff"] >= -0.03 and not low
        res["n_bajo"] = low
        out["against_bm25@3"][cell] = res
    return out
