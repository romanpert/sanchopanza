"""Browse, line v6 in development: the crawl hook with line v5 against the same hook with v6, and
Haiku with no hook as the reference, on eight new crawls.

python benchmarks/browse/nav_v6.py --tasks | --preflight
python benchmarks/browse/nav_v6.py --smoke [--only F4]   # one HAIKU-V6 session, its own file
python benchmarks/browse/nav_v6.py --live                # the development phase
python benchmarks/browse/nav_v6.py                       # free: the tables so far

Confirmation 3 (`docs/results/2026-10-02-browse-nav/`, section 20) made Claude Code with
`sanchopanza install --crawl` much cheaper and one crawl short per model; every miss was an
extraction the agent never checked. v6 (`crawl_hook.STRATEGY_LINE_V6`) is v5 with four clauses
for them. This is development, not a confirmation: nothing here is registered or sealed, and the
tasks (`truth_v6.py`) were chosen after reading the misses, half of them shaped like them.

The `-V5` and `-V6` arms get exactly what `sanchopanza install --crawl` writes (built by
`install._merge_crawl`) plus `SANCHOPANZA_CRAWL_LINE_VERSION` in the settings' `env`; the
`HAIKU` arm gets Claude Code as it is. The session itself, the grading and the phase loop are
`nav_e2e.py`'s and `phase.py`'s; this file only says which tasks, arms and files.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import shutil
import statistics
import subprocess
import sys
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


nav = _load("browse_nav_e2e_v6", HERE / "nav_e2e.py")
confirm3 = _load("browse_nav_confirm3_v6", HERE / "nav_confirm3.py")
A = nav.ANSWER_LINE

RESULTS = nav.base.ROOT / "docs" / "results" / "2026-10-03-browse-v6"
SESSIONS = RESULTS / "nav-v6-sessions.jsonl"
SMOKE_SESSIONS = RESULTS / "nav-v6-smoke-sessions.jsonl"
REPORT = RESULTS / "nav-v6.json"
MODEL = "claude-haiku-4-5"
TREATED = {"HAIKU-V5": "5", "HAIKU-V6": "6"}
ARMS = ("HAIKU-V5", "HAIKU-V6", "HAIKU")
RUNS = 3
SESSION_MAX_USD = 1.00
CEILING_USD = 12.00  # list price, through the subscription; about 10 expected
SMOKE_CEILING_USD = 1.50
CLAUDE_VERSION = "2.1.287"
# Confirmation 3's pilot (BC693) called ScheduleWakeup; a bench session must reach nothing else.
DISALLOWED = (
    "WebFetch WebSearch Bash SendMessage ListAgents ScheduleWakeup CronCreate RemoteTrigger"
)
# A phrase only that version of the line holds, to check in each transcript that the hook ran.
MARKS = {
    "5": "check that against what the site shows before you answer",
    "6": "never a URL pattern you guessed",
}

LT = "https://ecommerce-playground.lambdatest.io/index.php?route=product/category&path="
# Answers from `truth_v6.py`, 2026-10-03, each checked by a second route (F1 by the Store API, F2
# by distinct product URLs, F3 sorted on one page, F4 by the API's category filter, F5 and F6 by
# the other DataTables page over the same rows, F7 on one page of 75, F8 by ids in one request).
TASKS: list[tuple[str, str, str, list[Any]]] = [
    ("F1", "https://scrapeme.live/shop/",
     "How many of the products in this shop cost more than 150 pounds?" + A, ["218"]),
    ("F2", "https://www.scrapingcourse.com/pagination",
     "In this whole product listing, how many products cost less than $50?" + A, ["96"]),
    ("F3", LT + "57",
     "How many products in this category cost less than $130 (the price shown)?" + A, ["30"]),
    ("F4", "https://practicesoftwaretesting.com/",
     "How many of this tool shop's products are in its Pliers category?" + A, ["5"]),
    ("F5", "https://datatables.net/examples/basic_init/zero_configuration.html",
     "In this page's staff table, how many people work in the London office and earn more than "
     "$100,000?" + A, ["11"]),
    ("F6", "https://datatables.net/examples/data_sources/server_side.html",
     "In this page's staff table, how many people hold the position Developer?" + A, ["4"]),
    ("F7", LT + "33",
     "How many products in this category are made by Apple and cost more than $150 (the price "
     "shown)?" + A, ["22"]),
    ("F8", "https://rickandmortyapi.com/api/character",
     "This lists the characters of Rick and Morty. How many of them have the species Human?" + A,
     ["366"]),
]  # fmt: skip
# What a session answers when it falls into the trap the task was shaped around (truth_v6.py).
TRAPS = {"F2": ["26", "156"], "F3": ["6"], "F4": ["4"], "F6": ["7", "8"], "F8": ["434"]}


def settings_for(arm: str, work: pathlib.Path) -> pathlib.Path:
    """The plain arm: the bench's permissions and no hook. The treated arms: the same, plus what
    `sanchopanza install --crawl` writes, and the line's version in the settings' `env`."""
    from sanchopanza.harness.install import _merge_crawl

    settings: dict[str, Any] = {"permissions": {"allow": nav.TOOLS.split()}}
    if arm in TREATED:
        settings, _added, _removed = _merge_crawl(settings, True, command=confirm3.crawl_command())
        settings = {**settings, "env": {"SANCHOPANZA_CRAWL_LINE_VERSION": TREATED[arm]}}
    path = work / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def one_session(task: tuple, run: int, arm: str) -> dict[str, Any]:
    """nav's session, timed, with the treatment checked rather than assumed: a treated session
    whose transcript does not show its own version of the line is `not_run`, and so is one that
    shows the other version."""
    started = time.monotonic()
    row = nav.one_session(task, run, arm)
    text = confirm3._transcript(row["workdir"])
    row = {**row, "wall_s": round(time.monotonic() - started, 1),
           "line_seen": {v: mark in text for v, mark in MARKS.items()},
           "guard_stops": text.count("evaluate stopped after")}  # fmt: skip
    if arm in TREATED and row.get("ok"):
        mine = TREATED[arm]
        other = next(v for v in MARKS if v != mine)
        if not row["line_seen"][mine] or row["line_seen"][other]:
            return {**row, "not_run": True, "subtype": f"line v{mine} not (only) in the transcript"}
    return row


def claude_on_path() -> str:
    exe = shutil.which("claude") or ""
    if not exe:
        return ""
    done = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
    return done.stdout.strip().split(" ")[0]


def preflight() -> list[str]:
    """Before anything is spent: the pinned Claude Code is first on PATH, and the hook a treated
    session runs answers a session start with the version its settings name."""
    problems: list[str] = []
    version = claude_on_path()
    if version != CLAUDE_VERSION:
        problems.append(f"claude on PATH is {version or 'missing'}, not {CLAUDE_VERSION}")
    from sanchopanza.harness.crawl_hook import LINES

    command = [str(nav.HOOK_PYTHON), "-m", "sanchopanza", "crawl-hook"]
    event = json.dumps({"hook_event_name": "SessionStart", "source": "startup"}).encode()
    for arm, wanted in TREATED.items():
        env = {**nav.base.clean_env(dict(os.environ)), "PYTHONPATH": str(SRC),
               "SANCHOPANZA_CRAWL_LINE_VERSION": wanted}  # fmt: skip
        try:
            done = subprocess.run(command, input=event, env=env, capture_output=True, timeout=60)
            context = json.loads(done.stdout or b"{}")["hookSpecificOutput"]["additionalContext"]
        except (subprocess.TimeoutExpired, ValueError, KeyError, OSError) as error:
            problems.append(f"{arm}: {error.__class__.__name__}: {error}")
            continue
        if context != LINES[wanted]:
            problems.append(f"{arm}: the hook answered another line: {context[:80]!r}")
    return problems


def plan(tasks: list[tuple], runs: list[int]) -> list[tuple]:
    """The two lines first, task by task; the reference arm after, so that if the ceiling is
    reached it is the reference that is left short, not the comparison."""
    lines = nav.phase.planned(tasks, runs, ("HAIKU-V5", "HAIKU-V6"))
    return lines + nav.phase.planned(tasks, runs, ("HAIKU",))


def _cell(rows: list[dict[str, Any]], tid: str, arm: str) -> list[dict[str, Any]]:
    return [r for r in rows if r["task"] == tid and r["arm"] == arm]


def _answer(row: dict[str, Any]) -> str:
    return nav.answer_line(row.get("answer") or "")[:60]


def analyse(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Right and mean list cost per arm and per task, every answer beside its truth, and which
    answers are the trap the task was built around. A killed session is charged the cap."""
    charged = confirm3.procedure.charged
    out: dict[str, Any] = {"arms": {}, "tasks": {}}
    for arm in ARMS:
        cell = [r for r in rows if r["arm"] == arm]
        if not cell:
            continue
        out["arms"][arm] = {
            "right": f"{sum(bool(r['success']) for r in cell)}/{len(cell)}",
            "mean_usd": round(statistics.mean(charged(r) for r in cell), 4),
            "median_usd": round(statistics.median(charged(r) for r in cell), 4),
            "total_usd": round(sum(charged(r) for r in cell), 4),
            "worst_usd": round(max(charged(r) for r in cell), 4),
            "mean_turns": round(statistics.mean(r.get("turns") or 0 for r in cell), 1),
            "hangs_killed": sum(str(r.get("subtype") or "").startswith("runner:") for r in cell),
            "guard_stops": sum(int(r.get("guard_stops") or 0) for r in cell),
            "traps_fallen": sum(
                _answer(r) in TRAPS.get(r["task"], []) for r in cell if not r["success"]
            ),
        }  # fmt: skip
    for tid, _url, _question, required in TASKS:
        out["tasks"][tid] = {"truth": required[0]} | {
            arm: {"right": f"{sum(bool(r['success']) for r in c)}/{len(c)}",
                  "mean_usd": round(statistics.mean(charged(r) for r in c), 4),
                  "answers": [_answer(r) for r in sorted(c, key=lambda r: r["run"])],
                  "turns": [r.get("turns") for r in sorted(c, key=lambda r: r["run"])]}
            for arm in ARMS if (c := _cell(rows, tid, arm))
        }  # fmt: skip
    out["versions"] = sorted({r.get("version", "") for r in rows})
    out["list_usd_total"] = round(sum(r["list_usd"] for r in rows), 4)
    return out


def install() -> None:
    """Point the shared runner at this phase's model, settings and rules. Every session, and the
    hook it starts, imports sanchopanza from this worktree."""
    os.environ["PYTHONPATH"] = str(SRC)
    nav.MODELS.update(dict.fromkeys(ARMS, MODEL))
    nav.settings_for = settings_for
    nav.DISALLOWED = DISALLOWED
    nav.SESSION_MAX_USD = SESSION_MAX_USD
    if "F" not in nav.ANSWER_LINE_TASKS:  # F tasks are graded on their ANSWER line, as E were
        nav.ANSWER_LINE_TASKS = (*nav.ANSWER_LINE_TASKS, "F")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ("--tasks", "--preflight", "--smoke", "--live"):
        ap.add_argument(flag, action="store_true")
    ap.add_argument("--only", default="F4", help="the smoke session's task")
    args = ap.parse_args()
    install()
    if args.tasks:
        for tid, url, question, required in TASKS:
            print(f"{tid}  {url}\n    {question}\n    required: {required}\n")
        return 0
    if args.preflight or args.live or args.smoke:
        problems = preflight()
        if problems:
            print("preflight failed, nothing spent:\n  " + "\n  ".join(problems))
            return 2
        print(f"preflight: claude {CLAUDE_VERSION}, the hook answers v5 and v6 as asked")
        if args.preflight:
            return 0
    RESULTS.mkdir(parents=True, exist_ok=True)
    sessions = SMOKE_SESSIONS if args.smoke else SESSIONS
    rows = nav.done_sessions(sessions)
    code = 0
    if args.smoke:
        task = next(t for t in TASKS if t[0] == args.only.upper())
        limits = nav.phase.Limits(session_max_usd=SESSION_MAX_USD, ceiling_usd=SMOKE_CEILING_USD)
        code, rows = nav.phase.run_phase(
            [(0, task, 1, "HAIKU-V6")], rows, limits, one_session, sessions
        )
        print(json.dumps(rows[-1] if rows else {}, indent=1)[:3000])
        return code
    if args.live:
        limits = nav.phase.Limits(session_max_usd=SESSION_MAX_USD, ceiling_usd=CEILING_USD)
        code, rows = nav.phase.run_phase(
            plan(TASKS, list(range(1, RUNS + 1))), rows, limits, one_session, sessions
        )
    counted = nav.phase.counted(rows)
    if not counted:
        print("nothing recorded yet")
        return code
    report = analyse(counted)
    report["not_run"] = [
        {k: r.get(k) for k in ("task", "run", "arm", "subtype")} for r in rows if r.get("not_run")
    ]
    REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
