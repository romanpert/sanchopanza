"""Browse, phase 4f (development, free): how often does a session fail several actions in a row,
and what does that cost? Counted in every recorded multi-step session's transcript.

python benchmarks/browse/streaks.py

The error note in `loop_hook` fires at a streak of two failed calls and again at four. Whether a
live phase can measure it depends on how often that happens at all, which costs nothing to
count: a streak that never happens is a note that never speaks.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sanchopanza.context.transcript import calls as calls_of  # noqa: E402
from sanchopanza.context.transcript import messages_from_claude_code  # noqa: E402
from sanchopanza.harness import loop_hook  # noqa: E402


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


replay = _load("browse_loop_replay", HERE / "loop_replay.py")
nav = replay.nav
SOURCES = ("nav-pilot", "nav-traps", "nav-loop", "nav-smoke")


def streaks_in(calls: list[Any]) -> list[int]:
    """The length of every run of consecutive failed calls."""
    out, run = [], 0
    for call in calls:
        if loop_hook.failed(call.result, call.is_error):
            run += 1
        elif run:
            out.append(run)
            run = 0
    return [*out, run] if run else out


def main() -> int:
    rows = []
    for source in SOURCES:
        for row in nav.done_sessions(nav.RESULTS / f"{source}-sessions.jsonl"):
            if row.get("not_run") or not row.get("workdir"):
                continue
            path = replay.transcript_of(row["workdir"])
            if path is None:
                continue
            calls = calls_of(messages_from_claude_code(str(path)))
            runs = streaks_in(calls)
            rows.append({
                "source": source, "task": row["task"], "arm": row["arm"], "run": row["run"],
                "turns": row.get("turns"), "calls": len(calls),
                "failed": sum(runs), "streaks": runs,
                "notes_it_would_say": sum((r >= 2) + (r >= 4) for r in runs),
            })  # fmt: skip
    total_calls = sum(r["calls"] for r in rows)
    total_failed = sum(r["failed"] for r in rows)
    with_note = [r for r in rows if r["notes_it_would_say"]]
    report = {
        "sessions": len(rows),
        "calls": total_calls,
        "failed_calls": total_failed,
        "failed_share": round(total_failed / total_calls, 4) if total_calls else None,
        "sessions_with_a_streak_of_2_or_more": f"{len(with_note)}/{len(rows)}",
        "by_arm_model": {
            model: {
                "sessions": len(part := [r for r in rows if nav.MODELS.get(r["arm"]) == model]),
                "failed_calls": sum(r["failed"] for r in part),
                "calls": sum(r["calls"] for r in part),
                "with_a_streak": sum(bool(r["notes_it_would_say"]) for r in part),
            }
            for model in sorted({nav.MODELS.get(r["arm"], "?") for r in rows})
        },
        "sessions_detail": rows,
    }
    (nav.RESULTS / "streaks.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "sessions_detail"}, indent=1))
    for r in with_note:
        print(f"  {r['source']:10} {r['task']} {r['arm']:11} run{r['run']} turns={r['turns']} "
              f"streaks={r['streaks']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
