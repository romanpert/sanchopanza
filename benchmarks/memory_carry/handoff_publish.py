"""The public outputs of F2 (docs/results/2026-10-16-memory-f2/), W17
(docs/results/2026-10-16-memory-w17/) and the equal-work lot
(docs/results/2026-10-17-memory-equal-work/), from the lot's folder, free.

- `rows-<run>.json`: every arm's row with numbers and flags only: no text the agent or the
  model wrote, no handoff text, no session id, no path (the work folder by its opaque name).
  H's handoff turn is at its own cost (`handoff_cost.own_row`), its reported total kept beside.
  The equal-work rows also keep the checks after session 2 and the nudge's numbers and flags
  (its own cost as the night recorded it), not the id of the session it resumed.
- `<run>-table.json`: the run's sealed analysis of the night's rows (`handoff_analyze.analyse`
  for F2, `handoff_pairs.analyse` for W17, `handoff_ew.analyse` for the equal-work lot). It must
  give the same text from the full rows and from the public rows, and the same as the table the
  night wrote: in every field for W17 and the equal-work lot, in every field but the costs for
  F2 (H's handoff turn re-costed after the night; the criteria never read a cost).
- `costs.json`: per run what it spent (sessions' own costs, Jev and the preflights) and, for F2,
  the handoff turn's own cost against its tokens priced at Claude Code's rates. The runs already
  in an existing costs.json are kept, and its `lot` total is over all of them (W17's Sonnet run
  and its Opus redo are published from different lot folders).

    python benchmarks/memory_carry/handoff_publish.py ROOT OUT_DIR [RUN ...]

With no RUN, F2's three runs.
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
import handoff_ew  # noqa: E402
import handoff_pairs  # noqa: E402

RUNS = ("f2-pilot", "f2-sonnet", "f2-opus")
ROW_KEYS = ("scene", "model", "arm", "repeat", "planned", "tests_pass", "task_pass", "fact_pass",
            "decision_pass", "intact_pass", "kept_all", "cut", "cost", "jev_usd",
            "jev_decisions", "jev_failed", "code_decisions", "tokens", "subagents",
            "crossed_midnight", "limit_hit", "pasted_verbatim", "hook_starts",
            # W17's rows only: the stratum, the install's scope, the call cap, S's send-backs
            # by another rule than the scene's own, and a session charged for reporting no cost
            "line", "scope", "call_cap", "sendbacks_other_rule", "cost_charged",
            # the equal-work lot's rows only: the checks after session 2, whether it was nudged
            "kept_all_s2", "checks_s2", "nudged")  # fmt: skip
SESSION_KEYS = ("tag", "returncode", "subtype", "timeout", "cost", "turns", "tools", "seconds",
                "tokens", "subagents", "limit_hit", "first_prompt", "last_prompt", "is_error",
                "touched")  # fmt: skip
HANDOFF_KEYS = ("returncode", "subtype", "cost", "cost_reported_total", "cost_source",
                "cost_reported", "context_carried", "same_session", "first_prompt", "tokens",
                "seconds", "tools", "chars", "names")  # fmt: skip
NUDGE_KEYS = ("tag", "returncode", "subtype", "timeout", "cost", "cost_reported",
              "cost_reported_total", "cost_source", "cost_charged", "context_carried",
              "same_session", "first_prompt", "last_prompt", "tokens", "seconds", "turns", "tools",
              "touched", "subagents", "session_starts", "tree_kept", "first_request",
              "session_2_last_request", "chars")  # fmt: skip
INIT_KEYS = ("model", "version", "permission_mode", "api_key_source", "mcp_servers", "plugins",
             "skills", "agents")  # fmt: skip
COST_FIELDS = ("cost_median_usd", "cost_ratio_median")


CHECK_KEYS = ("tests_pass", *(f"{c}_pass" for c in handoff.CHECKS), "kept_all")


def public_checks(found: dict[str, Any]) -> dict[str, Any]:
    """The checks after session 2: the scene's checks' flags only (`handoff.CHECKS`)."""
    return {k: found[k] for k in CHECK_KEYS if k in (found or {})}


def public_row(row: dict[str, Any]) -> dict[str, Any]:
    row = handoff_cost.own_row(row)
    out = {k: public_checks(row[k]) if k == "checks_s2" else row[k] for k in ROW_KEYS if k in row}
    out["folder"] = Path(str(row.get("folder") or "")).name
    out["given"] = len(row.get("given") or [])
    out["native_after_1"] = len(row.get("native_after_1") or [])
    out["sessions"] = [{**{k: s[k] for k in SESSION_KEYS if k in s},
                        "init": {k: (s.get("init") or {}).get(k) for k in INIT_KEYS},
                        "native": len(s.get("native") or [])}
                       for s in row.get("sessions") or []]  # fmt: skip
    if row.get("handoff"):
        out["handoff"] = {k: row["handoff"][k] for k in HANDOFF_KEYS if k in row["handoff"]}
    if "nudge" in row:
        out["nudge"] = public_nudge(row["nudge"] or {})
    return out


def public_nudge(push: dict[str, Any]) -> dict[str, Any]:
    """The nudge's numbers and flags: not the session it resumed, its start time or its text."""
    out = {k: push[k] for k in NUDGE_KEYS if k in push}
    if "init" in push:
        out["init"] = {k: (push.get("init") or {}).get(k) for k in INIT_KEYS}
    return out


def planned(run: str) -> list[tuple[str, str, int]]:
    return sorted({(s, m, r) for s, m, _, r in handoff.build_plan(run)})


def analysis(rows: list[dict[str, Any]], run: str, out: Path | None) -> dict[str, Any]:
    """The run's sealed analysis: the equal-work lot's (`handoff_ew`), W17's pairs
    (`handoff_pairs`) or F2's triples (`handoff_analyze`)."""
    if handoff.lot_of(run) == "ew":
        handoff_ew.model_is_mine(handoff.RUNS[run]["model"], run)
        return handoff_ew.analyse(rows, out, planned(run))
    sealed = handoff_pairs if handoff.lot_of(run) == "w17" else handoff_analyze
    return sealed.analyse(rows, handoff.RUNS[run]["model"], out, planned(run))


def same_as_night(new: dict[str, Any], old: dict[str, Any], run: str) -> bool:
    """W17's and the equal-work lot's tables equal the night's in every field; F2's in every
    field but the costs."""
    skip = COST_FIELDS if handoff.lot_of(run) == "f2" else ()
    return {k: v for k, v in new.items() if k not in skip} == \
        {k: v for k, v in old.items() if k not in skip}  # fmt: skip


def runs_of(names: list[str]) -> tuple[str, ...]:
    for name in names:
        if name not in handoff.RUNS:
            raise SystemExit(f"{name}: not a run ({', '.join(handoff.RUNS)})")
    return tuple(names) or RUNS


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


def one_lot(names: list[str]) -> None:
    """Refuses (SystemExit) a costs.json whose runs, kept or new, are not all runs of one lot
    (`handoff.lot_of`): a results folder never mixes F2, W17 and the equal-work lot."""
    unknown = sorted({k for k in names if k not in handoff.RUNS})
    if unknown:
        raise SystemExit(f"costs.json: {', '.join(unknown)} not a run ({', '.join(handoff.RUNS)})")
    lots = sorted({handoff.lot_of(k) for k in names})
    if len(lots) > 1:
        raise SystemExit(f"costs.json would mix the lots {', '.join(lots)}: {', '.join(names)}")


def merged_costs(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    """costs.json after publishing `new`: the runs already there are kept (a lot's runs may live
    in different lot folders, as W17's Sonnet run and its Opus redo), each run published now
    replaces its entry, and the lot's total is recomputed over all of them (`one_lot` first)."""
    one_lot([k for k in (*old, *new) if k != "lot"])
    runs = {k: v for k, v in old.items() if k != "lot"}
    runs = {**runs, **{k: v for k, v in new.items() if k != "lot"}}
    total = round(sum(v["spent_usd"] for v in runs.values()), 4)
    return {**runs, "lot": {"spent_usd": total}}


def main(argv: list[str]) -> int:
    root, dest = Path(argv[0]), Path(argv[1])
    runs = runs_of(argv[2:])
    dest.mkdir(parents=True, exist_ok=True)
    old_costs = dest / "costs.json"
    old = json.loads(old_costs.read_text(encoding="utf-8")) if old_costs.exists() else {}
    one_lot([k for k in (*old, *runs) if k != "lot"])  # before anything is written to `dest`
    report: dict[str, Any] = {}
    for run in runs:
        rows = handoff.rows_of(root / run)
        public = [public_row(r) for r in rows]
        (dest / f"rows-{run}.json").write_text(json.dumps(public, indent=1) + "\n",
                                                encoding="utf-8", newline="\n")  # fmt: skip
        full = json.dumps(analysis(rows, run, root / run), indent=1, ensure_ascii=False)
        night = json.loads((root / f"{run}-table.json").read_text(encoding="utf-8"))
        same = "same_as_the_night_but_costs" if handoff.lot_of(run) == "f2" else \
            "same_as_the_night"  # fmt: skip
        report[run] = {"table_from_public_rows": json.dumps(analysis(public, run, None), indent=1,
                                                            ensure_ascii=False) == full,
                       same: same_as_night(json.loads(full), night, run)}  # fmt: skip
        if handoff.lot_of(run) == "f2":
            report[run]["costs"] = costs(rows, handoff.RUNS[run]["model"])
        report[run]["spent_usd"] = round(spent(rows, root, run), 6)
        (dest / f"{run}-table.json").write_text(full + "\n", encoding="utf-8", newline="\n")
    report = merged_costs(old, report)
    (dest / "costs.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8",
                                     newline="\n")  # fmt: skip
    print(json.dumps(report, indent=1))
    ok = all(v["table_from_public_rows"] and v.get("same_as_the_night_but_costs",
                                                   v.get("same_as_the_night"))
             for k, v in report.items() if k in runs)  # fmt: skip
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
