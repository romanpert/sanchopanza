"""Browse, v7 in development: line v6 plus the crawl notes (`harness.crawl_notes`) against Haiku
alone, and line v6 without notes if the ceiling allows, on the five F tasks that held 15 of the
28 line misses of `nav_v6.py`.

python benchmarks/browse/nav_v7.py --preflight
python benchmarks/browse/nav_v7.py --smoke [--only F5]   # one HAIKU-V7 session, its own file
python benchmarks/browse/nav_v7.py --live                # the development round
python benchmarks/browse/nav_v7.py                       # free: the tables so far

`nav_v6.py` found that a sentence does not move the cheap model's largest miss: one call reads
the open page while the page states its size on screen. v7 makes that check in the guard instead:
the wrapped evaluate returns notes on what the page and the network said (`crawl_notes`). This is
development on tasks seen before, not a confirmation. Everything but the arms, the tasks and the
files is `nav_v6.py`'s, which is `nav_e2e.py`'s and `phase.py`'s.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import sys
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent


def _load(name: str, path: pathlib.Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


v6 = _load("browse_nav_v6_for_v7", HERE / "nav_v6.py")
nav = v6.nav

SESSIONS = v6.RESULTS / "nav-v7-sessions.jsonl"
SMOKE_SESSIONS = v6.RESULTS / "nav-v7-smoke-sessions.jsonl"
REPORT = v6.RESULTS / "nav-v7.json"
TASK_IDS = ("F1", "F2", "F3", "F5", "F8")
TASKS = [t for t in v6.TASKS if t[0] in TASK_IDS]
# Arm -> (line version, notes). V7 is v6's line with the notes; V6 runs last, only if it fits.
TREATED = {"HAIKU-V7": ("6", True), "HAIKU-V6": ("6", False)}
ARMS = ("HAIKU-V7", "HAIKU", "HAIKU-V6")
CEILING_USD = 6.00  # list price; about 5 expected if all three arms run (the README says how)
NOTES_SEEN = "sanchopanza notes"  # in every wrapped evaluate Playwright MCP echoes back
# A real stop, as the tool result shows it; the bare sentence is also in the wrapper's own code.
GUARD_STOP = "### Error\\nError: evaluate stopped after"


def settings_for(arm: str, work: pathlib.Path) -> pathlib.Path:
    """What `sanchopanza install --crawl` writes, the line's version, and the notes for V7."""
    from sanchopanza.harness.install import _merge_crawl

    settings: dict[str, Any] = {"permissions": {"allow": nav.TOOLS.split()}}
    if arm in TREATED:
        version, notes = TREATED[arm]
        command = v6.confirm3.crawl_command()
        settings, _added, _removed = _merge_crawl(settings, True, command=command)
        env = {"SANCHOPANZA_CRAWL_LINE_VERSION": version}
        settings = {**settings, "env": {**env, "SANCHOPANZA_CRAWL_NOTES": "1"} if notes else env}
    path = work / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def one_session(task: tuple, run: int, arm: str) -> dict[str, Any]:
    """v6's session (line checked in the transcript), plus: a V7 session in which no evaluate
    carried the notes, or a V6 session in which one did, is `not_run`; and the guard's stops
    counted as tool results, not as copies of the sentence."""
    row = v6.one_session(task, run, arm)
    text = v6.confirm3._transcript(row["workdir"])
    row = {**row, "notes_seen": NOTES_SEEN in text, "guard_stops": text.count(GUARD_STOP)}
    evaluated = bool((row.get("tools") or {}).get("mcp__playwright__browser_evaluate"))
    if arm in TREATED and row.get("ok") and evaluated and row["notes_seen"] != TREATED[arm][1]:
        return {
            **row,
            "not_run": True,
            "subtype": f"notes {'missing' if TREATED[arm][1] else 'present'}",
        }
    return row


def preflight() -> list[str]:
    """v6's checks (pinned Claude Code, the hook answers the line asked for), and the hook with
    `SANCHOPANZA_CRAWL_NOTES=1` wraps an evaluate with the notes."""
    import os
    import subprocess

    from sanchopanza.harness.crawl_notes import NOTES_MARK

    problems = v6.preflight()
    env = {**nav.base.clean_env(dict(os.environ)), "PYTHONPATH": str(v6.SRC),
           "SANCHOPANZA_CRAWL_NOTES": "1"}  # fmt: skip
    event = {"hook_event_name": "PreToolUse", "tool_name": "mcp__playwright__browser_evaluate",
             "tool_input": {"function": "() => 1"}}  # fmt: skip
    command = [str(nav.HOOK_PYTHON), "-m", "sanchopanza", "crawl-hook"]
    try:
        done = subprocess.run(command, input=json.dumps(event).encode(), env=env,
                              capture_output=True, timeout=60)  # fmt: skip
        out = json.loads(done.stdout or b"{}")["hookSpecificOutput"]
        if NOTES_MARK not in out["updatedInput"]["function"] or "permissionDecision" in out:
            problems.append("the hook did not wrap the evaluate with the notes as asked")
    except (subprocess.TimeoutExpired, ValueError, KeyError, OSError) as error:
        problems.append(f"notes: {error.__class__.__name__}: {error}")
    return problems


def install() -> None:
    v6.install()
    nav.MODELS.update(dict.fromkeys(ARMS, v6.MODEL))
    nav.settings_for = settings_for
    v6.TREATED = {arm: version for arm, (version, _notes) in TREATED.items()}
    v6.ARMS = ARMS
    v6.TASKS = TASKS


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for flag in ("--preflight", "--smoke", "--live"):
        ap.add_argument(flag, action="store_true")
    ap.add_argument("--only", default="F5", help="the smoke session's task")
    args = ap.parse_args()
    install()
    if args.preflight or args.live or args.smoke:
        problems = preflight()
        if problems:
            print("preflight failed, nothing spent:\n  " + "\n  ".join(problems))
            return 2
        print("preflight: claude pinned, the hook answers the line and wraps with notes")
        if args.preflight:
            return 0
    v6.RESULTS.mkdir(parents=True, exist_ok=True)
    sessions = SMOKE_SESSIONS if args.smoke else SESSIONS
    rows = nav.done_sessions(sessions)
    code = 0
    limits = nav.phase.Limits(session_max_usd=v6.SESSION_MAX_USD, ceiling_usd=CEILING_USD)
    if args.smoke:
        task = next(t for t in TASKS if t[0] == args.only.upper())
        smoke = nav.phase.Limits(session_max_usd=v6.SESSION_MAX_USD, ceiling_usd=1.5)
        code, rows = nav.phase.run_phase([(0, task, 1, "HAIKU-V7")], rows, smoke, one_session,
                                         sessions)  # fmt: skip
        print(json.dumps(rows[-1] if rows else {}, indent=1)[:3000])
        return code
    if args.live:
        plan = [p for arm in ARMS for p in nav.phase.planned(TASKS, [1, 2, 3], (arm,))]
        code, rows = nav.phase.run_phase(plan, rows, limits, one_session, sessions)
    counted = nav.phase.counted(rows)
    if not counted:
        print("nothing recorded yet")
        return code
    report = v6.analyse(counted)
    report["not_run"] = [
        {k: r.get(k) for k in ("task", "run", "arm", "subtype")} for r in rows if r.get("not_run")
    ]
    REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
