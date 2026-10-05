"""The judged pass at the fires the wider windows add over R4: Jev's `triage_many` over the free
source-only shortlist, as `judge.py` judges R4's fires, so judged gold@5 is measured there too.

    .venv/Scripts/python.exe -m benchmarks.find_auto.windows_judge          # recorded only, free
    .venv/Scripts/python.exe -m benchmarks.find_auto.windows_judge --live   # Jev, hard cap CAP_USD

Jobs: every hard session (singles and both probes) where W1-4 or W4-5 fires before the gold was
reached and R4 does not fire; one job per distinct (instance, query). Recorded answers come first
(`answers.jsonl`); live decisions are recorded there too (hashed keys, no text). The key is read
from TYPESAFE_API_KEY in the environment and never printed or written. Live calls stop once the
spend reaches CAP_USD - judge.MARGIN_USD.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from .evaluate import gold_lines, hits, qhash, verified
from .judge import CappedReplay
from .windows import FACTS, SHOWN, WORK, _judged, _known

CAP_USD = 0.10  # approved hard cap for this pass; a flag may lower it, never raise it
RULES = ("W1-4", "W4-5")
BASE = "R4 (today)"
OUT = WORK / "judged-added.json"


def jobs(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Distinct (instance, query) at the added fires, with the sessions and rules each serves."""
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for f in facts:
        if not f["hard"] or BASE in f["fires"]:
            continue
        for rule in RULES:
            fire = f["fires"].get(rule)
            if fire is None or (f["reach_call"] is not None and fire["call"] >= f["reach_call"]):
                continue
            key = (f["instance"], qhash(fire["query"]))
            job = found.setdefault(key, {"instance": f["instance"], "query": fire["query"],
                                         "tags": []})  # fmt: skip
            job["tags"].append(f"{rule}:{f['key']}")
    return list(found.values())


async def run(live: bool, cap: float) -> dict[str, Any]:
    inner = None
    if live:
        key = os.environ.get("TYPESAFE_API_KEY", "")
        if not key:
            raise SystemExit("--live needs TYPESAFE_API_KEY in the environment")
        from sanchopanza.providers import create

        inner = create("jev", api_key=key)
    decider = CappedReplay(inner, min(cap, CAP_USD))
    table = verified()
    rows = []
    for job in jobs(json.loads(FACTS.read_text(encoding="utf-8"))):
        keys = _known(job["instance"]).get(qhash(job["query"]), [])
        lines = gold_lines(table[job["instance"]]["patch"])
        before = decider.spent
        kept = await _judged(job["instance"], job["query"], keys, decider) if keys else None
        free = hits(keys, lines)[f"any@{SHOWN}"] if keys else None
        judged = None if kept is None else hits(kept, lines)[f"any@{SHOWN}"]
        rows.append({"instance": job["instance"], "tags": job["tags"], "kept": len(kept or []),
                     "free_at5": free, "judged_at5": judged,
                     "usd": round(decider.spent - before, 6)})  # fmt: skip
        print(f"{job['instance']} free={free} judged={judged} spent={decider.spent:.4f}",
              file=sys.stderr)  # fmt: skip
    report: dict[str, Any] = {"spend_usd": round(decider.spent, 6), "cap_usd": min(cap, CAP_USD),
                              "live_calls": decider.live_calls, "refused": decider.refused,
                              "jobs": len(rows), "by_rule": {}, "rows": rows}  # fmt: skip
    for rule in RULES:
        mine = [r for r in rows if any(t.startswith(rule + ":") for t in r["tags"])]
        done = [r for r in mine if r["judged_at5"] is not None]
        report["by_rule"][rule] = {
            "fires": sum(sum(t.startswith(rule + ":") for t in r["tags"]) for r in mine),
            "free_at5": f"{sum(bool(r['free_at5']) for r in mine)}/{len(mine)}",
            "judged_at5": f"{sum(bool(r['judged_at5']) for r in done)}/{len(done)}",
        }
    WORK.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--cap", type=float, default=CAP_USD)
    args = parser.parse_args(argv)
    report = asyncio.run(run(args.live, args.cap))
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
