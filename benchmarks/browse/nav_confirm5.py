"""Browse, fifth confirmation: Claude Code with the crawl hook as v8.1 left it against Claude Code
alone, on Haiku and on Sonnet, on eight new crawls and four interactive tasks.

python benchmarks/browse/nav_confirm5.py --tasks | --record-hash | --preflight | --live
python benchmarks/browse/nav_confirm5.py                  # free: the verdicts so far

Registered in `docs/results/2026-10-03-browse-v6/prereg-crawl5.md`. The procedure (the sealing
check, the hang rule, the phase loop), the grading and the hypotheses are confirmation 4's, which
are confirmation 3's (`nav_confirm3._compare`), loaded here through `nav_v8.py`; that runner gives
the `-SP` arms v8.1's settings and treatment checks, its arms being named `-V81` there. What is
new is only what the prereg adds before the first session: the tasks, four runs on the interactive
tasks, and the rule for a site that is down (`site_down`).
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
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


v8 = _load("browse_nav_v8_for_5", HERE / "nav_v8.py")
conf4, conf3, nav = v8.conf4, v8.conf3, v8.nav
procedure = conf3.procedure
A = nav.ANSWER_LINE

RESULTS = conf4.RESULTS
PREREG = RESULTS / "prereg-crawl5.md"
SESSIONS = RESULTS / "nav-confirm5-sessions.jsonl"
REPORT = RESULTS / "nav-confirm5.json"
ARMS = conf3.ARMS  # HAIKU, HAIKU-SP, SONNET, SONNET-SP
CRAWL_RUNS = 3
INTERACTIVE_RUNS = 4
# List price, through the subscription; about 18 expected (prereg). The phase reserves one session
# cap (1.00) before each session, so the last one starts with at most 24.00 spent.
CEILING_USD = 25.00
SP_ENV = dict(v8.V81_ENV)  # v8.1, set in the session's own --settings and nowhere else
CLAUDE_VERSION = conf4.CLAUDE_VERSION
SETTINGS_HOME = pathlib.Path.home() / ".claude" / "settings.json"

# Answers from `truth_confirm5.py`, 2026-10-05, each checked by a second route (H1 by the API's
# region filter, H2 by the income-level endpoint, H3 by the challenge-rating filter, H4 by a SoQL
# count, H5 by the API's house filter, H6 on each book's page, H7 by category, H8 by the table as
# the browser draws it, page by page, in `check_tasks5.py`).
CRAWLS: list[tuple[str, str, str, list[Any]]] = [
    ("H1", "https://anapioficeandfire.com/api/houses",
     "This lists the noble houses of A Song of Ice and Fire. How many of the houses are in the "
     "region The Reach?" + A, ["72"]),
    ("H2", "https://api.worldbank.org/v2/country?format=json",
     "This lists the World Bank's countries and economies. How many of them have the income "
     "level High income?" + A, ["86"]),
    ("H3", "https://www.dnd5eapi.co/api/2014/monsters",
     "This lists the monsters of the D&D 5e reference. How many of them have a challenge rating "
     "of 10 or more?" + A, ["55"]),
    ("H4", "https://data.cityofnewyork.us/resource/vfnx-vebw.json",
     "This is the 2018 Central Park squirrel census. How many of the squirrel sightings it "
     "records have Cinnamon as the primary fur color?" + A, ["392"]),
    ("H5", "https://api.potterdb.com/v1/characters",
     "This lists Harry Potter characters. How many of the characters have a house field that "
     "is exactly Ravenclaw, with no other words in it?" + A, ["203"]),
    ("H6", "https://books.toscrape.com/catalogue/category/books/young-adult_21/index.html",
     "How many books in this category cost more than 35.00 (the price shown, in pounds)?" + A,
     ["29"]),
    ("H7", "https://www.demoblaze.com/",
     "Across all of this store's products, on every page of its list, how many cost less than "
     "$500?" + A, ["4"]),
    ("H8", "https://testautomationpractice.blogspot.com/",
     "In this page's Pagination Web Table, across all of its pages, how many products cost more "
     "than $15.00?" + A, ["10"]),
]  # fmt: skip
# Walked by hand on 2026-10-05 (`check_tasks5.py`): the line should not reach them, and the
# guard, the notes, the echo cut and the screenshot rule should change nothing.
INTERACTIVE: list[tuple[str, str, str, list[Any]]] = [
    *conf3.INTERACTIVE,  # I1, I2: confirmation 3's, walked in check_tasks3.py
    ("I3", "https://www.globalsqa.com/angularJs-protractor/BankingProject/#/login",
     "Log in as the customer Hermoine Granger, choose account 1001, deposit 1500, then withdraw "
     "400, and report the balance shown and the message shown after the withdrawal.",
     ["6196", "transaction successful"]),
    ("I4", "https://testpages.eviltester.com/pages/forms/html-form/",
     "Fill in this form with the username ada and the password lovelace1815, replace the comment "
     "with first program, tick Checkbox 1 and untick Checkbox 3, choose radio 3 and Drop Down "
     "Item 5, submit it, and report the values the results page shows for the comments, the "
     "checkboxes, the radio and the dropdown.",
     ["first program", "cb1", "rd3", "dd5"]),
]  # fmt: skip
TASKS = CRAWLS + INTERACTIVE
CRAWL_IDS = frozenset(t[0] for t in CRAWLS)

# A page load as Playwright MCP reports it, and the status it adds when the server did not answer
# 2xx (a 200 shows no status line). Prereg rule (a): a session is `site_down` when it was graded
# wrong and every page load it reports carries a 5xx.
_PAGE = re.compile(r"^- Page URL: ", re.M)
_STATUS_5XX = re.compile(r"^- HTTP status: 5\d\d\b", re.M)
SITE_DOWN = "site_down: every page load answered 5xx"


def runs_of(tid: str) -> int:
    return CRAWL_RUNS if tid in CRAWL_IDS else INTERACTIVE_RUNS


def planned() -> list[tuple]:
    """(task index, task, run, arm): task by task, run by run, arm by arm."""
    return [(i, task, run, arm) for i, task in enumerate(TASKS)
            for run in range(1, runs_of(task[0]) + 1) for arm in ARMS]  # fmt: skip


def as_v81(arm: str) -> str:
    """The name `nav_v8.py` gives the same arm: `HAIKU-SP` is its `HAIKU-V81`."""
    return arm.replace("-SP", "-V81")


def settings_for(arm: str, work: pathlib.Path) -> pathlib.Path:
    """v8.1's round settings: plain arms get the bench's permissions and no hook; `-SP` arms get
    what `install --crawl` writes, the events of `V8_HOOKS` and `V81_HOOKS`, and v8.1's env, in
    the session's own `--settings` only."""
    return v8.settings_for(as_v81(arm), work)


def page_loads(text: str) -> tuple[int, int]:
    """(page loads reported, of which 5xx), from the tool results of a transcript."""
    loads = down = 0
    for line in text.splitlines():
        try:
            content = (json.loads(line).get("message") or {}).get("content")
        except (ValueError, AttributeError):
            continue
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            for seen in v8._texts(block.get("content")):
                pages = len(_PAGE.findall(seen))
                loads += pages
                down += min(pages, len(_STATUS_5XX.findall(seen)))
    return loads, down


def site_down(row: dict[str, Any]) -> bool:
    loads, down = int(row.get("page_loads") or 0), int(row.get("page_loads_5xx") or 0)
    return not row.get("success") and loads > 0 and down == loads


def downs_before(tid: str, run: int, arm: str) -> int:
    """How many times this session has already been recorded as `site_down`."""
    return sum(bool(r.get("site_down")) for r in nav.done_sessions(SESSIONS)
               if (r["task"], r["run"], r["arm"]) == (tid, run, arm))  # fmt: skip


def one_session(task: tuple, run: int, arm: str) -> dict[str, Any]:
    """nav's session, timed, with v8.1's treatment checked in the transcript (`nav_v8.treatment`:
    the line on crawls only, no wrapper echoed, the notes at the head, the first screenshot
    denied), and the prereg's site-down rule: the first time, `not_run` and repeated at the end;
    the second time, counted as the arm's failure."""
    started = time.monotonic()
    row = nav.one_session(task, run, arm)
    text = conf3._transcript(row["workdir"])
    loads, down = page_loads(text)
    row = {**row, "wall_s": round(time.monotonic() - started, 1),
           "line_seen": v8.LINE_SEEN in text, "notes_seen": v8.NOTES_SEEN in text,
           "guard_stops": text.count(v8.GUARD_STOP), "echoed_wrappers": text.count(v8.ECHOED),
           "echo_cut": text.count(v8.ECHO_CUT), "click_notes": len(v8.CLICK_NOTE.findall(text)),
           "rows_notes": len(v8.ROWS_NOTE.findall(text)), **v8.v81_counts(text),
           "page_loads": loads, "page_loads_5xx": down}  # fmt: skip
    if v8.limit_hit(row):
        return {**row, "limit_hit": True, "not_run": True, "subtype": "usage limit or 429"}
    if row.get("ok"):
        why = v8.treatment(row, text, as_v81(arm), task[0] in CRAWL_IDS)
        if why:
            return {**row, "not_run": True, "subtype": why}
    if site_down(row):
        if downs_before(task[0], run, arm):
            return {**row, "site_down": True, "site_down_again": True}
        return {**row, "site_down": True, "not_run": True, "subtype": SITE_DOWN}
    return row


def _cell(rows: list[dict[str, Any]], tid: str, arm: str) -> list[dict[str, Any]]:
    return [r for r in rows if r["task"] == tid and r["arm"] == arm]


def verdicts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Confirmation 4's hypotheses, computed by its own code (`nav_confirm3._compare`) over this
    phase's tasks. Only a label changes: no harm counts 16 sessions here, not 6."""
    complete = all(len(_cell(rows, t[0], arm)) == runs_of(t[0]) for t in TASKS for arm in ARMS)
    out: dict[str, Any] = {"complete": complete}
    inter = len(INTERACTIVE) * INTERACTIVE_RUNS
    for base in ("HAIKU", "SONNET"):
        compared = conf3._compare(rows, base, f"{base}-SP")
        no_harm = {k: (v.replace("/6", f"/{inter}") if isinstance(v, str) else v)
                   for k, v in compared["no_harm"].items()}  # fmt: skip
        out[base] = {**compared, "no_harm": no_harm}
    out["beats_on_both_models"] = all(out[m]["beats_the_harness"] for m in ("HAIKU", "SONNET"))
    return out


ROUND = v8.Round(
    "confirm5", tuple((t[0], runs_of(t[0])) for t in TASKS), ARMS, SESSIONS,
    RESULTS / "nav-confirm5-smoke-sessions.jsonl", REPORT, CEILING_USD, (), 0.0,
    (("crawls HAIKU-SP/HAIKU", tuple(CRAWL_IDS), "HAIKU-SP", "HAIKU"),
     ("crawls SONNET-SP/SONNET", tuple(CRAWL_IDS), "SONNET-SP", "SONNET")),
)  # fmt: skip


def described(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Not hypotheses: confirmation 4's description (hangs, guard stops, wall time, per task, the
    cheap model with sanchopanza against the dear one without it), what v8.1's hooks did per arm,
    and every site-down session."""
    hooks = {arm: {k: v for k, v in data.items() if k not in ("sessions", "right", "list_usd")}
             for arm, data in v8.analyse(rows, ROUND)["arms"].items()}  # fmt: skip
    return {**conf3.described(rows), "hooks": hooks,
            "site_down_again": [{k: r.get(k) for k in ("task", "run", "arm")}
                                for r in rows if r.get("site_down_again")]}  # fmt: skip


def prompt_of(task: tuple) -> str:
    return f"Open {task[1]} in the browser. {task[2]}"


def preflight() -> list[str]:
    """Before anything is spent: v8.1's preflight (the pinned Claude Code; line v6, the notes,
    the echo cut, the notes at the head and the first screenshot denied, each through the real
    hook command), then this phase's own: the line answers every crawl's prompt and none of the
    interactive ones, and no sanchopanza hook sits in the user's settings."""
    from sanchopanza.harness.crawl_hook import STRATEGY_LINE_V6

    problems = v8.preflight(v8.ROUNDS["v81"])
    env = {**nav.base.clean_env(dict(os.environ)), "PYTHONPATH": str(conf3.SRC), **SP_ENV}
    checks = tuple(
        ({"hook_event_name": "UserPromptSubmit", "prompt": prompt_of(task)},
         (lambda out: out["hookSpecificOutput"]["additionalContext"] == STRATEGY_LINE_V6)
         if task[0] in CRAWL_IDS else (lambda out: out is None))
        for task in TASKS
    )  # fmt: skip
    problems += v8._hook_checks(env, checks, "confirm5 prompts")
    return problems + user_hook_problems(SETTINGS_HOME)


def user_hook_problems(path: pathlib.Path) -> list[str]:
    """A sanchopanza hook in the user's settings would reach every session that loads them; the
    sessions load none (`--setting-sources ""`), and the user's file must not hold one either."""
    try:
        hooks = json.loads(path.read_text(encoding="utf-8")).get("hooks") if path.exists() else {}
    except (OSError, ValueError) as error:
        return [f"{path} unreadable: {error.__class__.__name__}"]
    if re.search(r"sanchopanza|crawl-hook", json.dumps(hooks or {})):
        return [f"{path} has a sanchopanza hook: v8.1 goes only in a session's --settings"]
    return []


def install() -> None:
    """v8.1's runner (and through it confirmation 4's procedure), pointed at this phase's tasks,
    arms' settings and files."""
    v8.install()
    conf3.CRAWLS, conf3.INTERACTIVE, conf3.TASKS = CRAWLS, INTERACTIVE, TASKS
    nav.settings_for = settings_for
    procedure.PREREG, procedure.SESSIONS, procedure.REPORT = PREREG, SESSIONS, REPORT


def run_live() -> tuple[int, list[dict[str, Any]]]:
    """Every planned session, then the site-down repeats at the end, under one ceiling."""
    rows = nav.done_sessions(SESSIONS)
    limits = nav.phase.Limits(session_max_usd=nav.SESSION_MAX_USD, ceiling_usd=CEILING_USD)
    downed = {(r["task"], r["run"], r["arm"]) for r in rows if r.get("site_down")}
    plan = planned()
    first = [p for p in plan if (p[1][0], p[2], p[3]) not in downed]
    code, rows = nav.phase.run_phase(first, rows, limits, one_session, SESSIONS)
    if code == 0:  # the repeats: whatever the plan still lacks, site-down sessions among them
        code, rows = nav.phase.run_phase(plan, rows, limits, one_session, SESSIONS)
    if code == 2:
        nav.phase._log(SESSIONS, f"{v8.STOP_LIMIT}: the subscription refused a session; stopped")
    return code, rows


def report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counted = nav.phase.counted(rows)
    return {"verdicts": verdicts(counted), "described": described(counted),
            "versions": sorted({r.get("version", "") for r in counted}),
            "list_usd_counted": round(sum(r["list_usd"] for r in counted), 4),
            "list_usd_spent": round(sum(r["list_usd"] for r in rows), 4),
            "not_run": [{k: r.get(k) for k in ("task", "run", "arm", "subtype")}
                        for r in rows if r.get("not_run")]}  # fmt: skip


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ("--tasks", "--record-hash", "--preflight", "--live"):
        ap.add_argument(flag, action="store_true")
    args = ap.parse_args()
    install()
    if args.tasks:
        for tid, url, question, required in TASKS:
            print(f"{tid} x{runs_of(tid)}  {url}\n    {question}\n    required: {required}\n")
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
        print("preflight: claude pinned; the hooks answer as v8.1's env asks, on these prompts")
        if args.preflight:
            return 0
    code = 0
    if args.live:
        procedure.require_registration()
        RESULTS.mkdir(parents=True, exist_ok=True)
        code, _rows = run_live()
    rows = nav.done_sessions(SESSIONS)
    if not nav.phase.counted(rows):
        print("nothing recorded yet")
        return code
    out = report(rows)
    REPORT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
