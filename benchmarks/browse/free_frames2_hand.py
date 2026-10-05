"""Browse, development: the second FRAMES pilot (sources v2) by hand, and the base cut at 70 %.

python benchmarks/browse/free_frames2_hand.py  # free: the private rows in, frames2-hand.json out

As `free_frames_hand.py` for the first pilot, on the rows of `free_frames2.py`. Writes task ids,
booleans, sign names, counts and dollars only: no question, no answer, no quote.

- Every final ANSWER, and every ANSWER given before the hook's block in the -SRC2 arms, was read
  by hand against the gold. `HAND_AFTER` and `HAND_BEFORE` list only the verdicts that differ
  from the runner's provisional grade, with the reason in the abstract.
- Where the hook fired, right or wrong at the stop it blocked (by hand), and on which signs; where
  it stood aside, whether for no sign or for the cap.
- The base arms cut at 70 % of their cap (`free_cut.cut_at`, budget rule), paired by task with
  the -SRC2 arms: exact McNemar.
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
frames2 = _load("browse_free_frames2", HERE / "free_frames2.py")
OUT = hand.frames.RESULTS / "frames2-hand.json"
PAIRS = (("SONNET", "SONNET-SRC2"), ("HAIKU", "HAIKU-SRC2"))

# Hand verdicts on the final ANSWER that differ from the runner's grade (2026-10-05).
HAND_AFTER: dict[tuple[str, str], tuple[bool, str]] = {
    ("FR425", "HAIKU"): (True, "the gold's name with the initials run together"),
    ("FR55", "SONNET"): (
        True,
        "the two gold items named as the ones survived, the third as the cause of death",
    ),
    ("FR142", "HAIKU"): (True, "the gold law under its short name, with the section"),
    ("FR142", "HAIKU-SRC2"): (True, "the gold law without the leading article"),
}
# Hand verdicts on the ANSWER before the block (-SRC2 arms) that differ from the runner's grade.
HAND_BEFORE: dict[tuple[str, str], tuple[bool, str]] = {}
# Wrong against the gold and defensible from a source: flagged, not regraded.
DISPUTED: dict[str, str] = {}


def graded(row: Mapping[str, Any]) -> dict[str, Any]:
    key = (row["task"], row["arm"])
    after = HAND_AFTER.get(key, (bool(row.get("ok_auto")), ""))[0]
    before = HAND_BEFORE.get(key, (bool(row.get("ok_before")), ""))[0]
    if not row.get("hook_fired"):
        before = after  # no block: the answer at the stop is the final one
    return {**row, "ok_hand": after, "ok_hand_before": before}


def trigger(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Where the hook fired or stood aside, against the hand grade at that stop."""
    seen = [r for r in rows if r.get("hook_seen")]

    def n(right: bool, fired: bool) -> int:
        return sum(
            1 for r in seen if bool(r["ok_hand_before"]) is right and bool(r["hook_fired"]) is fired
        )

    signs: dict[str, int] = {}
    for r in seen:
        for sign in r["hook_seen"].get("signs") or [] if r.get("hook_fired") else []:
            signs[sign] = signs.get(sign, 0) + 1
    quiet = [r for r in seen if not r.get("hook_fired")]
    return {
        "checked": len(seen),
        "fires_right": n(True, True),
        "fires_wrong": n(False, True),
        "silent_right": n(True, False),
        "silent_wrong": n(False, False),
        "signs_when_fired": signs,
        "silent_over_cap": sum(bool(r["hook_seen"].get("over_cap")) for r in quiet),
        "silent_over_cap_with_signs": sum(
            bool(r["hook_seen"].get("over_cap") and r["hook_seen"].get("signs")) for r in quiet
        ),
        "silent_no_web": sum(not r["hook_seen"].get("web_calls") for r in quiet),
        "fired_tasks": sorted(r["task"] for r in seen if r.get("hook_fired")),
    }


def report(rows: Sequence[Mapping[str, Any]], leaks: Mapping[str, int] | None) -> dict[str, Any]:
    rows = [graded(r) for r in rows]
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in frames2.ARMS}
    out: dict[str, Any] = {
        "sessions": len(rows),
        "list_usd": round(sum(r["list_usd"] for r in rows), 2),
        "regraded_by_hand": {f"{t}-{a}": f"{v} ({why})" for (t, a), (v, why) in HAND_AFTER.items()},
        "regraded_before_block": {
            f"{t}-{a}": f"{v} ({why})" for (t, a), (v, why) in HAND_BEFORE.items()
        },
        "disputed_gold": DISPUTED,
        "leak_hand_scan": leaks,
        "by_arm": {arm: hand.cell(group) for arm, group in by_arm.items()},
    }
    for base, src in PAIRS:
        cut_rows = [hand.cut_row(r) for r in by_arm[base]]
        cell = out["by_arm"][src]
        cell["before_after_hand"] = hand.matrix(by_arm[src], "ok_hand_before", "ok_hand")
        cell["before_after_runner"] = hand.matrix(by_arm[src], "ok_before", "ok_auto")
        cell["trigger"] = trigger(by_arm[src])
        cell |= hand.spend_split(by_arm[src])
        out["by_arm"][f"{base}-CUT70"] = hand.cell(cut_rows) | {
            "cut": [r["task"] for r in cut_rows if r["cut"]]
        }
        out[f"paired_{src}_vs_{base}"] = hand.paired(by_arm[base], by_arm[src])
        out[f"paired_{src}_vs_{base}-CUT70"] = hand.paired(cut_rows, by_arm[src])
    return out


def main() -> int:
    rows = frames2.phase.counted(frames2.free.nav.done_sessions(frames2.SESSIONS))
    result = report(rows, hand.leak_scan(rows))
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
