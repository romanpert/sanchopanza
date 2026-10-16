"""F2's public outputs (docs/results/2026-10-16-memory-f2/), from the run folder, free.

- `rows-<run>.json`: every arm's row with numbers and flags only: no text the agent or the
  model wrote, no handoff text, no session id, no path (the work folder by its opaque name).
  H's handoff turn is at its own cost (`handoff_cost.own_row`), its reported total kept beside.
- `<run>-table.json`: the analysis (`handoff_analyze.analyse`) of the night's rows. It must give
  the same text from the full rows and from the public rows, and the same as the table the
  night wrote in every field but the costs (the criteria never read a cost).
- `costs.json`: per run, the handoff turn's own cost against its tokens priced at Claude Code's
  rates, and what the lot spent (sessions' own costs, Jev and the preflights).

    python benchmarks/memory_carry/handoff_publish.py ROOT OUT_DIR
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import handoff  # noqa: E402
import handoff_analyze  # noqa: E402
import handoff_cost  # noqa: E402

RUNS = ("f2-pilot", "f2-sonnet", "f2-opus")
ROW_KEYS = ("scene", "model", "arm", "repeat", "planned", "tests_pass", "task_pass", "fact_pass",
            "decision_pass", "intact_pass", "kept_all", "cut", "cost", "jev_usd",
            "jev_decisions", "jev_failed", "code_decisions", "tokens", "subagents",
            "crossed_midnight", "limit_hit", "pasted_verbatim", "hook_starts")  # fmt: skip
SESSION_KEYS = ("tag", "returncode", "subtype", "timeout", "cost", "turns", "tools", "seconds",
                "tokens", "subagents", "limit_hit", "first_prompt", "last_prompt", "is_error",
                "touched")  # fmt: skip
HANDOFF_KEYS = ("returncode", "subtype", "cost", "cost_reported_total", "cost_source",
                "cost_reported", "context_carried", "same_session", "first_prompt", "tokens",
                "seconds", "tools", "chars", "names")  # fmt: skip
INIT_KEYS = ("model", "version", "permission_mode", "api_key_source", "mcp_servers", "plugins",
             "skills", "agents")  # fmt: skip
COST_FIELDS = ("cost_median_usd", "cost_ratio_median")


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    row = handoff_cost.own_row(row)
    out = {k: row[k] for k in ROW_KEYS if k in row}
    out["folder"] = Path(str(row.get("folder") or "")).name
    out["given"] = len(row.get("given") or [])
    out["native_after_1"] = len(row.get("native_after_1") or [])
    out["sessions"] = [{**{k: s[k] for k in SESSION_KEYS if k in s},
                        "init": {k: (s.get("init") or {}).get(k) for k in INIT_KEYS},
                        "native": len(s.get("native") or [])}
                       for s in row.get("sessions") or []]  # fmt: skip
    if row.get("handoff"):
        out["handoff"] = {k: row["handoff"][k] for k in HANDOFF_KEYS if k in row["handoff"]}
    return out


def analysis(rows: list[dict[str, Any]], run: str, out: Path | None) -> dict[str, Any]:
    plan = handoff.build_plan(run)
    planned = sorted({(s, m, r) for s, m, _, r in plan})
    return handoff_analyze.analyse(rows, handoff.RUNS[run]["model"], out, planned)


def same_but_costs(new: dict[str, Any], old: dict[str, Any]) -> bool:
    return {k: v for k, v in new.items() if k not in COST_FIELDS} == \
        {k: v for k, v in old.items() if k not in COST_FIELDS}  # fmt: skip


def costs(rows: list[dict[str, Any]], model: str) -> dict[str, Any]:
    hands = [handoff_cost.own_row(r)["handoff"] for r in rows if r["arm"] == "H"
             and r.get("handoff")]  # fmt: skip
    gaps = [abs(h["cost"] - handoff_cost.priced(h["tokens"], model)) for h in hands]
    own = sorted(h["cost"] for h in hands)
    return {"model": model, "handoffs": len(hands),
            "handoff_turn_cost_median": round(statistics.median(own), 6) if own else None,
            "sources": sorted({h["cost_source"] for h in hands}),
            "max_gap_to_tokens_priced": max(gaps, default=0.0)}  # fmt: skip


def spent(rows: list[dict[str, Any]], root: Path, run: str) -> float:
    """What the run spent: every arm at its own cost, its Jev decisions, the preflights."""
    arms = sum(float(handoff_cost.own_row(r).get("cost") or 0.0) + float(r.get("jev_usd") or 0)
               for r in rows)  # fmt: skip
    path = root / run / "ledger.jsonl"
    lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    return arms + sum(float(x["usd"]) for x in lines if x["kind"] == "preflight")


def main(argv: list[str]) -> int:
    root, dest = Path(argv[0]), Path(argv[1])
    dest.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for run in RUNS:
        rows = handoff.rows_of(root / run)
        public = [public_row(r) for r in rows]
        (dest / f"rows-{run}.json").write_text(json.dumps(public, indent=1) + "\n",
                                                encoding="utf-8", newline="\n")  # fmt: skip
        full = json.dumps(analysis(rows, run, root / run), indent=1)
        night = json.loads((root / f"{run}-table.json").read_text(encoding="utf-8"))
        report[run] = {"table_from_public_rows": json.dumps(analysis(public, run, None),
                                                            indent=1) == full,
                       "same_as_the_night_but_costs": same_but_costs(json.loads(full), night),
                       "costs": costs(rows, handoff.RUNS[run]["model"]),
                       "spent_usd": round(spent(rows, root, run), 6)}  # fmt: skip
        (dest / f"{run}-table.json").write_text(full + "\n", encoding="utf-8", newline="\n")
    report["lot"] = {"spent_usd": round(sum(v["spent_usd"] for v in report.values()), 4)}
    (dest / "costs.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8",
                                     newline="\n")  # fmt: skip
    print(json.dumps(report, indent=1))
    ok = all(v["table_from_public_rows"] and v["same_as_the_night_but_costs"]
             for k, v in report.items() if k != "lot")  # fmt: skip
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
