"""Browse, phase 3b: Claude Code browsing with Playwright MCP, with and without the hook.

python benchmarks/browse/e2e_mcp.py --record-hash
python benchmarks/browse/e2e_mcp.py --pilot --live --env-file PATH/.env   # excluded from counts
python benchmarks/browse/e2e_mcp.py --live --env-file PATH/.env           # see prereg-e2e-mcp.md
python benchmarks/browse/e2e_mcp.py                                       # free: re-grades

Phase 3 measured the hook where it could not win: `playwright-cli` serves 7,000-29,000
character snapshots against ~45,000 tokens of fixed context a turn. What most people install is
Playwright MCP, and 0.0.83's `browser_snapshot` returns the whole snapshot inline: 50,157
characters for a GitHub repository page, 860,106 for Wikipedia's Mount Everest (probed
2026-09-30, no model). This phase asks the same question there, set up as an ordinary session:
the MCP server as its README installs it, Read/Grep/Glob, no instructions about which tool to use.
Shared pieces (grading, analysis, environment, journal) come from `e2e.py`.
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
RESULTS = base.RESULTS
PREREG = RESULTS / "prereg-e2e-mcp.md"
SESSIONS = RESULTS / "e2e-mcp-sessions.jsonl"
MODEL = base.MODEL
PLAYWRIGHT_MCP = "@playwright/mcp@0.0.83"
RUNS = 4
SESSION_MAX_USD = 1.50
CEILING_USD = 20.00
TIMEOUT_S = 900
TOOLS = "mcp__playwright Read Grep Glob"
JEV_SESSION_MAX_USD = 0.20  # the hook's per-session Jev ceiling (the autopilot's, shared)

TASKS = [
    ("M1", "https://github.com/microsoft/playwright",
     "Which license is this repository under, and which language makes up the largest share "
     "of its code?", [["apache"], ["typescript"]]),
    ("M2", "https://en.wikipedia.org/wiki/Mount_Everest",
     "What elevation in metres does the infobox give?", ["8848.86"]),
    ("M3", "https://docs.python.org/3/library/functions.html",
     "According to this page, what is the default value of the start parameter of sum()?",
     [["start=0", "start = 0", "`0`", "**0**", "is 0", "of 0", "zero"]]),
    ("M4", "https://en.wikipedia.org/wiki/Python_(programming_language)",
     "From the infobox, who designed Python and in which year did it first appear?",
     ["guido van rossum", "1991"]),
    ("M5", "https://www.npmjs.com/package/react",
     "Which license is this package published under?", [["mit"]]),
    ("M6", "https://books.toscrape.com/",
     "Go to page 2 of the catalogue and report the title of the first book listed.",
     ["in her wake"]),
]  # fmt: skip

APPEND = "Answer the user's question briefly with the facts found on the page."


def mcp_config(work: pathlib.Path) -> pathlib.Path:
    npx = shutil.which("npx") or "npx"
    config = {
        "mcpServers": {
            "playwright": {
                "command": npx,
                "args": ["-y", PLAYWRIGHT_MCP, "--headless", "--isolated"],
            }
        }
    }
    path = work / "mcp.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def settings_for(arm: str, work: pathlib.Path) -> pathlib.Path:
    settings: dict[str, Any] = {"permissions": {"allow": TOOLS.split()}}
    if arm == "LEAN":
        command = f'"{base.PYTHON.as_posix()}" -m sanchopanza.harness.browse_hook'
        settings["hooks"] = {
            "PostToolUse": [
                {"matcher": "Read|mcp__playwright__.*",
                 "hooks": [{"type": "command", "command": command}]}
            ]
        }  # fmt: skip
    path = work / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def tool_calls(work: pathlib.Path) -> dict[str, int]:
    """Tool uses by name, from the session's transcript (Claude Code keeps it by directory)."""
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(work))
    folder = pathlib.Path.home() / ".claude" / "projects" / slug
    counts: dict[str, int] = {}
    for path in folder.glob("*.jsonl") if folder.is_dir() else []:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            content = (json.loads(line).get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    counts[block["name"]] = counts.get(block["name"], 0) + 1
    return counts


def one_session(task: tuple, run: int, arm: str, key: str) -> dict[str, Any]:
    tid, url, question, required = task
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-mcp-{tid.lower()}r{run}{arm.lower()}-"))
    journal = work / "journal.jsonl"
    env = base.clean_env(dict(os.environ))
    env["SANCHOPANZA_JOURNAL"] = str(journal)
    env["SANCHOPANZA_ARCHIVE"] = str(work / "archive")
    if arm == "LEAN":
        env["TYPESAFE_API_KEY"] = key
        env["SANCHOPANZA_SESSION_MAX_USD"] = f"{JEV_SESSION_MAX_USD:g}"
    else:
        env.pop("TYPESAFE_API_KEY", None)
    argv = [
        shutil.which("claude") or "claude", "-p", "--model", MODEL,
        "--append-system-prompt", APPEND,
        "--settings", str(settings_for(arm, work)), "--setting-sources", "",
        "--mcp-config", str(mcp_config(work)), "--strict-mcp-config",
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
    jev_usd, jev_calls = base.journal_usd(journal)
    browse_events = []
    if journal.exists():
        events = [json.loads(x) for x in journal.read_text(encoding="utf-8").splitlines() if x]
        browse_events = [e.get("data", {}) for e in events if e.get("kind") == "browse"]
    answer = str(out.get("result") or "")
    return {
        "task": tid, "run": run, "arm": arm,
        "ok": not out.get("is_error", True), "subtype": out.get("subtype"),
        "success": base.graded(answer, required), "answer": answer[:600],
        "list_usd": float(out.get("total_cost_usd") or 0.0),
        "turns": out.get("num_turns"),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "jev_usd": jev_usd, "jev_calls": jev_calls, "pruned": browse_events,
        "tools": tool_calls(work), "workdir": str(work),
    }  # fmt: skip


def done_sessions() -> list[dict[str, Any]]:
    if not SESSIONS.exists():
        return []
    return [json.loads(x) for x in SESSIONS.read_text(encoding="utf-8").splitlines() if x.strip()]


def require_prereg() -> None:
    registered = PREREG.with_suffix(".sha256")
    if not registered.exists() or registered.read_text().strip() != base.digest(PREREG):
        raise SystemExit(f"{PREREG.name} missing or changed since it was registered: nothing spent")


def key_from(env_file: str | None) -> str:
    key = os.environ.get("TYPESAFE_API_KEY", "")
    if not key and env_file:
        text = pathlib.Path(env_file).read_text(encoding="utf-8")
        found = re.search(r"^TYPESAFE_API_KEY=(.*)$", text, re.M)
        key = found.group(1).strip().strip("'\"") if found else ""
    return key


FIXED = {  # Phase 3c: the same design, the hook with Phase 3b's three faults fixed
    "prereg": RESULTS / "prereg-e2e-mcp-fixed.md",
    "sessions": RESULTS / "e2e-mcp-fixed-sessions.jsonl",
    "report": "e2e-mcp-fixed.json",
}
JEV_CEILING_USD = 2.00  # Phase 3c: the hook now sees snapshots of up to ~2,700 elements
NEW = {  # Phase 3d: new tasks, so the hook is not measured on the pages it was fixed on
    "prereg": RESULTS / "prereg-e2e-mcp-new.md",
    "sessions": RESULTS / "e2e-mcp-new-sessions.jsonl",
    "report": "e2e-mcp-new.json",
}
WIDE = {  # Phase 3f: twelve more tasks, five of them several steps long
    "prereg": RESULTS / "prereg-e2e-wide.md",
    "sessions": RESULTS / "e2e-mcp-wide-sessions.jsonl",
    "report": "e2e-mcp-wide.json",
}
WIDE_RUNS = 3
WIDE_TASKS = [
    ("W1", "https://github.com/psf/requests",
     "Which license is this repository under, and which language makes up the largest share "
     "of its code?", [["apache"], ["python"]]),
    ("W2", "https://github.com/microsoft/vscode",
     "Which license is this repository under, and which language makes up the largest share "
     "of its code?", [["mit"], ["typescript"]]),
    ("W3", "https://en.wikipedia.org/wiki/Mount_Kilimanjaro",
     "What elevation in metres does the infobox give?", ["5895"]),
    ("W4", "https://en.wikipedia.org/wiki/Spain",
     "According to the infobox, what is the capital and what is the currency?",
     ["madrid", ["euro"]]),
    ("W5", "https://www.rfc-editor.org/rfc/rfc9110.html",
     "What is the title of section 15.5.5?", [["not found"]]),
    ("W6", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/418",
     "What is the name of this HTTP status code?", ["teapot"]),
    ("W7", "https://en.wikipedia.org/wiki/List_of_tallest_buildings",
     "Which building is the tallest in the world according to this page?", ["burj khalifa"]),
    ("W8", "https://books.toscrape.com/",
     "Go to the Travel category and report the price of the third book listed there.",
     ["48.87"]),
    ("W9", "https://books.toscrape.com/",
     "Go to the Mystery category, open the second book listed, and report its UPC.",
     ["19ed25f4641d5efd"]),
    ("W10", "https://quotes.toscrape.com/",
     "Go to page 3 of the quotes and report the author of the first quote there.",
     ["neruda"]),
    ("W11", "https://quotes.toscrape.com/",
     "Open the quotes tagged 'love' and report the author of the first one.", ["gide"]),
    ("W12", "https://books.toscrape.com/",
     "Go to page 3 of the catalogue and report the title of the first book on it.",
     ["slow states of collapse"]),
]  # fmt: skip
X = {  # Phase 3h: twelve more tasks for the two fixes designed on 3f's (fccc06a)
    "prereg": RESULTS / "prereg-e2e-x.md",
    "sessions": RESULTS / "e2e-mcp-x-sessions.jsonl",
    "report": "e2e-mcp-x.json",
}
X_TASKS = [
    ("X1", "https://github.com/pallets/click",
     "Which license is this repository under, and which language makes up the largest share "
     "of its code?", [["bsd"], ["python"]]),
    ("X2", "https://github.com/facebook/react",
     "Which license is this repository under, and which language makes up the largest share "
     "of its code?", [["mit"], ["javascript"]]),
    ("X3", "https://github.com/golang/go", "Which license is this repository under?",
     [["bsd"]]),
    ("X4", "https://en.wikipedia.org/wiki/France",
     "According to the infobox, what is the capital and what is the currency?",
     ["paris", ["euro"]]),
    ("X5", "https://en.wikipedia.org/wiki/Mount_Fuji",
     "How high is its highest point in metres, according to the infobox?", ["3776"]),
    ("X6", "https://en.wikipedia.org/wiki/List_of_highest_mountains_on_Earth",
     "Which mountain is the highest according to this page?", ["everest"]),
    ("X7", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/404",
     "What is the name of this HTTP status code?", [["not found"]]),
    ("X8", "https://www.rfc-editor.org/rfc/rfc9110.html",
     "What is the title of section 15.3.1?", [["200 ok"]]),
    ("X9", "https://books.toscrape.com/",
     "Go to the Science category and report the price of the first book listed there.",
     ["42.96"]),
    ("X10", "https://books.toscrape.com/",
     "Go to the Poetry category, open the second book listed, and report its UPC.",
     ["1dfe412b8ac00530"]),
    ("X11", "https://quotes.toscrape.com/",
     "Go to page 2 of the quotes and report the author of the first quote there.",
     ["monroe"]),
    ("X12", "https://quotes.toscrape.com/",
     "Open the quotes tagged 'humor' and report the author of the first one.", ["austen"]),
]  # fmt: skip
Y = {  # Phase 3j: twelve new tasks for the saved-output fix (07f6a72) and position (b16ce65)
    "prereg": RESULTS / "prereg-e2e-y.md",
    "sessions": RESULTS / "e2e-mcp-y-sessions.jsonl",
    "report": "e2e-mcp-y.json",
}
JEV_CEILING_Y_USD = 1.00  # Phase 3j: within what is left of the owner's 5 USD of Jev
Y_TASKS = [
    ("Y1", "https://github.com/expressjs/express",
     "Which license is this repository under, and which language makes up the largest share "
     "of its code?", [["mit"], ["javascript"]]),
    ("Y2", "https://github.com/rust-lang/rust",
     "Which license is this repository under, and which language makes up the largest share "
     "of its code?", [["apache", "mit"], ["rust"]]),
    ("Y3", "https://en.wikipedia.org/wiki/Germany",
     "According to the infobox, what is the capital and what is the currency?",
     ["berlin", ["euro"]]),
    ("Y4", "https://en.wikipedia.org/wiki/Danube",
     "According to the infobox, how long is the river in kilometres, and where is its mouth?",
     ["2850", ["danube delta", "black sea"]]),
    ("Y5", "https://en.wikipedia.org/wiki/List_of_lakes_by_area",
     "Which lake is listed first in the table?", ["caspian"]),
    ("Y6", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/503",
     "What is the name of this HTTP status code?", [["service unavailable"]]),
    ("Y7", "https://www.rfc-editor.org/rfc/rfc9111.html",
     "What is the title of section 5.2?", [["cache-control", "cache control"]]),
    ("Y8", "https://books.toscrape.com/",
     "Go to the Travel category and report the title of the third book listed there.",
     ["see america"]),
    ("Y9", "https://books.toscrape.com/",
     "Go to the History category and report the price of the last book listed there.",
     ["43.70"]),
    ("Y10", "https://quotes.toscrape.com/",
     "Open the quotes tagged 'life' and report the author of the second one.", ["gide"]),
    ("Y11", "https://quotes.toscrape.com/",
     "Go to page 3 of the quotes and report the author of the first quote there.",
     ["neruda"]),
    ("Y12", "https://books.toscrape.com/",
     "Go to the Philosophy category, find the book 'The Stranger', and report its price.",
     ["17.44"]),
]  # fmt: skip
Z = {  # Phase 3l: twelve new tasks for the infobox and page-order fixes (0138a2d)
    "prereg": RESULTS / "prereg-e2e-z.md",
    "sessions": RESULTS / "e2e-mcp-z-sessions.jsonl",
    "report": "e2e-mcp-z.json",
}
Z_TASKS = [
    ("Z1", "https://en.wikipedia.org/wiki/Nile",
     "According to the infobox, how long is the river in kilometres, and where is its mouth?",
     ["7088", ["mediterranean"]]),
    ("Z2", "https://en.wikipedia.org/wiki/Mont_Blanc",
     "According to the infobox, in which year was the first ascent?", ["1786"]),
    ("Z3", "https://en.wikipedia.org/wiki/Italy",
     "According to the infobox, what is the capital and what is the currency?",
     ["rome", ["euro"]]),
    ("Z4", "https://en.wikipedia.org/wiki/Amazon_River",
     "According to the infobox, how long is the river in kilometres?", [["6575", "6400"]]),
    ("Z5", "https://en.wikipedia.org/wiki/List_of_largest_cities",
     "Which city is listed first in the table?", ["jakarta"]),
    ("Z6", "https://en.wikipedia.org/wiki/List_of_river_systems_by_length",
     "Which river is ranked first in the table?", ["nile"]),
    ("Z7", "https://github.com/django/django",
     "Which license is this repository under, and which language makes up the largest share "
     "of its code?", [["bsd"], ["python"]]),
    ("Z8", "https://github.com/vuejs/core",
     "Which license is this repository under, and which language makes up the largest share "
     "of its code?", [["mit"], ["typescript"]]),
    ("Z9", "https://books.toscrape.com/",
     "Go to the Fantasy category and report the title of the last book listed on its first "
     "page.", ["folly"]),
    ("Z10", "https://quotes.toscrape.com/",
     "Open the quotes tagged 'inspirational' and report the author of the third one.",
     ["edison"]),
    ("Z11", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/301",
     "What is the name of this HTTP status code?", [["moved permanently"]]),
    ("Z12", "https://www.rfc-editor.org/rfc/rfc9112.html",
     "What is the title of section 3.2?", [["request target", "request-target"]]),
]  # fmt: skip
U = {  # Phase 3n: twelve new tasks for nearest infobox rows, card facts, position words (4416aa4)
    "prereg": RESULTS / "prereg-e2e-u.md",
    "sessions": RESULTS / "e2e-mcp-u-sessions.jsonl",
    "report": "e2e-mcp-u.json",
}
U_TASKS = [
    ("U1", "https://en.wikipedia.org/wiki/Rhine",
     "According to the infobox, how long is the river in kilometres, and where is its mouth?",
     ["1230", ["north sea"]]),
    ("U2", "https://en.wikipedia.org/wiki/Matterhorn",
     "According to the infobox, in which year was the first ascent?", ["1865"]),
    ("U3", "https://en.wikipedia.org/wiki/Austria",
     "According to the infobox, what is the capital and what is the currency?",
     ["vienna", ["euro"]]),
    ("U4", "https://en.wikipedia.org/wiki/Mississippi_River",
     "According to the infobox, how long is the river in kilometres, and where is its mouth?",
     ["3766", ["gulf of mexico"]]),
    ("U5", "https://books.toscrape.com/",
     "Go to the Science Fiction category, find the book 'The Project', and report its price.",
     ["10.65"]),
    ("U6", "https://books.toscrape.com/",
     "Go to the Horror category, find the book 'Pet Sematary', and report its price.",
     ["10.56"]),
    ("U7", "https://quotes.toscrape.com/",
     "Open the quotes tagged 'friendship' and report the author of the final one.",
     ["tennyson"]),
    ("U8", "https://books.toscrape.com/",
     "Go to the Classics category and report the title of the book at the bottom of its first "
     "page.", ["alice"]),
    ("U9", "https://en.wikipedia.org/wiki/List_of_countries_and_dependencies_by_area",
     "Which country is listed first in the table?", ["russia"]),
    ("U10", "https://github.com/pallets/jinja",
     "Which license is this repository under, and which language makes up the largest share "
     "of its code?", [["bsd"], ["python"]]),
    ("U11", "https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Status/429",
     "What is the name of this HTTP status code?", [["too many requests"]]),
    ("U12", "https://www.rfc-editor.org/rfc/rfc9113.html",
     "What is the title of section 6.5?", [["settings"]]),
]  # fmt: skip
NEW_TASKS = [
    ("N1", "https://github.com/pallets/flask",
     "Which license is this repository under, and which language makes up the largest share "
     "of its code?", [["bsd"], ["python"]]),
    ("N2", "https://en.wikipedia.org/wiki/Eiffel_Tower",
     "What height to the tip, in metres, does the infobox give?", ["330"]),
    ("N3", "https://docs.python.org/3/library/json.html",
     "According to this page, what is the default value of the indent parameter of "
     "json.dumps()?", [["none"]]),
    ("N4", "https://quotes.toscrape.com/",
     "Who is the author of the first quote on the page?", ["einstein"]),
    ("N5", "https://books.toscrape.com/catalogue/category/books/poetry_23/index.html",
     "What is the title of the first book listed in this category?", ["a light in the attic"]),
    ("N6", "https://en.wikipedia.org/wiki/Guido_van_Rossum",
     "According to the infobox, in which year and in which city was he born?",
     ["1956", ["hague"]]),
]  # fmt: skip


phase = base.phase


def main() -> int:
    global PREREG, SESSIONS
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--pilot", action="store_true", help="M1 and M2 once per arm (run 0), excluded")
    ap.add_argument("--fixed", action="store_true", help="Phase 3c (prereg-e2e-mcp-fixed.md)")
    ap.add_argument("--new", action="store_true", help="Phase 3d (prereg-e2e-mcp-new.md)")
    ap.add_argument(
        "--warmup",
        action="store_true",
        help="one uncounted PLAIN session first (run -9, -10 on a resume), to warm the cache",
    )
    ap.add_argument("--wide", action="store_true", help="Phase 3f (prereg-e2e-wide.md)")
    ap.add_argument("--x", action="store_true", help="Phase 3h (prereg-e2e-x.md)")
    ap.add_argument("--y", action="store_true", help="Phase 3j (prereg-e2e-y.md)")
    ap.add_argument("--z", action="store_true", help="Phase 3l (prereg-e2e-z.md)")
    ap.add_argument("--u", action="store_true", help="Phase 3n (prereg-e2e-u.md)")
    args = ap.parse_args()
    report_name, tasks, n_runs = "e2e-mcp.json", TASKS, RUNS
    if args.fixed:
        PREREG, SESSIONS, report_name = FIXED["prereg"], FIXED["sessions"], FIXED["report"]
    if args.new:
        PREREG, SESSIONS, report_name = NEW["prereg"], NEW["sessions"], NEW["report"]
        tasks = NEW_TASKS
    if args.wide:
        PREREG, SESSIONS, report_name = WIDE["prereg"], WIDE["sessions"], WIDE["report"]
        tasks, n_runs = WIDE_TASKS, WIDE_RUNS
    if args.x:
        PREREG, SESSIONS, report_name = X["prereg"], X["sessions"], X["report"]
        tasks, n_runs = X_TASKS, WIDE_RUNS
    if args.y:
        PREREG, SESSIONS, report_name = Y["prereg"], Y["sessions"], Y["report"]
        tasks, n_runs = Y_TASKS, WIDE_RUNS
    if args.z:
        PREREG, SESSIONS, report_name = Z["prereg"], Z["sessions"], Z["report"]
        tasks, n_runs = Z_TASKS, WIDE_RUNS
    if args.u:
        PREREG, SESSIONS, report_name = U["prereg"], U["sessions"], U["report"]
        tasks, n_runs = U_TASKS, WIDE_RUNS
    if args.record_hash:
        registered = PREREG.with_suffix(".sha256")
        if registered.exists() and registered.read_text().strip() != base.digest(PREREG):
            raise SystemExit(f"{registered.name} holds a different hash: nothing written")
        registered.write_text(base.digest(PREREG) + "\n", encoding="utf-8")
        print(PREREG.name, base.digest(PREREG))
        return 0
    rows = done_sessions()
    if args.live:
        if not args.pilot:
            require_prereg()
        key = key_from(args.env_file)
        if not key:
            raise SystemExit("LEAN ranks with Jev: no TYPESAFE_API_KEY, nothing spent")
        runs = [0] if args.pilot else list(range(1, n_runs + 1))
        guarded = any((args.fixed, args.new, args.wide, args.x, args.y, args.z, args.u))
        limits = phase.Limits(
            session_max_usd=SESSION_MAX_USD, ceiling_usd=CEILING_USD,
            jev_session_max_usd=JEV_SESSION_MAX_USD,
            jev_ceiling_usd=(JEV_CEILING_Y_USD if args.y or args.z or args.u else JEV_CEILING_USD)
            if guarded else None,
        )  # fmt: skip
        code, rows = phase.run_phase(
            phase.planned(tasks[:2] if args.pilot else tasks, runs, ("PLAIN", "LEAN")), rows,
            limits, lambda task, run, arm: one_session(task, run, arm, key), SESSIONS,
            warmup_task=tasks[0] if args.warmup else None,
        )  # fmt: skip
        if code:
            return code
    report = base.analyze(phase.counted(rows))
    report["pilot"] = [
        {k: r[k] for k in ("task", "arm", "success", "list_usd", "turns", "tools", "pruned")}
        for r in rows
        if r["run"] <= 0
    ]
    (RESULTS / report_name).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
