"""Offline replay: at every native compaction already recorded, what would the guard have added?

Free: no model, no network. Reads the saved Claude Code transcripts of the two earlier
end-to-end runs whose compactions were Claude Code's own summary:

- docs/results/2026-09-28-context-e2e: arms N and R (R fell back to the native summary in all
  its compactions), tasks t01-t12, one `/compact` after phase A;
- docs/results/2026-09-28-context-lean: arm N, Haiku t01-t07 and Sonnet t01, automatic
  compaction in the middle of phase B, sometimes several times.

For each compaction: the history before it (every earlier compaction included, summaries left
out) goes through `guard.build`; the planted one-shot facts are looked for in the native
summary that followed, in the guard block, and in either. The facts are the tasks' own
(`tasks.py` of each run). Aggregates only go to `replay.json`.

    python docs/results/2026-09-29-context-guard/offline/replay.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parents[1]
sys.path.insert(0, str(RESULTS.parents[1] / "src"))

from sanchopanza.context import guard  # noqa: E402
from sanchopanza.context.transcript import merge_consecutive  # noqa: E402

CACHE = Path.home() / ".cache" / "sanchopanza"


def _module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def entries(path: Path) -> list[dict[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _conversational(entry: dict[str, Any]) -> bool:
    message = entry.get("message")
    return (
        entry.get("type") in ("user", "assistant")
        and not entry.get("isSidechain")
        and not entry.get("isMeta")
        and isinstance(message, dict)
        and message.get("role") in ("user", "assistant")
    )


def compactions(path: Path) -> list[dict[str, Any]]:
    """For each compact_boundary: the whole history before it and the summary after it."""
    history: list[dict[str, Any]] = []
    out: list[dict[str, Any]] = []
    pending: dict[str, Any] | None = None
    for entry in entries(path):
        if entry.get("type") == "system" and entry.get("subtype") == "compact_boundary":
            pending = {"messages": merge_consecutive(history), "summary": ""}
            out.append(pending)
            continue
        if not _conversational(entry):
            continue
        if entry.get("isCompactSummary"):
            if pending is not None:
                content = entry["message"].get("content")
                pending["summary"] = content if isinstance(content, str) else json.dumps(content)
            continue
        history.append(entry["message"])
    return out


def facts_lean(f: Any) -> dict[str, str]:
    return {"token": f.token, "check": f"{f.check_id}", "check_expected": f.check_expected}


def facts_e2e(f: Any) -> dict[str, str]:
    return {"token": f.token, "probe": f.code, "tolerance": f.tolerance}


def score(
    kind: str, found: dict[str, str], summary: str, block: str, messages: list
) -> dict[str, Any]:
    seen = "\n".join(json.dumps(m, ensure_ascii=False) for m in messages)
    row: dict[str, Any] = {}
    for name, value in found.items():
        present = value in seen  # was the value in the conversation before this compaction?
        row[name] = {
            "before": present,
            "summary": guard.contains(summary, value),
            "guard": guard.contains(block, value),
        }
    return row


def sessions() -> list[tuple[str, str, str, Path, dict[str, str]]]:
    lean = _module(RESULTS / "2026-09-28-context-lean" / "tasks.py", "lean_tasks")
    e2e = _module(RESULTS / "2026-09-28-context-e2e" / "tasks.py", "e2e_tasks")
    out = []
    for index in range(12):
        f, *_ = e2e.facts_for(index)
        for arm in ("N", "R"):
            path = CACHE / "context-e2e" / "runs" / f.task / arm / "session.jsonl"
            if path.exists():
                out.append(("e2e", "haiku", f"{f.task}/{arm}", path, facts_e2e(f)))
    for index in range(8):
        f, *_ = lean.facts_for(index)
        for model in ("haiku", "sonnet"):
            path = CACHE / "context-lean" / model / "runs" / f.task / "N" / "session.jsonl"
            if path.exists():
                out.append(("lean", model, f"{f.task}/N", path, facts_lean(f)))
    return out


def main() -> int:
    rows = []
    for run, model, name, path, found in sessions():
        for number, c in enumerate(compactions(path), start=1):
            g = guard.build(c["messages"])
            block = guard.block(g)
            rows.append({
                "run": run, "model": model, "session": name, "compaction": number,
                "summary_chars": len(c["summary"]), "block_chars": len(block),
                "candidates": g.candidates, "facts_kept": len(g.facts),
                "facts": score(run, found, c["summary"], block, c["messages"]),
            })  # fmt: skip
    totals: dict[str, dict[str, int]] = {}
    for row in rows:
        for name, s in row["facts"].items():
            if not s["before"]:
                continue  # not yet produced at this compaction: nothing to keep
            t = totals.setdefault(
                f"{row['run']}:{name}", {"n": 0, "summary": 0, "guard": 0, "either": 0}
            )
            t["n"] += 1
            t["summary"] += s["summary"]
            t["guard"] += s["guard"]
            t["either"] += s["summary"] or s["guard"]
    blocks = [r["block_chars"] for r in rows]
    report = {
        "compactions": len(rows),
        "sessions": len({(r["run"], r["model"], r["session"]) for r in rows}),
        "block_chars": {
            "min": min(blocks),
            "median": sorted(blocks)[len(blocks) // 2],
            "max": max(blocks),
        },
        "summary_chars_median": sorted(r["summary_chars"] for r in rows)[len(rows) // 2],
        "facts": totals,
        "rows": rows,
    }  # fmt: skip
    (HERE / "replay.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
