"""Browse, development: the `sources` trigger, versions 2 and 2.1, replayed on both FRAMES pilots.

python benchmarks/browse/free_frames_variants.py  # free: transcripts in, frames-variants.json out

No model and no money. Every session of the two pilots (160) is cut at its first stop as in
`free_frames_trigger.py` (the -SRC and -SRC2 arms before the block, subagents by timestamp) and
read by the hook's own code: the signs as version 2 measured them, the signs with
`shown_work` (version 2.1), and the spend estimate. The variants differ in the number sign
(v2 / v2.1) and in the share of the cap past which the hook stands aside (0.6 as measured, 0.8,
or no check). A session counts as reaching a stop unless it ended at its cap without one, or (a
base arm) spent more than the -SRC cap, which a -SRC session would have hit first.

The bound on the gain assumes every block on a wrong session fixes it at pilot 2's rate (2 of 5)
and harms none (0 of 9 on pilot 2), and prices each block at what pilot 2's blocks cost after the
block, model by model. One exploratory sign is replayed beside them, never wired: `list`, an
ANSWER line of three or more items.

Writes ids, arm, booleans, sign names, counts and dollars only: no question, answer or quote.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import sys
import tempfile
from collections.abc import Mapping, Sequence
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "src"))

from sanchopanza.harness import sources_v2  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


trigger = _load("browse_free_frames_trigger", HERE / "free_frames_trigger.py")
hand2 = _load("browse_free_frames2_hand", HERE / "free_frames2_hand.py")
frames, frames2 = trigger.frames, hand2.frames2
OUT = frames.RESULTS / "frames-variants.json"
SRC_CAP = {"SONNET": 1.05, "HAIKU": 0.42}
FIX_RATE = 2 / 5  # pilot 2: wrong -> right in 2 of the 5 blocks on wrong sessions
SHARES = {"60 %": 0.6, "80 %": 0.8, "no check": None}
_ITEMS = re.compile(r",\s*(?:and\s+)?|\s+and\s+")


def model_of(arm: str) -> str:
    return "SONNET" if arm.startswith("SONNET") else "HAIKU"


def list_answer(answer: str) -> bool:
    """The exploratory sign: an ANSWER line of three or more items."""
    return len([x for x in _ITEMS.split(answer or "") if x.strip()]) >= 3


def reached_stop(row: Mapping[str, Any], cap: float) -> bool:
    """False for a session that ended at its cap with no stop, or a base session that spent
    more than the -SRC cap, which a -SRC session would have hit before stopping."""
    if row.get("subtype") == "error_max_budget_usd" and not row.get("hook_fired"):
        return False
    return frames.is_src(row["arm"]) or float(row["list_usd"]) <= cap


def read_session(row: Mapping[str, Any], right: bool, pilot: int) -> dict[str, Any]:
    folder = frames.trace.folder_of(row["workdir"])
    cap = SRC_CAP[model_of(row["arm"])]
    with tempfile.TemporaryDirectory() as tmp:
        main = trigger.at_first_stop(folder, pathlib.Path(tmp), frames.MARKS)
        entries = sources_v2._entries(main)
        every = [entries, *(sources_v2._entries(p) for p in sources_v2.subagent_transcripts(main))]
        names = [n for g in every for n in sources_v2._tool_uses(g).values()]
        results = [t for g in every for t in sources_v2._results(g)]
        final, question = sources_v2._last_text(entries), sources_v2._question(entries)
        spent = sources_v2._spent(every)
    return {"pilot": pilot, "task": row["task"], "arm": row["arm"], "model": model_of(row["arm"]),
            "right": right, "web_calls": sum(bool(sources_v2.WEB_TOOL.match(n)) for n in names),
            "stopped": reached_stop(row, cap), "estimated_usd": round(spent, 4), "cap_usd": cap,
            "signs_v2": sources_v2.signs(question, final, results),
            "signs_v21": sources_v2.signs(question, final, results, shown_work=True),
            "list": list_answer(sources_v2.answer_line(final)),
            "live_fired": bool(row.get("hook_fired"))}  # fmt: skip


def fires(s: Mapping[str, Any], signs: str, share: float | None, extra: bool = False) -> bool:
    found = bool(s[signs]) or (extra and s["list"])
    within = share is None or s["estimated_usd"] <= share * s["cap_usd"]
    return bool(s["stopped"] and s["web_calls"] and found and within)


def variants() -> dict[str, tuple[str, float | None, bool]]:
    out = {f"v2, {k}": ("signs_v2", v, False) for k, v in SHARES.items()}
    out |= {f"v2.1, {k}": ("signs_v21", v, False) for k, v in SHARES.items()}
    return out | {"v2 + list (exploratory), 60 %": ("signs_v2", 0.6, True)}


def cell(sessions: Sequence[Mapping[str, Any]], spec: tuple, block_usd: float) -> dict[str, Any]:
    fired = [s for s in sessions if fires(s, *spec)]
    wrong = [s for s in fired if not s["right"]]
    n, fixes = len(sessions), FIX_RATE * len(wrong)
    extra = len(fired) * block_usd
    return {"sessions": n, "fires_right": len(fired) - len(wrong), "fires_wrong": len(wrong),
            "wrong_tasks_fired": sorted({s["task"] for s in wrong}),
            "bound_right_per_100": round(100 * fixes / n, 2),
            "extra_usd_per_session": round(extra / n, 4),
            "usd_per_right_answer": round(extra / fixes, 3) if fixes else None}  # fmt: skip


def misses(sessions: Sequence[Mapping[str, Any]], spec: tuple) -> dict[str, int]:
    """Why a wrong session was not asked: no web, no stop, past the share, no sign."""
    out = {"no_web": 0, "no_stop": 0, "past_share": 0, "no_sign": 0}
    for s in (x for x in sessions if not x["right"] and not fires(x, *spec)):
        signs, share, extra = spec
        has = bool(s[signs]) or (extra and s["list"])
        key = ("no_web" if not s["web_calls"] else "no_stop" if not s["stopped"]
               else "no_sign" if not has else "past_share")  # fmt: skip
        out[key] += 1
    return out


def block_cost(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """Pilot 2: what the sessions spent after the block, per block, by model."""
    out = {}
    for model in SRC_CAP:
        fired = [r for r in rows if model_of(r["arm"]) == model and frames.is_src(r["arm"])
                 and r.get("hook_fired")]  # fmt: skip
        out[model] = sum(float(r.get("usd_after_block") or 0.0) for r in fired) / len(fired)
    return out


def summary(sessions: Sequence[Mapping[str, Any]], block_usd: Mapping[str, float]) -> dict:
    live = [s for s in sessions if s["pilot"] == 2 and s["arm"].endswith("-SRC2")]
    agree = sum(fires(s, "signs_v2", 0.6) == s["live_fired"] for s in live)
    out: dict[str, Any] = {"sessions": len(sessions), "fix_rate": FIX_RATE,
                           "block_usd": {k: round(v, 4) for k, v in block_usd.items()},
                           "replay_agrees_with_live_v2": f"{agree} of {len(live)}"}  # fmt: skip
    for model in SRC_CAP:
        group = [s for s in sessions if s["model"] == model]
        out[model] = {"sessions": len(group), "web": sum(bool(s["web_calls"]) for s in group),
                      "wrong": sum(not s["right"] for s in group)}  # fmt: skip
        for name, spec in variants().items():
            out[model][name] = cell(group, spec, block_usd[model]) | {"missed": misses(group, spec)}
    return out


def rows_of(pilot: int) -> list[tuple[Mapping[str, Any], bool]]:
    if pilot == 1:
        rows = frames.phase.counted(frames.free.nav.done_sessions(frames.SESSIONS))
        return [(r, trigger.right_at_stop(r)) for r in rows]
    rows = frames2.phase.counted(frames2.free.nav.done_sessions(frames2.SESSIONS))
    out = []
    for r in rows:
        graded = hand2.graded(r)
        at_stop = graded["ok_hand_before"] if frames.is_src(r["arm"]) else graded["ok_hand"]
        out.append((r, bool(at_stop)))
    return out


def main() -> int:
    sessions = [read_session(r, ok, p) for p in (1, 2) for r, ok in rows_of(p)]
    pilot2 = frames2.phase.counted(frames2.free.nav.done_sessions(frames2.SESSIONS))
    result = {"summary": summary(sessions, block_cost(pilot2)), "sessions": sessions}
    OUT.write_text(json.dumps(result, indent=1), encoding="utf-8")
    print(json.dumps(result["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
