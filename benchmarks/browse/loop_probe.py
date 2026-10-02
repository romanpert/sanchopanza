"""Browse, phase 4d: does the loop guard see the answer once the page is part of `done`?

python benchmarks/browse/loop_probe.py --env-file PATH/.env

The first HAIKU-LOOP sessions asked `goal_met` twelve times and got 0.01-0.03 every time, in a
session that ended with the answer in hand. The diagnosis was that `done` held the agent's
narration and a small model narrates intent, not findings. The fix adds what the page says
(`loop_hook.facts_seen`). This asks the same question both ways on the recorded sessions'
**last** tool result, where the answer is on screen if it is anywhere.

Two Jev decisions per session, about 0.00004 USD each. A ceiling is in the code anyway.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import pathlib
import re
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.context.transcript import messages_from_claude_code, task_of  # noqa: E402
from sanchopanza.harness import loop_hook  # noqa: E402
from sanchopanza.points import loop as point  # noqa: E402
from sanchopanza.policy import Thresholds  # noqa: E402
from sanchopanza.providers import create  # noqa: E402
from sanchopanza.squire import Squire  # noqa: E402

RESULTS = ROOT / "docs" / "results" / "2026-10-02-browse-nav"
SESSIONS = (RESULTS / "nav-loop-sessions.jsonl", RESULTS / "nav-traps-sessions.jsonl")
CEILING_USD = 0.02


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


mcp = _load("browse_e2e_mcp", HERE / "e2e_mcp.py")


def last_result(workdir: str) -> tuple[str, list[dict[str, Any]]]:
    """The text of the last tool result of a recorded session, and its messages."""
    slug = re.sub(r"[^A-Za-z0-9]", "-", workdir)
    folder = pathlib.Path.home() / ".claude" / "projects" / slug
    for path in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        messages = messages_from_claude_code(str(path))
        from sanchopanza.context.transcript import calls as calls_of

        calls = calls_of(messages)
        if calls:
            return calls[-1].result, messages
    return "", []


async def ask(squire: Squire, goal: str, done: str, pending: str) -> dict[str, float]:
    state, questions = point.questions(goal=goal, done=done, pending=pending)
    decision = await squire.decide("loop", state, questions)
    return {
        "goal_met": decision.answer("goal_met").truth or 0.0,
        "repeats_check": decision.answer("repeats_check").truth or 0.0,
    }


async def main_async(key: str) -> dict[str, Any]:
    squire = Squire(
        create("jev", api_key=key),
        thresholds=Thresholds(max_usd=CEILING_USD, max_decisions=200),
    )
    rows: list[dict[str, Any]] = []
    for path in SESSIONS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line) if line.strip() else None
            if not row or not row.get("success") or not row.get("workdir"):
                continue
            result, messages = last_result(row["workdir"])
            if not result or not messages:
                continue
            goal = task_of(messages)
            said = loop_hook.narration(messages)
            with_page = loop_hook.established(messages, result, goal)
            before = await ask(squire, goal, said, "another snapshot")
            after = await ask(squire, goal, with_page, "another snapshot")
            rows.append({
                "task": row["task"], "arm": row["arm"],
                "narration_only": before, "with_the_page": after,
                "page_chars": len(loop_hook.facts_seen(result, goal)),
            })  # fmt: skip
    met_before = [r["narration_only"]["goal_met"] for r in rows]
    met_after = [r["with_the_page"]["goal_met"] for r in rows]
    saturated = Thresholds().saturated
    report = {
        "sessions": len(rows),
        "all_of_them_ended_with_the_answer": True,
        "saturated_threshold": saturated,
        "goal_met_narration_only": {
            "mean": round(sum(met_before) / len(met_before), 4) if met_before else None,
            "above_threshold": sum(p >= saturated for p in met_before),
        },
        "goal_met_with_the_page": {
            "mean": round(sum(met_after) / len(met_after), 4) if met_after else None,
            "above_threshold": sum(p >= saturated for p in met_after),
        },
        "jev_usd": round(squire.meter.cost_usd, 5),
        "rows": rows,
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "loop-probe.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()
    key = mcp.key_from(args.env_file)
    if not key:
        raise SystemExit("no TYPESAFE_API_KEY: nothing spent")
    report = asyncio.run(main_async(key))
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
    for row in report["rows"]:
        before = row["narration_only"]["goal_met"]
        after = row["with_the_page"]["goal_met"]
        print(
            f"  {row['task']} {row['arm']}: goal_met {before:.2f} -> {after:.2f}"
            f"  ({row['page_chars']} chars of page)"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
