"""Browse, third confirmation: Claude Code with sanchopanza's crawl installed against Claude Code
alone, on Haiku and on Sonnet, on tasks no line, arm or check has met.

python benchmarks/browse/nav_confirm3.py --tasks | --record-hash | --preflight | --live
python benchmarks/browse/nav_confirm3.py                  # free: the verdicts so far

Two confirmations of the strategy line failed (README sections 16-17): v2 lost answers; v5 kept
them and one hang charged at the session cap decided the cost. What is confirmed here is not a
line in a system prompt but the package as a user installs it: `sanchopanza install --crawl`
writes two hooks (`harness.crawl_hook`): the line at SessionStart and a time limit on every
browser_evaluate. The `-SP` arms get exactly those settings, built by `install._merge_crawl`,
and nothing else; the plain arms get Claude Code as it is.

The owner's bar (2026-10-03): with sanchopanza, Claude Code has to beat the harness without it
on price and on answers at once, model by model. The hypotheses and thresholds are in
`verdicts()` and in prereg-crawl3.md, and neither moves once the first session has run. This
file loads its own copy of `nav_confirm.py` for the procedure (sealing, the hang rule, the
phase), so the first two confirmations are left exactly as they were sealed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import statistics
import subprocess
import sys
import time
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"


def _fresh(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / "nav_confirm.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


procedure = _fresh("browse_nav_confirm_v3")
nav = procedure.nav
A = nav.ANSWER_LINE

PREREG = nav.RESULTS / "prereg-crawl3.md"
SESSIONS = nav.RESULTS / "nav-confirm3-sessions.jsonl"
REPORT = nav.RESULTS / "nav-confirm3.json"
MODELS = {"HAIKU": "claude-haiku-4-5", "SONNET": "claude-sonnet-5"}
ARMS = ("HAIKU", "HAIKU-SP", "SONNET", "SONNET-SP")
RUNS = 3
CEILING_USD = 34.00  # list price, through the subscription; about 25 expected (prereg)
LINE_MARK = 80  # the first characters of the line, as the transcript must show them

# Answers from `truth_confirm3.py`, 2026-10-03, each checked by a second route (E1 by a text
# parse of the listing, E2 by page number and star colour, E3 in one GraphQL call, E4 sorted by
# price, E5 against the same products in the WooCommerce catalogue, E6 against each page's
# Next.js data, E7 by any year on each family's page, E8 by each book's information table).
CRAWLS: list[tuple[str, str, str, list[Any]]] = [
    ("E1", "https://web-scraping.dev/products",
     "This product listing runs over several pages. Across all of its pages, how many products "
     "cost less than $10?" + A, ["10"]),
    ("E2", "https://web-scraping.dev/testimonials",
     "This page loads more testimonials as you scroll down. Among all of the testimonials it can "
     "show, how many give five stars?" + A, ["36"]),
    ("E3", "https://web-scraping.dev/reviews",
     "This page shows more reviews each time you press its Load More button. Among all of the "
     "reviews it can show, how many give five stars?" + A, ["51"]),
    ("E4", "https://www.scrapingcourse.com/ecommerce/",
     "Across all of the pages of this shop, how many products cost more than $50 (the price "
     "shown)?" + A, ["55"]),
    ("E5", "https://www.scrapingcourse.com/infinite-scrolling",
     "This page loads more products as you scroll down. Among all of the products it can show, "
     "how many cost more than $60?" + A, ["27"]),
    ("E6", "https://sandbox.oxylabs.io/products",
     "Across every page of this game catalogue, how many games are listed with the genre "
     "Fantasy?" + A, ["208"]),
    ("E7", "https://www.scrapethissite.com/pages/frames/",
     "This page lists turtle families; each family's own page says when it was first "
     "discovered. How many of the families were first discovered before 1850?" + A, ["7"]),
    ("E8", "https://books.toscrape.com/catalogue/category/books/poetry_23/index.html",
     "Each book in this Poetry category has its own page showing how many copies are in stock. "
     "How many copies are in stock across all of the books in the category, added up?" + A,
     ["235"]),
]  # fmt: skip
# Walked by hand on 2026-10-03 (`check_tasks3.py`): the line and the guard should change nothing.
INTERACTIVE: list[tuple[str, str, str, list[Any]]] = [
    ("I1", "https://the-internet.herokuapp.com/login",
     "Log in as tomsmith with the password SuperSecretPassword!, report the message shown after "
     "logging in, then log out and report the message shown after logging out.",
     ["you logged into a secure area", "you logged out of the secure area"]),
    ("I2", "https://www.saucedemo.com/",
     "Log in as standard_user with the password secret_sauce, sort the products by price from "
     "high to low, put the first two products in that order in the cart, check out as Ada "
     "Lovelace with postal code 28001, and report the names of the two products and the item "
     "total, the tax and the total shown on the overview page.",
     ["fleece jacket", "backpack", "79.98", "6.40", "86.38"]),
]  # fmt: skip
TASKS = CRAWLS + INTERACTIVE


def crawl_command() -> str:
    return f'"{nav.HOOK_PYTHON.as_posix()}" -m sanchopanza crawl-hook'


def settings_for(arm: str, work: pathlib.Path) -> pathlib.Path:
    """The plain arms: the bench's permissions and no hook. The `-SP` arms: the same, plus what
    `sanchopanza install --crawl` writes, built by the install code itself."""
    from sanchopanza.harness.install import _merge_crawl

    settings: dict[str, Any] = {"permissions": {"allow": nav.TOOLS.split()}}
    if arm.endswith("-SP"):
        settings, _added, _removed = _merge_crawl(settings, True, command=crawl_command())
    path = work / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def _transcript(workdir: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]", "-", workdir)
    folder = pathlib.Path.home() / ".claude" / "projects" / slug
    paths = folder.glob("*.jsonl") if folder.is_dir() else []
    return "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in paths)


def one_session(task: tuple, run: int, arm: str) -> dict[str, Any]:
    """nav's session, timed, with the treatment checked rather than assumed: an `-SP` session
    whose transcript does not show the line never had its hooks run, and is `not_run`."""
    from sanchopanza.harness.crawl_hook import STRATEGY_LINE

    started = time.monotonic()
    row = nav.one_session(task, run, arm)
    row = {**row, "wall_s": round(time.monotonic() - started, 1)}
    text = _transcript(row["workdir"])
    row = {**row, "line_seen": STRATEGY_LINE[:LINE_MARK] in text,
           "guard_stops": text.count("evaluate stopped after")}  # fmt: skip
    if arm.endswith("-SP") and not row["line_seen"] and row.get("ok"):
        return {**row, "not_run": True, "subtype": "the crawl hooks never ran"}
    return row


def preflight() -> list[str]:
    """Before anything is spent: the hook command an `-SP` session will run imports this
    worktree's crawl hook, answers a session start with the line and wraps an evaluate."""
    problems: list[str] = []
    from sanchopanza.harness.crawl_hook import STRATEGY_LINE

    command = [str(nav.HOOK_PYTHON), "-m", "sanchopanza", "crawl-hook"]
    env = {**nav.base.clean_env(dict(os.environ)), "PYTHONPATH": str(SRC)}
    for event, check in (
        ({"hook_event_name": "SessionStart", "source": "startup"},
         lambda out: out["hookSpecificOutput"]["additionalContext"] == STRATEGY_LINE),
        ({"hook_event_name": "PreToolUse", "tool_name": "mcp__playwright__browser_evaluate",
          "tool_input": {"function": "() => 1"}},
         lambda out: "permissionDecision" not in out["hookSpecificOutput"]
         and "120000" in out["hookSpecificOutput"]["updatedInput"]["function"]),
    ):  # fmt: skip
        try:
            done = subprocess.run(command, input=json.dumps(event).encode(), env=env,
                                  capture_output=True, timeout=60)  # fmt: skip
            if not check(json.loads(done.stdout or b"{}")):
                problems.append(
                    f"{event['hook_event_name']}: unexpected answer {done.stdout[:120]!r}"
                )
        except (subprocess.TimeoutExpired, ValueError, KeyError, OSError) as error:
            problems.append(f"{event['hook_event_name']}: {error.__class__.__name__}: {error}")
    return problems


def _cell(rows: list[dict[str, Any]], tid: str, arm: str) -> list[dict[str, Any]]:
    return [r for r in rows if r["task"] == tid and r["arm"] == arm]


def _compare(rows: list[dict[str, Any]], base: str, treated: str) -> dict[str, Any]:
    """The registered comparison of one model with and without sanchopanza."""
    charged = procedure.charged
    crawl_ids = [t[0] for t in CRAWLS]
    inter_ids = [t[0] for t in INTERACTIVE]

    def total(ids: list[str], arm: str) -> float:
        return sum(charged(r) for t in ids for r in _cell(rows, t, arm))

    def wins(ids: list[str], arm: str) -> int:
        return sum(bool(r["success"]) for t in ids for r in _cell(rows, t, arm))

    def mean(tid: str, arm: str) -> float:
        return statistics.mean(charged(r) for r in _cell(rows, tid, arm) or [{"list_usd": 0}])

    ratio = total(crawl_ids, treated) / max(total(crawl_ids, base), 1e-9)
    cheaper = sum(mean(t, treated) < mean(t, base) for t in crawl_ids)
    inter_ratio = total(inter_ids, treated) / max(total(inter_ids, base), 1e-9)
    price = ratio <= 0.75 and cheaper >= 6
    answers = wins(crawl_ids, treated) >= wins(crawl_ids, base)
    no_harm = wins(inter_ids, treated) >= wins(inter_ids, base) - 1 and inter_ratio <= 1.25
    return {
        "price": {"ratio_total": round(ratio, 3), "tasks_cheaper": f"{cheaper}/8",
                  "holds": price},
        "answers": {base: f"{wins(crawl_ids, base)}/24", treated: f"{wins(crawl_ids, treated)}/24",
                    "holds": answers},
        "no_harm": {base: f"{wins(inter_ids, base)}/6", treated: f"{wins(inter_ids, treated)}/6",
                    "cost_ratio": round(inter_ratio, 3), "holds": no_harm},
        "beats_the_harness": price and answers and no_harm,
    }  # fmt: skip


def verdicts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The registered hypotheses, computed exactly as prereg-crawl3.md states them."""
    complete = all(len(_cell(rows, t[0], arm)) == RUNS for t in TASKS for arm in ARMS)
    haiku = _compare(rows, "HAIKU", "HAIKU-SP")
    sonnet = _compare(rows, "SONNET", "SONNET-SP")
    both = haiku["beats_the_harness"] and sonnet["beats_the_harness"]
    return {"complete": complete, "HAIKU": haiku, "SONNET": sonnet, "beats_on_both_models": both}


def described(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Not hypotheses: hangs, guard stops, wall time, per task; and the cheap model with
    sanchopanza against the dear one without it."""
    charged = procedure.charged
    crawl_ids = [t[0] for t in CRAWLS]
    out: dict[str, Any] = {"arms": {}, "tasks": {}}
    for arm in ARMS:
        cell = [r for r in rows if r["arm"] == arm]
        if not cell:
            continue
        out["arms"][arm] = {
            "sessions": len(cell),
            "hangs_killed_by_the_runner": sum(
                str(r.get("subtype") or "").startswith("runner:") for r in cell
            ),  # fmt: skip
            "guard_stops": sum(int(r.get("guard_stops") or 0) for r in cell),
            "median_wall_s": statistics.median(float(r.get("wall_s") or 0) for r in cell),
            "list_usd": round(sum(charged(r) for r in cell), 4),
        }
    for tid in [t[0] for t in TASKS]:
        out["tasks"][tid] = {
            arm: {"right": f"{sum(bool(r['success']) for r in c)}/{len(c)}",
                  "mean_usd": round(statistics.mean(charged(r) for r in c), 4),
                  "turns": [r.get("turns") for r in c]}
            for arm in ARMS if (c := _cell(rows, tid, arm))
        }  # fmt: skip
    cheap = sum(charged(r) for t in crawl_ids for r in _cell(rows, t, "HAIKU-SP"))
    dear = sum(charged(r) for t in crawl_ids for r in _cell(rows, t, "SONNET"))
    out["haiku_with_sanchopanza_vs_sonnet_alone"] = {
        "crawl_cost_ratio": round(cheap / max(dear, 1e-9), 3),
        "right": {arm: sum(bool(r["success"]) for t in crawl_ids for r in _cell(rows, t, arm))
                  for arm in ("HAIKU-SP", "SONNET")},
    }  # fmt: skip
    return out


def install() -> None:
    """Point the shared runner at this phase's models, settings and files. Every session, and
    the hook it starts, imports sanchopanza from this worktree: main's package has no crawl."""
    os.environ["PYTHONPATH"] = str(SRC)
    nav.MODELS.update({arm: MODELS[arm.split("-")[0]] for arm in ARMS})
    nav.settings_for = settings_for
    procedure.PREREG = PREREG
    procedure.SESSIONS = SESSIONS
    procedure.REPORT = REPORT


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
        print("preflight: the crawl hook answers as registered")
        if args.preflight:
            return 0
    rows = nav.done_sessions(SESSIONS)
    code = 0
    if args.live:
        procedure.require_registration()
        limits = nav.phase.Limits(session_max_usd=nav.SESSION_MAX_USD, ceiling_usd=CEILING_USD)
        plan = nav.phase.planned(TASKS, list(range(1, RUNS + 1)), ARMS)
        code, rows = nav.phase.run_phase(plan, rows, limits, one_session, SESSIONS)
    counted = nav.phase.counted(rows)
    if not counted:
        print("nothing recorded yet")
        return code
    report = {"verdicts": verdicts(counted), "described": described(counted),
              "versions": sorted({r.get("version", "") for r in counted}),
              "list_usd_total": round(sum(r["list_usd"] for r in counted), 4)}  # fmt: skip
    REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
