"""Browse, fourth confirmation: Claude Code with the crawl hook as v7 left it (line v6 plus the
crawl notes) against Claude Code alone, on Haiku and on Sonnet, on eight new crawls.

python benchmarks/browse/nav_confirm4.py --tasks | --record-hash | --preflight | --live
python benchmarks/browse/nav_confirm4.py                  # free: the verdicts so far

Registered in `docs/results/2026-10-03-browse-v6/prereg-crawl4.md`. The procedure (the
sealing check, the hang rule, the phase loop) and the hypotheses are confirmation 3's, loaded
here as a copy of `nav_confirm3.py` with only its tasks, arms' treatment and files replaced; that
file and its sealed record are left as they were. The `-SP` arms get what `sanchopanza install
--crawl` writes plus, in the settings' `env`, `SANCHOPANZA_CRAWL_LINE_VERSION=6` and
`SANCHOPANZA_CRAWL_NOTES=1`: v7 is not the package's default, and a user turns it on that way.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


conf3 = _load("browse_nav_confirm3_for_4", HERE / "nav_confirm3.py")
procedure = conf3.procedure
nav = conf3.nav
A = nav.ANSWER_LINE

RESULTS = nav.base.ROOT / "docs" / "results" / "2026-10-03-browse-v6"
PREREG = RESULTS / "prereg-crawl4.md"
SESSIONS = RESULTS / "nav-confirm4-sessions.jsonl"
REPORT = RESULTS / "nav-confirm4.json"
ARMS = conf3.ARMS  # HAIKU, HAIKU-SP, SONNET, SONNET-SP
RUNS = 3
CEILING_USD = 26.00  # list price, through the subscription; about 18 expected (prereg)
CLAUDE_VERSION = "2.1.287"
DISALLOWED = (
    "WebFetch WebSearch Bash SendMessage ListAgents ScheduleWakeup CronCreate RemoteTrigger"
)
SP_ENV = {"SANCHOPANZA_CRAWL_LINE_VERSION": "6", "SANCHOPANZA_CRAWL_NOTES": "1"}
LINE_SEEN = "never a URL pattern you guessed"  # only line v6 holds it
NOTES_SEEN = "sanchopanza notes"  # in every wrapped evaluate Playwright MCP echoes back
GUARD_STOP = "### Error\\nError: evaluate stopped after"

# Answers from `truth_confirm4.py`, 2026-10-03, each checked by a second route (G1 in one call,
# G2 and G8 by id, G3 in one call, G4 in one call, G5 and G7 on each book's page, G6 by email).
# G3: the API's `length` field gives 77, the facts' own text 78; either is accepted.
CRAWLS: list[tuple[str, str, str, list[Any]]] = [
    ("G1", "https://dummyjson.com/products",
     "This is a product catalogue API. How many of its products have a rating of 4.5 or "
     "higher?" + A, ["44"]),
    ("G2", "https://swapi.dev/api/people/",
     "This lists the people of Star Wars. How many of them have blue eyes?" + A, ["19"]),
    ("G3", "https://catfact.ninja/facts",
     "This lists cat facts. How many of the facts are longer than 150 characters?" + A,
     [["77", "78"]]),
    ("G4", "https://pokeapi.co/api/v2/pokemon",
     "This lists Pokemon. How many of the names in the list end in -mega?" + A, ["88"]),
    ("G5", "https://books.toscrape.com/catalogue/category/books/fantasy_19/index.html",
     "How many books in this category are rated four stars or more?" + A, ["21"]),
    ("G6", "https://www.lambdatest.com/selenium-playground/table-pagination-demo",
     "In this page's table of people, how many have a last name that begins with M?" + A, ["6"]),
    ("G7", "https://books.toscrape.com/catalogue/category/books/sequential-art_5/index.html",
     "How many books in this category cost less than 20.00 (the price shown, in pounds)?" + A,
     ["19"]),
    ("G8", "https://swapi.dev/api/planets/",
     "This lists the planets of Star Wars. How many have a population of more than one "
     "billion?" + A, ["19"]),
]  # fmt: skip
INTERACTIVE = conf3.INTERACTIVE  # I1, I2: walked by hand for confirmation 3 (check_tasks3.py)
TASKS = CRAWLS + INTERACTIVE


def settings_for(arm: str, work: pathlib.Path) -> pathlib.Path:
    """Confirmation 3's settings, and v7's switches in the `-SP` arms' `env`."""
    path = conf3.settings_for(arm, work)
    if arm.endswith("-SP"):
        settings = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({**settings, "env": SP_ENV}), encoding="utf-8")
    return path


def one_session(task: tuple, run: int, arm: str) -> dict[str, Any]:
    """nav's session, timed, with the treatment checked rather than assumed: an `-SP` session
    whose transcript lacks line v6, or that ran an evaluate without the notes, is `not_run`;
    a plain session that shows either is `not_run` too."""
    started = time.monotonic()
    row = nav.one_session(task, run, arm)
    text = conf3._transcript(row["workdir"])
    evaluated = bool((row.get("tools") or {}).get("mcp__playwright__browser_evaluate"))
    row = {**row, "wall_s": round(time.monotonic() - started, 1),
           "line_seen": LINE_SEEN in text, "notes_seen": NOTES_SEEN in text,
           "guard_stops": text.count(GUARD_STOP)}  # fmt: skip
    if not row.get("ok"):
        return row
    treated = arm.endswith("-SP")
    if treated and (not row["line_seen"] or (evaluated and not row["notes_seen"])):
        return {**row, "not_run": True, "subtype": "the crawl hooks never ran as registered"}
    if not treated and (row["line_seen"] or row["notes_seen"]):
        return {**row, "not_run": True, "subtype": "a plain session saw the treatment"}
    return row


def preflight() -> list[str]:
    """Before anything is spent: the pinned Claude Code, and the hook with the `-SP` arms' env
    answers a session start with line v6 and wraps an evaluate with the notes, approving
    nothing."""
    from sanchopanza.harness.crawl_hook import STRATEGY_LINE_V6
    from sanchopanza.harness.crawl_notes import NOTES_MARK

    problems: list[str] = []
    exe = shutil.which("claude") or ""
    version = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
    if not exe or not version.stdout.startswith(CLAUDE_VERSION):
        problems.append(f"claude on PATH is not {CLAUDE_VERSION}: {version.stdout.strip()!r}")
    command = [str(nav.HOOK_PYTHON), "-m", "sanchopanza", "crawl-hook"]
    env = {**nav.base.clean_env(dict(os.environ)), "PYTHONPATH": str(conf3.SRC), **SP_ENV}
    for event, check in (
        ({"hook_event_name": "SessionStart", "source": "startup"},
         lambda out: out["additionalContext"] == STRATEGY_LINE_V6),
        ({"hook_event_name": "PreToolUse", "tool_name": "mcp__playwright__browser_evaluate",
          "tool_input": {"function": "() => 1"}},
         lambda out: "permissionDecision" not in out
         and NOTES_MARK in out["updatedInput"]["function"]
         and "120000" in out["updatedInput"]["function"]),
    ):  # fmt: skip
        try:
            done = subprocess.run(command, input=json.dumps(event).encode(), env=env,
                                  capture_output=True, timeout=60)  # fmt: skip
            if not check(json.loads(done.stdout or b"{}")["hookSpecificOutput"]):
                problems.append(f"{event['hook_event_name']}: unexpected {done.stdout[:120]!r}")
        except (subprocess.TimeoutExpired, ValueError, KeyError, OSError) as error:
            problems.append(f"{event['hook_event_name']}: {error.__class__.__name__}: {error}")
    return problems


def install() -> None:
    """Point confirmation 3's procedure at this phase's tasks, treatment and files."""
    conf3.install()
    conf3.CRAWLS, conf3.INTERACTIVE, conf3.TASKS = CRAWLS, INTERACTIVE, TASKS
    nav.settings_for = settings_for
    nav.DISALLOWED = DISALLOWED
    if "G" not in nav.ANSWER_LINE_TASKS:
        nav.ANSWER_LINE_TASKS = (*nav.ANSWER_LINE_TASKS, "G")
    procedure.PREREG, procedure.SESSIONS, procedure.REPORT = PREREG, SESSIONS, REPORT


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ("--tasks", "--record-hash", "--preflight", "--live"):
        ap.add_argument(flag, action="store_true")
    args = ap.parse_args()
    install()
    if args.tasks:
        for tid, url, question, required in TASKS:
            print(f"{tid}  {url}\n    {question}\n    required: {required}\n")
        return 0
    if args.record_hash:
        PREREG.with_suffix(".sha256").write_text(nav.base.digest(PREREG) + "\n", encoding="utf-8")
        print(f"registered {PREREG.name}: {nav.base.digest(PREREG)}")
        return 0
    if args.preflight or args.live:
        problems = preflight()
        if problems:
            print("preflight failed, nothing spent:\n  " + "\n  ".join(problems))
            return 2
        print("preflight: claude pinned; the hook answers line v6 and wraps with the notes")
        if args.preflight:
            return 0
    rows = nav.done_sessions(SESSIONS)
    code = 0
    if args.live:
        procedure.require_registration()
        RESULTS.mkdir(parents=True, exist_ok=True)
        limits = nav.phase.Limits(session_max_usd=nav.SESSION_MAX_USD, ceiling_usd=CEILING_USD)
        plan = nav.phase.planned(TASKS, list(range(1, RUNS + 1)), ARMS)
        code, rows = nav.phase.run_phase(plan, rows, limits, one_session, SESSIONS)
    counted = nav.phase.counted(rows)
    if not counted:
        print("nothing recorded yet")
        return code
    report = {"verdicts": conf3.verdicts(counted), "described": conf3.described(counted),
              "versions": sorted({r.get("version", "") for r in counted}),
              "list_usd_total": round(sum(r["list_usd"] for r in counted), 4)}  # fmt: skip
    REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
