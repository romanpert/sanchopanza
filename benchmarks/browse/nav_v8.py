"""Browse, v8 in development: confirmation 4's arms on the tasks where v7 missed or cost more,
with v8's three switches (`harness.crawl_hook`, commit 9901cdb) in two new arms.

python benchmarks/browse/nav_v8.py --preflight
python benchmarks/browse/nav_v8.py --smoke             # HAIKU-V8 on G6 and I2, its own file
python benchmarks/browse/nav_v8.py --live              # the development round
python benchmarks/browse/nav_v8.py                     # free: the tables so far

Confirmation 4 (README 2026-10-03, its section) failed Haiku on the interactive tasks' cost and
Sonnet on the JSON APIs' price. v8 cuts the wrapper Playwright MCP echoes (`ECHO=short`), adds
the click and JSON-row notes (`NOTES=2`) and gives the line only to gathering prompts
(`LINE_AT=prompt`).
The tasks are confirmation 4's own, so this is development, not a confirmation: G3, G6 and I2
(the misses and the cost), G4 and G8 (the APIs where Sonnet with v7 cost more) and G1 (no
regression). Everything but the arms, the tasks and the files is `nav_confirm4.py`'s: its
settings, grading, Claude Code pin and hang rule, loaded here as a copy.
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


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


conf4 = _load("browse_nav_confirm4_for_v8", HERE / "nav_confirm4.py")
conf3 = conf4.conf3
nav = conf4.nav

RESULTS = conf4.RESULTS
SESSIONS = RESULTS / "nav-v8-sessions.jsonl"
SMOKE_SESSIONS = RESULTS / "nav-v8-smoke-sessions.jsonl"
REPORT = RESULTS / "nav-v8.json"
TASK_IDS = ("G3", "G6", "I2", "G4", "G8", "G1")
TASKS = [next(t for t in conf4.TASKS if t[0] == tid) for tid in TASK_IDS]
SMOKE = (("G6", "HAIKU-V8"), ("I2", "HAIKU-V8"))
RUNS = 2
CEILING_USD = 12.00  # list price, smoke included; about 6 expected from confirmation 4's means
SMOKE_CEILING_USD = 1.50
V7_ENV = dict(conf4.SP_ENV)  # confirmation 4's -SP arms
V8_ENV = {
    "SANCHOPANZA_CRAWL_LINE_VERSION": "6",
    "SANCHOPANZA_CRAWL_NOTES": "2",
    "SANCHOPANZA_CRAWL_ECHO": "short",
    "SANCHOPANZA_CRAWL_LINE_AT": "prompt",
}
TREATED = {"HAIKU-V7": V7_ENV, "HAIKU-V8": V8_ENV, "SONNET-V8": V8_ENV}
ARMS = ("HAIKU", "HAIKU-V7", "HAIKU-V8", "SONNET", "SONNET-V8")
MODELS = {"HAIKU": "claude-haiku-4-5", "SONNET": "claude-sonnet-5"}

LINE_SEEN = conf4.LINE_SEEN  # only line v6 holds it
NOTES_SEEN = conf4.NOTES_SEEN  # the wrapper's own mark, in the hook's recorded answer
GUARD_STOP = conf4.GUARD_STOP
# The wrapper as Playwright MCP echoes it, and the line the echo cut puts in its place.
ECHOED = "await page.evaluate('/* sanchopanza evaluate guard */"
ECHO_CUT = "your function, inside sanchopanza's evaluate guard (not repeated)"
# v8's two notes, as the wrapper writes them into a result (numbers, so never the code itself).
CLICK_NOTE = re.compile(r"\d+ clicks did not change the page text")
ROWS_NOTE = re.compile(r"fetched JSON rows \d+, distinct \d+")
# The subscription refusing a session: an API 429 or a usage limit, in the reply or on stderr.
LIMIT = re.compile(r"\b429\b|weekly limit|hit your (?:\w+ )?limit|rate.?limit", re.I)
STOP_LIMIT = "STOP-LIMIT"


def model_of(arm: str) -> str:
    return MODELS[arm.split("-")[0]]


def settings_for(arm: str, work: pathlib.Path) -> pathlib.Path:
    """Plain arms: the bench's permissions and no hook. V7: what `install --crawl` writes and
    confirmation 4's env. V8: the same, plus the two events `crawl_hook.V8_HOOKS` names (with the
    same command), and v8's env. Only in the session's own `--settings`."""
    from sanchopanza.harness.crawl_hook import V8_HOOKS
    from sanchopanza.harness.install import CRAWL_COMMAND, _merge_crawl, _merge_owned

    settings: dict[str, Any] = {"permissions": {"allow": nav.TOOLS.split()}}
    if arm in TREATED:
        command = conf3.crawl_command()
        settings, _added, _removed = _merge_crawl(settings, True, command=command)
        if arm.endswith("-V8"):
            settings, _added, _removed = _merge_owned(
                settings, True, V8_HOOKS, command, CRAWL_COMMAND, "crawl"
            )
        settings = {**settings, "env": dict(TREATED[arm])}
    path = work / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def _stderr(workdir: str) -> str:
    path = pathlib.Path(workdir or ".") / "stderr.txt"
    try:
        return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""
    except OSError:
        return ""


def limit_hit(row: dict[str, Any]) -> bool:
    """A 429 or a usage limit: in a failed session's reply or stderr, or 'limit' wording in any
    reply. A count of 429 in a right answer is not one (the ANSWER line of a finished session)."""
    answer = str(row.get("answer") or "")
    if row.get("limit_hit"):
        return True
    if not row.get("ok"):
        said = f"{answer}\n{row.get('subtype') or ''}\n{_stderr(row['workdir'])}"
        return bool(LIMIT.search(said))
    return bool(re.search(r"weekly limit|hit your (?:\w+ )?limit", answer, re.I))


def guardable_evaluates(text: str, counted: int) -> int:
    """The evaluate calls the guard can wrap: those whose input has a `function`. I2 run 1 of
    HAIKU-V8 sent `{"code": ...}`; Playwright MCP refused it, and the guard rightly left it alone,
    so no wrapper was there to see. With no evaluate call readable in `text` (a test's plain
    string), the tool count stands."""
    found = guardable = 0
    for line in text.splitlines():
        try:
            content = (json.loads(line).get("message") or {}).get("content")
        except (ValueError, AttributeError):
            continue
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if str(block.get("name") or "").endswith("__browser_evaluate"):
                found += 1
                guardable += bool(str((block.get("input") or {}).get("function") or "").strip())
    return guardable if found else counted


def treatment(row: dict[str, Any], text: str, arm: str, gathering: bool) -> str | None:
    """Why a session did not get exactly its arm's treatment, or None when it did."""
    counted = int((row.get("tools") or {}).get("mcp__playwright__browser_evaluate") or 0)
    evaluated = bool(guardable_evaluates(text, counted))
    if arm not in TREATED:
        if row["line_seen"] or row["notes_seen"] or row["echo_cut"]:
            return "a plain session saw the treatment"
        return None
    if arm.endswith("-V7"):
        if not row["line_seen"] or (evaluated and not row["notes_seen"]):
            return "the crawl hooks never ran as registered"
        return None
    if gathering and not row["line_seen"]:
        return "v8: no line on a gathering prompt"
    if not gathering and row["line_seen"]:
        return "v8: the line on an acting prompt"
    if row["echoed_wrappers"]:
        return "v8: the wrapper echoed uncut"
    if evaluated and not row["notes_seen"]:
        return "v8: an evaluate without the guard"
    return None


def one_session(task: tuple, run: int, arm: str) -> dict[str, Any]:
    """nav's session, timed, with v8's treatment checked in the transcript: the line on gathering
    prompts only, no wrapper echoed, and the v8 notes counted where they fired."""
    started = time.monotonic()
    row = nav.one_session(task, run, arm)
    text = conf3._transcript(row["workdir"])
    row = {**row, "wall_s": round(time.monotonic() - started, 1),
           "line_seen": LINE_SEEN in text, "notes_seen": NOTES_SEEN in text,
           "guard_stops": text.count(GUARD_STOP), "echoed_wrappers": text.count(ECHOED),
           "echo_cut": text.count(ECHO_CUT), "click_notes": len(CLICK_NOTE.findall(text)),
           "rows_notes": len(ROWS_NOTE.findall(text))}  # fmt: skip
    if limit_hit(row):
        return {**row, "limit_hit": True, "not_run": True, "subtype": "usage limit or 429"}
    if not row.get("ok"):
        return row
    why = treatment(row, text, arm, task[0].startswith("G"))
    return {**row, "not_run": True, "subtype": why} if why else row


def _usage_limited(original: Any) -> Any:
    def check(row: dict[str, Any]) -> bool:
        return bool(row.get("limit_hit")) or original(row)

    return check


def preflight() -> list[str]:
    """Confirmation 4's checks (pinned Claude Code; line v6 at SessionStart and the notes with
    its env), and with v8's env: no line at SessionStart, the line on a gathering prompt and none
    on an acting one, the v2 notes in the wrapper, and the echo cut on a result."""
    from sanchopanza.harness.crawl_hook import ECHO_LINE, MARK, STRATEGY_LINE_V6

    problems = conf4.preflight()
    command = [str(nav.HOOK_PYTHON), "-m", "sanchopanza", "crawl-hook"]
    env = {**nav.base.clean_env(dict(os.environ)), "PYTHONPATH": str(conf3.SRC), **V8_ENV}
    gather, act = (f"Open {t[1]} in the browser. {t[2]}" for t in (TASKS[1], TASKS[2]))
    echoed = f"### Result\n1\n### Ran Playwright code\n```js\nawait page.evaluate('{MARK} x');\n```"
    for event, check in (
        ({"hook_event_name": "SessionStart", "source": "startup"}, lambda out: out is None),
        ({"hook_event_name": "UserPromptSubmit", "prompt": gather},
         lambda out: out["hookSpecificOutput"]["additionalContext"] == STRATEGY_LINE_V6),
        ({"hook_event_name": "UserPromptSubmit", "prompt": act}, lambda out: out is None),
        ({"hook_event_name": "PreToolUse", "tool_name": "mcp__playwright__browser_evaluate",
          "tool_input": {"function": "() => 1"}},
         lambda out: "clicks did not change"
         in out["hookSpecificOutput"]["updatedInput"]["function"]),
        ({"hook_event_name": "PostToolUse", "tool_name": "mcp__playwright__browser_evaluate",
          "tool_response": [{"type": "text", "text": echoed}]},
         lambda out: ECHO_LINE in out["hookSpecificOutput"]["updatedToolOutput"][0]["text"]),
    ):  # fmt: skip
        try:
            done = subprocess.run(command, input=json.dumps(event).encode(), env=env,
                                  capture_output=True, timeout=60)  # fmt: skip
            out = json.loads(done.stdout) if done.stdout.strip() else None
            if not check(out):
                problems.append(f"v8 {event['hook_event_name']}: unexpected {done.stdout[:120]!r}")
        except (subprocess.TimeoutExpired, ValueError, KeyError, TypeError, OSError) as error:
            problems.append(f"v8 {event['hook_event_name']}: {error.__class__.__name__}: {error}")
    return problems


def install() -> None:
    """Confirmation 4's procedure, pointed at this round's arms, settings and limit check."""
    conf4.install()
    nav.MODELS.update({arm: model_of(arm) for arm in ARMS})
    nav.settings_for = settings_for
    nav.phase.usage_limited = _usage_limited(nav.phase.usage_limited)


def _cell(rows: list[dict[str, Any]], tid: str, arm: str) -> list[dict[str, Any]]:
    return [r for r in rows if r["task"] == tid and r["arm"] == arm]


def _mean(rows: list[dict[str, Any]]) -> float:
    return statistics.mean(r["list_usd"] for r in rows) if rows else 0.0


def analyse(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Right answers and mean cost per arm and task, the two ratios v8 is for, and what the
    hooks did (line, echo cuts, v8 notes, guard stops)."""
    tasks = {
        tid: {arm: {"right": f"{sum(bool(r['success']) for r in c)}/{len(c)}",
                    "mean_usd": round(_mean(c), 4), "turns": [r.get("turns") for r in c]}
              for arm in ARMS if (c := _cell(rows, tid, arm))}
        for tid in TASK_IDS
    }  # fmt: skip
    arms = {}
    for arm in ARMS:
        part = [r for r in rows if r["arm"] == arm]
        if part:
            arms[arm] = {
                "sessions": len(part), "right": sum(bool(r["success"]) for r in part),
                "list_usd": round(sum(r["list_usd"] for r in part), 4),
                "median_wall_s": statistics.median(float(r.get("wall_s") or 0) for r in part),
                **{k: sum(int(r.get(k) or 0) for r in part)
                   for k in ("guard_stops", "echo_cut", "echoed_wrappers", "click_notes",
                             "rows_notes")},
                "line_sessions": sum(bool(r.get("line_seen")) for r in part),
            }  # fmt: skip

    def ratio(tids: tuple[str, ...], treated: str, base: str) -> float | None:
        num = sum(_mean(_cell(rows, t, treated)) for t in tids)
        den = sum(_mean(_cell(rows, t, base)) for t in tids)
        return round(num / den, 3) if num and den else None

    return {
        "sessions": len(rows), "arms": arms, "tasks": tasks,
        "ratios": {"I2 HAIKU-V8/HAIKU": ratio(("I2",), "HAIKU-V8", "HAIKU"),
                   "I2 HAIKU-V7/HAIKU": ratio(("I2",), "HAIKU-V7", "HAIKU"),
                   "G4+G8 SONNET-V8/SONNET": ratio(("G4", "G8"), "SONNET-V8", "SONNET"),
                   "G4 SONNET-V8/SONNET": ratio(("G4",), "SONNET-V8", "SONNET"),
                   "G8 SONNET-V8/SONNET": ratio(("G8",), "SONNET-V8", "SONNET")},
        "versions": sorted({r.get("version", "") for r in rows}),
        "list_usd_total": round(sum(r["list_usd"] for r in rows), 4),
    }  # fmt: skip


def spent(path: pathlib.Path) -> float:
    return sum(float(r.get("list_usd") or 0) for r in nav.done_sessions(path))


def _run(plan: list[tuple], path: pathlib.Path, ceiling: float) -> tuple[int, list[dict]]:
    rows = nav.done_sessions(path)
    limits = nav.phase.Limits(session_max_usd=nav.SESSION_MAX_USD, ceiling_usd=ceiling)
    code, rows = nav.phase.run_phase(plan, rows, limits, one_session, path)
    if code == 2:
        nav.phase._log(path, f"{STOP_LIMIT}: the subscription refused a session; stopped")
    return code, rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ("--preflight", "--smoke", "--live"):
        ap.add_argument(flag, action="store_true")
    args = ap.parse_args()
    install()
    if args.preflight or args.live or args.smoke:
        problems = preflight()
        if problems:
            print("preflight failed, nothing spent:\n  " + "\n  ".join(problems))
            return 2
        print("preflight: claude pinned; v7 and v8 answer as their env asks")
        if args.preflight:
            return 0
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.smoke:
        plan = [(0, next(t for t in TASKS if t[0] == tid), 1, arm) for tid, arm in SMOKE]
        code, rows = _run(plan, SMOKE_SESSIONS, SMOKE_CEILING_USD)
        print(json.dumps([{k: r.get(k) for k in (*nav.phase.SHOWN, "answer", "subtype",
                                                  "line_seen", "echo_cut", "echoed_wrappers",
                                                  "click_notes", "rows_notes", "not_run")}
                          for r in rows], indent=1)[:6000])  # fmt: skip
        return code
    code = 0
    if args.live:
        ceiling = CEILING_USD - spent(SMOKE_SESSIONS)
        plan = nav.phase.planned(TASKS, list(range(1, RUNS + 1)), ARMS)
        code, _rows = _run(plan, SESSIONS, ceiling)
    counted = nav.phase.counted(nav.done_sessions(SESSIONS))
    if not counted:
        print("nothing recorded yet")
        return code
    report = analyse(counted)
    report["not_run"] = [
        {k: r.get(k) for k in ("task", "run", "arm", "subtype")}
        for r in nav.done_sessions(SESSIONS) if r.get("not_run")
    ]  # fmt: skip
    REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
