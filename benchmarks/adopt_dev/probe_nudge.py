"""Does Haiku call find_in_repo once its description says when, its server carries the same rule
as instructions, and a nudge suggests it after a wide early search? A development probe on the
behaviour set (`behaviour-set.json`: 7 issues no statement token greps to the gold within 5 hits,
3 controls where one does), arms S and N on each. Paid (subscription, list price).

    python -m benchmarks.adopt_dev.probe_nudge check     # free: see check_nudge.py
    python -m benchmarks.adopt_dev.probe_nudge run       # the probe (resumable)
    python -m benchmarks.adopt_dev.probe_nudge summary   # tables from the rows, free

Everything but the pins is the alwaysLoad probe's driver (`probe_alwaysload.py`, reused as is):
arm S is `sanchopanza install --scope project --write` from the frozen copy of e57c374 (extras jev
and mcp; find, its description, instructions and nudge all on by default there), wired through
`hook_env.py` as the sealed runner does; arm N is Claude Code alone. Claude Code 2.1.285, Haiku
4.5, 1.50 USD per call; a session starts only if the rows' cost so far plus its cap fits under
14.00 USD. Grading is the official SWE-bench harness.

Per session, besides what the alwaysLoad probe records: find's calls with the API call that made
each, the nudge's firings (journal kind `find_nudge`, hooks.jsonl lines of `find-hook`), searches
and find calls before the first Read of a gold file, and searches before the first edit
(`nudge-facts.json` beside `row.json`).

Writes only under ~/.cache/sanchopanza/adopt/dev-nudge/ and work-dn/. Log lines that end a run:
`PROBE DONE`, `PROBE STOP: <why>` or `PROBE FAILED: <why>`; the launcher adds `exit <n>`.
"""

from __future__ import annotations

import os

os.environ.setdefault("ADOPT_DEV_PROFILE", "nudge")

import argparse  # noqa: E402
import json  # noqa: E402
import signal  # noqa: E402
import statistics  # noqa: E402
import traceback  # noqa: E402
from typing import Any  # noqa: E402

from . import common  # noqa: E402

if common.PROFILE != "nudge":
    raise RuntimeError(f"common.py was pinned to {common.PROFILE!r} first: run this on its own")

from . import probe_alwaysload as base  # noqa: E402
from .nudge_facts import describe  # noqa: E402

OUT, PLAN = common.OUT, common.PLAN


def gold_of(name: str) -> list[str]:
    drawn = common.read_json(common.BEHAVIOUR_SET)
    return next(c["gold"] for c in drawn["classified"] if c["instance_id"] == name)


def class_of(name: str) -> str:
    drawn = common.read_json(common.BEHAVIOUR_SET)
    return "behaviour" if name in drawn["behaviour"] else "control"


def session_facts(name: str, arm: str) -> dict[str, Any] | None:
    evidence = OUT / name / arm
    if not (evidence / "row.json").exists():
        return None
    facts = describe(evidence, gold_of(name))
    (evidence / "nudge-facts.json").write_text(json.dumps(facts, indent=1), encoding="utf-8")
    return facts


def report_nudge(record: dict[str, Any]) -> None:
    facts = session_facts(record["instance"], record["arm"]) or {}
    gold = facts.get("before_gold_read", {})
    base.log(f"{record['instance']} {record['arm']}: find calls "
             f"{[c['api_call'] for c in facts.get('find_calls', [])]} nudge fired "
             f"{len(facts.get('nudge', {}).get('journal', []))} searches before gold read "
             f"{gold.get('searches')} first edit at call "
             f"{facts.get('first_edit_call')}")  # fmt: skip


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 4) if values else None


def arm_table(rows: list[dict[str, Any]], arm: str, cls: str | None) -> dict[str, Any]:
    mine = [r for r in rows if r["arm"] == arm and (cls is None or r["class"] == cls)]
    graded = [r for r in mine if r.get("resolved") is not None]
    reads = [r["nudge"]["before_gold_read"]["searches"] for r in mine
             if r["nudge"]["before_gold_read"]["searches"] is not None]  # fmt: skip
    return {"sessions": len(mine), "resolved": sum(bool(r["resolved"]) for r in graded),
            "graded": len(graded),
            "find_called": sum(bool(r["nudge"]["find_calls"]) for r in mine),
            "nudge_fired": sum(bool(r["nudge"]["nudge"]["journal"]) for r in mine),
            "median_cost_usd": _median([r["cost_usd"] for r in mine]),
            "median_searches_before_gold_read": _median(reads),
            "gold_never_read": len(mine) - len(reads)}  # fmt: skip


def summary() -> dict[str, Any]:
    done = base.summary()
    rows = []
    for row in done["rows"]:
        facts = session_facts(row["instance"], row["arm"]) or {}
        rows.append({**row, "class": class_of(row["instance"]), "nudge": facts})
    tables = {f"{arm} {cls or 'all'}": arm_table(rows, arm, cls)
              for arm in ("S", "N") for cls in (None, "behaviour", "control")}  # fmt: skip
    out = {**done, "rows": rows, "tables": tables}
    (OUT / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "run", "summary"))
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.action == "check":
        from .check_nudge import check

        return check()
    if args.action == "summary":
        print(json.dumps(summary()["tables"], indent=1))
        return 0
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # a stray Ctrl+C killed phase A mid-grade
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    base.AFTER_SESSION.append(report_nudge)
    base.log(f"PROBE START nudge plan {[(n, a) for n, a in PLAN]} spent {base.spent():.2f} USD "
             f"cap {common.TOTAL_CAP_USD:.2f}")  # fmt: skip
    try:
        base.probe()
    except base.Stop as why:
        summary()
        base.log(f"PROBE STOP: {why} (spent {base.spent():.2f} USD)")
        return 0
    except Exception as exc:  # noqa: BLE001  (logged with its trace; the monitor greps for it)
        traceback.print_exc()
        base.log(f"PROBE FAILED: {type(exc).__name__}: {exc} (spent {base.spent():.2f} USD)")
        return 1
    done = summary()
    base.log(f"PROBE DONE: {len(done['rows'])} rows, spent {done['spent_usd']:.2f} USD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
