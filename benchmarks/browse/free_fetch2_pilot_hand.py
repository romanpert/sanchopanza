"""Browse, development: the fetch v2 pilot graded by hand, paired by task.

python benchmarks/browse/free_fetch2_pilot_hand.py  # free: private rows in, the JSON out

As `free_fetch_pilot_hand.py`: every final ANSWER read by hand against the gold, `HAND` lists only
the verdicts that differ from the runner's provisional grade (reason in the abstract), exact
McNemar paired by task, the same cells on the tasks where both arms used the web, the wider leak
scan. Writes task ids, booleans, counts and dollars only: no question, no answer, no quote.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p2 = _load("browse_free_fetch2_pilot", HERE / "free_fetch2_pilot.py")
first = _load("browse_free_fetch_pilot_hand", HERE / "free_fetch_pilot_hand.py")
hand = first.hand
OUT = p2.frames.RESULTS / "fetch2-pilot-hand.json"
BASE, ARM = p2.ARMS

# Hand verdicts on the final ANSWER that differ from the runner's grade (2026-10-05).
HAND: dict[tuple[str, str], tuple[bool, str]] = {
    ("FR444", "HAIKU-FETCH2"): (True, "the gold's number in digits"),
    ("FR321", "HAIKU-FETCH2"): (True, "the gold's number without its unit"),
    # A judgment call, counted both ways in the README: the value is the gold's, the question
    # asks for it written in words.
    ("FR30", "HAIKU-FETCH2"): (True, "the gold's number in digits where the question asks words"),
}
# Wrong against the gold and defensible from a source: flagged, not regraded.
DISPUTED: dict[str, str] = {}


def graded(row: Mapping[str, Any]) -> dict[str, Any]:
    right = HAND.get((row["task"], row["arm"]), (bool(row.get("ok_auto")), ""))[0]
    return {**row, "ok_hand": right}


def report(rows: Sequence[Mapping[str, Any]], leaks: Mapping[str, int] | None) -> dict[str, Any]:
    rows = [graded(r) for r in rows]
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in p2.ARMS}
    out: dict[str, Any] = {
        "sessions": len(rows),
        "list_usd": round(sum(r["list_usd"] for r in rows), 2),
        "max_pages": p2.MAX_PAGES,
        "regraded_by_hand": {f"{t}-{a}": f"{v} ({why})" for (t, a), (v, why) in HAND.items()},
        "disputed_gold": DISPUTED,
        "leak_hand_scan": leaks,
        "by_arm": {arm: p2.pilot.cell(group, "ok_hand") for arm, group in by_arm.items() if group},
    }
    if by_arm[BASE] and by_arm[ARM]:
        out[f"{ARM}_vs_{BASE}"] = first.pair_cells(by_arm[BASE], by_arm[ARM])
    return out


def main() -> int:
    rows = p2.phase.counted(p2.free.nav.done_sessions(p2.SESSIONS))
    result = report(rows, hand.leak_scan(rows))
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
