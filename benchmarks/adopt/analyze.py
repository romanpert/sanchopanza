"""Per chain and arm: bugs resolved, list-price cost, time, compactions, and what S used of
sanchopanza (find calls, the skill, guard blocks attached, shell denials). Free.

    python benchmarks/adopt/analyze.py [--chains a,b]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from run import ARM_SPECS, RUNS  # noqa: E402


def denials(evidence: Path) -> int:
    """PreToolUse denials by our permission hook, read from the call streams' tool results."""
    count = 0
    for stream in evidence.glob("stream-*.jsonl"):
        for line in stream.read_text(encoding="utf-8", errors="replace").splitlines():
            if '"is_error":true' in line.replace(" ", "") and "denied" in line.lower() and (
                "sanchopanza" in line.lower() or "this job does not" in line.lower()
            ):
                count += 1
    return count


def memory_log(evidence: Path) -> dict[str, Any]:
    """What memory gave: on prompts (records injected when a request arrives) and on touch
    (memory v3: records given when the agent opens or edits a file an earlier session changed,
    logged as `PostToolUse` events with `shown`)."""
    path = evidence / "memory.jsonl"
    out: dict[str, Any] = {"memory_prompts": 0, "memory_injected": 0, "memory_records": 0,
                           "memory_chars": 0, "memory_touch_given": 0,
                           "memory_touch_records": 0, "memory_touch_chars": 0}  # fmt: skip
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        shown = event.get("shown") or []
        chars = int(event.get("chars") or 0)
        if event.get("event") == "UserPromptSubmit":
            out = {**out, "memory_prompts": out["memory_prompts"] + 1,
                   "memory_injected": out["memory_injected"] + bool(shown),
                   "memory_records": out["memory_records"] + len(shown),
                   "memory_chars": out["memory_chars"] + chars}  # fmt: skip
        elif event.get("event") == "PostToolUse" and shown:
            out = {**out, "memory_touch_given": out["memory_touch_given"] + 1,
                   "memory_touch_records": out["memory_touch_records"] + len(shown),
                   "memory_touch_chars": out["memory_touch_chars"] + chars}  # fmt: skip
    return out


def hook_log(evidence: Path) -> dict[str, int]:
    path = evidence / "hooks.jsonl"
    out = {"guard_blocks": 0, "guard_notes": 0, "hook_events": 0, "hook_seconds": 0.0}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        out["hook_events"] += 1
        out["hook_seconds"] += event.get("seconds", 0.0)
        if event["sub"] == "guard-hook" and event["event"] == "SessionStart" and event["out_chars"]:
            out["guard_blocks"] += 1
        if event["sub"] == "guard-hook" and event["event"] == "PreCompact" and event["out_chars"]:
            out["guard_notes"] += 1
    out["hook_seconds"] = round(out["hook_seconds"], 1)
    return out


def summarise(chain: str, arm: str) -> dict[str, Any] | None:
    evidence = RUNS / chain / arm
    row_path = evidence / "row.json"
    if not row_path.exists():
        return None
    row = json.loads(row_path.read_text(encoding="utf-8"))
    grade_path = evidence / "grade.json"
    grade = json.loads(grade_path.read_text(encoding="utf-8")) if grade_path.exists() else {}
    calls = row["calls"]
    tools: dict[str, int] = {}
    for c in calls:
        for name, n in (c.get("tools") or {}).items():
            tools[name] = tools.get(name, 0) + n
    return {
        "chain": chain, "arm": arm, "resolved": grade.get("resolved"),
        "bugs": len(grade.get("bugs", [])),
        "cost_usd": round(sum(c.get("cost_usd", 0.0) for c in calls), 4),
        "jev_usd": round(row.get("jev_usd", 0.0), 4),
        "wall_s": row.get("wall_s"),
        "turns": sum(c.get("turns") or 0 for c in calls),
        "compactions": sum(len(c.get("compactions") or []) for c in calls),
        "compaction_pre_tokens": [m.get("pre_tokens") or m.get("preTokens")
                                  for c in calls for m in c.get("compactions") or []],
        "not_run": sum(1 for c in calls if str(c.get("status", "")).startswith("NOT RUN")),
        "subtypes": [c.get("subtype") or c.get("status") for c in calls],
        "find_calls": tools.get("mcp__sanchopanza__find_in_repo", 0),
        "skill_calls": tools.get("Skill", 0),
        "tool_calls": sum(tools.values()),
        "denials": denials(evidence),
        **hook_log(evidence),
        **memory_log(evidence),
    }  # fmt: skip


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chains", default="")
    args = parser.parse_args(argv)
    names = [c for c in args.chains.split(",") if c] or sorted(p.name for p in RUNS.iterdir())
    rows = [r for n in names for a in ARM_SPECS if (r := summarise(n, a))]
    for r in rows:
        print(json.dumps(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
