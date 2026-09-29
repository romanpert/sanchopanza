"""The registered analysis: runs.jsonl -> analysis.json, and the tables for the README.

    python run.py collect

Hypotheses as in prereg.md (and its amendment A2: judged on the tasks whose failing check can
reach the model, `check_position` early or late; reported on all tasks too; H6 for arm K). Paired
by task (every arm forks the same phase A). Facts' location
after the last compaction is read from the saved transcripts (~/.cache): the native summary text
and the guard block (the attachment that starts with the guard's header), and scored as
summary / guard / both / neither.
"""

# ruff: noqa: E501
from __future__ import annotations

import json
import random
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2] / "src"))
import arms  # noqa: E402
import run  # noqa: E402

from sanchopanza.context.guard import HEADER, contains  # noqa: E402

ONE_SHOT = ("token", "probe", "check", "rule")
VALUES = {"token": ("token",), "probe": ("probe_code", "tolerance"), "check": ("check_id", "check_expected"),
          "rule": ("rule_ref",)}  # fmt: skip


def _entries(path: Path) -> list[dict[str, Any]]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text("utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def after_last_compaction(path: Path) -> tuple[str, str]:
    """(native summary text, guard block text) of the last compaction in the session file."""
    summary, block = "", ""
    for entry in _entries(path):
        if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
            summary, block = "", ""
            continue
        text = json.dumps(entry, ensure_ascii=False)
        if entry.get("isCompactSummary"):
            content = (entry.get("message") or {}).get("content")
            summary = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        elif HEADER in text and not block:
            block = json.loads(json.dumps(text))  # the raw entry: the attachment's shape varies
    return summary, block


def where(row: dict[str, Any], facts: dict[str, Any]) -> dict[str, str]:
    path = arms.tree(row["model"]) / "runs" / row["task"] / row["arm"] / "session.jsonl"
    summary, block = after_last_compaction(path)
    out = {}
    for fact in ONE_SHOT:
        values = [str(facts[k]) for k in VALUES[fact]]
        s = all(contains(summary, v) for v in values)
        g = all(block and contains(block.replace("\\n", " "), v) for v in values)
        out[fact] = "both" if s and g else "summary" if s else "guard" if g else "neither"
    return out


def boot(pairs: Sequence[tuple[float, float]], seed: int = 20260929) -> list[float]:
    rng = random.Random(seed)
    diffs = []
    for _ in range(4000):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        diffs.append(sum(a - b for a, b in sample) / len(sample))
    diffs.sort()
    return [round(diffs[int(0.025 * len(diffs))], 4), round(diffs[int(0.975 * len(diffs))], 4)]


def mcnemar(only_a: int, only_b: int) -> float:
    from math import comb

    n = only_a + only_b
    if n == 0:
        return 1.0
    k = min(only_a, only_b)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n)


def arm_table(rs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "n": len(rs),
        "success": sum(r["success"] for r in rs),
        **{f: sum(r["facts"].get(f, False) for r in rs) for f in (*ONE_SHOT, "limit", "visible")},
        "one_shot": sum(r["facts"].get(f, False) for r in rs for f in ONE_SHOT),
        "usd": round(sum(r["cost"]["counted_usd"] for r in rs), 4),
        "input_tokens": sum(r["usage"]["input_all"] for r in rs),
        "compactions": [r["compaction"]["boundaries"] for r in rs],
    }


def judge(by: dict[str, dict[str, dict[str, Any]]], tasks: list[str]) -> dict[str, Any]:
    n, g, gj = (by.get(a, {}) for a in ("N", "G", "GJ"))
    paired = [t for t in tasks if t in n and t in g]
    tn, tg = arm_table([n[t] for t in paired]), arm_table([g[t] for t in paired])
    worst = max((tn[f] - tg[f] for f in ONE_SHOT), default=0)
    out: dict[str, Any] = {
        "paired_tasks": len(paired),
        "H1": {"G": tg["success"], "N": tn["success"], "holds": tg["success"] >= tn["success"] + 2,
               "mcnemar_p": mcnemar(sum(g[t]["success"] and not n[t]["success"] for t in paired),
                                    sum(n[t]["success"] and not g[t]["success"] for t in paired))},
        "H2": {"G": tg["one_shot"], "N": tn["one_shot"], "worst_single_fact_drop": worst,
               "holds": tg["one_shot"] >= tn["one_shot"] + 3 and worst <= 1},
        "H3": {"limit": [tg["limit"], tn["limit"]], "visible": [tg["visible"], tn["visible"]],
               "usd": [tg["usd"], tn["usd"]],
               "usd_ratio": round(tg["usd"] / tn["usd"], 3) if tn["usd"] else None,
               "usd_paired_diff_ci": boot([(g[t]["cost"]["counted_usd"], n[t]["cost"]["counted_usd"]) for t in paired]) if paired else None,
               "holds": tg["limit"] >= tn["limit"] - 1 and tg["visible"] >= tn["visible"] - 1
               and tg["usd"] <= 1.10 * tn["usd"]},
    }  # fmt: skip
    k = by.get("K", {})
    with_k = [t for t in tasks if t in k and t in g]
    if with_k:
        tk, tgk = arm_table([k[t] for t in with_k]), arm_table([g[t] for t in with_k])
        out["H6"] = {"tasks": with_k, "K": tk["success"], "G": tgk["success"],
                     "holds": tk["success"] >= tgk["success"] - 1,
                     "one_shot": [tk["one_shot"], tgk["one_shot"]],
                     "choosers": [c for t in with_k for c in k[t]["guard"]["choosers"]],
                     "notes_chars": [c for t in with_k for c in k[t]["guard"].get("notes_chars", [])],
                     "decider_usd": round(sum(decider_usd(k[t]) for t in with_k), 5)}  # fmt: skip
    both = [t for t in paired if t in gj]
    if both:
        tgj = arm_table([gj[t] for t in both])
        tg2 = arm_table([g[t] for t in both])
        out["H4"] = {"GJ": tgj["success"], "G": tg2["success"], "holds": tgj["success"] >= tg2["success"] - 1,
                     "decider_asked": sum(c == "decider" for t in both for c in gj[t]["guard"]["choosers"]),
                     "choosers": [c for t in both for c in gj[t]["guard"]["choosers"]]}  # fmt: skip
    return out


def decider_usd(row: dict[str, Any]) -> float:
    """The decider's cost in one arm's session, from its journal (every hook call appends)."""
    path = arms.tree(row["model"]) / "runs" / row["task"] / row["arm"] / "journal.jsonl"
    return sum(float(e.get("cost_usd") or (e.get("data") or {}).get("cost_usd") or 0.0) for e in _entries(path))


def measurable(facts: dict[str, Any]) -> list[str]:
    """Amendment A2: tasks whose failing check is not cut out of the log by Claude Code."""
    return sorted(t for t, f in facts.items() if f.get("check_position") != "middle")


def main() -> int:
    rows = [r for r in run.rows(run.B_ROWS) if r.get("valid")]
    facts = run.gen.load_facts(run.TASKS_DIR)
    report: dict[str, Any] = {"rows": len(rows), "invalid_rows": len(run.rows(run.INVALID_ROWS)),
                              "spent_usd": run.spent()}  # fmt: skip
    for model in arms.MODELS:
        mine = [r for r in rows if r["model"] == model]
        if not mine:
            continue
        by: dict[str, dict[str, dict[str, Any]]] = {}
        for r in mine:
            by.setdefault(r["arm"], {})[r["task"]] = r
        tasks = sorted({r["task"] for r in mine})
        report[model] = {
            "arms": {a: arm_table(list(v.values())) for a, v in by.items()},
            "per_task": {t: {a: {"success": by[a][t]["success"], "facts": by[a][t]["facts"],
                                 "compactions": by[a][t]["compaction"]["boundaries"],
                                 "usd": by[a][t]["cost"]["counted_usd"],
                                 "where": where(by[a][t], facts[t]),
                                 "guard": by[a][t].get("guard")}
                             for a in by if t in by[a]} for t in tasks},
            "judged": judge(by, [t for t in tasks if t in measurable(facts)]) if model == "haiku" else "descriptive",
            "judged_all_tasks": judge(by, tasks) if model == "haiku" else "descriptive",
        }  # fmt: skip
    (HERE / "analysis.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: (v["judged"] if isinstance(v, dict) and "judged" in v else v) for k, v in report.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
