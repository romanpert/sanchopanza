"""Browse, development: how long each browser_evaluate and browser_run_code call took, from the
transcripts' own timestamps.

python benchmarks/browse/call_durations.py

The crawl hook's time limit is 120 s by default. Too low, and it kills extractions that would
have returned; it never sees `browser_run_code`, which runs Playwright code in Node and could
hang the same way. Every recorded session of this line is read: the time from the assistant
message that made the call to the user message that carried its result. Free.
"""

from __future__ import annotations

import json
import pathlib
import re
import statistics
from datetime import datetime
from typing import Any

HOME = pathlib.Path.home() / ".claude" / "projects"
RESULTS = pathlib.Path(__file__).resolve().parents[2] / "docs/results/2026-10-02-browse-nav"
TOOLS = ("browser_evaluate", "browser_run_code", "browser_run_code_unsafe")


def _when(entry: dict[str, Any]) -> datetime | None:
    stamp = entry.get("timestamp")
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else None


def durations(path: pathlib.Path) -> list[dict[str, Any]]:
    started: dict[str, tuple[str, datetime]] = {}
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        when = _when(entry)
        content = (entry.get("message") or {}).get("content")
        for block in content if isinstance(content, list) and when else []:
            name = str(block.get("name") or "")
            if block.get("type") == "tool_use" and name.split("__")[-1] in TOOLS:
                started[block["id"]] = (name.split("__")[-1], when)
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in started:
                tool, at = started.pop(block["tool_use_id"])
                text = json.dumps(block.get("content"))
                out.append(
                    {
                        "tool": tool,
                        "seconds": (when - at).total_seconds(),
                        "error": '"### Error' in text
                        or "is_error" in text
                        and block.get("is_error"),
                        "stopped": "evaluate stopped after" in text,
                    }
                )
    out += [
        {"tool": tool, "seconds": None, "error": True, "stopped": False, "unanswered": True}
        for tool, _ in started.values()
    ]
    return out


def main() -> int:
    calls: list[dict[str, Any]] = []
    workdirs = set()
    for sessions in RESULTS.glob("nav-*-sessions.jsonl"):
        for line in sessions.read_text(encoding="utf-8").splitlines():
            workdirs.add(json.loads(line).get("workdir", ""))
    for workdir in sorted(w for w in workdirs if w):
        folder = HOME / re.sub(r"[^A-Za-z0-9]", "-", workdir)
        for path in folder.glob("*.jsonl") if folder.is_dir() else []:
            calls += durations(path)
    report: dict[str, Any] = {"sessions_read": len(workdirs)}
    for tool in TOOLS:
        mine = [c for c in calls if c["tool"] == tool]
        timed = sorted(c["seconds"] for c in mine if c["seconds"] is not None)
        if not mine:
            continue
        report[tool] = {
            "calls": len(mine),
            "never_answered": sum(bool(c.get("unanswered")) for c in mine),
            "median_s": round(statistics.median(timed), 1) if timed else None,
            "p95_s": round(timed[int(0.95 * (len(timed) - 1))], 1) if timed else None,
            "max_s": round(timed[-1], 1) if timed else None,
            "over_60_s": sum(s > 60 for s in timed),
            "over_120_s": sum(s > 120 for s in timed),
            "over_120_s_and_returned_data": sum(
                c["seconds"] > 120 and not c["error"] for c in mine if c["seconds"] is not None
            ),
        }
    (RESULTS / "call-durations.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
