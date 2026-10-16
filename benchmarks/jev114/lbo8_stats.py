"""Analysis of lot lbo8 (benchmarks/jev114/lbo8.py), as registered in
docs/results/2026-10-16-lbo8/prereg.md. Pure functions over the rows, no I/O but `write_summary`.

The hybrid answers with Jev 1.14 (long window) where its top-choice probability is >= the cut
(0.8: "covered") and with Opus 5.5 elsewhere, so it differs from Opus alone only on the covered
tasks. Over the lot's tasks:

- b: covered tasks only Jev got right; c: covered tasks only Opus got right;
- n: the 78 less the covered tasks with no Opus grade in the reading (an uncovered task is the
  same answer in both arms, with or without its session);
- estimate (b - c) / n with Tango's score 95 % interval (`lbo8.tango_ci`), compared unrounded
  with the margin (-5 points): "no peor" when the lower bound is above it, "peor" when the
  upper bound is below it, else "no concluyente"; "no medido" with fewer than 8 covered tasks
  with an Opus grade; "pausa" while a phase is paused.

Opus sessions with no letter are read as in lb162x (`lb162x_stats.grade`): an infrastructure
error or a stop by a cap lowered below the full one is not run in the primary reading and wrong
in the sensitivity reading; a session another model mostly served is out of both.

Secondary: the saving of Opus's cost, (Opus alone - (Jev on every task + Opus on the
uncovered)) / Opus alone, each group's Opus cost its size times its measured mean
(`lb162x_stats.totals`), with a paired bootstrap over the tasks (10,000 draws, seed 20261016,
percentile 95 %): "ahorra" when the lower bound is above 0. Jev's precision and Opus's
accuracy on the covered (Wilson), McNemar exact on the disagreements, and the 0.6 and 0.7 cuts
on the same rows (descriptive).
"""

from __future__ import annotations

import json
import pathlib
import random
from collections.abc import Mapping, Sequence
from typing import Any

import lb162_stats as lbs
import lb162x_stats as xs
import lbo8
from l4_stats import mcnemar_exact
from l6_analysis import wilson

MARGIN = lbo8.MARGIN  # -0.05
CUT = lbo8.CUT  # 0.8
MIN_COVERED_SESSIONS = lbo8.MIN_COVERED_SESSIONS  # 8
FULL_CAP = xs.OPUS_FULL_CAP_USD  # 6.00, arm N's Opus cap
BOOT_DRAWS, BOOT_SEED = lbo8.BOOT_DRAWS, lbo8.BOOT_SEED
DESCRIPTIVE_CUTS = (0.6, 0.7)


# ---- tasks ---------------------------------------------------------------------------------------


def tasks(jev_rows: Sequence[Mapping[str, Any]], opus: Mapping[str, Mapping[str, Any]],
          cut: float = CUT, as_wrong: bool = False, infra_counts: bool = False,
          cut_at_full: bool = False) -> list[xs.Task]:  # fmt: skip
    """Every row of phase J (a task a stop left unasked is uncovered: Opus answers it) with
    Opus's grade and cost under the reading."""
    out = []
    for r in jev_rows:
        s = opus.get(r["id"])
        cell = r.get(lbs.CELL) or {}
        out.append(xs.Task(lbs.is_covered(r, cut), float(cell.get("usd") or 0.0),
                           lbs.jev_right(r), xs.cost(s, FULL_CAP, infra_counts, cut_at_full),
                           xs.grade(s, FULL_CAP, as_wrong), str(r.get("length")),
                           str(r.get("difficulty"))))  # fmt: skip
    return out


def counts(ts: Sequence[xs.Task]) -> dict[str, int]:
    """b, c, n and the covered tasks with and without an Opus grade."""
    cov = [t for t in ts if t.covered]
    graded = [t for t in cov if t.ok is not None]
    b = sum(t.jev_ok and not t.ok for t in graded)
    c = sum(bool(t.ok) and not t.jev_ok for t in graded)
    return {"tasks": len(ts), "n": len(ts) - (len(cov) - len(graded)), "covered": len(cov),
            "covered_with_opus": len(graded), "covered_without_opus": len(cov) - len(graded),
            "jev_only_right": b, "opus_only_right": c}  # fmt: skip


# ---- the primary verdict -------------------------------------------------------------------------


def verdict(ts: Sequence[xs.Task], paused: Sequence[str] = (), margin: float = MARGIN,
            min_covered: int = MIN_COVERED_SESSIONS) -> dict[str, Any]:  # fmt: skip
    """Hybrid minus Opus alone: Tango's interval and the verdict at `margin` (unrounded)."""
    k = counts(ts)
    b, c, n = k["jev_only_right"], k["opus_only_right"], k["n"]
    est, lo, hi = lbo8.tango_ci(b, c, n) if n else (None, None, None)
    if paused:
        said = "pausa"
    elif k["covered_with_opus"] < min_covered or lo is None:
        said = "no medido"
    else:
        said = lbo8.verdict(lo, hi, margin)
    return {
        **k, "diff": None if est is None else round(est, 6),
        "ci95": None if lo is None else (round(lo, 6), round(hi, 6)),
        "ci95_points": None if lo is None else (round(lo * 100, 2), round(hi * 100, 2)),
        "method": "Tango score 95 % (paired)", "margin": margin,
        "min_covered_sessions": min_covered, "verdict": said, "pause": list(paused),
        "mcnemar_p": mcnemar_exact(b, c),
    }  # fmt: skip


# ---- the saving ----------------------------------------------------------------------------------


def bootstrap(ts: Sequence[xs.Task], draws: int = BOOT_DRAWS, seed: int = BOOT_SEED) -> list[float]:
    """The saving share over `draws` resamples of the tasks with replacement (seeded); a
    resample with no measured cost in a group it holds gives nothing."""
    rng = random.Random(seed)
    n = len(ts)
    out = []
    for _ in range(draws):
        value = xs.share(ts, [rng.randrange(n) for _ in range(n)])
        if value is not None:
            out.append(value)
    return out


def saving(ts: Sequence[xs.Task], paused: Sequence[str] = (), draws: int = BOOT_DRAWS,
           seed: int = BOOT_SEED) -> dict[str, Any]:  # fmt: skip
    """The measured saving share, its paired bootstrap CI and its reading ("ahorra" when the
    lower bound is above 0; lb162x_stats.reading)."""
    every = list(range(len(ts)))
    got = xs.totals(ts, every)
    point = xs.share(ts, every)
    values = bootstrap(ts, draws, seed) if point is not None else []
    ci = lbs.percentile_ci(values)
    return {
        "n": len(ts), "covered": sum(t.covered for t in ts),
        "measured": sum(t.usd is not None for t in ts),
        "share": None if point is None else round(point, 4),
        "ci95": None if ci is None else (round(ci[0], 4), round(ci[1], 4)),
        "usd": None if got is None else {k: round(v, 4) for k, v in got.items()}
        | {"saving": round(got["alone"] - got["hybrid"], 4)},
        "bootstrap": {"draws": draws, "kept": len(values), "seed": seed, "unit": "task"},
        "reading": "pausa" if paused else xs.reading(ci), "pause": list(paused),
    }  # fmt: skip


# ---- secondaries ---------------------------------------------------------------------------------


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def covered_accuracy(ts: Sequence[xs.Task]) -> dict[str, Any]:
    """Jev's precision on the covered tasks and Opus's accuracy on those with its grade."""
    cov = [t for t in ts if t.covered]
    graded = [t for t in cov if t.ok is not None]
    jev, opus = sum(t.jev_ok for t in cov), sum(bool(t.ok) for t in graded)
    return {"covered": len(cov), "jev_right": jev, "jev_precision": _rate(jev, len(cov)),
            "jev_wilson95": wilson(jev, len(cov)) if cov else None,
            "opus_graded": len(graded), "opus_right": opus,
            "opus_accuracy": _rate(opus, len(graded)),
            "opus_wilson95": wilson(opus, len(graded)) if graded else None}  # fmt: skip


def overall(ts: Sequence[xs.Task]) -> dict[str, Any]:
    """Descriptive: Opus alone and the hybrid on the tasks with an Opus grade."""
    known = [t for t in ts if t.ok is not None]
    alone = sum(bool(t.ok) for t in known)
    hybrid = sum((t.jev_ok if t.covered else bool(t.ok)) for t in known)
    return {"tasks_known": len(known), "opus_right": alone,
            "opus_accuracy": _rate(alone, len(known)), "hybrid_right": hybrid,
            "hybrid_accuracy": _rate(hybrid, len(known))}  # fmt: skip


def cut_reading(jev_rows: Sequence[Mapping[str, Any]], opus: Mapping[str, Mapping[str, Any]],
                cut: float) -> dict[str, Any]:  # fmt: skip
    """Descriptive: another cut on the same rows (its Tango interval, the saving's point)."""
    ts = tasks(jev_rows, opus, cut)
    v = verdict(ts, min_covered=0)
    return {"cut": cut, **{k: v[k] for k in ("covered", "covered_with_opus", "jev_only_right",
                                             "opus_only_right", "n", "diff", "ci95_points")},
            "saving_share": xs.share(ts, list(range(len(ts)))), "descriptive": True}  # fmt: skip


def analyse(jev_rows: Sequence[Mapping[str, Any]], opus: Mapping[str, Mapping[str, Any]],
            paused: Sequence[str] = ()) -> dict[str, Any]:  # fmt: skip
    ts = tasks(jev_rows, opus)
    return {
        "cut": CUT, "margin": MARGIN,
        "primary": verdict(ts, paused),
        "sensitivity_not_run_as_wrong": verdict(tasks(jev_rows, opus, as_wrong=True), paused),
        "saving": saving(ts, paused),
        "saving_sensitivity_infra_counted": saving(tasks(jev_rows, opus, infra_counts=True),
                                                   paused),
        "saving_sensitivity_reduced_cap_at_full": saving(
            tasks(jev_rows, opus, cut_at_full=True), paused),
        "covered_accuracy": covered_accuracy(ts),
        "overall": overall(ts),
        "descriptive_cuts": [cut_reading(jev_rows, opus, c) for c in DESCRIPTIVE_CUTS],
        "jev": {"rows": len(jev_rows),
                "status": {s: sum(r.get("status") == s for r in jev_rows)
                           for s in ("answered", "failed", "stopped")},
                "usd": round(sum(float((r.get(lbs.CELL) or {}).get("usd") or 0.0)
                                 for r in jev_rows), 6)},
        "opus_sessions": xs.sessions(list(opus.values()), FULL_CAP),
    }  # fmt: skip


def write_summary(path: pathlib.Path, out: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8", newline="\n")
