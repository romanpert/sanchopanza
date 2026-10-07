"""The GAIA head-to-head's numbers: one cell per arm and the paired comparison per model.

Counts, costs and task ids only: nothing here reads a question or an answer. Success is GAIA's
official grade and, beside it, the grade with the hand verdicts. The comparison pairs the two
arms on each task (first run of each): exact McNemar on the discordant tasks
(`sanchopanza.eval.stats.mcnemar`, inlined so the runner needs no install) and a paired
bootstrap over tasks of the mean cost difference and the ratio of mean costs (Jev included in
SP's cost), with a fixed seed.
"""

from __future__ import annotations

import json
import math
import pathlib
import random
import statistics
from collections.abc import Mapping, Sequence
from typing import Any

SEED = 20261005
REPLICAS = 5000
TOKEN_KINDS = ("input", "cache_read", "cache_write", "output", "web_searches")


def _ok(row: Mapping[str, Any], hand: Mapping[tuple, bool]) -> bool:
    return bool(hand.get((row["task"], row["arm"], row["run"]), row["ok_oficial"]))


def cost(row: Mapping[str, Any]) -> float:
    """List price of the session, Jev's decisions included."""
    return float(row["list_usd"]) + float(row.get("jev_usd") or 0.0)


def _sum_maps(maps: Sequence[Mapping[str, int]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for m in maps:
        for k, v in m.items():
            out = {**out, k: out.get(k, 0) + int(v)}
    return dict(sorted(out.items()))


def arm_cell(mine: Sequence[Mapping[str, Any]], hand: Mapping[tuple, bool]) -> dict[str, Any]:
    if not mine:
        return {"sessions": 0}
    usd = [cost(r) for r in mine]
    turns = [int(r.get("turns") or 0) for r in mine]
    tokens = {k: sum(int((r.get("tokens") or {}).get(k, 0)) for r in mine) for k in TOKEN_KINDS}
    return {
        "sessions": len(mine),
        "ok_oficial": sum(bool(r["ok_oficial"]) for r in mine),
        "ok_with_hand": sum(_ok(r, hand) for r in mine),
        "by_level": {
            str(lv): f"{sum(bool(r['ok_oficial']) for r in mine if r['level'] == lv)}/"
            f"{sum(r['level'] == lv for r in mine)}"
            for lv in sorted({r["level"] for r in mine})
        },
        "total_usd": round(sum(usd), 4),
        "usd_per_correct": (round(sum(usd) / right, 4)
                            if (right := sum(_ok(r, hand) for r in mine)) else None),
        "mean_usd": round(statistics.mean(usd), 4),
        "median_usd": round(statistics.median(usd), 4),
        "mean_turns": round(statistics.mean(turns), 1),
        "median_turns": statistics.median(turns),
        "mean_wall_s": round(statistics.mean(r["wall_s"] for r in mine), 1),
        "median_wall_s": statistics.median(r["wall_s"] for r in mine),
        "tokens_total": tokens,
        "tools": _sum_maps([r.get("tools") or {} for r in mine]),
        "hooks_with_output": _sum_maps([r.get("hooks") or {} for r in mine]),
        "sp_hook_calls": _sum_maps([r.get("shim_runs") or {} for r in mine]),
        "sessions_with_sp_hooks": sum(int(r.get("shim_calls") or 0) > 0 for r in mine),
        "jev_calls": sum(int(r.get("jev_calls") or 0) for r in mine),
        "jev_by_point": _sum_maps([r.get("jev_by_point") or {} for r in mine]),
        "jev_errors": sum(int(r.get("jev_errors") or 0) for r in mine),
        "jev_error_kinds": _sum_maps([r.get("jev_error_kinds") or {} for r in mine]),
        "jev_usd": round(sum(float(r.get("jev_usd") or 0.0) for r in mine), 6),
        "hit_cap": sum(bool(r["hit_cap"]) for r in mine),
        "leak": sorted(r["task"] for r in mine if r["leak"]),
        "no_final_answer": sum(r["final_answer"] is None for r in mine),
        "denied": sum(r["denied"] + len(r["hook_denied"]) for r in mine),
    }


def mcnemar(a: Sequence[bool], b: Sequence[bool]) -> tuple[int, int, float]:
    """Discordant counts (a right and b wrong; b right and a wrong) and exact two-sided p."""
    only_a = sum(1 for x, y in zip(a, b, strict=True) if x and not y)
    only_b = sum(1 for x, y in zip(a, b, strict=True) if y and not x)
    n = only_a + only_b
    if n == 0:
        return 0, 0, 1.0
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return only_a, only_b, min(1.0, 2 * tail)


def bootstrap_cost(a: Sequence[float], b: Sequence[float], *, replicas: int = REPLICAS,
                   seed: int = SEED) -> dict[str, Any]:  # fmt: skip
    """Mean difference a - b and ratio mean(a)/mean(b), each with a paired 95 % interval."""
    n = len(a)
    rng = random.Random(seed)
    diffs: list[float] = []
    ratios: list[float] = []
    for _ in range(replicas):
        idx = [rng.randrange(n) for _ in range(n)]
        sa, sb = sum(a[i] for i in idx), sum(b[i] for i in idx)
        diffs.append((sa - sb) / n)
        ratios.append(sa / sb if sb else math.inf)
    diffs.sort()
    ratios.sort()
    lo, hi = int(0.025 * replicas), int(0.975 * replicas) - 1
    mean_b = sum(b) / n
    return {
        "mean_diff": round((sum(a) - sum(b)) / n, 4),
        "diff_ci95": [round(diffs[lo], 4), round(diffs[hi], 4)],
        "ratio": round(sum(a) / n / mean_b, 3) if mean_b else None,
        "ratio_ci95": [round(ratios[lo], 3), round(ratios[hi], 3)],
    }


KEY_FIELDS = ("task", "arm", "run")


def blind_sheet(items: Sequence[Mapping[str, Any]], sheet: pathlib.Path, key: pathlib.Path,
                seed: int = SEED) -> int:  # fmt: skip
    """A hand read with no arm in sight: each item's content under an opaque id, shuffled, in
    `sheet`; the id -> (task, arm, run) map in `key`, which the reader never opens. Private
    files: the content carries the set's questions and answers."""
    order = list(items)
    random.Random(seed).shuffle(order)
    ids = [f"r{n:04d}" for n in range(1, len(order) + 1)]
    content = [{"id": i, **{k: v for k, v in x.items() if k not in KEY_FIELDS}}
               for i, x in zip(ids, order, strict=True)]  # fmt: skip
    keys = [{"id": i, **{k: x[k] for k in KEY_FIELDS}} for i, x in zip(ids, order, strict=True)]
    sheet.write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in content),
                     encoding="utf-8")  # fmt: skip
    key.write_text("".join(json.dumps(x) + "\n" for x in keys), encoding="utf-8")
    return len(content)


def blind_verdicts(answers: pathlib.Path, key: pathlib.Path) -> list[dict[str, Any]]:
    """The reader's {"id", "ok"} lines turned back into hand verdicts through `key`; an id the
    key does not hold is refused, never guessed."""
    keys = {}
    for line in key.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entry = json.loads(line)
            keys[entry["id"]] = entry
    out = []
    for line in answers.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        given = json.loads(line)
        if given.get("id") not in keys:
            raise ValueError(f"verdict for an id the key does not hold: {given.get('id')!r}")
        out.append({**{k: keys[given["id"]][k] for k in KEY_FIELDS}, "ok": bool(given["ok"])})
    return out


MARGIN_POINTS = 2.0  # non-inferiority margin on success, fixed before any run (plan, section 2)
HEADROOM = 0.05  # N wrong on fewer than this share of the tasks: "sin margen"
ALPHA = 0.05


def bootstrap_success(a: Sequence[bool], b: Sequence[bool], *, replicas: int = REPLICAS,
                      seed: int = SEED) -> dict[str, Any]:  # fmt: skip
    """Success a - b in percentage points, with a paired 95 % interval (tasks resampled)."""
    n = len(a)
    rng = random.Random(seed)
    diffs = []
    for _ in range(replicas):
        idx = [rng.randrange(n) for _ in range(n)]
        diffs.append(100.0 * sum(int(a[i]) - int(b[i]) for i in idx) / n)
    diffs.sort()
    lo, hi = int(0.025 * replicas), int(0.975 * replicas) - 1
    return {
        "diff_points": round(100.0 * (sum(map(int, a)) - sum(map(int, b))) / n, 2),
        "diff_points_ci95": [round(diffs[lo], 2), round(diffs[hi], 2)],
    }


def verdict(pair: Mapping[str, Any], grade: str = "with_hand") -> str:
    """The preregistered verdict of S (`a`) against N (`b`) for one suite and one model:
    "sin margen" when N is wrong on fewer than HEADROOM of the tasks; "gana (coste)" when the
    cost ratio's 95 % interval lies below 1 and the success interval stays above -MARGIN_POINTS;
    "gana (éxito)" when McNemar's exact p < ALPHA with S right more often and the cost ratio's
    interval does not lie above 1; otherwise "no gana"."""
    tasks = int(pair.get("tasks") or 0)
    if not tasks:
        return "sin datos"
    cell, cost = pair[grade], pair["cost"]
    lo_diff = cell["diff_points_ci95"][0]
    lo_ratio, hi_ratio = cost["ratio_ci95"]
    if tasks - cell["b_ok"] < HEADROOM * tasks:
        return "sin margen"
    if hi_ratio < 1.0 and lo_diff >= -MARGIN_POINTS:
        return "gana (coste)"
    if cell["p"] < ALPHA and cell["a_only"] > cell["b_only"] and lo_ratio <= 1.0:
        return "gana (éxito)"
    return "no gana"


def paired(rows: Sequence[Mapping[str, Any]], hand: Mapping[tuple, bool], arm_a: str,
           arm_b: str) -> dict[str, Any]:  # fmt: skip
    """`arm_a` against `arm_b` on the tasks both ran (first run of each)."""
    first: dict[tuple, Mapping[str, Any]] = {}
    for r in sorted(rows, key=lambda r: r["run"]):
        first.setdefault((r["task"], r["arm"]), r)
    tasks = sorted(
        {t for t, arm in first if arm == arm_a} & {t for t, arm in first if arm == arm_b}
    )
    if not tasks:
        return {"tasks": 0}
    a = [first[(t, arm_a)] for t in tasks]
    b = [first[(t, arm_b)] for t in tasks]
    out: dict[str, Any] = {"tasks": len(tasks), "a": arm_a, "b": arm_b}
    for name, grade in (("oficial", lambda r: bool(r["ok_oficial"])),
                        ("with_hand", lambda r: _ok(r, hand))):  # fmt: skip
        ga, gb = [grade(r) for r in a], [grade(r) for r in b]
        only_a, only_b, p = mcnemar(ga, gb)
        out[name] = {
            "a_ok": sum(ga),
            "b_ok": sum(gb),
            "a_only": only_a,
            "b_only": only_b,
            "p": round(p, 4),
            "a_only_tasks": [t for t, x, y in zip(tasks, ga, gb, strict=True) if x and not y],
            "b_only_tasks": [t for t, x, y in zip(tasks, ga, gb, strict=True) if y and not x],
            **bootstrap_success(ga, gb),
        }
    out["cost"] = bootstrap_cost([cost(r) for r in a], [cost(r) for r in b])
    out["wall"] = bootstrap_cost([float(r["wall_s"]) for r in a], [float(r["wall_s"]) for r in b])
    return out
