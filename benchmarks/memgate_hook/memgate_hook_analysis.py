"""Analysis of lot memgate-hook (benchmarks/memgate_hook/memgate_hook.py): the installed memory
hook's recall at a first prompt, the short window (S) against the long one (L), on the same
SWE-chat requests. Pure functions over scored rows, no I/O. The rule is the one in
docs/results/2026-10-16-memgate-hook/prereg.md; the statistics are lot L4's (`l4_stats`):
exact McNemar, a paired bootstrap over requests and one over the groups they come from."""

from __future__ import annotations

import math
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "jev114"))

import l4_stats as st  # noqa: E402

RELATED = frozenset({"lineage", "file"})
ALPHA = 0.05
HIT_NOT_WORSE = -0.05  # "no peor": both hit CIs' lower bounds at or above -5 points
NOISE_MARGIN = 0.05  # the guard: the larger false-alarm CI upper bound at most +5 points
FAILURE_GAP = 0.02  # L failing on more than 2 % more asked requests than S withholds a verdict
MIN_REQUESTS = 30
SCENARIOS = ((0.10, 0.02), (0.08, 0.02), (0.06, 0.02), (0.05, 0.01), (0.15, 0.05))
CUT = 0.8  # the hook's MEMORY_KEEP_AT, for the test-retest's agreement


# ---- per row ----------------------------------------------------------------------------------


def asked(row: Mapping[str, Any]) -> bool:
    return bool(row["S"]["asked"] or row["L"]["asked"])


def failed(arm: Mapping[str, Any]) -> bool:
    """The arm timed out, or asked and got no probability at all (after any fall back)."""
    timed_out = "timed out" in str(arm.get("reason", ""))
    answered = any(p is not None for p in (arm.get("probabilities") or {}).values())
    return timed_out or (bool(arm.get("asked")) and not answered)


def has_related(row: Mapping[str, Any]) -> bool:
    """A candidate the decider was shown is related to the request (`lineage` or `file`)."""
    return any(v in RELATED for v in row["labels"].values())


def hit(row: Mapping[str, Any], arm: str) -> bool:
    return any(row["labels"].get(k) in RELATED for k in row[arm]["shown"])


def gave(row: Mapping[str, Any], arm: str, changed: bool | None = None) -> bool:
    """The arm gave a record; with `changed`, one that changed files (True) or none (False)."""
    shown = row[arm]["shown"]
    if changed is None:
        return bool(shown)
    return any(bool(row.get("changed", {}).get(k)) == changed for k in shown)


# ---- the verdict ------------------------------------------------------------------------------


def _bounds(result: Mapping[str, Any]) -> tuple[float, float] | None:
    """The wider of the request and the group bootstrap CIs: (smaller low, larger high)."""
    cis = [c for c in (result.get("ci95"), result.get("ci95_cluster")) if c is not None]
    if not cis:
        return None
    return min(c[0] for c in cis), max(c[1] for c in cis)


def verdict(primary: Mapping[str, Any], guard: Mapping[str, Any], gap: float, n_hit: int,
            n_noise: int, min_requests: int = MIN_REQUESTS) -> str:  # fmt: skip
    """The registered rule, in its order of precedence. Only "mejora" supports moving the
    installed hook to the long window; every other reading keeps it short."""
    if n_hit < min_requests or n_noise < min_requests:
        return "no concluyente (n bajo)"
    hits, noise = _bounds(primary), _bounds(guard)
    if primary.get("diff") is None or hits is None or noise is None:
        return "no medido"
    if gap > FAILURE_GAP:
        return "no medido (fallos)"
    if noise[1] > NOISE_MARGIN:
        return "peor en ruido"
    extra_hits = primary["only_new"] - primary["only_old"]
    extra_noise = guard["only_new"] - guard["only_old"]
    cluster = primary.get("ci95_cluster")
    if (primary["p"] < ALPHA and primary["diff"] > 0 and cluster is not None
            and cluster[0] > 0 and extra_hits >= extra_noise):  # fmt: skip
        return "mejora"
    if hits[0] >= HIT_NOT_WORSE:
        return "no peor"
    return "peor"


def describe(rows: Sequence[Mapping[str, Any]], arm: str) -> dict[str, Any]:
    """v5's first-request reading for the prompt alone (no touch), over every first request:
    recall (requests with a related record in the pool given one), precision (records given
    that are related), noise (requests with nothing related given anything)."""
    rel = [r for r in rows if r["related_in_pool"]]
    unrel = [r for r in rows if not r["related_in_pool"]]
    given = [(r, k) for r in rows for k in r[arm]["shown"]]
    good = sum(r["labels"].get(k) in RELATED for r, k in given)
    fallbacks = Counter(r[arm]["window_fallback"] for r in rows if "window_fallback" in r[arm])
    return {
        "requests": len(rows),
        "recall": round(sum(hit(r, arm) for r in rel) / len(rel), 4) if rel else None,
        "precision": round(good / len(given), 4) if given else None,
        "noise": round(sum(gave(r, arm) for r in unrel) / len(unrel), 4) if unrel else None,
        "records_given": len(given),
        "failed": sum(failed(r[arm]) for r in rows if asked(r)),
        "fallbacks": dict(sorted(fallbacks.items())),
        "long_usd": round(sum(float(r[arm].get("long_usd") or 0) for r in rows), 6),
    }  # fmt: skip


def _paired(rows: Sequence[Mapping[str, Any]], outcome: Any) -> dict[str, Any]:
    return st.paired_binary([outcome(r, "L") for r in rows], [outcome(r, "S") for r in rows],
                            [r["cluster"] for r in rows])  # fmt: skip


def analyse(rows: Sequence[Mapping[str, Any]], *, min_requests: int = MIN_REQUESTS) -> dict:
    launched = [r for r in rows if asked(r)]
    n = len(launched)
    fails = {arm: sum(failed(r[arm]) for r in launched) for arm in ("S", "L")}
    gap = (fails["L"] - fails["S"]) / n if n else 0.0
    differ = [r for r in launched if not r.get("same_candidates", True)]
    complete = [r for r in launched if not failed(r["S"]) and not failed(r["L"])
                and r.get("same_candidates", True)]  # fmt: skip
    hittable = [r for r in complete if r.get("hittable", has_related(r))]
    blocked = [r for r in complete if has_related(r) and not r.get("hittable", True)]
    without = [r for r in complete if not has_related(r)]
    primary = _paired(hittable, hit)
    guard = _paired(without, gave)
    return {
        "first_requests": len(rows), "asked": n, "complete": len(complete),
        "candidates_differ": len(differ), "failed": fails, "failure_gap": round(gap, 4),
        "hittable": len(hittable), "related_but_gated": len(blocked),
        "without_related": len(without),
        "hit_L_vs_S": primary, "false_alarm_L_vs_S": guard,
        "false_alarm_by_record": {
            "changed_files": _paired(without, lambda r, a: gave(r, a, True)),
            "changed_nothing": _paired(without, lambda r, a: gave(r, a, False)),
        },
        "verdict": verdict(primary, guard, gap, len(hittable), len(without), min_requests),
        "describe": {arm: describe(rows, arm) for arm in ("S", "L")},
    }  # fmt: skip


def retest(pairs: Sequence[tuple[float, float]]) -> dict[str, Any]:
    """Descriptive: v5's cached probability against this run's S, per record."""
    if not pairs:
        return {"records": 0}
    diffs = sorted(abs(a - b) for a, b in pairs)
    agree = sum((a >= CUT) == (b >= CUT) for a, b in pairs)
    return {"records": len(pairs), "mean_abs_diff": round(sum(diffs) / len(diffs), 4),
            "median_abs_diff": round(diffs[len(diffs) // 2], 4),
            "agree_at_cut": round(agree / len(pairs), 4)}  # fmt: skip


# ---- power ------------------------------------------------------------------------------------


def _pmf(k: int, n: int, p: float) -> float:
    if p <= 0.0:
        return 1.0 if k == 0 else 0.0
    if p >= 1.0:
        return 1.0 if k == n else 0.0
    log = (math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1)
           + k * math.log(p) + (n - k) * math.log(1 - p))  # fmt: skip
    return math.exp(log)


def mcnemar_power(n: int, only_l: float, only_s: float, alpha: float = ALPHA) -> float:
    """P(exact McNemar p < alpha with L ahead) on `n` paired requests, when a request is
    L-only right with probability `only_l` and S-only right with `only_s`. Exact, by summing
    over the number of discordant pairs."""
    pd = only_l + only_s
    if n <= 0 or pd <= 0:
        return 0.0
    q = only_l / pd
    total = 0.0
    for d in range(1, n + 1):
        weight = _pmf(d, n, pd)
        if weight < 1e-12:
            continue
        for k in range(d, d // 2, -1):  # L-only counts, from the most extreme down
            if st.mcnemar_exact(k, d - k) >= alpha:
                break
            total += weight * _pmf(k, d, q)
    return round(total, 3)


def power_table(n: int) -> dict[str, Any]:
    """The primary test's power on `n` hittable requests, for a few discordance scenarios
    (L-only, S-only), and the L-only rate 80 % power needs at 0.02 S-only. The McNemar part
    only: the group-CI and net conditions of "mejora" lower it further."""
    table = {f"L-only {a:.2f}, S-only {b:.2f}": mcnemar_power(n, a, b) for a, b in SCENARIOS}
    needed = next((round(a / 1000, 3) for a in range(25, 501, 5)
                   if mcnemar_power(n, a / 1000, 0.02) >= 0.8), None)  # fmt: skip
    return {"n": n, "scenarios": table, "L_only_for_80pct_at_S_only_0.02": needed}
