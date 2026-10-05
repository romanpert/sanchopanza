"""Browse, development: the fetch pilot graded by hand, paired by task within each model.

python benchmarks/browse/free_fetch_pilot_hand.py  # free: private rows in, the JSON out

Reads the rows of `free_fetch_pilot.py` (outside the repository) and, where they are still on
disk, Claude Code's transcripts. Writes task ids, booleans, counts and dollars only: no question,
no answer, no quote.

- Every final ANSWER was read by hand against the gold. `HAND` lists only the verdicts that differ
  from the runner's provisional grade, with the reason in the abstract.
- Paired by task, -FETCH against its base, exact McNemar (`sanchopanza.eval.stats.mcnemar`).
- The same cells on the sessions that used the web at all in both arms of the pair: a session the
  model answers from memory says nothing about fetching.
- The wider leak scan of the first pilot (`free_frames_hand.leak_scan`).
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


hand = _load("browse_free_frames_hand", HERE / "free_frames_hand.py")
pilot = _load("browse_free_fetch_pilot", HERE / "free_fetch_pilot.py")
OUT = pilot.frames.RESULTS / "fetch-pilot-hand.json"
PAIRS = (("SONNET", "SONNET-FETCH"), ("HAIKU", "HAIKU-FETCH"))
WEB = ("web_search", "web_fetch", "fetch_passages")

# Hand verdicts on the final ANSWER that differ from the runner's grade (2026-10-05).
_SERIES = "the gold's yes and its item; the gold adds a detail the answer leaves out"
_UNIT = "the gold's number without its unit"
HAND: dict[tuple[str, str], tuple[bool, str]] = {
    ("FR110", "SONNET"): (True, _SERIES),
    ("FR110", "SONNET-FETCH"): (True, _SERIES),
    ("FR110", "HAIKU"): (True, _SERIES),
    ("FR161", "HAIKU"): (True, _UNIT),
    ("FR161", "HAIKU-FETCH"): (True, _UNIT),
}
# Wrong against the gold and defensible from a source: flagged, not regraded.
DISPUTED: dict[str, str] = {
    "FR502": "the question reads two ways; both Sonnet arms answered one reading's item, the gold "
    "follows the other; Haiku's wrong answer fits neither",
}


def graded(row: Mapping[str, Any]) -> dict[str, Any]:
    right = HAND.get((row["task"], row["arm"]), (bool(row.get("ok_auto")), ""))[0]
    return {**row, "ok_hand": right}


def used_web(row: Mapping[str, Any]) -> bool:
    calls = row.get("calls") or {}
    return any(calls.get(k) for k in WEB)


def pair_cells(base: Sequence[Mapping[str, Any]], arm: Sequence[Mapping[str, Any]]) -> dict:
    """Both arms' cells and McNemar, on every task and on the tasks where both used the web."""
    webbed = {r["task"] for r in base if used_web(r)} & {r["task"] for r in arm if used_web(r)}
    out: dict[str, Any] = {}
    for name, keep in (("all", None), ("both_used_the_web", webbed)):
        a = [r for r in base if keep is None or r["task"] in keep]
        b = [r for r in arm if keep is None or r["task"] in keep]
        out[name] = {
            "tasks": sorted(r["task"] for r in a) if keep is not None else len(a),
            "base": pilot.cell(a, "ok_hand"),
            "fetch": pilot.cell(b, "ok_hand"),
            "paired": hand.paired(a, b),
        }
    return out


def report(rows: Sequence[Mapping[str, Any]], leaks: Mapping[str, int] | None) -> dict[str, Any]:
    rows = [graded(r) for r in rows]
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in pilot.ARMS}
    out: dict[str, Any] = {
        "sessions": len(rows),
        "list_usd": round(sum(r["list_usd"] for r in rows), 2),
        "regraded_by_hand": {f"{t}-{a}": f"{v} ({why})" for (t, a), (v, why) in HAND.items()},
        "disputed_gold": DISPUTED,
        "leak_hand_scan": leaks,
        "by_arm": {arm: pilot.cell(group, "ok_hand") for arm, group in by_arm.items() if group},
    }
    for base, arm in PAIRS:
        if by_arm[base] and by_arm[arm]:
            out[f"{arm}_vs_{base}"] = pair_cells(by_arm[base], by_arm[arm])
    return out


def main() -> int:
    rows = pilot.phase.counted(pilot.free.nav.done_sessions(pilot.SESSIONS))
    result = report(rows, hand.leak_scan(rows))
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
