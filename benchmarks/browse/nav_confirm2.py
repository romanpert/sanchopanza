"""Browse, strategy line v5: the second confirmation, on tasks no line has been developed on.

python benchmarks/browse/nav_confirm2.py --tasks | --record-hash | --live | (no flag: verdicts)

Line v2 is being confirmed by `nav_confirm.py`. While it ran, development found why the lines
lost sessions to walking (an extraction that clicked or navigated inside the evaluate) and v5
says so (README section 15). v5 is confirmed here on tasks it has never met. The procedure, the
hypotheses and their thresholds are `nav_confirm.py`'s, unchanged: this file loads its own copy
of that module and gives it these tasks, these arms and these files, so the first confirmation
is left exactly as it was sealed.
"""

from __future__ import annotations

import importlib.util
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _fresh(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, HERE / "nav_confirm.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


first = _fresh("browse_nav_confirm")  # the first confirmation, as sealed
confirmation = _fresh("browse_nav_confirm_v5")  # the same procedure, given what follows
A = confirmation.nav.ANSWER_LINE

# Answers from `truth_confirm2.py`, 2026-10-02, each checked by a second route (D3 and D4 against
# the static site, D5 and D6 against the static copies, D7 at 100 rows a page).
CRAWLS: list[tuple[str, str, str, list[Any]]] = [
    ("D1", "https://books.toscrape.com/",
     "Across the whole catalogue, every one of its pages, how many books cost less than 11.00 "
     "(the price shown, in pounds)?" + A, ["23"]),
    ("D2", "https://books.toscrape.com/",
     "In the category called Default, across all of its pages, how many books are rated three "
     "stars?" + A, ["27"]),
    ("D3", "https://quotes.toscrape.com/js-delayed/",
     "This site shows its quotes only after a delay. How many quotes on it, counting every one "
     "of its pages, are tagged 'life'?" + A, ["13"]),
    ("D4", "https://quotes.toscrape.com/search.aspx",
     "Using this search form, how many quotes by Albert Einstein are tagged 'inspirational'?"
     + A, ["1"]),
    ("D5", "https://webscraper.io/test-sites/e-commerce/scroll/computers/laptops",
     "This page loads more laptops as you scroll down. Among all of the laptops it can show, how "
     "many cost less than $500?" + A, ["38"]),
    ("D6", "https://webscraper.io/test-sites/e-commerce/more/computers/tablets",
     "This page shows more tablets each time you press its button. Among all of the tablets it "
     "can show, how many cost more than $500?" + A, ["3"]),
    ("D7", "https://www.scrapethissite.com/pages/forms/",
     "Search this table for teams whose name contains New York. Across all of the pages of "
     "results, in how many of those team seasons did the team win 40 games or more?" + A,
     ["12"]),
    ("D8", "https://books.toscrape.com/",
     "What do the prices of all the books in the Fantasy category, across all of its pages, add "
     "up to (the prices shown, in pounds)?" + A, ["1900.51"]),
]  # fmt: skip
INTERACTIVE = [t for t in confirmation.nav.TASKS if t[0] == "A2"] + [
    t for t in confirmation.nav.TRAP_TASKS if t[0] == "B2"
]

confirmation.CRAWLS = CRAWLS
confirmation.INTERACTIVE = INTERACTIVE
confirmation.TASKS = CRAWLS + INTERACTIVE
confirmation.ARMS = ("HAIKU", "HAIKU-HINT5")
confirmation.PREREG = confirmation.nav.RESULTS / "prereg-strategy2.md"
confirmation.SESSIONS = confirmation.nav.RESULTS / "nav-confirm2-sessions.jsonl"
confirmation.REPORT = confirmation.nav.RESULTS / "nav-confirm2.json"


if __name__ == "__main__":
    raise SystemExit(confirmation.main())
