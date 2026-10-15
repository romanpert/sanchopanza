"""Analysis of lot lb162 (benchmarks/jev114/lb162.py), as registered in
docs/results/2026-10-15-lb162/prereg.md. Pure functions over the rows, no I/O.

The hybrid answers with Jev 1.14 (long window) where Jev's top-choice probability is >= TAU and
with Sonnet 5.5 elsewhere. Against Sonnet alone it only moves on the covered tasks, so

    hybrid - Sonnet = sum over covered (Jev right - Sonnet right) / n

over the n tasks Jev was asked; an uncovered task contributes 0 and needs no Sonnet answer. The
estimator is written as coverage x mean gain on the covered tasks that have a Sonnet answer: with
every covered task answered it is exactly the sum above; if a stop leaves covered tasks without
Sonnet (they run in a seeded random order), it stays unbiased instead of shrinking to 0.

Paired bootstrap over the n tasks (lot L4's `l4_stats.bootstrap`: 10,000 draws, seed 20261015,
percentile 95 % CI), exact McNemar on the covered disagreements, and the verdict fixed before
the data: "no peor" if the CI's lower bound > MARGIN, "peor" if its upper bound < MARGIN, else
"no concluyente".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import b3conf_power as power
import l4_stats as st
from l6_analysis import wilson

TAU = 0.6
MARGIN = -0.10
CELL = "j14-L"
SONNET_UNCOVERED_EST_USD = 0.123  # Sonnet 5.5 (N) mean list USD per task, 2026-10-06 (50 tasks)


@dataclass(frozen=True)
class Unit:
    """One task Jev was asked: covered or not, and on a covered one Jev's and Sonnet's grades
    (`sonnet_ok` None when Sonnet has no session for it)."""

    covered: bool
    jev_ok: bool
    sonnet_ok: bool | None

    @property
    def gain(self) -> int | None:
        if not self.covered:
            return 0
        return None if self.sonnet_ok is None else int(self.jev_ok) - int(self.sonnet_ok)


def is_covered(row: Mapping[str, Any], tau: float = TAU) -> bool:
    """Answered with a probability for its pick, and that probability >= tau."""
    cell = row.get(CELL) or {}
    return (row.get("status") == "answered" and cell.get("letter") is not None
            and cell.get("p") is not None and cell["p"] >= tau)  # fmt: skip


def jev_right(row: Mapping[str, Any]) -> bool:
    cell = row.get(CELL) or {}
    return cell.get("letter") is not None and cell["letter"] == row["gold"]


def asked(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The tasks of the lot: every task but those a stop left unasked."""
    return [r for r in rows if r.get("status") != "stopped"]


def units(jev_rows: Sequence[Mapping[str, Any]], sonnet: Mapping[str, Mapping[str, Any]],
          tau: float = TAU) -> list[Unit]:  # fmt: skip
    out = []
    for r in asked(jev_rows):
        cov = is_covered(r, tau)
        s = sonnet.get(r["id"]) if cov else None
        out.append(Unit(cov, jev_right(r), None if s is None else bool(s["ok"])))
    return out


def estimate(us: Sequence[Unit], idx: Sequence[int]) -> float | None:
    """Hybrid minus Sonnet on the tasks `idx`: coverage x mean gain on covered tasks answered by
    Sonnet. 0 with nothing covered; None when covered tasks exist but none has a Sonnet answer."""
    if not idx:
        return None
    cov = [us[i] for i in idx if us[i].covered]
    gains = [u.gain for u in cov if u.gain is not None]
    if not cov:
        return 0.0
    if not gains:
        return None
    return len(cov) / len(idx) * sum(gains) / len(gains)


def verdict(ci: tuple[float, float] | None, margin: float = MARGIN) -> str:
    if ci is None:
        return "no medido"
    lo, hi = ci
    if lo > margin:
        return "no peor"
    if hi < margin:
        return "peor"
    return "no concluyente"


def primary(us: Sequence[Unit]) -> dict[str, Any]:
    """The registered result: estimate, paired bootstrap CI, McNemar, verdict."""
    n = len(us)
    idx = list(range(n))
    diff = estimate(us, idx)
    ci = st.ci95(st.bootstrap(lambda i: estimate(us, i), st.items_as_units(n))) if n else None
    both = [u for u in us if u.covered and u.sonnet_ok is not None]
    b = sum(u.jev_ok and not u.sonnet_ok for u in both)
    c = sum(u.sonnet_ok and not u.jev_ok for u in both)
    return {"n": n, "covered": sum(u.covered for u in us),
            "covered_without_sonnet": sum(u.covered and u.sonnet_ok is None for u in us),
            "diff": None if diff is None else round(diff, 4), "ci95": ci,
            "bootstrap": {"draws": st.BOOT, "seed": st.BOOT_SEED, "unit": "task"},
            "mcnemar": {"jev_only_right": b, "sonnet_only_right": c,
                        "p": st.mcnemar_exact(b, c)},
            "margin": MARGIN, "verdict": verdict(ci),
            "ci95_normal": normal_ci(us)}  # fmt: skip


def normal_ci(us: Sequence[Unit]) -> tuple[float, float] | None:
    """b3conf_power's normal-approximation CI of the same paired gain, a descriptive cross-check
    of the bootstrap (only with every covered task answered by Sonnet)."""
    if len(us) < 2 or any(u.covered and u.sonnet_ok is None for u in us):
        return None
    rows = [power.Row(covered=u.covered, jev_ok=u.jev_ok, sonnet_ok=bool(u.sonnet_ok),
                      sonnet_usd=0.0, jev_usd=0.0) for u in us]  # fmt: skip
    _, lo, hi = power.paired_ci(rows)
    return (round(lo, 4), round(hi, 4))


def _share(k: int, n: int) -> float | None:
    return round(k / n, 4) if n else None


def descriptive(us: Sequence[Unit]) -> dict[str, Any]:
    cov = [u for u in us if u.covered]
    both = [u for u in cov if u.sonnet_ok is not None]
    k = sum(u.jev_ok for u in cov)
    gains = [u.gain for u in us if u.gain is not None]
    return {"n": len(us), "covered": len(cov), "coverage": _share(len(cov), len(us)),
            "jev_right_covered": k, "jev_precision_covered": _share(k, len(cov)),
            "jev_precision_wilson95": wilson(k, len(cov)),
            "sonnet_right_covered": sum(bool(u.sonnet_ok) for u in both),
            "sonnet_accuracy_covered": _share(sum(bool(u.sonnet_ok) for u in both), len(both)),
            "jev_right_all": sum(u.jev_ok for u in us),
            "jev_accuracy_all": _share(sum(u.jev_ok for u in us), len(us)),
            "gain_sum": sum(gains)}  # fmt: skip


def by_band(jev_rows: Sequence[Mapping[str, Any]], us: Sequence[Unit], key: str) -> dict:
    """The descriptive reading per LongBench band (`length` or `difficulty`)."""
    rows = asked(jev_rows)
    bands = sorted({str(r[key]) for r in rows})
    out = {}
    for band in bands:
        mine = [u for r, u in zip(rows, us, strict=True) if str(r[key]) == band]
        out[band] = descriptive(mine) | {"diff": estimate(mine, list(range(len(mine))))}
    return out


def costs(jev_rows: Sequence[Mapping[str, Any]], sonnet: Mapping[str, Mapping[str, Any]],
          tau: float = TAU) -> dict[str, Any]:  # fmt: skip
    """Measured: Jev on every task asked (discarded shorter retries included) and Sonnet on the
    covered tasks. Estimated (not measured): Sonnet on the uncovered tasks, at SONNET_UNCOVERED."""
    rows = asked(jev_rows)
    jev = sum(float((r.get(CELL) or {}).get("usd") or 0.0) for r in rows)
    covered_ids = [r["id"] for r in rows if is_covered(r, tau)]
    sonnet_cov = sum(float(sonnet[i]["usd"]) for i in covered_ids if i in sonnet)
    uncovered = len(rows) - len(covered_ids)
    est_unc = uncovered * SONNET_UNCOVERED_EST_USD
    sonnet_alone = sonnet_cov + est_unc
    saving = sonnet_cov - jev
    return {"jev_usd_all": round(jev, 6), "sonnet_usd_covered": round(sonnet_cov, 6),
            "sonnet_sessions_covered": sum(i in sonnet for i in covered_ids),
            "estimate": {"sonnet_usd_uncovered": round(est_unc, 4),
                         "per_task_usd": SONNET_UNCOVERED_EST_USD,
                         "sonnet_alone_usd": round(sonnet_alone, 4),
                         "hybrid_usd": round(jev + est_unc, 4),
                         "saving_usd": round(saving, 4),
                         "saving_share": _share_f(saving, sonnet_alone)}}  # fmt: skip


def _share_f(x: float, total: float) -> float | None:
    return round(x / total, 4) if total else None


def analyse(jev_rows: Sequence[Mapping[str, Any]],
            sonnet: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:  # fmt: skip
    us = units(jev_rows, sonnet)
    return {"tau": TAU, "primary": primary(us), "descriptive": descriptive(us),
            "stopped_unasked": len(jev_rows) - len(asked(jev_rows)),
            "jev_failed": sum(r.get("status") == "failed" for r in jev_rows),
            "by_length": by_band(jev_rows, us, "length"),
            "by_difficulty": by_band(jev_rows, us, "difficulty"),
            "costs": costs(jev_rows, sonnet)}  # fmt: skip
