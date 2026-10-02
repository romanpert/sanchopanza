"""Browse, phase 4: multi-step browsing, and whether a small model needs our ranking to do it.

python benchmarks/browse/nav_e2e.py --tasks                     # free: print the task set
python benchmarks/browse/nav_e2e.py --pilot --live              # a smoke run, excluded from counts
python benchmarks/browse/nav_e2e.py --record-hash
python benchmarks/browse/nav_e2e.py --live                      # see prereg-nav.md
python benchmarks/browse/nav_e2e.py                             # free: re-grades what is recorded

Everything measured in `docs/results/2026-09-30-browse/` was one or two pages and about four
turns. These tasks take ten to twenty actions, and four of the six have no URL to guess: a
login and a cart, a list built by typing. They were each walked by hand with no model
(`check_tasks.py`), which is where their required substrings come from.

The arms are deliberately in this order, because the first pair can end the line:

- `SONNET`: an ordinary Claude Code session with Playwright MCP. The baseline people have.
- `HAIKU`: the same session on `claude-haiku-4-5` and nothing of ours. **If this matches
  SONNET, the ranking has nothing to add and the phase stops here.**

`docs/results/2026-10-02-browse-nav/README.md` section 4 is why: a turn of such a session costs
0.0143 USD and 0.0135 of it is its own context read back from cache, so the only saving left is
the price of whoever takes the turn - which is worth nothing unless the cheap model can.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


base = _load("browse_e2e", HERE / "e2e.py")
mcp = _load("browse_e2e_mcp", HERE / "e2e_mcp.py")
phase = _load("browse_phase", HERE / "phase.py")

RESULTS = base.ROOT / "docs" / "results" / "2026-10-02-browse-nav"
PREREG = RESULTS / "prereg-nav.md"
SESSIONS = RESULTS / "nav-sessions.jsonl"
PILOT_SESSIONS = RESULTS / "nav-pilot-sessions.jsonl"
MODELS = {"SONNET": "claude-sonnet-5", "HAIKU": "claude-haiku-4-5"}
ARMS = ("SONNET", "HAIKU")
RUNS = 3
SESSION_MAX_USD = 1.00  # a 20-turn Sonnet session costs about 0.34 by the recorded curve
CEILING_USD = 14.00
PILOT_CEILING_USD = 3.00
TIMEOUT_S = 1800
TOOLS = "mcp__playwright Read Grep Glob"
APPEND = (
    "Use the browser to carry out the request, then answer briefly with the facts you found. "
    "The request may take several steps; take them."
)

# (id, url, request, required substrings). An item that is a list is met by any alternative.
# A1, A2, A3 and A6 have no URL shortcut. Walked by hand on 2026-10-02 (`check_tasks.py`).
TASKS: list[tuple[str, str, str, list[Any]]] = [
    (
        "A1",
        "https://www.saucedemo.com/",
        "Log in as standard_user with the password secret_sauce, put the Sauce Labs Backpack, the "
        "Sauce Labs Bike Light and the Sauce Labs Bolt T-Shirt in the cart, start the checkout as "
        "Ada Lovelace with postal code 28001, and report the item total, the tax and the total "
        "shown on the overview page.",
        ["55.97", "4.48", "60.45"],
    ),
    (
        "A2",
        "https://demo.playwright.dev/todomvc/",
        "Add these five to-do items, in this order: buy milk; write the prereg; walk the dog; pay "
        "the VPS; read QASPER. Then mark 'buy milk' and 'write the prereg' as completed, open the "
        "Active filter, and report how many items are left and their titles.",
        ["3", "walk the dog", "pay the vps", "read qasper"],
    ),
    (
        "A3",
        "https://quotes.toscrape.com/login",
        "Log in with username scraper and password scraper (any credentials are accepted), then "
        "open the quotes tagged 'life', go to page 2 of that tag and report the author of the "
        "first quote listed there.",
        ["mark twain"],
    ),
    (
        "A4",
        "https://books.toscrape.com/",
        "Report the UPC of the first book listed in each of these three categories: Travel, "
        "Mystery and Classics.",
        ["a22124811bfa8350", "e00eb4fd7b871a48", "abbb492978ff656d"],
    ),
    (
        "A5",
        "https://quotes.toscrape.com/",
        "Report the author of the first quote listed on each of pages 1, 2, 3, 4 and 5.",
        ["einstein", "monroe", "neruda", ["seuss", "dr. seuss"], "martin"],
    ),
    (
        "A6",
        "https://books.toscrape.com/",
        "Starting at page 1 of the catalogue and moving forward one page at a time, find the book "
        "'Algorithms to Live By: The Computer Science of Human Decisions' and report its UPC and "
        "its price.",
        ["38d45839cb1c83c1", "30.81"],
    ),
]
PILOT_TASKS = [TASKS[0], TASKS[3]]


def settings_for(work: pathlib.Path) -> pathlib.Path:
    """No hook in either arm: this phase compares models, not our cut."""
    path = work / "settings.json"
    path.write_text(json.dumps({"permissions": {"allow": TOOLS.split()}}), encoding="utf-8")
    return path


def one_session(task: tuple, run: int, arm: str) -> dict[str, Any]:
    tid, url, question, required = task
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-nav-{tid.lower()}r{run}{arm.lower()}-"))
    env = base.clean_env(dict(os.environ))
    env.pop("TYPESAFE_API_KEY", None)  # neither arm decides anything
    argv = [
        shutil.which("claude") or "claude", "-p", "--model", MODELS[arm],
        "--append-system-prompt", APPEND,
        "--settings", str(settings_for(work)), "--setting-sources", "",
        "--mcp-config", str(mcp.mcp_config(work)), "--strict-mcp-config",
        "--allowedTools", TOOLS, "--disallowedTools", "WebFetch WebSearch Bash",
        "--output-format", "json", "--max-budget-usd", f"{SESSION_MAX_USD:g}",
        "--", f"Open {url} in the browser. {question}",
    ]  # fmt: skip
    try:
        done = subprocess.run(argv, cwd=work, env=env, capture_output=True, timeout=TIMEOUT_S)
        out = json.loads(done.stdout.decode("utf-8", errors="replace") or "{}")
    except (subprocess.TimeoutExpired, ValueError) as error:
        out = {"is_error": True, "subtype": f"runner: {error.__class__.__name__}"}
    usage = out.get("usage") or {}
    answer = str(out.get("result") or "")
    return {
        "task": tid, "run": run, "arm": arm, "model": MODELS[arm],
        "ok": not out.get("is_error", True), "subtype": out.get("subtype"),
        "success": base.graded(answer, required), "answer": answer[:800],
        "list_usd": float(out.get("total_cost_usd") or 0.0),
        "turns": out.get("num_turns"),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "jev_usd": 0.0, "jev_calls": 0,
        "tools": mcp.tool_calls(work), "version": claude_version(work),
        "workdir": str(work),
    }  # fmt: skip


def claude_version(work: pathlib.Path) -> str:
    """The transcript's own `version`: a phase must not mix two Claude Code versions."""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(work))
    folder = pathlib.Path.home() / ".claude" / "projects" / slug
    for path in folder.glob("*.jsonl") if folder.is_dir() else []:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            version = json.loads(line).get("version")
            if version:
                return str(version)
    return ""


def done_sessions(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def analyse(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"sessions": len(rows), "by_arm": {}}
    for arm in ARMS:
        part = [r for r in rows if r["arm"] == arm]
        if not part:
            continue
        ok = [r for r in part if r["ok"]]
        out["by_arm"][arm] = {
            "model": MODELS[arm],
            "sessions": len(part),
            "finished": len(ok),
            "success": f"{sum(r['success'] for r in part)}/{len(part)}",
            "median_turns": sorted(r["turns"] or 0 for r in ok)[len(ok) // 2] if ok else None,
            "mean_list_usd": round(sum(r["list_usd"] for r in part) / len(part), 4),
            "total_list_usd": round(sum(r["list_usd"] for r in part), 4),
        }

    def for_task(tid: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for arm in ARMS:
            part = [r for r in rows if r["task"] == tid and r["arm"] == arm]
            if part:
                out[arm] = f"{sum(r['success'] for r in part)}/{len(part)}"
        return out

    out["by_task"] = {tid: for_task(tid) for tid in sorted({r["task"] for r in rows})}
    out["versions"] = sorted({r.get("version", "") for r in rows})
    out["list_usd_total"] = round(sum(r["list_usd"] for r in rows), 4)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", action="store_true", help="print the task set and stop")
    ap.add_argument("--pilot", action="store_true", help="two tasks, one run, its own file")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--record-hash", action="store_true")
    args = ap.parse_args()

    if args.tasks:
        for tid, url, question, required in TASKS:
            print(f"{tid}  {url}\n    {question}\n    required: {required}\n")
        return 0
    if args.record_hash:
        PREREG.with_suffix(".sha256").write_text(base.digest(PREREG) + "\n", encoding="utf-8")
        print(f"registered {PREREG.name}: {base.digest(PREREG)}")
        return 0

    tasks = PILOT_TASKS if args.pilot else TASKS
    runs = [1] if args.pilot else list(range(1, RUNS + 1))
    sessions = PILOT_SESSIONS if args.pilot else SESSIONS
    ceiling = PILOT_CEILING_USD if args.pilot else CEILING_USD
    rows = done_sessions(sessions)
    code = 0
    if args.live:
        if not args.pilot:
            registered = PREREG.with_suffix(".sha256")
            if not registered.exists() or registered.read_text().strip() != base.digest(PREREG):
                raise SystemExit(f"{PREREG.name} is not registered as it stands: nothing spent")
        RESULTS.mkdir(parents=True, exist_ok=True)
        limits = phase.Limits(session_max_usd=SESSION_MAX_USD, ceiling_usd=ceiling)
        plan = phase.planned(tasks, runs, ARMS)
        code, rows = phase.run_phase(plan, rows, limits, one_session, sessions)
    if not rows:
        print("nothing recorded yet")
        return code
    report = analyse(phase.counted(rows))
    name = "nav-pilot.json" if args.pilot else "nav.json"
    (RESULTS / name).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
