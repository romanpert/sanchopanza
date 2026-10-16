"""F2's public outputs (docs/results/2026-10-16-memory-f2/), from the run folder, free.

- `rows-<run>.json`: every arm's row with numbers and flags only: no text the agent or the
  model wrote, no handoff text, no session id, no path (the work folder by its opaque name).
- `check`: the sealed analysis (`handoff_analyze.analyse`, as `handoff_night.table` ran it)
  recomputed from the full rows and from the public rows must equal the table the night wrote,
  byte for byte.
- `costs`: reported beside the sealed table, never deciding. Claude Code 2.1.287 reports, for a
  resumed `-p` turn, the session's cumulative `total_cost_usd` (session 1 plus the turn); the
  sealed table therefore counts H's session 1 twice. The turn's own cost is the reported total
  minus session 1's, checked against the turn's own tokens priced at Claude Code's rates
  (`meter.CLAUDE_CODE_RATES`, 1-hour cache writes). This gives each arm's cost per triple, the
  paired median ratios and what the lot spent.

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
import meter  # noqa: E402

RUNS = ("f2-pilot", "f2-sonnet", "f2-opus")
ROW_KEYS = ("scene", "model", "arm", "repeat", "planned", "tests_pass", "task_pass", "fact_pass",
            "decision_pass", "intact_pass", "kept_all", "cut", "cost", "jev_usd",
            "jev_decisions", "jev_failed", "code_decisions", "tokens", "subagents",
            "crossed_midnight", "limit_hit", "pasted_verbatim", "hook_starts")  # fmt: skip
SESSION_KEYS = ("tag", "returncode", "subtype", "timeout", "cost", "turns", "tools", "seconds",
                "tokens", "subagents", "limit_hit", "first_prompt", "last_prompt", "is_error",
                "touched")  # fmt: skip
HANDOFF_KEYS = (
    "returncode",
    "subtype",
    "cost",
    "cost_reported",
    "context_carried",
    "same_session",
    "first_prompt",
    "tokens",
    "seconds",
    "tools",
    "chars",
    "names",
)
INIT_KEYS = ("model", "version", "permission_mode", "api_key_source", "mcp_servers", "plugins",
             "skills", "agents")  # fmt: skip
MODEL_IDS = {"sonnet": meter.SONNET_55, "opus": meter.OPUS_55}


def public_row(row: dict[str, Any]) -> dict[str, Any]:
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


def table(rows: list[dict[str, Any]], run: str, out: Path | None) -> str:
    """The text `handoff_night.table` wrote for `run`."""
    plan = handoff.build_plan(run)
    planned = sorted({(s, m, r) for s, m, _, r in plan})
    result = handoff_analyze.analyse(rows, handoff.RUNS[run]["model"], out, planned)
    return json.dumps(result, indent=1)


def priced(tokens: dict[str, int], model: str) -> float:
    r = meter.rates_of(meter.CLAUDE_CODE_RATES, MODEL_IDS[model])
    return (tokens["input"] * r.input + tokens["output"] * r.output +
            tokens["cache_read"] * r.read + tokens["cache_write"] * r.write_1h) / 1e6  # fmt: skip


def own_cost(row: dict[str, Any]) -> float:
    """An arm's cost with H's handoff turn at its own cost (reported total minus session 1)."""
    cost = float(row["cost"]) + float(row.get("jev_usd") or 0.0)
    if row["arm"] != "H" or not row.get("handoff"):
        return cost
    return cost - float(row["sessions"][0]["cost"])


def costs(rows: list[dict[str, Any]], model: str) -> dict[str, Any]:
    h_rows = [r for r in rows if r["arm"] == "H" and r.get("handoff")]
    gaps = [abs(r["handoff"]["cost"] - r["sessions"][0]["cost"]
                - priced(r["handoff"]["tokens"], model)) for r in h_rows]  # fmt: skip
    gap = max(gaps, default=0.0)
    trip = handoff_analyze.triples([r for r in rows if r["model"] == model])
    done = [
        t for t in trip.values() if all(handoff_analyze.ran(t.get(a)) for a in ("N0", "H", "S"))
    ]

    def med(values: list[float]) -> float | None:
        return round(statistics.median(values), 6) if values else None

    per_arm = {a: med([own_cost(t[a]) for t in done]) for a in ("N0", "H", "S")}
    ratio = {f"S/{b}": med([own_cost(t["S"]) / own_cost(t[b]) for t in done])
             for b in ("H", "N0")}  # fmt: skip
    turn = med([r["handoff"]["cost"] - r["sessions"][0]["cost"] for r in h_rows])
    return {"model": model, "triples": len(done), "handoff_turn_own_cost_median": turn,
            "max_gap_to_tokens_priced": gap, "cost_median_usd": per_arm,
            "cost_ratio_median": ratio,
            "session_1_counted_twice_usd": round(sum(r["sessions"][0]["cost"] for r in h_rows),
                                                 6)}  # fmt: skip


def main(argv: list[str]) -> int:
    root, dest = Path(argv[0]), Path(argv[1])
    dest.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    for run in RUNS:
        rows = handoff.rows_of(root / run)
        public = [public_row(r) for r in rows]
        (dest / f"rows-{run}.json").write_text(json.dumps(public, indent=1) + "\n",
                                                encoding="utf-8", newline="\n")  # fmt: skip
        written = (root / f"{run}-table.json").read_text(encoding="utf-8")
        report[run] = {"table_from_rows": table(rows, run, root / run) == written,
                       "table_from_public_rows": table(public, run, None) == written,
                       "costs": costs(rows, handoff.RUNS[run]["model"]),
                       "ledger_usd": round(handoff.ledger(root / run), 6)}  # fmt: skip
        (dest / f"{run}-table.json").write_text(written, encoding="utf-8", newline="\n")
    spent = sum(v["ledger_usd"] for v in report.values())
    twice = sum(v["costs"]["session_1_counted_twice_usd"] for v in report.values())
    report["lot"] = {"ledger_usd": round(spent, 4), "session_1_counted_twice_usd": round(twice, 4),
                     "spent_usd": round(spent - twice, 4)}  # fmt: skip
    (dest / "costs.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8",
                                     newline="\n")  # fmt: skip
    print(json.dumps(report, indent=1))
    return 0 if all(v.get("table_from_rows", True) and v.get("table_from_public_rows", True)
                    for v in report.values()) else 1  # fmt: skip


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
