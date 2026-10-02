"""Browse, development: does a dear main agent that hands browsing to a cheap subagent pay?

python benchmarks/browse/delegate_e2e.py --dev [--tasks S1,H2] [--runs 1] [--ceiling 3]
python benchmarks/browse/delegate_e2e.py                       # free: the report so far

A warm browsing turn costs what the session's own context costs to read again, and the page is
the smaller part of it (README section 4). So the biggest lever on a browsing session run by a
dear model is not a smaller page but a cheaper reader: let the main agent hand the whole
browsing part to a subagent on Haiku, which carries strategy line v5 and runs under the evaluate
time limit, and answer from its report. The main agent's context never holds a snapshot.

Arms, Claude Code 2.1.287 with Playwright MCP, same tools and permissions as `nav_e2e.py`:

- `SONNET` (recorded, not re-run here): Sonnet browses itself (`nav-strategy`, `nav-hard`).
- `SONNET-DELEGATE`: Sonnet as the main agent with a `browser` subagent (`--agents`, Haiku,
  the line in its prompt), the crawl hook's time limit on every evaluate, and one sentence that
  says to delegate. No decision of ours, no Jev: if delegation pays, a Jev check of the
  subagent's report is the next question, not this one.

Development on tasks already spent (S1-S5, H1-H5): it decides whether a registered phase is
worth its cost, and confirms nothing.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


nav = _load("browse_nav_e2e", HERE / "nav_e2e.py")
RESULTS = nav.base.ROOT / "docs" / "results" / "2026-10-03-browse-delegate"
SESSIONS = RESULTS / "delegate-sessions.jsonl"
REPORT = RESULTS / "delegate.json"
MAIN = "claude-sonnet-5"
SUB = "claude-haiku-4-5"
SESSION_MAX_USD = 1.00
TASKS = {t[0]: t for t in nav.STRATEGY_TASKS + nav.HARD_TASKS}
BASELINE = ("nav-strategy-sessions.jsonl", "nav-hard-sessions.jsonl")

DELEGATE = (
    "For any part of the request that needs the browser, hand it to the browser agent with the "
    "request word for word, and answer from its report; open the browser yourself only if the "
    "report says it could not finish."
)


def browser_agent() -> dict[str, Any]:
    from sanchopanza.harness.crawl_hook import STRATEGY_LINE

    return {
        "browser": {
            "description": "Carries out anything that needs the web browser (opening pages, "
            "reading them, clicking, filling forms, gathering data across many pages) and "
            "reports what it found.",
            "prompt": "You operate a web browser through the Playwright tools to carry out the "
            f"request you are given, then report briefly the facts you found. {STRATEGY_LINE} "
            "End your report with how many pages and items you read.",
            "model": SUB,
        }
    }


def settings(work: pathlib.Path) -> pathlib.Path:
    """The bench's permissions and the crawl hook's time limit, nothing else."""
    command = f'"{nav.HOOK_PYTHON.as_posix()}" -m sanchopanza crawl-hook'
    hook = [{"type": "command", "command": command, "timeout": 30}]
    body = {
        "permissions": {"allow": nav.TOOLS.split()},
        "hooks": {"PreToolUse": [{"matcher": r"mcp__.*__browser_evaluate", "hooks": hook}]},
    }
    path = work / "settings.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _transcripts(work: pathlib.Path) -> list[pathlib.Path]:
    folder = pathlib.Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(work))
    return sorted(folder.rglob("*.jsonl")) if folder.is_dir() else []


def tool_calls(work: pathlib.Path) -> dict[str, int]:
    """Tool uses by name in the main transcript and every subagent's."""
    counts: dict[str, int] = {}
    for path in _transcripts(work):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            content = (json.loads(line).get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    counts[block["name"]] = counts.get(block["name"], 0) + 1
    return counts


def one_session(task: tuple, run: int, arm: str) -> dict[str, Any]:
    tid, url, question, required = task
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-dlg-{tid.lower()}r{run}-"))
    agents = work / "agents.json"
    agents.write_text(json.dumps(browser_agent()), encoding="utf-8")
    env = {**nav.base.clean_env(dict(os.environ)), "PYTHONPATH": str(SRC)}
    env.pop("TYPESAFE_API_KEY", None)
    argv = [
        shutil.which("claude") or "claude",
        "-p",
        "--model",
        MAIN,
        "--append-system-prompt",
        f"{nav.APPEND} {DELEGATE}",
        "--agents",
        str(agents),
        "--settings",
        str(settings(work)),
        "--setting-sources",
        "",
        "--mcp-config",
        str(nav.mcp.mcp_config(work)),
        "--strict-mcp-config",
        "--allowedTools",
        f"{nav.TOOLS} Task Agent",
        "--disallowedTools",
        nav.DISALLOWED,
        "--output-format",
        "json",
        "--max-budget-usd",
        f"{SESSION_MAX_USD:g}",
        "--",
        f"Open {url} in the browser. {question}",
    ]
    started = time.monotonic()
    try:
        done = subprocess.run(argv, cwd=work, env=env, capture_output=True, timeout=nav.TIMEOUT_S)
        out = json.loads(done.stdout.decode("utf-8", errors="replace") or "{}")
        (work / "stderr.txt").write_bytes(done.stderr)
    except (subprocess.TimeoutExpired, ValueError) as error:
        out = {"is_error": True, "subtype": f"runner: {error.__class__.__name__}"}
    answer = str(out.get("result") or "")
    by_model = {
        m: round(float(u.get("costUSD") or 0), 5) for m, u in (out.get("modelUsage") or {}).items()
    }
    return {
        "task": tid,
        "run": run,
        "arm": arm,
        "model": MAIN,
        "subagent_model": SUB,
        "ok": not out.get("is_error", True),
        "subtype": out.get("subtype"),
        "success": nav.grade(answer, required, tid),
        "answer": answer[: nav.ANSWER_KEPT],
        "list_usd": float(out.get("total_cost_usd") or 0.0),
        "usd_by_model": by_model,
        "turns": out.get("num_turns"),
        "wall_s": round(time.monotonic() - started, 1),
        "tools": tool_calls(work),
        "version": nav.claude_version(work),
        "workdir": str(work),
    }


def baseline() -> list[dict[str, Any]]:
    rows = []
    for name in BASELINE:
        for row in nav.done_sessions(nav.RESULTS / name):
            if row["arm"] == "SONNET" and row["task"] in TASKS and not row.get("not_run"):
                rows.append(row)
    return rows


def report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base = baseline()
    out: dict[str, Any] = {"tasks": {}}
    for tid in TASKS:
        mine = [r for r in rows if r["task"] == tid]
        theirs = [r for r in base if r["task"] == tid]
        if not mine:
            continue
        out["tasks"][tid] = {
            "SONNET": {
                "right": f"{sum(r['success'] for r in theirs)}/{len(theirs)}",
                "mean_usd": round(statistics.mean(r["list_usd"] for r in theirs), 4)
                if theirs
                else None,
            },
            "SONNET-DELEGATE": {
                "right": f"{sum(r['success'] for r in mine)}/{len(mine)}",
                "mean_usd": round(statistics.mean(r["list_usd"] for r in mine), 4),
                "delegated": sum(
                    bool(r["tools"].get("Task") or r["tools"].get("Agent")) for r in mine
                ),
            },
        }
    done = [t for t, v in out["tasks"].items() if v["SONNET"]["mean_usd"] is not None]
    if done:
        dear = sum(out["tasks"][t]["SONNET"]["mean_usd"] for t in done)
        cheap = sum(out["tasks"][t]["SONNET-DELEGATE"]["mean_usd"] for t in done)
        out["ratio_of_task_means"] = round(cheap / dear, 3)
    out["versions"] = sorted({r.get("version", "") for r in rows})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dev", action="store_true")
    ap.add_argument("--tasks", default=",".join(TASKS))
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--ceiling", type=float, default=3.0)
    args = ap.parse_args()
    RESULTS.mkdir(parents=True, exist_ok=True)
    rows = nav.done_sessions(SESSIONS)
    code = 0
    if args.dev:
        tasks = [TASKS[t] for t in args.tasks.split(",")]
        limits = nav.phase.Limits(session_max_usd=SESSION_MAX_USD, ceiling_usd=args.ceiling)
        plan = nav.phase.planned(tasks, list(range(1, args.runs + 1)), ("SONNET-DELEGATE",))
        code, rows = nav.phase.run_phase(plan, rows, limits, one_session, SESSIONS)
    counted = nav.phase.counted(rows)
    if counted:
        result = report(counted)
        REPORT.write_text(json.dumps(result, indent=1), encoding="utf-8")
        print(json.dumps(result, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
