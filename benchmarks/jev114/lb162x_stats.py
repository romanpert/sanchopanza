"""Analysis of lot lb162x (benchmarks/jev114/lb162x.py), as registered in
docs/results/2026-10-16-lb162x/prereg.md. Pure functions over the rows, no I/O.

Lot lb162 routed 162 LongBench v2 tasks: Jev 1.14 (long window) answered alone where its top
choice was >= 0.6 (60 covered), the expensive model the rest. Lot lb162x reuses Jev's recorded
answers and runs the expensive model where lb162 did not:

- phase B, Opus 5.5 on all 162 (the primary verdict): hybrid(Jev on the covered, Opus elsewhere)
  minus Opus alone = coverage x the mean gain over the covered tasks with an Opus session
  (lb162_stats.estimate), paired bootstrap, the -10-point rule, McNemar, the "sustituye" claim;
  and the measured saving of Opus's cost;
- phase A, Sonnet 5.5 on the 102 uncovered: the measured saving of Sonnet's cost over the 162
  (lb162's Sonnet sessions on the covered plus phase A's), and Sonnet alone's accuracy on all 162.

Cost of the expensive model over the tasks:

    alone  = its cost on the covered + its cost on the uncovered
    hybrid = Jev on every task      + its cost on the uncovered
    saving share = (alone - hybrid) / alone

each group's cost being its size times its measured mean, so a ceiling stop (the sessions run in
a seeded random order) keeps a ratio estimator rather than shrinking the cost.

Sessions with no letter. An infrastructure error (`lb162_stats.infra`) is not run in the primary
readings and wrong (at its cost) in the sensitivity readings. A session stopped by a cap *below*
the phase's full cap (the cap is lowered only when the ceiling needs it) with no letter is not
run in the primary reading and wrong in the sensitivity reading: counting it wrong would lower
the expensive model and favour the hybrid. One stopped by the full cap stays wrong (arm N's rule).
In the cost reading a lowered-cap stop counts at its cost, and at the full cap in a sensitivity
reading. Paired bootstrap over the tasks (lot L4's `l4_stats.bootstrap`: 10,000 draws, seed
20261015, percentile 95 % CI).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import l4_stats as st
import lb162_stats as lbs
from l6_analysis import wilson

MARGIN = lbs.MARGIN  # -0.10, compared unrounded
MIN_COVERAGE = lbs.MIN_COVERAGE  # 0.20
SONNET_FULL_CAP_USD = 3.00  # arm N's --max-budget-usd on LongBench (h2h_longdoc.CAPS["SONNET"])
OPUS_FULL_CAP_USD = 6.00  # h2h_longdoc.CAPS["OPUS"]
# No verdict on fewer measurements (else "no medido"): covered tasks with an Opus session for
# phase B's verdict; sessions of the lot's own model for a saving reading.
MIN_COVERED_SESSIONS = 20
MIN_SAVING_SESSIONS = 40
ESTIMATE_SHARE = 0.2668  # lb162's published estimate (summary.json costs.estimate.saving_share)


# ---- one session --------------------------------------------------------------------------------


def lowered_stop(session: Mapping[str, Any], full_cap: float) -> bool:
    """No letter because a cap below the phase's full cap stopped the session."""
    cap = float(session.get("cap_usd") or full_cap)
    return session.get("letter") is None and bool(session.get("hit_cap")) and cap < full_cap


def not_run(session: Mapping[str, Any], full_cap: float) -> bool:
    """Not run in the primary readings: an infrastructure error, a lowered-cap stop, or a
    session most of whose cost went to another model than the phase's."""
    served = session.get("served_ok")
    return lbs.infra(session) or lowered_stop(session, full_cap) or served is False


def grade(session: Mapping[str, Any] | None, full_cap: float, as_wrong: bool) -> bool | None:
    """Right, wrong, or None (no session, or not run in this reading)."""
    if session is None:
        return None
    if not_run(session, full_cap):
        return False if as_wrong else None
    return bool(session["ok"])


def cost(session: Mapping[str, Any] | None, full_cap: float, infra_counts: bool,
         cut_at_full: bool) -> float | None:  # fmt: skip
    """USD of one session under a reading; None when it is not a cost measurement."""
    if session is None or (lbs.infra(session) and not infra_counts):
        return None
    usd = float(session["usd"])
    reduced = float(session.get("cap_usd") or full_cap) < full_cap
    if cut_at_full and reduced and session.get("hit_cap"):
        usd = max(usd, full_cap)
    return usd


# ---- tasks --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Task:
    """One of the n tasks: covered or not, Jev's cost and grade, the expensive model's cost and
    grade (None without a usable session), and the band labels."""

    covered: bool
    jev_usd: float
    jev_ok: bool
    usd: float | None
    ok: bool | None
    length: str
    difficulty: str


def tasks(jev_rows: Sequence[Mapping[str, Any]], sessions: Mapping[str, Mapping[str, Any]],
          full_cap: float, infra_counts: bool = False, cut_at_full: bool = False,
          as_wrong: bool = False) -> list[Task]:  # fmt: skip
    """lb162's asked tasks with the expensive model's sessions (`sessions` by id)."""
    out = []
    for r in lbs.asked(jev_rows):
        s = sessions.get(r["id"])
        cell = r.get(lbs.CELL) or {}
        out.append(Task(lbs.is_covered(r), float(cell.get("usd") or 0.0), lbs.jev_right(r),
                        cost(s, full_cap, infra_counts, cut_at_full),
                        grade(s, full_cap, as_wrong), str(r["length"]),
                        str(r["difficulty"])))  # fmt: skip
    return out


# ---- the saving ---------------------------------------------------------------------------------


def _group_total(group: Sequence[Task]) -> float | None:
    """len(group) x the mean measured cost in it; 0 for an empty group, None when the group has
    tasks but no measured cost."""
    measured = [t.usd for t in group if t.usd is not None]
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
    return {"covered": cov, "uncovered": unc, "jev": jev, "alone": cov + unc,
            "hybrid": jev + unc}  # fmt: skip


def share(ts: Sequence[Task], idx: Sequence[int]) -> float | None:
    got = totals(ts, idx)
    if got is None or got["alone"] <= 0:
        return None
    return (got["alone"] - got["hybrid"]) / got["alone"]


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


def saving(ts: Sequence[Task], paused: Sequence[str] = (), min_sessions: int = 0,
           own_uncovered_only: bool = False) -> dict[str, Any]:  # fmt: skip
    """The measured saving share, its paired bootstrap CI and its reading; "no medido" with
    fewer than `min_sessions` of the lot's own sessions (all measured tasks, or only the
    uncovered ones when the covered ones come from lb162)."""
    n = len(ts)
    every = list(range(n))
    got = totals(ts, every)
    point = share(ts, every)
    # No CI without the point: a resample must not stand in for a measurement that is not there.
    values = st.bootstrap(lambda i: share(ts, i), st.items_as_units(n)) if point is not None else []
    ci = lbs.percentile_ci(values)
    own = sum(t.usd is not None and not (own_uncovered_only and t.covered) for t in ts)
    said = "pausa" if paused else reading(ci) if own >= min_sessions else "no medido"
    return {
        "n": n, "covered": sum(t.covered for t in ts), "own_sessions": own,
        "min_sessions": min_sessions,
        "covered_measured": sum(t.covered and t.usd is not None for t in ts),
        "uncovered": sum(not t.covered for t in ts),
        "uncovered_measured": sum(not t.covered and t.usd is not None for t in ts),
        "share": None if point is None else round(point, 4),
        "ci95": None if ci is None else (round(ci[0], 4), round(ci[1], 4)),
        "usd": None if got is None else {k: round(v, 4) for k, v in got.items()}
        | {"saving": round(got["alone"] - got["hybrid"], 4)},
        "bootstrap": {"draws": st.BOOT, "kept": len(values), "seed": st.BOOT_SEED,
                      "unit": "task"},
        "reading": said, "pause": list(paused),
    }  # fmt: skip


# ---- phase B: the verdict against Opus alone -----------------------------------------------------


def units(ts: Sequence[Task]) -> list[lbs.Unit]:
    """lb162_stats' units: an uncovered task adds 0 whatever the expensive model did."""
    return [lbs.Unit(t.covered, t.jev_ok, t.ok if t.covered else None) for t in ts]


def relabel(found: Mapping[str, Any], name: str) -> dict[str, Any]:
    """lb162_stats names the expensive model `sonnet`; here it is `name`."""
    out = {}
    for key, value in found.items():
        value = relabel(value, name) if isinstance(value, Mapping) else value
        out[key.replace("sonnet", name)] = value
    return out


def verdict(ts: Sequence[Task], paused: Sequence[str] = (),
            min_covered: int = MIN_COVERED_SESSIONS) -> dict[str, Any]:  # fmt: skip
    """Hybrid minus the expensive model alone, its CI, McNemar on the covered disagreements,
    the -10-point verdict ("no medido" with fewer than `min_covered` covered tasks answered)
    and the product claim (also coverage >= 20 %)."""
    us = units(ts)
    first = lbs.primary(us, paused)
    if not paused and first["sonnet_sessions"] < min_covered:
        first = {**first, "verdict": "no medido"}
    coverage = sum(u.covered for u in us) / len(us) if us else None
    return relabel(first, "opus") | {"coverage": None if coverage is None else round(coverage, 4),
                                     "claim": lbs.claim(first, coverage),
                                     "min_coverage": MIN_COVERAGE,
                                     "min_covered_sessions": min_covered}  # fmt: skip


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def accuracy(ts: Sequence[Task]) -> dict[str, Any]:
    """Descriptive: the expensive model alone and the hybrid on the tasks with its answer, by
    coverage, with Wilson intervals, and the McNemar of Jev against it on the uncovered (what
    Jev alone would have given up where it was unsure)."""
    known = [t for t in ts if t.ok is not None]
    unc = [t for t in known if not t.covered]
    cov = [t for t in known if t.covered]
    alone = sum(bool(t.ok) for t in known)
    hybrid = sum((t.jev_ok if t.covered else bool(t.ok)) for t in known)
    b = sum(t.jev_ok and not t.ok for t in unc)
    c = sum(bool(t.ok) and not t.jev_ok for t in unc)
    got = totals(ts, list(range(len(ts))))
    return {
        "tasks_known": len(known), "alone_right": alone, "alone_accuracy": _rate(alone, len(known)),
        "alone_wilson95": wilson(alone, len(known)) if known else None,
        "hybrid_right": hybrid, "hybrid_accuracy": _rate(hybrid, len(known)),
        "covered_known": len(cov), "alone_right_covered": sum(bool(t.ok) for t in cov),
        "jev_right_covered": sum(t.jev_ok for t in cov),
        "uncovered_known": len(unc), "alone_right_uncovered": sum(bool(t.ok) for t in unc),
        "jev_right_uncovered": sum(t.jev_ok for t in unc),
        "uncovered_mcnemar": {"jev_only_right": b, "alone_only_right": c,
                              "p": st.mcnemar_exact(b, c)},
        "usd_per_right": None if got is None or not alone or not hybrid else {
            "alone": round(got["alone"] / alone, 4), "hybrid": round(got["hybrid"] / hybrid, 4)},
    }  # fmt: skip


def by_band(ts: Sequence[Task], key: str) -> dict[str, Any]:
    out = {}
    for band in sorted({getattr(t, key) for t in ts}):
        mine = [t for t in ts if getattr(t, key) == band]
        us = units(mine)
        measured = [t.usd for t in mine if t.usd is not None]
        point = share(mine, list(range(len(mine))))
        out[band] = {"n": len(mine), "covered": sum(t.covered for t in mine),
                     "measured": len(measured),
                     "mean_usd": round(sum(measured) / len(measured), 4) if measured else None,
                     "diff": lbs.estimate(us, list(range(len(us)))),
                     "share": None if point is None else round(point, 4)}  # fmt: skip
    return out


def sessions(rows: Sequence[Mapping[str, Any]], full_cap: float) -> dict[str, Any]:
    """A phase's sessions: count, cost, caps below the full one and how many of those it hit."""
    usd = sorted(float(r["usd"]) for r in rows)
    reduced = [r for r in rows if float(r.get("cap_usd") or full_cap) < full_cap]
    return {"sessions": len(usd), "usd": round(sum(usd), 4),
            "mean_usd": round(sum(usd) / len(usd), 4) if usd else None,
            "median_usd": usd[len(usd) // 2] if usd else None,
            "max_usd": usd[-1] if usd else None,
            "infra": sum(lbs.infra(r) for r in rows),
            "hit_cap": sum(bool(r.get("hit_cap")) for r in rows),
            "reduced_cap": len(reduced),
            "reduced_cap_hit": sum(bool(r.get("hit_cap")) for r in reduced),
            "lowered_stop_no_letter": sum(lowered_stop(r, full_cap) for r in rows),
            "min_cap_usd": min((float(r["cap_usd"]) for r in reduced), default=None)}  # fmt: skip


# ---- the two phases ------------------------------------------------------------------------------


def phase_b(jev_rows: Sequence[Mapping[str, Any]], opus: Mapping[str, Mapping[str, Any]],
            paused: Sequence[str] = (), min_covered: int = MIN_COVERED_SESSIONS,
            min_saving: int = MIN_SAVING_SESSIONS) -> dict[str, Any]:  # fmt: skip
    """The primary verdict (Opus 5.5), its sensitivity reading and the measured saving."""
    cap = OPUS_FULL_CAP_USD
    ts = tasks(jev_rows, opus, cap)

    def saved(found: Sequence[Task]) -> dict[str, Any]:
        return saving(found, paused, min_saving)

    return {
        "primary": verdict(ts, paused, min_covered),
        "sensitivity_not_run_as_wrong": verdict(tasks(jev_rows, opus, cap, as_wrong=True),
                                                paused, min_covered),
        "saving": saved(ts),
        "saving_sensitivity_infra_counted": saved(tasks(jev_rows, opus, cap, infra_counts=True)),
        "saving_sensitivity_reduced_cap_at_full": saved(
            tasks(jev_rows, opus, cap, cut_at_full=True)),
        "accuracy": accuracy(ts),
        "by_length": by_band(ts, "length"),
        "by_difficulty": by_band(ts, "difficulty"),
        "sessions": sessions(list(opus.values()), cap),
    }  # fmt: skip


def phase_a(jev_rows: Sequence[Mapping[str, Any]], lb162_sonnet: Mapping[str, Mapping[str, Any]],
            lb162x_sonnet: Mapping[str, Mapping[str, Any]], paused: Sequence[str] = (),
            min_saving: int = MIN_SAVING_SESSIONS) -> dict[str, Any]:  # fmt: skip
    """The measured saving of Sonnet's cost (reading fixed before the data) and Sonnet alone's
    accuracy on all 162 with lb162's hybrid minus Sonnet re-read (descriptive: lb162's verdict
    stands as sealed)."""
    cap = SONNET_FULL_CAP_USD
    both = {**lb162_sonnet, **lb162x_sonnet}
    ts = tasks(jev_rows, both, cap)

    def measured(found: Sequence[Task]) -> dict[str, Any]:
        return saving(found, paused, min_saving, own_uncovered_only=True)

    saved = measured(ts)
    return {
        "saving": saved | {"estimate_share": ESTIMATE_SHARE,
                           "estimate_check": None if paused else estimate_check(
                               None if saved["ci95"] is None else tuple(saved["ci95"]))},
        "saving_sensitivity_infra_counted": measured(tasks(jev_rows, both, cap,
                                                           infra_counts=True)),
        "saving_sensitivity_reduced_cap_at_full": measured(
            tasks(jev_rows, both, cap, cut_at_full=True)),
        "accuracy": accuracy(ts),
        "hybrid_minus_sonnet_reread": lbs.primary(units(ts), paused) | {"descriptive": True},
        "by_length": by_band(ts, "length"),
        "by_difficulty": by_band(ts, "difficulty"),
        "sessions": sessions(list(lb162x_sonnet.values()), cap),
    }  # fmt: skip


def opus_vs_sonnet(opus_ts: Sequence[Task], sonnet_ts: Sequence[Task]) -> dict[str, Any]:
    """Descriptive: the two expensive models on the tasks both answered."""
    pairs = [(o, s) for o, s in zip(opus_ts, sonnet_ts, strict=True)
             if o.ok is not None and s.ok is not None]  # fmt: skip
    b = sum(bool(o.ok) and not s.ok for o, s in pairs)
    c = sum(bool(s.ok) and not o.ok for o, s in pairs)
    return {"tasks": len(pairs), "opus_right": sum(bool(o.ok) for o, _ in pairs),
            "sonnet_right": sum(bool(s.ok) for _, s in pairs),
            "mcnemar": {"opus_only_right": b, "sonnet_only_right": c,
                        "p": st.mcnemar_exact(b, c)}}  # fmt: skip
