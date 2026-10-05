"""Browse, v9 in development: confirmation 5's open-page misses with notes v3, against Claude Code
alone, on Haiku and on Sonnet, and Sonnet with the notes and no line.

python benchmarks/browse/nav_v9.py --preflight
python benchmarks/browse/nav_v9.py --smoke     # HAIKU-V9 on H1 and H5, its own file
python benchmarks/browse/nav_v9.py --live      # the development round
python benchmarks/browse/nav_v9.py             # free: the tables so far

Confirmation 5 (README 2026-10-03, its section) held answers and no harm on both models and
failed price. Its 14 open-page misses were on pages whose size the notes could not read: a `Link`
header (H1), no total at all (H4), `meta.pagination.records` (H5); and H7's 303 cards came by
XMLHttpRequest, which the notes did not watch. v9 is v8.1 with notes v3
(`SANCHOPANZA_CRAWL_NOTES=3`, `harness/crawl_notes._V3`), and one more arm: Sonnet with the
notes and without the line (`SANCHOPANZA_CRAWL_LINE=0`), since on H7 line v6 sent Sonnet hunting
the list's API.

The tasks are confirmation 5's own, so this is development, not a confirmation: H1, H4, H5 and H7
(the misses) and H2, H8 (no regression), two runs each. Everything but the arms, the tasks, the
limit check and the files is `nav_confirm5.py`'s: its tasks, grading, Claude Code pin, site-down
rule and treatment checks, loaded here as a copy. A 429 stops the round only when it is the
subscription's (Anthropic's API or a usage limit), never when a site answered 429 to the agent.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import statistics
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


conf5 = _load("browse_nav_confirm5_for_v9", HERE / "nav_confirm5.py")
v8, conf4, conf3, nav = conf5.v8, conf5.conf4, conf5.conf3, conf5.nav
procedure = conf3.procedure

RESULTS = conf4.RESULTS
SESSIONS = RESULTS / "nav-v9-sessions.jsonl"
SMOKE_SESSIONS = RESULTS / "nav-v9-smoke-sessions.jsonl"
REPORT = RESULTS / "nav-v9.json"
TASK_IDS = ("H1", "H4", "H5", "H7", "H2", "H8")
TASKS = [next(t for t in conf5.TASKS if t[0] == tid) for tid in TASK_IDS]
MISSES, KEPT = TASK_IDS[:4], TASK_IDS[4:]
RUNS = 2
ARMS = ("HAIKU", "HAIKU-V9", "SONNET", "SONNET-V9", "SONNET-NOTES")
SMOKE = (("H1", "HAIKU-V9"), ("H5", "HAIKU-V9"))
CEILING_USD = 10.00  # list price, smoke included; about 5.5 expected from confirmation 5's means
SMOKE_CEILING_USD = 1.50  # the phase reserves the 1.00 session cap before each session
CLAUDE_VERSION = conf5.CLAUDE_VERSION
V9_ENV = {**v8.V81_ENV, "SANCHOPANZA_CRAWL_NOTES": "3"}
NOTES_ENV = {**V9_ENV, "SANCHOPANZA_CRAWL_LINE": "0"}
TREATED = {"HAIKU-V9": V9_ENV, "SONNET-V9": V9_ENV, "SONNET-NOTES": NOTES_ENV}

# The subscription refusing a session, as Claude Code reports it: the API's 429 (always with
# Claude Code's own "API Error: " or the API's error type) or a usage limit. A bare "429" or
# "rate limit" is not one: H5's site answers 429 to a fast walk, and that is the agent's problem.
API_429 = re.compile(r"API Error: 429\b|rate_limit_error")
USAGE_LIMIT = re.compile(r"weekly limit|hit your (?:\w+ )?limit|usage limit reached", re.I)
# Notes v3, as the agent saw them (in tool results, never in the wrapper's code).
V9_NOTES = {
    "link_notes": re.compile(r"Link header: (?:next|last) "),
    "keys_notes": re.compile(r"(?:says: |\| )JSON \w[\w.\[\]]*: "),
    "round_notes": re.compile(r"a JSON array of exactly \d+ items and no total"),
    "one_notes": re.compile(r"the one (?:JSON )?response this call (?:read|fetched)"),
}


def planned() -> list[tuple]:
    """(task index, task, run, arm): task by task, run by run, arm by arm."""
    return [(i, task, run, arm) for i, task in enumerate(TASKS)
            for run in range(1, RUNS + 1) for arm in ARMS]  # fmt: skip


def settings_for(arm: str, work: pathlib.Path) -> pathlib.Path:
    """Plain arms: the bench's permissions and no hook. The others: v8.1's hooks (what `install
    --crawl` writes plus `V8_HOOKS` and `V81_HOOKS`) and their own env. Only in the session's own
    `--settings`."""
    from sanchopanza.harness.crawl_hook import V8_HOOKS, V81_HOOKS
    from sanchopanza.harness.install import CRAWL_COMMAND, _merge_crawl, _merge_owned

    settings: dict[str, Any] = {"permissions": {"allow": nav.TOOLS.split()}}
    if arm in TREATED:
        command = conf3.crawl_command()
        settings, _added, _removed = _merge_crawl(settings, True, command=command)
        for hooks in (V8_HOOKS, V81_HOOKS):
            settings, _added, _removed = _merge_owned(
                settings, True, hooks, command, CRAWL_COMMAND, "crawl"
            )
        settings = {**settings, "env": dict(TREATED[arm])}
    path = work / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def api_limit_hit(row: dict[str, Any]) -> bool:
    """The subscription refused the session: Anthropic's 429 in a failed session's reply or
    stderr, or a usage limit in any reply. A site's 429 is neither."""
    answer = str(row.get("answer") or "")
    if row.get("limit_hit"):
        return True
    if USAGE_LIMIT.search(answer):
        return True
    if row.get("ok"):
        return False
    said = f"{answer}\n{row.get('subtype') or ''}\n{v8._stderr(row['workdir'])}"
    return bool(API_429.search(said) or USAGE_LIMIT.search(said))


def v9_counts(text: str) -> dict[str, int]:
    """The v3 notes by kind, in the tool results the agent saw."""
    out = dict.fromkeys(V9_NOTES, 0)
    for line in text.splitlines():
        try:
            content = (json.loads(line).get("message") or {}).get("content")
        except (ValueError, AttributeError):
            continue
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                seen = "\n".join(v8._texts(block.get("content")))
                for key, pattern in V9_NOTES.items():
                    out[key] += bool(pattern.search(seen))
    return out


def treatment(row: dict[str, Any], text: str, arm: str) -> str | None:
    """Why a session did not get exactly its arm's treatment (every task here gathers): v8.1's
    checks for the `-V9` arms; for `-NOTES`, the same with no line anywhere."""
    if arm not in TREATED:
        return v8.treatment(row, text, "HAIKU", True)
    if arm.endswith("-NOTES"):
        if row["line_seen"]:
            return "notes arm: the line was added"
        return v8.treatment(row, text, "SONNET-V81", False)
    return v8.treatment(row, text, "HAIKU-V81", True)


def downs_before(path: pathlib.Path, tid: str, run: int, arm: str) -> int:
    return sum(bool(r.get("site_down")) for r in nav.done_sessions(path)
               if (r["task"], r["run"], r["arm"]) == (tid, run, arm))  # fmt: skip


def session_in(path: pathlib.Path) -> Any:
    """nav's session, timed, with the treatment checked in the transcript, the v3 notes counted,
    the subscription's limits caught, and confirmation 5's site-down rule against `path`."""

    def one(task: tuple, run: int, arm: str) -> dict[str, Any]:
        started = time.monotonic()
        row = nav.one_session(task, run, arm)
        text = conf3._transcript(row["workdir"])
        loads, down = conf5.page_loads(text)
        row = {**row, "wall_s": round(time.monotonic() - started, 1),
               "line_seen": v8.LINE_SEEN in text, "notes_seen": v8.NOTES_SEEN in text,
               "guard_stops": text.count(v8.GUARD_STOP),
               "echoed_wrappers": text.count(v8.ECHOED), "echo_cut": text.count(v8.ECHO_CUT),
               "click_notes": len(v8.CLICK_NOTE.findall(text)),
               "rows_notes": len(v8.ROWS_NOTE.findall(text)), **v8.v81_counts(text),
               **v9_counts(text), "page_loads": loads, "page_loads_5xx": down}  # fmt: skip
        if api_limit_hit(row):
            return {**row, "limit_hit": True, "not_run": True, "subtype": "usage limit or 429"}
        if row.get("ok"):
            why = treatment(row, text, arm)
            if why:
                return {**row, "not_run": True, "subtype": why}
        if conf5.site_down(row):
            if downs_before(path, task[0], run, arm):
                return {**row, "site_down": True, "site_down_again": True}
            return {**row, "site_down": True, "not_run": True, "subtype": conf5.SITE_DOWN}
        return row

    return one


one_session = session_in(SESSIONS)


def run(plan: list[tuple], path: pathlib.Path, ceiling: float) -> tuple[int, list[dict]]:
    """Every planned session, then the site-down repeats, under one ceiling; STOP-LIMIT logged
    when the subscription refused a session."""
    rows = nav.done_sessions(path)
    limits = nav.phase.Limits(session_max_usd=nav.SESSION_MAX_USD, ceiling_usd=ceiling)
    downed = {(r["task"], r["run"], r["arm"]) for r in rows if r.get("site_down")}
    first = [p for p in plan if (p[1][0], p[2], p[3]) not in downed]
    one = session_in(path)
    code, rows = nav.phase.run_phase(first, rows, limits, one, path)
    if code == 0:
        code, rows = nav.phase.run_phase(plan, rows, limits, one, path)
    if code == 2:
        nav.phase._log(path, f"{v8.STOP_LIMIT}: the subscription refused a session; stopped")
    return code, rows


ROUND = v8.Round(
    "v9", tuple((t, RUNS) for t in TASK_IDS), ARMS, SESSIONS, SMOKE_SESSIONS, REPORT,
    CEILING_USD, SMOKE, SMOKE_CEILING_USD,
    (("crawls HAIKU-V9/HAIKU", TASK_IDS, "HAIKU-V9", "HAIKU"),
     ("crawls SONNET-V9/SONNET", TASK_IDS, "SONNET-V9", "SONNET"),
     ("crawls SONNET-NOTES/SONNET", TASK_IDS, "SONNET-NOTES", "SONNET"),
     ("crawls SONNET-NOTES/SONNET-V9", TASK_IDS, "SONNET-NOTES", "SONNET-V9"),
     ("misses HAIKU-V9/HAIKU", MISSES, "HAIKU-V9", "HAIKU"),
     ("misses SONNET-V9/SONNET", MISSES, "SONNET-V9", "SONNET"),
     ("misses SONNET-NOTES/SONNET", MISSES, "SONNET-NOTES", "SONNET"),
     ("H2+H8 HAIKU-V9/HAIKU", KEPT, "HAIKU-V9", "HAIKU"),
     ("H2+H8 SONNET-V9/SONNET", KEPT, "SONNET-V9", "SONNET"),
     ("H2+H8 SONNET-NOTES/SONNET", KEPT, "SONNET-NOTES", "SONNET"),
     ("H7 SONNET-NOTES/SONNET", ("H7",), "SONNET-NOTES", "SONNET"),
     ("H7 SONNET-V9/SONNET", ("H7",), "SONNET-V9", "SONNET")),
)  # fmt: skip
PAIRS = (("HAIKU-V9", "HAIKU"), ("SONNET-V9", "SONNET"), ("SONNET-NOTES", "SONNET"),
         ("SONNET-NOTES", "SONNET-V9"))  # fmt: skip


def prereg_like(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Confirmation 4's price and answers, computed the same way over these six crawls: the
    total crawl ratio (sessions charged as the prereg charges them), the tasks cheaper by mean,
    and the right answers. Development: these tasks were seen, so nothing here is a verdict."""
    charged = procedure.charged

    def cell(tid: str, arm: str) -> list[dict[str, Any]]:
        return [r for r in rows if r["task"] == tid and r["arm"] == arm]

    def mean(tid: str, arm: str) -> float:
        return statistics.mean(charged(r) for r in cell(tid, arm) or [{"list_usd": 0}])

    out = {}
    for treated, base in PAIRS:
        total = {a: sum(charged(r) for t in TASK_IDS for r in cell(t, a)) for a in (treated, base)}
        right = {a: sum(bool(r["success"]) for t in TASK_IDS for r in cell(t, a))
                 for a in (treated, base)}  # fmt: skip
        n = sum(len(cell(t, base)) for t in TASK_IDS)
        cheaper = sum(mean(t, treated) < mean(t, base) for t in TASK_IDS)
        out[f"{treated} vs {base}"] = {
            "ratio_total": round(total[treated] / max(total[base], 1e-9), 3),
            "tasks_cheaper": f"{cheaper}/{len(TASK_IDS)}",
            "right": f"{right[treated]}/{n} vs {right[base]}/{n}",
        }
    return out


COUNTED = ("link_notes", "keys_notes", "round_notes", "one_notes", "page_loads_5xx")


def analyse(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """v8's tables over this round (right answers and mean cost per arm and task, the ratios,
    what the hooks did), the v3 notes by kind per arm, and the prereg-like comparison."""
    out = v8.analyse(rows, ROUND)
    for arm, data in out["arms"].items():
        part = [r for r in rows if r["arm"] == arm]
        out["arms"][arm] = {**data, **{k: sum(int(r.get(k) or 0) for r in part) for k in COUNTED}}
    return {**out, "prereg_like": prereg_like(rows)}


def preflight() -> list[str]:
    """Confirmation 5's preflight (the pinned Claude Code; line v6, the notes, the echo cut, the
    notes at the head, the first screenshot denied; the line on every crawl prompt; no
    sanchopanza hook in the user's settings), then v9's own through the real hook command: the
    notes v3 wrapper with v9's env, the line on these prompts with v9's env and on none with the
    notes arm's."""
    from sanchopanza.harness.crawl_hook import STRATEGY_LINE_V6

    problems = conf5.preflight()
    base = {**nav.base.clean_env(dict(os.environ)), "PYTHONPATH": str(conf3.SRC)}
    wrapped = (
        {"hook_event_name": "PreToolUse", "tool_name": "mcp__playwright__browser_evaluate",
         "tool_input": {"function": "() => 1"}},
        lambda out: "XMLHttpRequest" in out["hookSpecificOutput"]["updatedInput"]["function"],
    )  # fmt: skip
    prompts = [{"hook_event_name": "UserPromptSubmit", "prompt": conf5.prompt_of(t)}
               for t in TASKS]  # fmt: skip
    problems += v8._hook_checks({**base, **V9_ENV}, (wrapped, *(
        (p, lambda out: out["hookSpecificOutput"]["additionalContext"] == STRATEGY_LINE_V6)
        for p in prompts)), "v9")  # fmt: skip
    problems += v8._hook_checks({**base, **NOTES_ENV}, (wrapped, *(
        (p, lambda out: out is None) for p in prompts)), "v9 notes arm")  # fmt: skip
    return problems


def install() -> None:
    """Confirmation 5's runner (and through it v8.1's and confirmation 4's procedure), pointed at
    this round's arms and settings."""
    conf5.install()
    nav.MODELS.update({arm: v8.model_of(arm) for arm in ARMS})
    nav.settings_for = settings_for


def spent(path: pathlib.Path) -> float:
    return sum(float(r.get("list_usd") or 0) for r in nav.done_sessions(path))


SMOKE_SHOWN = (*v8.SMOKE_SHOWN, *V9_NOTES)


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
        print("preflight: claude pinned; the hooks answer as v9's env asks, on these prompts")
        if args.preflight:
            return 0
    RESULTS.mkdir(parents=True, exist_ok=True)
    if args.smoke:
        plan = [(0, next(t for t in TASKS if t[0] == tid), 1, arm) for tid, arm in SMOKE]
        code, rows = run(plan, SMOKE_SESSIONS, SMOKE_CEILING_USD)
        print(json.dumps([{k: r.get(k) for k in (*nav.phase.SHOWN, *SMOKE_SHOWN)}
                          for r in rows], indent=1)[:6000])  # fmt: skip
        return code
    code = 0
    if args.live:
        code, _rows = run(planned(), SESSIONS, CEILING_USD - spent(SMOKE_SESSIONS))
    rows = nav.done_sessions(SESSIONS)
    counted = nav.phase.counted(rows)
    if not counted:
        print("nothing recorded yet")
        return code
    report = {**analyse(counted),
              "list_usd_spent": round(sum(r["list_usd"] for r in rows), 4),
              "not_run": [{k: r.get(k) for k in ("task", "run", "arm", "subtype")}
                          for r in rows if r.get("not_run")]}  # fmt: skip
    REPORT.write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
