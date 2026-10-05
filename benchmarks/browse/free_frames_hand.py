"""Browse, development: the FRAMES sources pilot graded by hand, and the base arms cut at 70 %.

python benchmarks/browse/free_frames_hand.py  # free: the private rows in, frames-hand.json out

Reads the pilot's rows (`free_frames.SESSIONS`, outside the repository) and, where they are still
on disk, Claude Code's transcripts of each session. Writes task ids, booleans, counts and dollars
only: no question, no answer, no quote.

- Every final ANSWER, and every ANSWER given before the hook's block in the -SRC arms, was read by
  hand against the gold on 2026-10-05. `HAND_AFTER` and `HAND_BEFORE` list only the verdicts that
  differ from the runner's provisional grade, with the reason in the abstract.
- The base arms cut at 70 % of their cap: `free_cut.cut_at` with the `budget` rule on each base
  session's recorded cost trajectory. A cut session counts as wrong and costs what it had spent
  at the cut. A -SRC cap is that same 70 %, so a -SRC arm against its base cut differs by the
  hook (and by run-to-run variance), not by the budget.
- Paired by task, -SRC against base and against base cut, exact McNemar
  (`sanchopanza.eval.stats.mcnemar`).
- A wider leak scan than the runner's: the hosts that serve the set and the set's names in every
  tool input and result of every session, main agent and subagents.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import statistics
import sys
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from sanchopanza.eval.stats import mcnemar  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


frames = _load("browse_free_frames", HERE / "free_frames.py")
cut = _load("browse_free_cut", HERE / "free_cut.py")
trace = frames.trace
OUT = frames.RESULTS / "frames-hand.json"
CUT_FRACTION = 0.7
AT_CAP = 0.9
PAIRS = (("SONNET", "SONNET-SRC"), ("HAIKU", "HAIKU-SRC"))
_LEAK = re.compile(
    "|".join(re.escape(h) for h in frames.DENIED_HOSTS) + r"|frames-benchmark|google/frames"
    r"|frames-test|krishna et al",
    re.I,
)

# Hand verdicts on the final ANSWER that differ from the runner's grade (2026-10-05).
HAND_AFTER: dict[tuple[str, str], tuple[bool, str]] = {
    ("FR121", "SONNET"): (True, "the gold's name; the gold string appends a year"),
    ("FR121", "SONNET-SRC"): (True, "the gold's name; the gold string appends a year"),
    ("FR121", "HAIKU"): (True, "the gold's name; the gold string appends a year"),
    ("FR121", "HAIKU-SRC"): (True, "the gold's name; the gold string appends a year"),
    ("FR623", "SONNET"): (True, "the gold career named as the activity, not the job title"),
    ("FR524", "HAIKU"): (
        True,
        "the gold exactly; the runner normalises a dots-and-dashes gold to an empty string",
    ),
    ("FR187", "HAIKU-SRC"): (
        False,
        "after the block the ANSWER line withdraws the answer: it "
        "names the gold only as unverified",
    ),
}
# Hand verdicts on the ANSWER before the block (-SRC arms) that differ from the runner's grade.
HAND_BEFORE: dict[tuple[str, str], tuple[bool, str]] = {
    ("FR121", "SONNET-SRC"): (True, "as HAND_AFTER"),
    ("FR121", "HAIKU-SRC"): (True, "as HAND_AFTER"),
}
# Wrong against the gold and defensible from a source: flagged, not regraded.
DISPUTED = {
    "FR633": "one of the figures the answer is computed from differs between two sources; the "
    "gold follows one, both Sonnet arms the other",
}


# --- pure ---------------------------------------------------------------------------------------


def graded(row: Mapping[str, Any]) -> dict[str, Any]:
    """The row with `ok_hand` (final ANSWER) and `ok_hand_before` (before the block)."""
    key = (row["task"], row["arm"])
    after = HAND_AFTER.get(key, (bool(row.get("ok_auto")), ""))[0]
    before = HAND_BEFORE.get(key, (bool(row.get("ok_before")), ""))[0]
    return {**row, "ok_hand": after, "ok_hand_before": before}


def cut_view(row: Mapping[str, Any], right: bool) -> dict[str, Any]:
    """What `free_cut.cut_at` reads for the budget rule, from the row's recorded trajectory."""
    traj = [float(x) for x in row.get("trajectory") or [row["list_usd"]]]
    zeros = [0] * len(traj)
    return {"traj": traj, "cap": float(row["cap_usd"]), "searches": zeros, "others": zeros,
            "gold_seen": [False] * len(traj), "success": right}  # fmt: skip


def cut_row(row: Mapping[str, Any], fraction: float = CUT_FRACTION) -> dict[str, Any]:
    """A base session as if its cap had been `fraction` of it: wrong and cheaper when cut."""
    view = cut_view(row, bool(row["ok_hand"]))
    at = cut.cut_at(view, "budget", f=fraction)
    if at is None:
        return {**row, "cut": False}
    return {**row, "cut": True, "ok_hand": False, "list_usd": round(view["traj"][at], 4)}


def cell(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    costs = [float(r["list_usd"]) for r in rows]
    return {
        "sessions": len(rows),
        "right_hand": sum(bool(r["ok_hand"]) for r in rows),
        "right_runner": sum(bool(r.get("ok_auto")) for r in rows),
        "mean_usd": round(statistics.mean(costs), 4) if costs else None,
        "median_usd": round(statistics.median(costs), 4) if costs else None,
        "total_usd": round(sum(costs), 3),
        "hit_cap": sum(bool(r.get("hit_cap")) for r in rows),
        "at_90pct_of_cap": sum(float(r["list_usd"]) >= AT_CAP * float(r["cap_usd"]) for r in rows),
        "leak_runner": sum(bool(r.get("leak")) for r in rows),
        "hook_fired": sum(bool(r.get("hook_fired")) for r in rows),
        "no_tool_call": sum(not r.get("tools") for r in rows),
    }


def matrix(rows: Sequence[Mapping[str, Any]], before: str, after: str) -> dict[str, int]:
    """Right/wrong before the block against after it, on the sessions where the hook fired."""
    fired = [r for r in rows if r.get("hook_fired")]
    pairs = [(bool(r[before]), bool(r[after])) for r in fired]
    return {
        f"{'right' if b else 'wrong'}->{'right' if a else 'wrong'}": pairs.count((b, a))
        for b in (True, False)
        for a in (True, False)
    }


def spend_split(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """What a -SRC arm spent before and after the block, per session of the arm."""
    after = sum(float(r.get("usd_after_block") or 0.0) for r in rows)
    total = sum(float(r["list_usd"]) for r in rows)
    n = len(rows) or 1
    return {"usd_after_block_total": round(after, 3),
            "mean_usd_before_block": round((total - after) / n, 4),
            "mean_usd_after_block": round(after / n, 4)}  # fmt: skip


def paired(a: Sequence[Mapping[str, Any]], b: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Exact McNemar over the tasks both arms ran: `a_only` right in a alone, `b_only` in b."""
    by_task = {r["task"]: bool(r["ok_hand"]) for r in b}
    tasks = [r["task"] for r in a if r["task"] in by_task]
    mine = {r["task"]: bool(r["ok_hand"]) for r in a}
    a_only, b_only, p = mcnemar([mine[t] for t in tasks], [by_task[t] for t in tasks])
    gone = [t for t in tasks if mine[t] and not by_task[t]]
    come = [t for t in tasks if by_task[t] and not mine[t]]
    return {"tasks": len(tasks), "a_only": a_only, "b_only": b_only, "p_exact": round(p, 4),
            "a_only_tasks": gone, "b_only_tasks": come}  # fmt: skip


def report(rows: Sequence[Mapping[str, Any]], leaks: Mapping[str, int] | None) -> dict[str, Any]:
    rows = [graded(r) for r in rows]
    by_arm = {arm: [r for r in rows if r["arm"] == arm] for arm in frames.ARMS}
    out: dict[str, Any] = {
        "sessions": len(rows),
        "list_usd": round(sum(r["list_usd"] for r in rows), 2),
        "regraded_by_hand": {f"{t}-{a}": f"{v} ({why})" for (t, a), (v, why) in HAND_AFTER.items()},
        "regraded_before_block": {
            f"{t}-{a}": f"{v} ({why})" for (t, a), (v, why) in HAND_BEFORE.items()
        },
        "disputed_gold": DISPUTED,
        "leak_hand_scan": leaks,
        "by_arm": {arm: cell(group) for arm, group in by_arm.items()},
    }
    for base, src in PAIRS:
        cut_rows = [cut_row(r) for r in by_arm[base]]
        out["by_arm"][src]["before_after_hand"] = matrix(by_arm[src], "ok_hand_before", "ok_hand")
        out["by_arm"][src]["before_after_runner"] = matrix(by_arm[src], "ok_before", "ok_auto")
        out["by_arm"][src] |= spend_split(by_arm[src])
        out["by_arm"][f"{base}-CUT70"] = cell(cut_rows) | {
            "cut": [r["task"] for r in cut_rows if r["cut"]]
        }
        out[f"paired_{src}_vs_{base}"] = paired(by_arm[base], by_arm[src])
        out[f"paired_{src}_vs_{base}-CUT70"] = paired(cut_rows, by_arm[src])
    return out


# --- reading (local only) -----------------------------------------------------------------------


def session_leak(row: Mapping[str, Any]) -> bool | None:
    """Do the session's tool inputs or results name a host that serves the set or the set
    itself? None when its transcript is gone."""
    calls = trace.load_calls(trace.folder_of(row["workdir"]))
    if not calls:
        return None
    return bool(_LEAK.search(" ".join(c["results"] + json.dumps(c["inputs"]) for c in calls)))


def leak_scan(rows: Sequence[Mapping[str, Any]]) -> dict[str, int] | None:
    """Sessions whose tool inputs or results name a host that serves the set or the set itself;
    None when a transcript is gone."""
    found = [session_leak(row) for row in rows]
    if any(x is None for x in found):
        return None
    return {"sessions": len(rows), "naming_the_set_or_its_hosts": sum(found)}


def main() -> int:
    rows = frames.phase.counted(frames.free.nav.done_sessions(frames.SESSIONS))
    result = report(rows, leak_scan(rows))
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
