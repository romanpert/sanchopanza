"""Browse, phase 4e (development): does the loop guard speak when the answer is in front of the
agent, and stay quiet when it is not? Replayed step by step on recorded sessions.

python benchmarks/browse/loop_replay.py --env-file PATH/.env          # asks Jev, under a ceiling
python benchmarks/browse/loop_replay.py                               # free: re-scores the cache

A live phase cannot tell a guard that is wrong from one that is silent, and turns are too noisy
to show a small effect (19, 20 and 37 turns for the same arm on the same task). This asks the
question the guard exists to answer, offline, at every step of every recorded session whose
answer appears on one page, and grades it against a label that needs no model: **is the answer
already in what the agent has in front of it?** - the task's own required substrings, looked
for in what `loop_hook.established` builds at that step.

So for each step: the label (answer visible or not), and `goal_met` as the guard would have got
it. What comes out is how often it would have spoken at the right moment, how often too early,
and how far ahead of the end of the session the right moment came - which is the saving the
guard could buy, read off the sessions themselves.

Only tasks whose answer sits on one page are replayed (A1, B1, B2): for an aggregation over many
pages the answer is never on one page, and this label would call every step "not yet".
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import pathlib
import re
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.context.transcript import calls as calls_of  # noqa: E402
from sanchopanza.context.transcript import messages_from_claude_code, task_of  # noqa: E402
from sanchopanza.harness import loop_hook  # noqa: E402
from sanchopanza.points import loop as point  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


nav = _load("browse_nav_e2e", HERE / "nav_e2e.py")
RESULTS = nav.RESULTS
CACHE = RESULTS / "loop-replay-cache.jsonl"
SINGLE_PAGE = ("A1", "B1", "B2")
SOURCES = ("nav-pilot", "nav-traps", "nav-loop", "nav-smoke")
CEILING_USD = 0.05
CUT = Thresholds().saturated
# Where a task's grading substrings would mislabel a page. B1's "first name" is the field's own
# label, on the form from the moment it appears, empty or not; the answer is on the page only
# once the field holds the last name typed into the other one.
LABELS: dict[str, list[Any]] = {"B1": ["first name lovelace"]}


def transcript_of(workdir: str) -> pathlib.Path | None:
    folder = pathlib.Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", workdir)
    found = sorted(folder.glob("*.jsonl")) if folder.is_dir() else []
    return found[0] if found else None


def steps_of(row: dict[str, Any], required: list[Any]) -> list[dict[str, Any]]:
    """Every tool result of a session, with what the guard would have been given at it."""
    path = transcript_of(row["workdir"])
    if path is None:
        return []
    messages = messages_from_claude_code(str(path))
    calls = calls_of(messages)
    goal = task_of(messages)
    out = []
    for i, call in enumerate(calls):
        name = call.tool.split("__")[-1]
        before = messages[: call.result_msg + 1]
        done = loop_hook.established(before, call.result, goal)
        facts = loop_hook.facts_seen(call.result, goal)
        out.append({
            "step": i + 1, "of": len(calls), "goal": goal, "done": done,
            "actions": loop_hook.actions_taken(calls[: i + 1]),
            "pending": f"{name} {loop_hook.short_input(call.tool, call.input)}",
            # On the page only: the narration says "I'll fill First Name" long before it is so.
            "visible": bool(facts) and nav.base.graded(facts, required),
            "blind": not facts,
        })  # fmt: skip
    return out


class Cache:
    def __init__(self, path: pathlib.Path) -> None:
        self.path, self.rows = path, {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row["key"]] = row

    def put(self, key: str, row: dict[str, Any]) -> None:
        self.rows[key] = row
        with self.path.open("a", encoding="utf-8") as sink:
            sink.write(json.dumps({"key": key, **row}) + "\n")


async def judge(step: dict[str, Any], squire: Squire | None, cache: Cache) -> float | None:
    state, questions = point.questions(
        goal=step["goal"],
        done=f"{step['done']}\n\nActions taken:\n{step['actions']}",
        pending=step["pending"],
    )
    key = hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()
    if key in cache.rows:
        return cache.rows[key]["goal_met"]
    if squire is None or squire.meter.cost_usd >= CEILING_USD:
        return None
    decision = await squire.decide("loop", state, questions)
    met = decision.answer("goal_met").truth
    if met is None:
        return None
    cache.put(key, {"goal_met": met, "repeats": decision.answer("repeats_check").truth})
    return met


def summarise(steps: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [s for s in steps if s.get("goal_met") is not None]
    pos = [s for s in judged if s["visible"]]
    neg = [s for s in judged if not s["visible"]]
    tp = sum(s["goal_met"] >= CUT for s in pos)
    fp = sum(s["goal_met"] >= CUT for s in neg)
    pairs = [(p["goal_met"], n["goal_met"]) for p in pos for n in neg]
    auc = (sum((a > b) + 0.5 * (a == b) for a, b in pairs) / len(pairs)) if pairs else None
    return {
        "steps_judged": len(judged),
        "answer_visible": len(pos),
        "not_yet": len(neg),
        "blind_steps": sum(s["blind"] for s in judged),
        f"spoke_when_visible_at_{CUT}": f"{tp}/{len(pos)}",
        f"spoke_too_early_at_{CUT}": f"{fp}/{len(neg)}",
        "auc_goal_met_vs_visible": round(auc, 3) if auc is not None else None,
        "goal_met_mean_visible": round(sum(s["goal_met"] for s in pos) / len(pos), 3)
        if pos
        else None,  # fmt: skip
        "goal_met_mean_not_yet": round(sum(s["goal_met"] for s in neg) / len(neg), 3)
        if neg
        else None,  # fmt: skip
    }


async def main_async(key: str) -> dict[str, Any]:
    required = {t[0]: t[3] for t in nav.TASKS + nav.TRAP_TASKS + nav.HARD_TASKS}
    required.update(LABELS)
    limits = Thresholds(max_usd=CEILING_USD, max_decisions=2000)
    squire = Squire(create("jev", api_key=key), thresholds=limits) if key else None
    cache = Cache(CACHE)
    sessions: list[dict[str, Any]] = []
    for source in SOURCES:
        for row in nav.done_sessions(RESULTS / f"{source}-sessions.jsonl"):
            if row.get("task") not in SINGLE_PAGE or row.get("not_run") or not row.get("workdir"):
                continue
            steps = steps_of(row, required[row["task"]])
            for step in steps:
                step["goal_met"] = await judge(step, squire, cache)
            first_visible = next((s["step"] for s in steps if s["visible"]), None)
            first_spoke = next((s["step"] for s in steps if (s.get("goal_met") or 0) >= CUT), None)
            sessions.append({
                "source": source, "task": row["task"], "arm": row["arm"], "run": row["run"],
                "turns": row.get("turns"), "steps": len(steps), "success": row.get("success"),
                "first_visible": first_visible, "first_spoke": first_spoke,
                "steps_after_visible": (len(steps) - first_visible) if first_visible else None,
                "goal_met": [s.get("goal_met") for s in steps],
                "visible": [s["visible"] for s in steps], "blind": [s["blind"] for s in steps],
            })  # fmt: skip
    every = [
        {"visible": v, "blind": b, "goal_met": g}
        for s in sessions
        for v, b, g in zip(s["visible"], s["blind"], s["goal_met"], strict=True)
    ]
    report = {
        "sessions": len(sessions),
        "jev_usd_this_run": round(squire.meter.cost_usd, 5) if squire else 0.0,
        "cut": CUT,
        "all": summarise(every),
        "by_task": {
            t: summarise(
                [
                    {"visible": v, "blind": b, "goal_met": g}
                    for s in sessions
                    if s["task"] == t
                    for v, b, g in zip(s["visible"], s["blind"], s["goal_met"], strict=True)
                ]
            )
            for t in SINGLE_PAGE
        },  # fmt: skip
        "sessions_detail": sessions,
    }
    (RESULTS / "loop-replay.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    key = nav.mcp.key_from(args.env_file) if args.env_file else ""
    report = asyncio.run(main_async(key))
    print(json.dumps({k: v for k, v in report.items() if k != "sessions_detail"}, indent=1))
    for s in report["sessions_detail"]:
        print(f"  {s['source']:10} {s['task']} {s['arm']:11} run{s['run']} steps={s['steps']:2} "
              f"visible_at={s['first_visible']} spoke_at={s['first_spoke']} "
              f"after_visible={s['steps_after_visible']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
