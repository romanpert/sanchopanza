"""Browse, phase 4c (development, free): is there any loop waste in a browsing session?

python benchmarks/browse/waste.py

Loop supervision (`points/loop.py`: `goal_met`, `repeats_check`) only pays if a session does
work it did not need. The paper behind that point measured 18x the clean-run median on coding
agents that fell into redundant verification. Nobody has looked for the same shape in a
browsing session, and there are 684 of them already recorded here.

This reads every recorded session's own transcript and counts four things that a cheap check
could have caught, with no model and no money:

- **a read after a read**: two read-only calls in a row with no action between them (a second
  snapshot of a page nothing has changed, a screenshot after a snapshot).
- **a revisit**: navigating to a URL this session already asked for.
- **a repeated action**: the same action tool with byte-identical input, twice.
- **the tail**: read-only calls after the last call that changed anything, *beyond the first
  one*, which is the shape `goal_met` is meant to stop. The first read after the last action is
  how the answer is obtained and is never waste - counting it was this script's first version,
  and it reported 28.9 % of all calls as tail, which is reading, not waste.

What it cannot see is whether the answer was already on screen earlier: that needs a judgment,
which is the point of the next step. This is the free half.
"""

from __future__ import annotations

import json
import pathlib
import re
import statistics as st
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OLD = ROOT / "docs" / "results" / "2026-09-30-browse"
NEW = ROOT / "docs" / "results" / "2026-10-02-browse-nav"
OUT = NEW / "waste.json"

READ_ONLY = (
    "browser_snapshot", "browser_take_screenshot", "browser_console_messages",
    "browser_network_requests", "Read", "Grep", "Glob", "ToolSearch",
)  # fmt: skip
ACTIONS = (
    "browser_click", "browser_fill_form", "browser_type", "browser_select_option",
    "browser_press_key", "browser_navigate", "browser_navigate_back", "browser_hover",
    "browser_drag", "browser_file_upload", "Bash",
)  # fmt: skip


def short(name: str) -> str:
    return name.split("__")[-1]


def calls_of(workdir: str) -> list[tuple[str, str]]:
    """(tool, input as canonical JSON) in order, from Claude Code's own transcript."""
    folder = pathlib.Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", workdir)
    out: list[tuple[str, str]] = []
    for path in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            content = (event.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name = short(block["name"])
                    out.append((name, json.dumps(block.get("input"), sort_keys=True)))
    return out


def waste_in(calls: list[tuple[str, str]]) -> dict[str, Any]:
    reads_after_reads = revisits = repeats = 0
    seen_urls: set[str] = set()
    seen_actions: set[tuple[str, str]] = set()
    last_changed = -1
    for i, (name, arguments) in enumerate(calls):
        if name in ACTIONS:
            last_changed = i
        if name in READ_ONLY and i and calls[i - 1][0] in READ_ONLY:
            reads_after_reads += 1
        if name == "browser_navigate":
            url = str(json.loads(arguments).get("url") or "")
            if url and url in seen_urls:
                revisits += 1
            seen_urls.add(url)
        elif name in ACTIONS:
            if (name, arguments) in seen_actions:
                repeats += 1
            seen_actions.add((name, arguments))
    return {
        "calls": len(calls),
        "read_after_read": reads_after_reads,
        "revisits": revisits,
        "repeated_actions": repeats,
        # The first read after the last action is how the answer is read off the page.
        "tail_calls": max(0, len(calls) - last_changed - 2) if calls else 0,
    }


def gather(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    out = []
    for row in rows:
        if not row.get("workdir") or row.get("run", 1) <= 0 or row.get("not_run"):
            continue
        calls = calls_of(row["workdir"])
        if not calls:  # the transcript is gone: counted as uncovered, never as zero waste
            out.append({"task": row["task"], "arm": row["arm"], "covered": False})
            continue
        out.append({
            "task": row["task"], "arm": row["arm"], "covered": True,
            "turns": row.get("turns"), "list_usd": row.get("list_usd"),
            "success": row.get("success"), **waste_in(calls),
        })  # fmt: skip
    return out


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    covered = [r for r in rows if r.get("covered")]
    if not covered:
        return {"sessions": len(rows), "covered": 0}
    total = sum(r["calls"] for r in covered)
    kinds = ("read_after_read", "revisits", "repeated_actions", "tail_calls")
    out: dict[str, Any] = {
        "sessions": len(rows),
        "covered": len(covered),
        "calls_total": total,
        "calls_median": st.median(r["calls"] for r in covered),
    }
    for kind in kinds:
        hit = [r for r in covered if r[kind]]
        out[kind] = {
            "calls": sum(r[kind] for r in covered),
            "share_of_calls": round(sum(r[kind] for r in covered) / total, 4),
            "sessions_with_any": f"{len(hit)}/{len(covered)}",
            "worst_session": max((r[kind] for r in covered), default=0),
        }
    out["any_waste_sessions"] = f"{sum(any(r[k] for k in kinds) for r in covered)}/{len(covered)}"
    return out


def main() -> int:
    files = sorted(OLD.glob("e2e-*-sessions.jsonl")) + [NEW / "nav-pilot-sessions.jsonl"]
    report: dict[str, Any] = {"by_file": {}}
    everything: list[dict[str, Any]] = []
    for path in files:
        rows = gather(path)
        if rows:
            report["by_file"][path.name] = summarise(rows)
            everything += rows
    report["all"] = summarise(everything)
    by_arm = {}
    for arm in sorted({r["arm"] for r in everything}):
        part = [r for r in everything if r["arm"] == arm]
        by_arm[arm] = summarise(part)
    report["by_arm"] = by_arm
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({"all": report["all"], "by_arm": report["by_arm"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
