"""Browse, phase 3: Claude Code browsing with playwright-cli, with and without the hook.

python benchmarks/browse/e2e.py --record-hash
python benchmarks/browse/e2e.py --live --env-file PATH/.env      # 36 sessions, see prereg-e2e.md
python benchmarks/browse/e2e.py                                  # free: re-grades what ran

Each session is a real `claude -p` with tools `Bash(playwright-cli:*)` and `Read`, in a fresh
directory, with user and project settings off. Results append to `e2e-sessions.jsonl`, so a
stopped run resumes where it stopped. List prices through the subscription (our evaluation
harness), not directly comparable with the API.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import random
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
RESULTS = ROOT / "docs" / "results" / "2026-09-30-browse"
PREREG = RESULTS / "prereg-e2e.md"
AMENDMENT = RESULTS / "prereg-e2e-amendment.md"
SESSIONS = RESULTS / "e2e-sessions.jsonl"
PYTHON = pathlib.Path(sys.executable)
MODEL = "claude-sonnet-5"
RUNS = 3
SESSION_MAX_USD = 1.00
CEILING_USD = 20.00
LEAN_JEV_MAX_USD = 0.20  # SANCHOPANZA_SESSION_MAX_USD in a LEAN session
JEV_CEILING_USD = 2.00  # Phase 3g (prereg-e2e-wide.md)
EARLY_STOP_USD = 8.00
TIMEOUT_S = 900

TASKS = [
    ("T1", "https://books.toscrape.com/",
     'In the Mystery category, find the book "Sharp Objects" and report its price and its star '
     "rating.", ["47.82", ["four", "4-star", "4 star", "4 stars", "4/5", "4 out of 5"]]),
    ("T2", "https://books.toscrape.com/",
     'Find the book "Tipping the Velvet" and report its UPC.', ["90fa61229261140a"]),
    ("T3", "https://quotes.toscrape.com/",
     "Open Jane Austen's author page and report her birth date and birth place.",
     ["1775", "steventon"]),
    ("T4", "https://en.wikipedia.org/wiki/Python_(programming_language)",
     "From the infobox, report who designed Python and the year it first appeared.",
     ["guido van rossum", "1991"]),
    ("T5", "https://en.wikipedia.org/wiki/Mount_Everest",
     "Report the elevation in metres given in the infobox.", ["8848.86"]),
    ("T6", "https://books.toscrape.com/",
     "Go to page 2 of the catalogue and report the title of the first book listed.",
     ["in her wake"]),
]  # fmt: skip

APPEND = (
    "You browse the web with the `playwright-cli` command in Bash. Useful commands: "
    "`playwright-cli -s={session} open <url>`, `goto <url>`, `snapshot` (prints the page's "
    "elements with refs like e12), `click <ref>`, `fill <ref> <text>`, `find <text>`, "
    "`close`. Always pass `-s={session}`. Answer the user's question with the facts found on "
    "the page, briefly, then close the browser."
)


def digest(path: pathlib.Path = PREREG) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def require_prereg() -> None:
    """Every registration of the phase, the design and any amendment."""
    for path in REGISTRATIONS:
        registered = path.with_suffix(".sha256")
        if not registered.exists() or registered.read_text().strip() != digest(path):
            raise SystemExit(
                f"{path.name} missing or changed since it was registered: nothing spent"
            )


REGISTRATIONS = (PREREG, AMENDMENT)
NEW_PREREG = RESULTS / "prereg-e2e-cli-new.md"  # Phase 3e: the fixed hook, new tasks


def use_new_tasks() -> None:
    """Phase 3e: Phase 3d's six new tasks with playwright-cli, four runs, its own files."""
    global PREREG, SESSIONS, REGISTRATIONS, RUNS, TASKS, REPORT
    mcp = _load_sibling("browse_e2e_mcp", HERE / "e2e_mcp.py")
    PREREG, REGISTRATIONS = NEW_PREREG, (NEW_PREREG,)
    SESSIONS, REPORT = RESULTS / "e2e-cli-new-sessions.jsonl", "e2e-cli-new.json"
    RUNS, TASKS = 4, mcp.NEW_TASKS


WIDE_PREREG = RESULTS / "prereg-e2e-wide.md"  # Phase 3g: twelve more tasks, playwright-cli
# Phases 3 and 3e lost runs to "Done - browser closed." as the final message; here the agent
# closes the browser first and answers last, so the final message is the answer.
APPEND_ANSWER_LAST = (
    "You browse the web with the `playwright-cli` command in Bash. Useful commands: "
    "`playwright-cli -s={session} open <url>`, `goto <url>`, `snapshot` (prints the page's "
    "elements with refs like e12), `click <ref>`, `fill <ref> <text>`, `find <text>`, "
    "`close`. Always pass `-s={session}`. When you have the facts, close the browser first, "
    "then give the answer briefly as your final message."
)


def use_wide_tasks() -> None:
    """Phase 3g: Phase 3f's twelve tasks with playwright-cli, three runs, answer last."""
    global PREREG, SESSIONS, REGISTRATIONS, RUNS, TASKS, REPORT, APPEND
    mcp = _load_sibling("browse_e2e_mcp", HERE / "e2e_mcp.py")
    PREREG, REGISTRATIONS = WIDE_PREREG, (WIDE_PREREG,)
    SESSIONS, REPORT = RESULTS / "e2e-cli-wide-sessions.jsonl", "e2e-cli-wide.json"
    RUNS, TASKS, APPEND = mcp.WIDE_RUNS, mcp.WIDE_TASKS, APPEND_ANSWER_LAST


X_PREREG = RESULTS / "prereg-e2e-x.md"  # Phase 3i: Phase 3h's twelve tasks, playwright-cli


def use_x_tasks() -> None:
    """Phase 3i: Phase 3h's twelve tasks with playwright-cli, three runs, answer last."""
    global PREREG, SESSIONS, REGISTRATIONS, RUNS, TASKS, REPORT, APPEND
    mcp = _load_sibling("browse_e2e_mcp", HERE / "e2e_mcp.py")
    PREREG, REGISTRATIONS = X_PREREG, (X_PREREG,)
    SESSIONS, REPORT = RESULTS / "e2e-cli-x-sessions.jsonl", "e2e-cli-x.json"
    RUNS, TASKS, APPEND = mcp.WIDE_RUNS, mcp.X_TASKS, APPEND_ANSWER_LAST


Y_PREREG = RESULTS / "prereg-e2e-y.md"  # Phase 3k: Phase 3j's twelve tasks, playwright-cli


def use_y_tasks() -> None:
    """Phase 3k: Phase 3j's twelve tasks with playwright-cli, three runs, answer last."""
    global PREREG, SESSIONS, REGISTRATIONS, RUNS, TASKS, REPORT, APPEND, JEV_CEILING_USD
    mcp = _load_sibling("browse_e2e_mcp", HERE / "e2e_mcp.py")
    JEV_CEILING_USD = mcp.JEV_CEILING_Y_USD
    PREREG, REGISTRATIONS = Y_PREREG, (Y_PREREG,)
    SESSIONS, REPORT = RESULTS / "e2e-cli-y-sessions.jsonl", "e2e-cli-y.json"
    RUNS, TASKS, APPEND = mcp.WIDE_RUNS, mcp.Y_TASKS, APPEND_ANSWER_LAST


Z_PREREG = RESULTS / "prereg-e2e-z.md"  # Phase 3m: Phase 3l's twelve tasks, playwright-cli


def use_z_tasks() -> None:
    """Phase 3m: Phase 3l's twelve tasks with playwright-cli, three runs, answer last."""
    global PREREG, SESSIONS, REGISTRATIONS, RUNS, TASKS, REPORT, APPEND, JEV_CEILING_USD
    mcp = _load_sibling("browse_e2e_mcp", HERE / "e2e_mcp.py")
    JEV_CEILING_USD = mcp.JEV_CEILING_Y_USD
    PREREG, REGISTRATIONS = Z_PREREG, (Z_PREREG,)
    SESSIONS, REPORT = RESULTS / "e2e-cli-z-sessions.jsonl", "e2e-cli-z.json"
    RUNS, TASKS, APPEND = mcp.WIDE_RUNS, mcp.Z_TASKS, APPEND_ANSWER_LAST


U_PREREG = RESULTS / "prereg-e2e-u.md"  # Phase 3o: Phase 3n's twelve tasks, playwright-cli


def use_u_tasks() -> None:
    """Phase 3o: Phase 3n's twelve tasks with playwright-cli, three runs, answer last."""
    global PREREG, SESSIONS, REGISTRATIONS, RUNS, TASKS, REPORT, APPEND, JEV_CEILING_USD
    mcp = _load_sibling("browse_e2e_mcp", HERE / "e2e_mcp.py")
    JEV_CEILING_USD = mcp.JEV_CEILING_Y_USD
    PREREG, REGISTRATIONS = U_PREREG, (U_PREREG,)
    SESSIONS, REPORT = RESULTS / "e2e-cli-u-sessions.jsonl", "e2e-cli-u.json"
    RUNS, TASKS, APPEND = mcp.WIDE_RUNS, mcp.U_TASKS, APPEND_ANSWER_LAST


def _load_sibling(name: str, path: pathlib.Path) -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


REPORT = "e2e.json"


def normal(text: str) -> str:
    return re.sub(r"(?<=\d)[,\s](?=\d{3}\b)", "", text.lower()).replace(" ", " ")


def graded(answer: str, required: list[Any]) -> bool:
    """Every required item present; an item that is a list is met by any of its alternatives
    (prereg-e2e-amendment.md)."""
    body = normal(answer)
    return all(
        any(normal(alt) in body for alt in (item if isinstance(item, list) else [item]))
        for item in required
    )


def settings_for(arm: str, work: pathlib.Path) -> pathlib.Path:
    settings: dict[str, Any] = {"permissions": {"allow": ["Bash(playwright-cli:*)", "Read"]}}
    if arm == "LEAN":
        command = f'"{PYTHON.as_posix()}" -m sanchopanza.harness.browse_hook'
        settings["hooks"] = {
            "PostToolUse": [
                {"matcher": "Bash|Read", "hooks": [{"type": "command", "command": command}]}
            ]
        }
    path = work / "settings.json"
    path.write_text(json.dumps(settings), encoding="utf-8")
    return path


def clean_env(base: dict[str, str]) -> dict[str, str]:
    """No API credential reaches the session: it runs on the subscription."""
    stripped = ("ANTHROPIC_", "CLAUDE_CODE_USE_", "AWS_BEARER_TOKEN_BEDROCK")
    return {k: v for k, v in base.items() if not k.startswith(stripped)}


def journal_usd(path: pathlib.Path) -> tuple[float, int]:
    if not path.exists():
        return 0.0, 0
    usd = calls = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("kind") == "decision":
            usd += float(event.get("data", {}).get("cost_usd") or 0.0)
            calls += 1
    return usd, calls


def one_session(task: tuple, run: int, arm: str, key: str) -> dict[str, Any]:
    tid, url, question, required = task
    session = f"{tid.lower()}r{run}{arm.lower()}"
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"sp-e2e-{session}-"))
    journal = work / "journal.jsonl"
    env = clean_env(dict(os.environ))
    env["SANCHOPANZA_JOURNAL"] = str(journal)
    env["SANCHOPANZA_ARCHIVE"] = str(work / "archive")
    if arm == "LEAN":
        env["TYPESAFE_API_KEY"] = key
        env["SANCHOPANZA_SESSION_MAX_USD"] = f"{LEAN_JEV_MAX_USD:.2f}"
    else:
        env.pop("TYPESAFE_API_KEY", None)
    argv = [
        shutil.which("claude") or "claude", "-p", "--model", MODEL,
        "--append-system-prompt", APPEND.format(session=session),
        "--settings", str(settings_for(arm, work)), "--setting-sources", "",
        "--strict-mcp-config", "--allowedTools", "Bash(playwright-cli:*) Read",
        "--disallowedTools", "WebFetch WebSearch", "--output-format", "json",
        "--max-budget-usd", f"{SESSION_MAX_USD:g}",
        "--", f"Start at {url}. {question}",
    ]  # fmt: skip
    try:
        done = subprocess.run(argv, cwd=work, env=env, capture_output=True, timeout=TIMEOUT_S)
        out = json.loads(done.stdout.decode("utf-8", errors="replace") or "{}")
    except (subprocess.TimeoutExpired, ValueError) as error:
        out = {"is_error": True, "subtype": f"runner: {error.__class__.__name__}"}
    finally:
        subprocess.run(["playwright-cli", f"-s={session}", "close"], capture_output=True,
                       timeout=60, check=False, shell=os.name == "nt")  # fmt: skip
    usage = out.get("usage") or {}
    jev_usd, jev_calls = journal_usd(journal)
    browse_events = []
    if journal.exists():
        events = [json.loads(x) for x in journal.read_text(encoding="utf-8").splitlines() if x]
        browse_events = [e.get("data", {}) for e in events if e.get("kind") == "browse"]
    answer = str(out.get("result") or "")
    return {
        "task": tid, "run": run, "arm": arm,
        "ok": not out.get("is_error", True), "subtype": out.get("subtype"),
        "success": graded(answer, required), "answer": answer[:600],
        "list_usd": float(out.get("total_cost_usd") or 0.0),
        "turns": out.get("num_turns"),
        "input_tokens": int(usage.get("input_tokens") or 0),
        "cache_read": int(usage.get("cache_read_input_tokens") or 0),
        "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
        "output_tokens": int(usage.get("output_tokens") or 0),
        "jev_usd": jev_usd, "jev_calls": jev_calls, "pruned": browse_events,
        "workdir": str(work),
    }  # fmt: skip


def done_sessions() -> list[dict[str, Any]]:
    if not SESSIONS.exists():
        return []
    return [json.loads(x) for x in SESSIONS.read_text(encoding="utf-8").splitlines() if x.strip()]


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, Any] = {"sessions": len(rows)}
    for arm in ("PLAIN", "LEAN"):
        rs = [r for r in rows if r["arm"] == arm]
        if not rs:
            continue
        report[arm] = {
            "runs": len(rs),
            "success": sum(r["success"] for r in rs),
            "list_usd_mean": round(sum(r["list_usd"] for r in rs) / len(rs), 4),
            "jev_usd_mean": round(sum(r["jev_usd"] for r in rs) / len(rs), 5),
            "turns_mean": round(sum(r["turns"] or 0 for r in rs) / len(rs), 2),
            "cache_read_mean": round(sum(r["cache_read"] for r in rs) / len(rs)),
            "cache_write_mean": round(sum(r["cache_write"] for r in rs) / len(rs)),
            "snapshots_pruned": sum(len(r["pruned"]) for r in rs),
        }
    tasks = sorted({r["task"] for r in rows})
    diffs = []
    for t in tasks:
        plain = [
            r["list_usd"] + r["jev_usd"] for r in rows if r["task"] == t and r["arm"] == "PLAIN"
        ]
        lean = [r["list_usd"] + r["jev_usd"] for r in rows if r["task"] == t and r["arm"] == "LEAN"]
        if plain and lean:
            diffs.append(sum(lean) / len(lean) - sum(plain) / len(plain))
    if diffs:
        rng = random.Random(2033)
        means = sorted(
            sum(diffs[rng.randrange(len(diffs))] for _ in diffs) / len(diffs) for _ in range(5000)
        )
        report["LEAN_minus_PLAIN_usd_per_task"] = {
            "value": round(sum(diffs) / len(diffs), 4),
            "bootstrap95": [round(means[125], 4), round(means[4875], 4)],
            "by_task": dict(zip(tasks, [round(d, 4) for d in diffs], strict=False)),
        }
    return report


phase = _load_sibling("browse_phase", HERE / "phase.py")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--record-hash", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--env-file", default=None)
    ap.add_argument("--pilot", action="store_true", help="T1 once per arm (run 0), excluded")
    ap.add_argument("--pilot2", action="store_true", help="T1 LEAN once more (run -1), excluded")
    ap.add_argument("--new", action="store_true", help="Phase 3e (prereg-e2e-cli-new.md)")
    ap.add_argument(
        "--warmup",
        action="store_true",
        help="one uncounted PLAIN session first (run -9, -10 on a resume), to warm the cache",
    )
    ap.add_argument("--wide", action="store_true", help="Phase 3g (prereg-e2e-wide.md)")
    ap.add_argument("--x", action="store_true", help="Phase 3i (prereg-e2e-x.md)")
    ap.add_argument("--y", action="store_true", help="Phase 3k (prereg-e2e-y.md)")
    ap.add_argument("--z", action="store_true", help="Phase 3m (prereg-e2e-z.md)")
    ap.add_argument("--u", action="store_true", help="Phase 3o (prereg-e2e-u.md)")
    args = ap.parse_args()
    if args.new:
        use_new_tasks()
    if args.wide:
        use_wide_tasks()
    if args.x:
        use_x_tasks()
    if args.y:
        use_y_tasks()
    if args.z:
        use_z_tasks()
    if args.u:
        use_u_tasks()
    if args.record_hash:
        for path in REGISTRATIONS:
            registered = path.with_suffix(".sha256")
            if registered.exists() and registered.read_text().strip() != digest(path):
                raise SystemExit(f"{registered.name} holds a different hash: nothing written")
            registered.write_text(digest(path) + "\n", encoding="utf-8")
            print(path.name, digest(path))
        return 0
    rows = done_sessions()
    if args.live:
        require_prereg()
        key = os.environ.get("TYPESAFE_API_KEY", "")
        if not key and args.env_file:
            found = re.search(
                r"^TYPESAFE_API_KEY=(.*)$",
                pathlib.Path(args.env_file).read_text(encoding="utf-8"),
                re.M,
            )
            key = found.group(1).strip().strip("'\"") if found else ""
        pilot = args.pilot or args.pilot2
        runs = [0] if args.pilot else [-1] if args.pilot2 else list(range(1, RUNS + 1))
        arms = ("LEAN",) if args.pilot2 else ("PLAIN", "LEAN")
        limits = phase.Limits(
            session_max_usd=SESSION_MAX_USD, ceiling_usd=CEILING_USD,
            jev_session_max_usd=LEAN_JEV_MAX_USD,
            jev_ceiling_usd=JEV_CEILING_USD
            if any((args.wide, args.x, args.y, args.z, args.u)) else None,
            early_stop_usd=EARLY_STOP_USD, early_tasks=frozenset(t[0] for t in TASKS[:2]),
        )  # fmt: skip
        code, rows = phase.run_phase(
            phase.planned(TASKS[:1] if pilot else TASKS, runs, arms), rows, limits,
            lambda task, run, arm: one_session(task, run, arm, key), SESSIONS,
            warmup_task=TASKS[0] if args.warmup else None,
        )  # fmt: skip
        if code:
            return code
    report = analyze([r for r in rows if r["run"] > 0])
    report["pilot"] = [r for r in rows if r["run"] <= 0]
    (RESULTS / REPORT).write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
