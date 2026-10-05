"""Browse, strategy line: the confirmation, on tasks the line was not developed on.

python benchmarks/browse/nav_confirm.py --tasks            # free: print the task set
python benchmarks/browse/nav_confirm.py --record-hash      # seal prereg-strategy.md
python benchmarks/browse/nav_confirm.py --live             # see prereg-strategy.md
python benchmarks/browse/nav_confirm.py                    # free: the verdicts so far

The development round (`nav_e2e.py --strategy`, README section 14) found that one fixed line in
the system prompt - "if the request needs data gathered from many pages, write one
browser_evaluate that collects them all, account for what it read, cap every loop" - made Haiku
about half as expensive on long crawls with no loss of answers. That line was written and
rewritten on S1-S5 and H1, so those numbers cannot confirm it. Here it meets eight crawls it
has never seen, over the mechanisms a crawl meets, and two interactive tasks where it should
change nothing. The hypotheses and their thresholds are in `verdicts()` and in the registered
document, and neither moves once the first session has run.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import statistics
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


nav = _load("browse_nav_e2e", HERE / "nav_e2e.py")

PREREG = nav.RESULTS / "prereg-strategy.md"
SESSIONS = nav.RESULTS / "nav-confirm-sessions.jsonl"
REPORT = nav.RESULTS / "nav-confirm.json"
ARMS = ("HAIKU", "HAIKU-HINT2")
RUNS = 3
CEILING_USD = 14.00  # list price, through the subscription; 60 sessions at about 0.17 expected
A = nav.ANSWER_LINE

# Answers from `truth_confirm.py`, 2026-10-02, each checked by a second route (C3 by the values
# near the cut; C4 by the page's own year tabs, 2010-2015; C5 and C6 by the static copies of the
# same catalogues; C7 by the tag pages; C8 on one page of 600 rows).
CRAWLS: list[tuple[str, str, str, list[Any]]] = [
    ("C1", "https://books.toscrape.com/",
     "In the Nonfiction category, across all of its pages, how many books cost less than 20.00 "
     "(the price shown, in pounds)?" + A, ["23"]),
    ("C2", "https://books.toscrape.com/",
     "Across the whole catalogue, every one of its pages, how many books are rated one star and "
     "cost more than 50.00 (the price shown, in pounds)?" + A, ["40"]),
    ("C3", "https://www.scrapethissite.com/pages/simple/",
     "Of the countries listed on this page, how many have an area greater than 1,000,000 square "
     "kilometres?" + A, ["31"]),
    ("C4", "https://www.scrapethissite.com/pages/ajax-javascript/",
     "Across all of the years this page lists, how many of the films shown won 3 or more awards?"
     + A, ["16"]),
    ("C5", "https://webscraper.io/test-sites/e-commerce/ajax/computers/tablets",
     "How many tablets in this category, across all of its pages, cost less than $300?" + A,
     ["15"]),
    ("C6", "https://webscraper.io/test-sites/e-commerce/more/computers/laptops",
     "This page shows more laptops each time you press its button. Among all of the laptops it "
     "can show, how many cost more than $1,500?" + A, ["3"]),
    ("C7", "https://quotes.toscrape.com/tableful/",
     "How many quotes on this site, counting every one of its pages, are tagged 'humor'?" + A,
     ["12"]),
    ("C8", "https://www.scrapethissite.com/pages/forms/",
     "This table lists hockey team seasons over many pages. In how many of those team seasons, "
     "across all of the pages, did the team lose 40 games or more?" + A, ["111"]),
]  # fmt: skip
# Interactive tasks the line has never been run on: it should change nothing there.
INTERACTIVE = [t for t in nav.TASKS if t[0] in ("A2", "A3")]
TASKS = CRAWLS + INTERACTIVE


def require_registration() -> None:
    sealed = PREREG.with_suffix(".sha256")
    if not sealed.exists() or sealed.read_text().strip() != nav.base.digest(PREREG):
        raise SystemExit(f"{PREREG.name} is not registered as it stands: nothing spent")


def charged(row: dict[str, Any]) -> float:
    """A session the runner had to kill reports no cost; it is charged the session cap, which
    is what it could have spent. A hang is not free (H1, development round: 30 minutes, 0 USD)."""
    if str(row.get("subtype") or "").startswith("runner:"):
        return float(nav.SESSION_MAX_USD)
    return float(row.get("list_usd") or 0.0)


def _cell(rows: list[dict[str, Any]], tid: str, arm: str) -> list[dict[str, Any]]:
    return [r for r in rows if r["task"] == tid and r["arm"] == arm]


def verdicts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The three registered hypotheses, computed exactly as prereg-strategy.md states them."""
    base, hint = ARMS
    crawl_ids = [t[0] for t in CRAWLS]
    inter_ids = [t[0] for t in INTERACTIVE]
    complete = all(
        len(_cell(rows, t[0], arm)) == RUNS for t in TASKS for arm in ARMS
    )  # fmt: skip

    def total(ids: list[str], arm: str) -> float:
        return sum(charged(r) for t in ids for r in _cell(rows, t, arm))

    def wins(ids: list[str], arm: str) -> int:
        return sum(bool(r["success"]) for t in ids for r in _cell(rows, t, arm))

    ratio = total(crawl_ids, hint) / max(total(crawl_ids, base), 1e-9)
    cheaper = sum(
        statistics.mean(charged(r) for r in _cell(rows, t, hint) or [{"list_usd": 0}])
        < statistics.mean(charged(r) for r in _cell(rows, t, base) or [{"list_usd": 0}])
        for t in crawl_ids
    )
    inter_ratio = total(inter_ids, hint) / max(total(inter_ids, base), 1e-9)
    return {
        "complete": complete,
        "H1_cost": {"ratio_total": round(ratio, 3), "tasks_cheaper": f"{cheaper}/8",
                    "holds": ratio <= 0.75 and cheaper >= 6},
        "H2_accuracy": {base: f"{wins(crawl_ids, base)}/24", hint: f"{wins(crawl_ids, hint)}/24",
                        "holds": wins(crawl_ids, hint) >= wins(crawl_ids, base) - 2},
        "H3_no_harm": {base: f"{wins(inter_ids, base)}/6", hint: f"{wins(inter_ids, hint)}/6",
                       "cost_ratio": round(inter_ratio, 3),
                       "holds": wins(inter_ids, hint) >= wins(inter_ids, base) - 1
                       and inter_ratio <= 1.25},
    }  # fmt: skip


def described(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Not hypotheses: how often the extraction was used, turns and cost per task, for reading."""
    out: dict[str, Any] = {}
    for tid in [t[0] for t in TASKS]:
        out[tid] = {}
        for arm in ARMS:
            cell = _cell(rows, tid, arm)
            if not cell:
                continue
            navs = [r["tools"].get("mcp__playwright__browser_navigate", 0) for r in cell]
            out[tid][arm] = {
                "right": f"{sum(bool(r['success']) for r in cell)}/{len(cell)}",
                "mean_usd": round(statistics.mean(charged(r) for r in cell), 4),
                "turns": [r.get("turns") for r in cell],
                "at_most_3_navigations": sum(n <= 3 for n in navs),
            }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tasks", action="store_true")
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    args = ap.parse_args()
    if args.tasks:
        for tid, url, question, required in TASKS:
            print(f"{tid}  {url}\n    {question}\n    required: {required}\n")
        return 0
    if args.record_hash:
        PREREG.with_suffix(".sha256").write_text(nav.base.digest(PREREG) + "\n", encoding="utf-8")
        print(f"registered {PREREG.name}: {nav.base.digest(PREREG)}")
        return 0
    rows = nav.done_sessions(SESSIONS)
    code = 0
    if args.live:
        require_registration()
        limits = nav.phase.Limits(session_max_usd=nav.SESSION_MAX_USD, ceiling_usd=CEILING_USD,
                                  jev_session_max_usd=nav.JEV_SESSION_MAX_USD)  # fmt: skip
        plan = nav.phase.planned(TASKS, list(range(1, RUNS + 1)), ARMS)
        code, rows = nav.phase.run_phase(plan, rows, limits, nav.one_session, SESSIONS)
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
