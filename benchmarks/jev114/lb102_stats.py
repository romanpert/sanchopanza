"""Analysis of lot lb102 (benchmarks/jev114/lb102.py), as registered in
docs/results/2026-10-16-lb102/prereg.md. Pure functions over the rows, no I/O.

Lot lb162 routed 162 LongBench v2 tasks: Jev 1.14 (long window) answered alone where its top
choice was >= 0.6 (60 covered), Sonnet 5.5 the rest. Its saving was estimated, because Sonnet
never ran on the 102 uncovered tasks. Lot lb102 runs Sonnet there, so over the 162 tasks

    Sonnet alone = Sonnet on the covered (lb162) + Sonnet on the uncovered (lb102)
    hybrid       = Jev on all 162 (lb162)        + Sonnet on the uncovered (lb102)
    saving share = (Sonnet alone - hybrid) / Sonnet alone

Each part is a group's size times its measured mean, so a ceiling stop that leaves uncovered
tasks without a session (they run in a seeded order) keeps a ratio estimator rather than
shrinking the cost. A session with no letter because the infrastructure broke (`infra`) is not
a cost measurement: excluded in the primary reading, counted at its cost in a sensitivity
reading. A session stopped by a cap below 3.00 USD (lb102 lowers the cap only when the ceiling
needs it) is counted at its cost in the primary and at 3.00 in a second sensitivity reading.
Paired bootstrap over the tasks (lot L4's `l4_stats.bootstrap`: 10,000 draws, seed 20261015).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import l4_stats as st
import lb162_stats as lbs

FULL_CAP_USD = 3.00  # arm N's --max-budget-usd on LongBench (h2h_longdoc.CAPS["SONNET"])
ESTIMATE_SHARE = 0.2668  # lb162's published estimate (summary.json costs.estimate.saving_share)


@dataclass(frozen=True)
class Task:
    """One of the n tasks: covered or not, Jev's cost and grade, Sonnet's cost and grade (None
    without a usable session), and the band labels."""

    covered: bool
    jev_usd: float
    jev_ok: bool
    sonnet_usd: float | None
    sonnet_ok: bool | None
    length: str
    difficulty: str


def sonnet_cost(session: Mapping[str, Any] | None, infra_counts: bool, cut_at_full: bool,
                ) -> tuple[float | None, bool | None]:  # fmt: skip
    """(USD, right) of one session under a reading; (None, None) when it does not count."""
    if session is None:
        return None, None
    if lbs.infra(session) and not infra_counts:
        return None, None
    usd = float(session["usd"])
    reduced = float(session.get("cap_usd") or FULL_CAP_USD) < FULL_CAP_USD
    if cut_at_full and reduced and session.get("hit_cap"):
        usd = max(usd, FULL_CAP_USD)
    return usd, (False if lbs.infra(session) else bool(session["ok"]))


def tasks(jev_rows: Sequence[Mapping[str, Any]], sonnet: Mapping[str, Mapping[str, Any]],
          infra_counts: bool = False, cut_at_full: bool = False) -> list[Task]:  # fmt: skip
    """The asked tasks of lb162 with Sonnet's sessions of both lots (`sonnet` by id)."""
    out = []
    for r in lbs.asked(jev_rows):
        usd, ok = sonnet_cost(sonnet.get(r["id"]), infra_counts, cut_at_full)
        cell = r.get(lbs.CELL) or {}
        out.append(Task(lbs.is_covered(r), float(cell.get("usd") or 0.0), lbs.jev_right(r), usd,
                        ok, str(r["length"]), str(r["difficulty"])))  # fmt: skip
    return out


def _group_total(group: Sequence[Task]) -> float | None:
    """len(group) x the mean measured Sonnet cost in it; 0 for an empty group, None when the
    group has tasks but no measured cost."""
    measured = [t.sonnet_usd for t in group if t.sonnet_usd is not None]
    if not group:
        return 0.0
    if not measured:
        return None
    return len(group) * sum(measured) / len(measured)


def totals(ts: Sequence[Task], idx: Sequence[int]) -> dict[str, float] | None:
    picked = [ts[i] for i in idx]
    cov = _group_total([t for t in picked if t.covered])
    unc = _group_total([t for t in picked if not t.covered])
    if cov is None or unc is None:
        return None
    jev = sum(t.jev_usd for t in picked)
    return {"sonnet_covered": cov, "sonnet_uncovered": unc, "jev": jev,
            "sonnet_alone": cov + unc, "hybrid": jev + unc}  # fmt: skip


def share(ts: Sequence[Task], idx: Sequence[int]) -> float | None:
    got = totals(ts, idx)
    if got is None or got["sonnet_alone"] <= 0:
        return None
    return (got["sonnet_alone"] - got["hybrid"]) / got["sonnet_alone"]


def reading(ci: tuple[float, float] | None) -> str:
    """Fixed before the data: "ahorra" when the CI's lower bound is above 0, "no ahorra" when
    its upper bound is at or below 0, "no concluyente" otherwise, "no medido" without a CI."""
    if ci is None:
        return "no medido"
    if ci[0] > 0:
        return "ahorra"
    if ci[1] <= 0:
        return "no ahorra"
    return "no concluyente"


def estimate_check(ci: tuple[float, float] | None, estimate: float = ESTIMATE_SHARE) -> str | None:
    """Where lb162's estimated share falls against the measured CI."""
    if ci is None:
        return None
    if estimate < ci[0]:
        return "estimate below the CI"
    if estimate > ci[1]:
        return "estimate above the CI"
    return "estimate inside the CI"


def primary(ts: Sequence[Task], paused: Sequence[str] = ()) -> dict[str, Any]:
    n = len(ts)
    every = list(range(n))
    got = totals(ts, every)
    point = share(ts, every)
    unc = [t for t in ts if not t.covered]
    # No CI without the point: a resample that happens to draw no uncovered task must not stand
    # in for a measurement that does not exist.
    values = st.bootstrap(lambda i: share(ts, i), st.items_as_units(n)) if point is not None else []
    ci = lbs.percentile_ci(values)
    return {
        "n": n, "covered": n - len(unc), "uncovered": len(unc),
        "uncovered_measured": sum(t.sonnet_usd is not None for t in unc),
        "share": None if point is None else round(point, 4),
        "ci95": None if ci is None else (round(ci[0], 4), round(ci[1], 4)),
        "usd": None if got is None else {k: round(v, 4) for k, v in got.items()}
        | {"saving": round(got["sonnet_alone"] - got["hybrid"], 4)},
        "bootstrap": {"draws": st.BOOT, "kept": len(values), "seed": st.BOOT_SEED,
                      "unit": "task"},
        "reading": "pausa" if paused else reading(ci), "pause": list(paused),
        "estimate_share": ESTIMATE_SHARE,
        "estimate_check": None if paused else estimate_check(ci),
    }  # fmt: skip


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def accuracy(ts: Sequence[Task]) -> dict[str, Any]:
    """Descriptive: Sonnet and Jev on the uncovered tasks, Sonnet alone and the hybrid on the
    tasks where both answers are known, and cost per right answer."""
    unc = [t for t in ts if not t.covered and t.sonnet_ok is not None]
    known = [t for t in ts if t.sonnet_ok is not None]
    s_right = sum(bool(t.sonnet_ok) for t in known)
    h_right = sum((t.jev_ok if t.covered else bool(t.sonnet_ok)) for t in known)
    got = totals(ts, list(range(len(ts))))
    b = sum(t.jev_ok and not t.sonnet_ok for t in unc)
    c = sum(bool(t.sonnet_ok) and not t.jev_ok for t in unc)
    return {
        "uncovered_with_session": len(unc),
        "sonnet_right_uncovered": sum(bool(t.sonnet_ok) for t in unc),
        "jev_right_uncovered": sum(t.jev_ok for t in unc),
        "uncovered_mcnemar": {"jev_only_right": b, "sonnet_only_right": c,
                              "p": st.mcnemar_exact(b, c)},
        "tasks_known": len(known), "sonnet_alone_right": s_right, "hybrid_right": h_right,
        "sonnet_alone_accuracy": _rate(s_right, len(known)),
        "hybrid_accuracy": _rate(h_right, len(known)),
        "usd_per_right": None if got is None or not s_right or not h_right else {
            "sonnet_alone": round(got["sonnet_alone"] / s_right, 4),
            "hybrid": round(got["hybrid"] / h_right, 4)},
    }  # fmt: skip


def by_band(ts: Sequence[Task], key: str) -> dict[str, Any]:
    out = {}
    for band in sorted({getattr(t, key) for t in ts}):
        mine = [t for t in ts if getattr(t, key) == band]
        unc = [t.sonnet_usd for t in mine if not t.covered and t.sonnet_usd is not None]
        point = share(mine, list(range(len(mine))))
        out[band] = {"n": len(mine), "uncovered": sum(not t.covered for t in mine),
                     "uncovered_measured": len(unc),
                     "sonnet_mean_usd_uncovered": round(sum(unc) / len(unc), 4) if unc else None,
                     "share": None if point is None else round(point, 4)}  # fmt: skip
    return out


def sessions(lb102_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """lb102's sessions: count, cost, caps below 3.00 and how many of those it stopped."""
    usd = sorted(float(r["usd"]) for r in lb102_rows)
    reduced = [r for r in lb102_rows if float(r.get("cap_usd") or FULL_CAP_USD) < FULL_CAP_USD]
    return {"sessions": len(usd), "usd": round(sum(usd), 4),
            "mean_usd": round(sum(usd) / len(usd), 4) if usd else None,
            "median_usd": usd[len(usd) // 2] if usd else None,
            "max_usd": usd[-1] if usd else None,
            "infra": sum(lbs.infra(r) for r in lb102_rows),
            "hit_cap": sum(bool(r.get("hit_cap")) for r in lb102_rows),
            "reduced_cap": len(reduced),
            "reduced_cap_hit": sum(bool(r.get("hit_cap")) for r in reduced),
            "min_cap_usd": min((float(r["cap_usd"]) for r in reduced), default=None)}  # fmt: skip


def analyse(jev_rows: Sequence[Mapping[str, Any]], lb162_sonnet: Mapping[str, Mapping[str, Any]],
            lb102_sonnet: Mapping[str, Mapping[str, Any]],
            paused: Sequence[str] = ()) -> dict[str, Any]:  # fmt: skip
    both = {**lb162_sonnet, **lb102_sonnet}
    ts = tasks(jev_rows, both)
    return {
        "primary": primary(ts, paused),
        "sensitivity_infra_counted": primary(tasks(jev_rows, both, infra_counts=True), paused),
        "sensitivity_reduced_cap_at_full": primary(tasks(jev_rows, both, cut_at_full=True),
                                                   paused),
        "accuracy": accuracy(ts),
        "by_length": by_band(ts, "length"),
        "by_difficulty": by_band(ts, "difficulty"),
        "sessions": sessions(list(lb102_sonnet.values())),
    }  # fmt: skip
