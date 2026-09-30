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


def main() -> int:
    global PREREG, SESSIONS
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--pilot", action="store_true", help="M1 and M2 once per arm (run 0), excluded")
    ap.add_argument("--fixed", action="store_true", help="Phase 3c (prereg-e2e-mcp-fixed.md)")
    ap.add_argument("--new", action="store_true", help="Phase 3d (prereg-e2e-mcp-new.md)")
    args = ap.parse_args()
    report_name, tasks = "e2e-mcp.json", TASKS
    if args.fixed:
        PREREG, SESSIONS, report_name = FIXED["prereg"], FIXED["sessions"], FIXED["report"]
    if args.new:
        PREREG, SESSIONS, report_name = NEW["prereg"], NEW["sessions"], NEW["report"]
        tasks = NEW_TASKS
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
        seen = {(r["task"], r["run"], r["arm"]) for r in rows}
        runs = [0] if args.pilot else list(range(1, RUNS + 1))
        for task in tasks[:2] if args.pilot else tasks:
            for run in runs:
                for arm in ("PLAIN", "LEAN"):
                    if (task[0], run, arm) in seen:
                        continue
                    spent = sum(r["list_usd"] for r in rows)
                    if spent + SESSION_MAX_USD > CEILING_USD:
                        print(f"ceiling: {spent:.2f} USD spent", file=sys.stderr)
                        return 1
                    jev = sum(r["jev_usd"] for r in rows)
                    if (args.fixed or args.new) and jev + JEV_SESSION_MAX_USD > JEV_CEILING_USD:
                        print(f"Jev ceiling: {jev:.4f} USD spent", file=sys.stderr)
                        return 1
                    row = one_session(task, run, arm, key)
                    rows.append(row)
                    with SESSIONS.open("a", encoding="utf-8") as sink:
                        sink.write(json.dumps(row, ensure_ascii=False) + "\n")
                    print(json.dumps({k: row[k] for k in ("task", "run", "arm", "success",
                          "list_usd", "turns", "tools")}), file=sys.stderr)  # fmt: skip
    report = base.analyze([r for r in rows if r["run"] > 0])
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
