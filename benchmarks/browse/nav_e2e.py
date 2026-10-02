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
TRAP_SESSIONS = RESULTS / "nav-traps-sessions.jsonl"
LOOP_SESSIONS = RESULTS / "nav-loop-sessions.jsonl"
MODELS = {
    "SONNET": "claude-sonnet-5",
    "HAIKU": "claude-haiku-4-5",
    "HAIKU-LOOP": "claude-haiku-4-5",  # the same model, with the loop guard hooked in
}
ARMS = ("SONNET", "HAIKU")
TRAP_ARMS = ("HAIKU", "HAIKU-LOOP")  # the trap tasks: does the loop guard save the floundering?
JEV_SESSION_MAX_USD = 0.05
JEV_CEILING_USD = 0.40  # for a whole loop phase, over the Jev budget this line was given
KEY = ""  # set in main() from --env-file; the -LOOP arm refuses to run without it
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
# Tasks with a deterministic trap, for measuring loop supervision: a cheap check only pays where
# a session goes wrong. saucedemo ships accounts built to misbehave, so the same fault happens
# every run. Both walked by hand on 2026-10-02.
#   B1: as `problem_user`, typing into Last Name writes into First Name instead. There is no way
#       to fill it from the keyboard, so the agent either reports the fault or loops on it.
#   B2: as `error_user`, Remove on the inventory page does nothing (the cart keeps the item);
#       Remove on the cart page works. An agent that believes the first one reports the totals
#       for two items (39.98 / 3.20 / 43.18) instead of one. That is a wrong answer, not a
#       wasted turn, which is what makes it worth measuring.
TRAP_TASKS: list[tuple[str, str, str, list[Any]]] = [
    (
        "B1",
        "https://www.saucedemo.com/",
        "Log in as problem_user with the password secret_sauce, put the Sauce Labs Backpack in the "
        "cart and start the checkout. Report exactly what happens when you try to enter the last "
        "name Lovelace in the checkout form, and which field the value ends up in.",
        [["first name", "firstname", "first-name"]],
    ),
    (
        "B2",
        "https://www.saucedemo.com/",
        "Log in as error_user with the password secret_sauce, put the Sauce Labs Backpack and the "
        "Sauce Labs Bike Light in the cart, then remove the Backpack so that only the Bike Light "
        "is left, go through the checkout as Ada Lovelace with postal code 28001 and report the "
        "item total, the tax and the total on the overview page.",
        ["9.99", "0.80", "10.79"],
    ),
]
TRAP_WRONG_B2 = ["39.98", "3.20", "43.18"]  # what an agent reports if the removal silently failed

# Aggregation over many pages: a count or a sum, where an agent fails by stopping early, counting
# a page twice or misreading one price in thirty. Every answer was computed from the sites' own
# HTML by `truth_hard.py` on 2026-10-02, not by a model. The request ends with an ANSWER line and
# `grade` reads only that line, numbers as whole numbers, so "page 10" elsewhere in a reply
# cannot pass for the count.
ANSWER_LINE = " End your reply with one line: ANSWER: <your answer>."
HARD_TASKS: list[tuple[str, str, str, list[Any]]] = [
    (
        "H1",
        "https://quotes.toscrape.com/",
        "How many quotes by Albert Einstein are there on this site, across all of its pages?"
        + ANSWER_LINE,
        ["10"],
    ),
    (
        "H2",
        "https://books.toscrape.com/",
        "In the Mystery category, across all of its pages, how many books cost more than "
        "40.00 (the price shown, in pounds)?" + ANSWER_LINE,
        ["11"],
    ),
    (
        "H3",
        "https://quotes.toscrape.com/",
        "How many quotes on this site are tagged 'inspirational', counting every page of that "
        "tag, and which author has the most of them?" + ANSWER_LINE,
        ["13", "monroe"],
    ),
    (
        "H4",
        "https://books.toscrape.com/",
        "What do the prices of all the books in the Travel category add up to?" + ANSWER_LINE,
        ["437.74"],
    ),
    (
        "H5",
        "https://books.toscrape.com/",
        "Which book in the Poetry category is the cheapest, and what does it cost?" + ANSWER_LINE,
        ["poems that make grown women cry", "14.19"],
    ),
]

PILOT_TASKS = [TASKS[0], TASKS[3]]


VENV_PYTHON = base.ROOT / ".venv" / "Scripts" / "python.exe"
# The interpreter the hook runs under: the project's own environment, the one the suite passes
# in, rather than whatever Python launched the runner.
HOOK_PYTHON = VENV_PYTHON if VENV_PYTHON.exists() else base.PYTHON
HOOK_TIMEOUT_S = 30  # Jev's client gives up at 10 s; a hook killed by Claude Code leaves no trace
HOOK_NEEDS = ("facts_seen", "error_note", "_journal_failure")  # the version this phase measures


def preflight() -> list[str]:
    """Probe, before anything is spent, that the hook every `-LOOP` session will load is the one
    this phase means to measure, that it starts, and that it answers an event the way it should.

    A flag says what was meant; a probe says what will run. Today's two faults were of that kind:
    a session whose hook never ran, and a phase that ran the version from before the fix."""
    problems: list[str] = []
    probe = (
        "import json, sanchopanza.harness.loop_hook as h; "
        f"print(json.dumps({{'file': h.__file__, 'has': [n for n in {list(HOOK_NEEDS)!r} "
        "if hasattr(h, n)]}))"
    )
    try:
        done = subprocess.run([str(HOOK_PYTHON), "-c", probe], capture_output=True, timeout=60)
        seen = json.loads(done.stdout.decode("utf-8", errors="replace") or "{}")
    except (subprocess.TimeoutExpired, ValueError, OSError) as error:
        return [f"the hook's interpreter could not import it: {error.__class__.__name__}"]
    missing = [n for n in HOOK_NEEDS if n not in seen.get("has", [])]
    if missing:
        problems.append(f"the hook at {seen.get('file')} is not this version: lacks {missing}")
    event = {"hook_event_name": "PostToolUse", "tool_name": "mcp__playwright__browser_click",
             "transcript_path": "does-not-exist.jsonl", "session_id": "preflight"}  # fmt: skip
    with tempfile.TemporaryDirectory() as home:
        env = {**base.clean_env(dict(os.environ)), "SANCHOPANZA_LOOP_HOME": home,
               "SANCHOPANZA_JOURNAL": str(pathlib.Path(home) / "j.jsonl")}  # fmt: skip
        env.pop("TYPESAFE_API_KEY", None)
        try:
            ran = subprocess.run(
                [str(HOOK_PYTHON), "-m", "sanchopanza.harness.loop_hook"],
                input=json.dumps(event).encode(), env=env, capture_output=True, timeout=60,
            )  # fmt: skip
        except (subprocess.TimeoutExpired, OSError) as error:
            return [*problems, f"the hook did not run: {error.__class__.__name__}"]
    if ran.returncode != 0 or ran.stdout.strip():
        problems.append(
            f"the hook on an event with no transcript should exit 0 and say nothing; it exited "
            f"{ran.returncode} with {ran.stdout[:120]!r}"
        )
    if not KEY:
        problems.append("no TYPESAFE_API_KEY for the -LOOP arm (--env-file)")
    return problems


def settings_for(arm: str, work: pathlib.Path) -> pathlib.Path:
    """No hook except in the `-LOOP` arm, which gets the loop guard and nothing else: this
    phase compares models, and then one model with and without that one hook."""
    settings: dict[str, Any] = {"permissions": {"allow": TOOLS.split()}}
    if arm.endswith("-LOOP"):
        command = f'"{HOOK_PYTHON.as_posix()}" -m sanchopanza.harness.loop_hook'
        settings["hooks"] = {
            "PostToolUse": [
                {"matcher": "mcp__playwright__.*|Read|Grep",
                 "hooks": [{"type": "command", "command": command, "timeout": HOOK_TIMEOUT_S}]}
            ]
        }  # fmt: skip
    path = work / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def one_session(task: tuple, run: int, arm: str) -> dict[str, Any]:
    tid, url, question, required = task
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-nav-{tid.lower()}r{run}{arm.lower()}-"))
    env = base.clean_env(dict(os.environ))
    journal = work / "journal.jsonl"
    if arm.endswith("-LOOP"):
        env["SANCHOPANZA_JOURNAL"] = str(journal)
        env["SANCHOPANZA_LOOP_HOME"] = str(work / "loop")
        env["SANCHOPANZA_SESSION_MAX_USD"] = f"{JEV_SESSION_MAX_USD:g}"
        if not KEY:
            raise SystemExit("the -LOOP arm needs TYPESAFE_API_KEY (--env-file): nothing spent")
        env["TYPESAFE_API_KEY"] = KEY
    else:
        env.pop("TYPESAFE_API_KEY", None)  # an arm with no hook decides nothing
    argv = [
        shutil.which("claude") or "claude", "-p", "--model", MODELS[arm],
        "--append-system-prompt", APPEND,
        "--settings", str(settings_for(arm, work)), "--setting-sources", "",
        "--mcp-config", str(mcp.mcp_config(work)), "--strict-mcp-config",
        "--allowedTools", TOOLS, "--disallowedTools", "WebFetch WebSearch Bash",
        "--output-format", "json", "--max-budget-usd", f"{SESSION_MAX_USD:g}",
        "--", f"Open {url} in the browser. {question}",
    ]  # fmt: skip
    try:
        done = subprocess.run(argv, cwd=work, env=env, capture_output=True, timeout=TIMEOUT_S)
        out = json.loads(done.stdout.decode("utf-8", errors="replace") or "{}")
        # The hook writes its reasons to stderr and the runner used to throw them away, which
        # left a session whose hook never ran (B2 run 2, 2026-10-02) with nothing to read.
        (work / "stderr.txt").write_bytes(done.stderr)
    except (subprocess.TimeoutExpired, ValueError) as error:
        out = {"is_error": True, "subtype": f"runner: {error.__class__.__name__}"}
    usage = out.get("usage") or {}
    answer = str(out.get("result") or "")
    row = {
        "task": tid, "run": run, "arm": arm, "model": MODELS[arm],
        "ok": not out.get("is_error", True), "subtype": out.get("subtype"),
        "success": grade(answer, required, tid), "answer": answer[:ANSWER_KEPT],
        "list_usd": float(out.get("total_cost_usd") or 0.0),
        "turns": out.get("num_turns"),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        **dict(zip(("jev_usd", "jev_calls"), base.journal_usd(journal), strict=True)),
        "tools": mcp.tool_calls(work), "version": claude_version(work),
        "workdir": str(work),
    }  # fmt: skip
    if not arm.endswith("-LOOP"):
        return row
    hook = hook_record(journal)
    row = {**row, **hook}
    # A `-LOOP` session whose hook never asked is not a `-LOOP` session. One of the six run on
    # 2026-10-02 had no journal at all with twenty tool calls in it, and the runner counted it
    # as treated. A treatment that is not exercised is not a treatment: it is marked here, and
    # `counted()` drops it, so a resume runs it again. Which way it failed is kept.
    if not hook["hook_decisions"]:
        why = "the decider failed on every call" if hook["hook_errors"] else "hook absent"
        return {**row, "not_run": True, "subtype": f"the hook never decided: {why}"}
    return row


def hook_record(journal: pathlib.Path) -> dict[str, int]:
    """What the loop guard did in one session, from its own journal: how often it asked, how
    often it spoke, how often it had no page in front of it, its error notes and its failures.
    A guard that is silent and a guard that is blind are different findings."""
    out = {"hook_decisions": 0, "hook_spoke": 0, "hook_blind": 0, "hook_error_notes": 0,
           "hook_errors": 0}  # fmt: skip
    if not journal.exists():
        return out
    for line in journal.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind, data = event.get("kind"), event.get("data") or {}
        if kind == "decision" and data.get("point") == "loop":
            outcome = data.get("outcome") or {}
            out["hook_decisions"] += 1
            out["hook_spoke"] += int(bool(outcome.get("spoke")))
            out["hook_blind"] += int(not outcome.get("page_chars"))
        elif kind == "loop_note":
            out["hook_error_notes"] += 1
        elif kind == "loop_error":
            out["hook_errors"] += 1
    return out


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


ANSWER_KEPT = 4000  # was 800, and an aggregation task puts its ANSWER line last
_ANSWER = re.compile(r"answer\s*:\s*(.*)", re.I)
_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")


def answer_line(answer: str) -> str:
    """The text after the last `ANSWER:` in a reply, or "" when there is none."""
    found = [m.group(1) for m in _ANSWER.finditer(answer or "")]
    return found[-1].strip().strip("*").strip() if found else ""


def grade(answer: str, required: list[Any], tid: str) -> bool:
    """Every required item present. For the aggregation tasks (H*) only the ANSWER line counts,
    and a number counts as a whole number: "10" is met by "There are 10 quotes" and not by
    "page 10 of 100" elsewhere in the reply, nor by "100" in the line.

    The first version required the literal "answer: 10", and graded "ANSWER: There are 10
    quotes by Albert Einstein" - which is right - as a failure (H1, Sonnet, 2026-10-02)."""
    if not tid.startswith("H"):
        return base.graded(answer, required)
    line = base.normal(answer_line(answer))
    if not line:
        return False

    def met(alternative: str) -> bool:
        wanted = base.normal(alternative)
        if _NUMBER.match(wanted):
            return re.search(rf"(?<![\d.]){re.escape(wanted)}(?![\d]|\.\d)", line) is not None
        return wanted in line

    return all(
        any(met(alt) for alt in (item if isinstance(item, list) else [item])) for item in required
    )


def final_answer(workdir: str) -> str:
    """The session's last assistant text, whole, from Claude Code's own transcript: the row
    kept only 800 characters before 2026-10-02, and an ANSWER line comes last."""
    from sanchopanza.context.transcript import message_text, messages_from_claude_code

    slug = re.sub(r"[^A-Za-z0-9]", "-", workdir)
    folder = pathlib.Path.home() / ".claude" / "projects" / slug
    for path in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        texts = [message_text(m) for m in messages_from_claude_code(str(path))
                 if m.get("role") == "assistant" and message_text(m).strip()]  # fmt: skip
        if texts:
            return texts[-1]
    return ""


def regrade(sessions: pathlib.Path, name: str) -> int:
    """Grade every recorded session again with `grade`, from its whole final answer, and say
    which verdicts changed. The first grade is kept beside the new one, never overwritten."""
    required = {t[0]: t[3] for t in TASKS + TRAP_TASKS + HARD_TASKS}
    rows = done_sessions(sessions)
    out, changed = [], []
    for row in rows:
        whole = final_answer(row.get("workdir", "")) or row.get("answer", "")
        verdict = grade(whole, required[row["task"]], row["task"])
        if verdict != row.get("success"):
            changed.append(f"{row['task']} {row['arm']} run{row['run']}: "
                           f"{row.get('success')} -> {verdict}")  # fmt: skip
        first = row.get("success_first_grade", row.get("success"))
        out.append({**row, "success_first_grade": first, "success": verdict,
                    "answer": whole[:ANSWER_KEPT], "regraded": True})  # fmt: skip
    sessions.write_text("".join(json.dumps(r) + "\n" for r in out), encoding="utf-8")
    report = analyse(phase.counted(out))
    report["regraded"] = changed
    (RESULTS / name).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


def done_sessions(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def analyse(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {"sessions": len(rows), "by_arm": {}}
    for arm in MODELS:
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
            "mean_turns": round(sum(r["turns"] or 0 for r in ok) / len(ok), 2) if ok else None,
        }
        if arm.endswith("-LOOP"):  # what the guard did: silent, blind and wrong are different
            out["by_arm"][arm]["hook"] = {
                key: sum(int(r.get(key) or 0) for r in part)
                for key in ("hook_decisions", "hook_spoke", "hook_blind", "hook_error_notes",
                            "hook_errors")
            }  # fmt: skip

    def for_task(tid: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for arm in MODELS:
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
    ap.add_argument("--traps", action="store_true", help="the trap tasks, mining for failures")
    ap.add_argument("--loop", action="store_true", help="arms HAIKU and HAIKU-LOOP")
    ap.add_argument("--hard", action="store_true", help="the aggregation tasks")
    ap.add_argument("--only", default="", help="comma-separated task ids, from any set")
    ap.add_argument("--runs", type=int, default=0, help="runs per task and arm")
    ap.add_argument("--tag", default="", help="a development round with its own files")
    ap.add_argument("--ceiling", type=float, default=0.0, help="list USD for this round")
    ap.add_argument(
        "--regrade", action="store_true", help="grade a --tag round again from whole answers"
    )
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--env-file", default=None, help="a .env holding TYPESAFE_API_KEY")
    ap.add_argument("--record-hash", action="store_true")
    args = ap.parse_args()

    if args.tasks:
        for tid, url, question, required in TASKS + TRAP_TASKS + HARD_TASKS:
            print(f"{tid}  {url}\n    {question}\n    required: {required}\n")
        return 0
    if args.record_hash:
        PREREG.with_suffix(".sha256").write_text(base.digest(PREREG) + "\n", encoding="utf-8")
        print(f"registered {PREREG.name}: {base.digest(PREREG)}")
        return 0

    global KEY
    KEY = mcp.key_from(args.env_file)  # e2e_mcp's reader, not a second copy of it
    tasks = HARD_TASKS if args.hard else (
        TRAP_TASKS if args.traps else (PILOT_TASKS if args.pilot else TASKS)
    )  # fmt: skip
    if args.only:
        wanted = {t.strip().upper() for t in args.only.split(",")}
        pool = {t[0]: t for t in TASKS + TRAP_TASKS + HARD_TASKS}
        unknown = sorted(wanted - set(pool))
        if unknown:
            raise SystemExit(f"no such task: {unknown}")
        tasks = [pool[t] for t in sorted(wanted)]
    arms = TRAP_ARMS if args.loop else ARMS
    one_run = (args.pilot or args.traps or args.hard) and not args.loop
    runs = list(range(1, (args.runs or (1 if one_run else RUNS)) + 1))
    if args.tag:  # a development round of its own, with its own files
        sessions = RESULTS / f"nav-{args.tag}-sessions.jsonl"
        name = f"nav-{args.tag}.json"
    else:
        sessions = (
            LOOP_SESSIONS
            if args.loop
            else (TRAP_SESSIONS if args.traps else (PILOT_SESSIONS if args.pilot else SESSIONS))
        )
        name = (
            "nav-loop.json"
            if args.loop
            else (
                "nav-traps.json" if args.traps else ("nav-pilot.json" if args.pilot else "nav.json")
            )
        )
    if args.regrade:
        if not args.tag or args.live:
            raise SystemExit("--regrade takes a --tag and spends nothing: drop --live")
        return regrade(sessions, name)
    development = args.pilot or args.traps or args.hard or bool(args.tag)
    ceiling = args.ceiling or (PILOT_CEILING_USD if development else CEILING_USD)
    rows = done_sessions(sessions)
    code = 0
    if args.live:
        if not development:
            registered = PREREG.with_suffix(".sha256")
            if not registered.exists() or registered.read_text().strip() != base.digest(PREREG):
                raise SystemExit(f"{PREREG.name} is not registered as it stands: nothing spent")
        if any(a.endswith("-LOOP") for a in arms):
            problems = preflight()
            if problems:
                raise SystemExit("preflight failed, nothing spent:\n- " + "\n- ".join(problems))
            print(f"preflight: hook {HOOK_PYTHON.name} ok", file=sys.stderr)
        RESULTS.mkdir(parents=True, exist_ok=True)
        limits = phase.Limits(
            session_max_usd=SESSION_MAX_USD, ceiling_usd=ceiling,
            jev_session_max_usd=JEV_SESSION_MAX_USD,
            jev_ceiling_usd=JEV_CEILING_USD if args.loop else None,
        )  # fmt: skip
        plan = phase.planned(tasks, runs, arms)
        code, rows = phase.run_phase(plan, rows, limits, one_session, sessions)
    if not rows:
        print("nothing recorded yet")
        return code
    report = analyse(phase.counted(rows))
    report["not_run"] = [
        {k: r.get(k) for k in ("task", "run", "arm", "subtype")} for r in rows if r.get("not_run")
    ]
    (RESULTS / name).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
