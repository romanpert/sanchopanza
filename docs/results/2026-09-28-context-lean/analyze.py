"""Tables from `runs.jsonl` and `phase-a.jsonl`: per-arm success with Wilson 95 % intervals,
per-fact counts, paired differences in phase-B input tokens and cost with a paired bootstrap
95 % interval, exact tests on success, cache-read share. Free.

    python analyze.py          # prints, writes analysis.json

Only valid rows count (a row is invalid when its session did not finish, phase B is not in the
transcript, or an arm's plugin or hooks left no trace); invalid rows are listed. Costs and input
tokens are the true per-invocation figures (difference of the cumulative result JSON).
`wilson` is the e2e run's (`../2026-09-28-context-e2e/analyze.py`); `fisher` follows
`run_round2.fisher`.
"""

# ruff: noqa: E501
from __future__ import annotations

import importlib.util
import json
import random
import sys
from math import comb
from pathlib import Path
from statistics import mean, median
from typing import Any

HERE = Path(__file__).resolve().parent
FACTS = ("token", "check", "limit", "visible")
PAIRS = (("N", "L"), ("N", "K"), ("K", "L"))
BOOT = 10_000


def _e2e_analyze():
    spec = importlib.util.spec_from_file_location(
        "e2e_analyze", HERE.parent / "2026-09-28-context-e2e" / "analyze.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wilson = _e2e_analyze().wilson


def rows(name: str) -> list[dict[str, Any]]:
    path = HERE / name
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def fisher(a_yes: int, a_n: int, b_yes: int, b_n: int) -> float | None:
    """Two-sided Fisher exact p on a 2x2 table."""
    if not a_n or not b_n:
        return None
    total_yes, n = a_yes + b_yes, a_n + b_n

    def prob(k: int) -> float:
        return comb(a_n, k) * comb(b_n, total_yes - k) / comb(n, total_yes)

    ks = range(max(0, total_yes - b_n), min(a_n, total_yes) + 1)
    seen = prob(a_yes)
    return round(min(1.0, sum(prob(k) for k in ks if prob(k) <= seen * (1 + 1e-9))), 4)


def mcnemar(x_only: int, y_only: int) -> float | None:
    """Exact (binomial) two-sided McNemar p on the discordant pairs."""
    n = x_only + y_only
    if n == 0:
        return None
    tail = sum(comb(n, i) for i in range(min(x_only, y_only) + 1)) / 2**n
    return round(min(1.0, 2 * tail), 4)


def bootstrap(diffs: list[float], seed: str) -> tuple[float, float] | None:
    if not diffs:
        return None
    rng = random.Random(seed)
    means = sorted(mean(rng.choice(diffs) for _ in diffs) for _ in range(BOOT))
    return (round(means[int(0.025 * BOOT)], 4), round(means[int(0.975 * BOOT) - 1], 4))


def b_input(r: dict[str, Any]) -> float:
    true = r["cost"].get("true_input")
    return float(true if true is not None else r["usage"]["input_all"])


def b_usd(r: dict[str, Any]) -> float:
    return float(r["cost"]["counted_usd"])


def per_arm(rs: list[dict[str, Any]]) -> dict[str, Any]:
    n, k = len(rs), sum(r["success"] for r in rs)
    beh = [r["behaviour"] for r in rs]
    comp = [r["compaction"] for r in rs]
    usage = [r["usage"] for r in rs]
    read, total = sum(u["cache_read"] for u in usage), sum(u["input_all"] for u in usage)
    return {
        "n": n, "success": k, "success_ci": wilson(k, n),
        "facts": {f: sum(bool(r["facts"].get(f)) for r in rs) for f in FACTS},
        "facts_ci": {f: wilson(sum(bool(r["facts"].get(f)) for r in rs), n) for f in FACTS},
        "b_input_median": median(b_input(r) for r in rs), "b_input_sum": sum(b_input(r) for r in rs),
        "b_usd_sum": round(sum(b_usd(r) for r in rs), 4), "b_usd_mean": round(mean(b_usd(r) for r in rs), 4),
        "cache_read_share": round(read / total, 4) if total else None,
        "compaction_fired": sum(c["fired"] for c in comp),
        "compactions": sum(c["boundaries"] for c in comp),
        "first_after_vs_last_before": [(e["before"], e["after"]) for c in comp for e in c["events"]],
        "calls_before_first_compaction": [c["events"][0]["calls_before"] for c in comp if c["events"]],
        "search_archive_calls": sum(b["search_archive_calls"] for b in beh),
        "archive_reads": sum(b["archive_reads"] for b in beh),
        "one_shot_reruns": sum(b["one_shot_reruns"] for b in beh),
        "parallel_batches": sum(b["parallel_batches"] for b in beh),
        "arrival_cuts": sum((r.get("hooks") or {}).get("arrival_cuts", 0) for r in rs),
        "plugin_fallbacks": sum(bool(r["plugin"]["fallback"]) and r["plugin"]["compact_events"] > 0 for r in rs),
        "capped_or_error": sum(r.get("subtype") != "success" for r in rs),
    }  # fmt: skip


def paired(by: dict[tuple[str, str], dict[str, Any]], x: str, y: str, model: str) -> dict[str, Any] | None:
    tasks = sorted({t for (t, a) in by if a == x} & {t for (t, a) in by if a == y})
    if not tasks:
        return None
    rx, ry = [by[(t, x)] for t in tasks], [by[(t, y)] for t in tasks]
    d_in = [b_input(a) - b_input(b) for a, b in zip(rx, ry, strict=True)]
    d_usd = [b_usd(a) - b_usd(b) for a, b in zip(rx, ry, strict=True)]
    x_only = sum(a["success"] and not b["success"] for a, b in zip(rx, ry, strict=True))
    y_only = sum(b["success"] and not a["success"] for a, b in zip(rx, ry, strict=True))
    sx, sy = sum(a["success"] for a in rx), sum(b["success"] for b in ry)
    return {
        "tasks": len(tasks), f"success_{x}": sx, f"success_{y}": sy,
        f"input_{x}_minus_{y}_mean": round(mean(d_in), 1),
        "input_diff_ci": bootstrap(d_in, f"{model}-{x}-{y}-input"),
        f"usd_{x}_minus_{y}_mean": round(mean(d_usd), 5),
        "usd_diff_ci": bootstrap(d_usd, f"{model}-{x}-{y}-usd"),
        "discordant": {f"{x}_only": x_only, f"{y}_only": y_only},
        "mcnemar_exact_p": mcnemar(x_only, y_only), "fisher_p": fisher(sx, len(tasks), sy, len(tasks)),
        "per_fact_discordant": {f: (sum(bool(a["facts"].get(f)) and not b["facts"].get(f) for a, b in zip(rx, ry, strict=True)),
                                    sum(bool(b["facts"].get(f)) and not a["facts"].get(f) for a, b in zip(rx, ry, strict=True)))
                                for f in FACTS},
    }  # fmt: skip


def analyse() -> dict[str, Any]:
    a_rows, b_rows = rows("phase-a.jsonl"), rows("runs.jsonl")
    out: dict[str, Any] = {"models": {}, "invalid": [], "spend": {}}
    out["invalid"] = [{k: r.get(k) for k in ("model", "task", "arm", "status", "invalid_reasons")}
                      for r in b_rows if not r["valid"]]  # fmt: skip
    for model in sorted({r["model"] for r in a_rows + b_rows}):
        valid = [r for r in b_rows if r["model"] == model and r["valid"]]
        by = {(r["task"], r["arm"]): r for r in valid}
        arms_seen = sorted({r["arm"] for r in valid})
        pa = [r for r in a_rows if r["model"] == model]
        out["models"][model] = {
            "phase_a": {"n": len(pa), "valid": sum(r["valid"] for r in pa),
                        "usd": round(sum(r["cost"]["counted_usd"] for r in pa), 4),
                        "last_context_median": median(r["transcript"]["last_context"] for r in pa) if pa else None,
                        "token_in_model_text": sum(r.get("token_in_model_text", False) for r in pa)},
            "arms": {arm: per_arm([r for r in valid if r["arm"] == arm]) for arm in arms_seen},
            "paired": {f"{x}_vs_{y}": paired(by, x, y, model) for x, y in PAIRS},
        }  # fmt: skip
    out["spend"] = {"phase_a_usd": round(sum(r["cost"]["counted_usd"] for r in a_rows), 4),
                    "phase_b_usd": round(sum(r["cost"]["counted_usd"] for r in b_rows), 4)}  # fmt: skip
    return out


def main() -> int:
    result = analyse()
    (HERE / "analysis.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
