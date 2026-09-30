"""Compaction inside Claude Code, end to end: native `/compact` against sanchopanza's pruning.

    python run_e2e.py estimate [--arms N,R]
    python run_e2e.py run --arms N,R --tasks t01-orders          # the pilot
    python run_e2e.py run --arms N,R                             # the rest
    TYPESAFE_API_KEY=... python run_e2e.py run --arms S,F        # the Jev arms, later

Per task: phase A once (`claude -p`, fresh repo), then the repo is snapshotted and every arm
forks the same phase A session (`--resume A --fork-session "/compact"`), so the arms differ
only from the compaction on. Per arm: restore the snapshot, compact, phase B
(`--resume <forked>`), run the hidden tests. Sessions: Claude Code 2.1.282, Haiku 4.5,
`--max-budget-usd 0.40`, `--setting-sources project --strict-mcp-config --permission-mode
dontAsk`, through our own evaluation harness. The sanchopanza arms load the plugin
`sanchopanza install --compact --plugin-dir` wrote, through `--plugin-dir`; nothing is written
to `~/.claude` settings. Raw evidence stays under `~/.cache/sanchopanza/context-e2e/`; this
folder gets one row of numbers per session (`phase-a.jsonl`, `runs.jsonl`).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(HERE))
import tasks as gen  # noqa: E402
import transcripts  # noqa: E402

# `sanchopanza install` as it was when this ran: the defaults grew on 2026-09-30 (guard,
# context budget, find_in_repo, skill), so a rerun opts out of them to measure the same arms.
PRE_0930 = ["--no-guard", "--no-find", "--no-skill", "--context-budget", "0"]

ROOT = Path.home() / ".cache" / "sanchopanza" / "context-e2e"
PYTHON = str(REPO / ".venv" / "Scripts" / "python.exe")
SANCHO = str(REPO / ".venv" / "Scripts" / "sanchopanza.exe")
WRAPPER = str(HERE / "compact_wrapper.py")
MODEL = "claude-haiku-4-5-20251001"
TOOLS = ("Bash", "Read", "Write", "Edit", "Glob", "Grep")
SESSION_CAP = 0.40
CLAUDE_TOTAL = 12.00
CLAUDE_STOP = 11.00
JEV_TOTAL = 0.50
JEV_STOP = 0.45
WORKERS = 4
TIMEOUT = 900
ARMS = ("N", "R", "S", "F")
TASKS_RUN = 6  # README amendment A2: t01-t06, all arms, within the spend ceiling
JEV_ARMS = ("S", "F")
KNOWN_MARKETPLACES = Path.home() / ".claude" / "plugins" / "known_marketplaces.json"

PROMPT_A = (
    "You are onboarding onto this repository. Do these steps in order.\n"
    "1. Read every Python file under pkg/ in full, one by one, and note what each does.\n"
    "2. Run `python tools/issue_token.py` exactly once. It issues this release's token and "
    "can only be run once.\n"
    "3. Run `python -m pytest -q tests`. One test fails; the test is right. Fix the bug in "
    "pkg/, then run the tests again until they pass.\n"
    "4. Run `python tools/probe.py` exactly once. It is expected to fail; do not try to fix "
    "it or run it again.\n"
    "Do not change any other file. Finish with a status report of at most three lines."
)
PROMPT_B = (
    "Next change, using what you learned earlier in this session:\n"
    "1. In pkg/release.py set RELEASE_TOKEN to the release token that tools/issue_token.py "
    "issued earlier in this session (it cannot be issued again).\n"
    "2. In pkg/guard.py set DRIFT_TOLERANCE to the tolerance tools/probe.py reported earlier "
    "in this session, and implement check_drift(value): raise GuardError, with the error code "
    "the probe reported in the message, when value exceeds DRIFT_TOLERANCE; return None "
    "otherwise.\n"
    "3. In pkg/deadlines.py implement grace_deadline(start): start moved forward by the "
    "package's grace window (the constant already defined in pkg/, in days) counted as "
    "working days, using the package's existing working-day helper.\n"
    "Keep the tests in tests/ passing. Do not guess a value you cannot find: say so instead."
)

_lock = threading.Lock()


# ---- small helpers --------------------------------------------------------------------


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def _append(path: Path, row: dict[str, Any]) -> None:
    with _lock, path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(row) + "\n")


def claude_spent() -> float:
    a = sum(r.get("cost_usd", 0.0) for r in _rows(HERE / "phase-a.jsonl"))
    b = sum(
        r["compact"].get("cost_usd", 0.0) + r["b"].get("cost_usd", 0.0)
        for r in _rows(HERE / "runs.jsonl")
    )
    return a + b


def jev_spent() -> float:
    return sum(r.get("jev_usd", 0.0) for r in _rows(HERE / "runs.jsonl"))


def child_env(arm: str | None, evidence: Path, keyfile: Path | None) -> dict[str, str]:
    """The session's environment: no Anthropic or TypeSafe credential, no sanchopanza vars
    except, in a pruning arm, the hook's own two and the function-hooks switch."""
    drop = ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "TYPESAFE_API_KEY")
    env = {
        k: v for k, v in os.environ.items()
        if k not in drop and not k.startswith(("SANCHOPANZA_", "SANCHO_"))
    }  # fmt: skip
    if arm in (None, "N"):
        return env
    parts = [PYTHON, WRAPPER, arm, str(evidence)]
    if arm in JEV_ARMS:
        parts.append(str(keyfile))
    if any(" " in p for p in parts):
        raise SystemExit(f"the hook splits its command on whitespace; a path has a space: {parts}")
    return {
        **env,
        "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1",
        "SANCHOPANZA_COMPACT_COMMAND": " ".join(parts),
        "SANCHOPANZA_COMPACT_MARKER": str(evidence / "marker.txt"),
    }


def claude(prompt: str, *, resume: str | None = None, fork: bool = False,
           plugin: Path | None = None) -> list[str]:  # fmt: skip
    cmd = ["claude", "-p", prompt, "--model", MODEL, "--max-budget-usd", f"{SESSION_CAP:.2f}",
           "--output-format", "json", "--setting-sources", "project", "--strict-mcp-config",
           "--permission-mode", "dontAsk"]  # fmt: skip
    if resume:
        cmd += ["--resume", resume]
    if fork:
        cmd += ["--fork-session"]
    if plugin is not None:
        cmd += ["--plugin-dir", str(plugin)]
    return [*cmd, "--allowedTools", *TOOLS]


def session(cmd: list[str], cwd: Path, env: dict[str, str], out: Path) -> dict[str, Any]:
    started = time.time()
    proc = subprocess.run(
        cmd, cwd=cwd, env=env, capture_output=True, text=True, encoding="utf-8",
        timeout=TIMEOUT, stdin=subprocess.DEVNULL,
    )  # fmt: skip
    seconds = round(time.time() - started, 1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(proc.stdout or "", encoding="utf-8")
    out.with_suffix(".stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        result = {}
    usage = result.get("usage") or {}
    return {
        "exit": proc.returncode,
        "seconds": seconds,
        "session_id": result.get("session_id"),
        "subtype": result.get("subtype"),
        "is_error": result.get("is_error"),
        "turns": result.get("num_turns"),
        "cost_usd": float(result.get("total_cost_usd") or 0.0),
        "usage": {
            k: usage.get(k, 0)
            for k in (
                "input_tokens",
                "cache_creation_input_tokens",
                "cache_read_input_tokens",
                "output_tokens",
            )
        },  # fmt: skip
        "result_text": str(result.get("result") or "")[:600],
    }


# ---- gates ----------------------------------------------------------------------------


# Rounds 1-2: the run's own rows. Amendment R3 (t07-t12): that round's true cost, stop 6.50.
BUDGET = {"spent": claude_spent, "stop": CLAUDE_STOP}


def use_round3_budget() -> None:
    import round3

    BUDGET.update(spent=round3.spent, stop=round3.CLAUDE_STOP)


class Gate:
    """The spend ceiling, with every session in flight holding its per-session cap."""

    def __init__(self) -> None:
        self.flight = 0
        self.stopped = False
        self.lock = threading.Lock()

    def enter(self, jev: bool) -> bool:
        with self.lock:
            spent_now, stop = BUDGET["spent"](), BUDGET["stop"]
            reserved = spent_now + (self.flight + 1) * SESSION_CAP
            if self.stopped or reserved > stop or (jev and jev_spent() > JEV_STOP):
                self.stopped = True
                return False
            self.flight += 1
            return True

    def leave(self) -> None:
        with self.lock:
            self.flight -= 1


def gated(gate: Gate, jev: bool, fn, *args, **kw) -> dict[str, Any] | None:
    if not gate.enter(jev):
        return None
    try:
        return fn(*args, **kw)
    finally:
        gate.leave()


# ---- the phases -----------------------------------------------------------------------


def phase_a(task: str, gate: Gate) -> dict[str, Any] | None:
    done = {r["task"]: r for r in _rows(HERE / "phase-a.jsonl")}
    if task in done:
        return done[task]
    work, snap, ev = ROOT / "work" / task, ROOT / "snap" / task, ROOT / "runs" / task / "A"
    for path in (work, snap, ev):
        if path.exists():
            shutil.rmtree(path)
    shutil.copytree(ROOT / "tasks" / "repos" / task, work)
    ev.mkdir(parents=True)
    res = gated(gate, False, session, claude(PROMPT_A), work, child_env(None, ev, None),
                ev / "result.json")  # fmt: skip
    if res is None:
        return None
    tr = transcripts.find(res["session_id"])
    consumed = {
        "token": not (work / "tools" / ".token_seed").exists(),
        "probe": not (work / "tools" / ".probe_state").exists(),
    }
    tests = gen.run_tests(work, ROOT / "tasks" / "hidden" / task)
    row = {
        "task": task, **{k: v for k, v in res.items() if k != "result_text"},
        "consumed": consumed, "visible_pass": gen.facts_passed(tests["tests"])["visible"],
        "transcript": transcripts.summary_a(tr) if tr else None,
        "valid": bool(res["session_id"]) and all(consumed.values()) and res["subtype"] == "success",
    }  # fmt: skip
    shutil.copytree(work, snap)
    if tr:
        shutil.copy(tr, ev / "session.jsonl")
    _append(HERE / "phase-a.jsonl", row)
    return row


def restore(task: str) -> Path:
    work, snap = ROOT / "work" / task, ROOT / "snap" / task
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(snap, work)
    return work


def one_arm(task: str, arm: str, a: dict[str, Any], gate: Gate, plugin: Path,
            keyfile: Path | None) -> dict[str, Any] | None:  # fmt: skip
    ev = ROOT / "runs" / task / arm
    if ev.exists():
        shutil.rmtree(ev)
    ev.mkdir(parents=True)
    work = restore(task)
    env = child_env(arm, ev, keyfile)
    plug = None if arm == "N" else plugin
    jev = arm in JEV_ARMS
    before = transcripts.find(a["session_id"])
    compact = gated(gate, jev, session, claude("/compact", resume=a["session_id"], fork=True,
                    plugin=plug), work, env, ev / "compact.json")  # fmt: skip
    if compact is None:
        return None
    forked = compact["session_id"]
    tr = transcripts.find(forked) if forked else None
    b = gated(gate, jev, session, claude(PROMPT_B, resume=forked, plugin=plug), work, env,
              ev / "b.json") if forked else None  # fmt: skip
    if b is None and forked:
        return None
    b = b or {"cost_usd": 0.0, "exit": None, "subtype": "not_run"}
    tests = gen.run_tests(work, ROOT / "tasks" / "hidden" / task)
    facts = gen.facts_passed(tests["tests"])
    fact = json.loads((ROOT / "tasks" / "facts.json").read_text("utf-8"))[int(task[1:3]) - 1]
    if tr:
        shutil.copy(tr, ev / "session.jsonl")
    row = {
        "task": task, "arm": arm, "a_session": a["session_id"],
        "compact": {k: v for k, v in compact.items() if k != "result_text"},
        "b": b,
        "hook": transcripts.hook_outcome(ev) if arm != "N" else None,
        "compaction": transcripts.compaction(tr) if tr else None,
        "after": transcripts.summary_b(tr, before) if tr else None,
        "summary_keeps": transcripts.summary_keeps(tr, fact) if tr else None,
        "window_constant": transcripts.constant_used(tr, fact) if tr else None,
        "tests": tests["tests"], "facts": facts,
        "success": tests["passed"],
        "jev_usd": transcripts.jev_cost(ev),
    }  # fmt: skip
    _append(HERE / "runs.jsonl", row)
    print(json.dumps({"task": task, "arm": arm, "success": row["success"], "facts": facts,
                      "claude_total": round(claude_spent(), 4)}), flush=True)  # fmt: skip
    return row


def recollect() -> None:
    """Recompute the transcript-derived fields of every row from the saved evidence."""
    out = []
    facts = {f["task"]: f for f in json.loads((ROOT / "tasks" / "facts.json").read_text("utf-8"))}
    for r in _rows(HERE / "runs.jsonl"):
        ev = ROOT / "runs" / r["task"] / r["arm"]
        tr, a_tr = ev / "session.jsonl", ROOT / "runs" / r["task"] / "A" / "session.jsonl"
        f = facts[r["task"]]
        out.append({**r, "compaction": transcripts.compaction(tr), "after": transcripts.summary_b(tr, a_tr),  # noqa: E501
                    "summary_keeps": transcripts.summary_keeps(tr, f),
                    "window_constant": transcripts.constant_used(tr, f),
                    "hook": transcripts.hook_outcome(ev) if r["arm"] != "N" else None})  # fmt: skip
    (HERE / "runs.jsonl").write_text(
        "".join(json.dumps(r) + chr(10) for r in out), encoding="utf-8"
    )


def one_task(task: str, arms: list[str], gate: Gate, plugin: Path, keyfile: Path | None) -> None:
    a = phase_a(task, gate)
    if a is None:
        return
    if not a["valid"]:
        print(json.dumps({"task": task, "excluded": "phase A invalid", "row": a}), flush=True)
        return
    done = {(r["task"], r["arm"]) for r in _rows(HERE / "runs.jsonl")}
    for arm in arms:
        if (task, arm) in done:
            continue
        if one_arm(task, arm, a, gate, plugin, keyfile) is None:
            return


# ---- setup ----------------------------------------------------------------------------


def prepare() -> Path:
    """Tasks and plugin under ROOT; checks the generator gives the registered fingerprint."""
    out = ROOT / "tasks"
    if not (out / "facts.json").exists():
        gen.build(out)
    digest = gen.tree_digest(out / "repos")
    registered = (HERE / "tasks.sha256").read_text("utf-8").split()[0]
    if digest != registered:
        raise SystemExit(f"task fingerprint {digest} is not the registered {registered}")
    plugin = ROOT / "plugin"
    subprocess.run(
        [SANCHO, "install", *PRE_0930, "--compact", "--plugin-dir", str(plugin),
         "--path", str(ROOT / "install-settings.json"), "--write"],
        check=True, capture_output=True, text=True,
    )  # fmt: skip
    return plugin


def keyfile_for(arms: list[str]) -> Path | None:
    if not any(a in JEV_ARMS for a in arms):
        return None
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        raise SystemExit("arms S and F need TYPESAFE_API_KEY in this process's environment")
    path = ROOT / ".jev-key"
    path.write_text(key, encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def marketplaces() -> list[str]:
    if not KNOWN_MARKETPLACES.exists():
        return []
    return sorted(json.loads(KNOWN_MARKETPLACES.read_text("utf-8")))


def estimate(arms: list[str], n: int) -> str:
    a_rows = _rows(HERE / "phase-a.jsonl")
    runs = _rows(HERE / "runs.jsonl")
    a_mean = sum(r["cost_usd"] for r in a_rows) / len(a_rows) if a_rows else 0.20
    arm_mean = {}
    for arm in arms:
        rs = [r for r in runs if r["arm"] == arm]
        prior = 0.20 if arm == "N" else 0.15
        arm_mean[arm] = (
            sum(r["compact"]["cost_usd"] + r["b"]["cost_usd"] for r in rs) / len(rs)
            if rs
            else prior
        )
    done_a = {r["task"] for r in a_rows}
    done = {(r["task"], r["arm"]) for r in runs}
    names = [f"t{i + 1:02d}-{gen.DOMAINS[i][0]}" for i in range(n)]
    todo = sum(a_mean for t in names if t not in done_a) + sum(
        arm_mean[arm] for t in names for arm in arms if (t, arm) not in done
    )
    return (
        f"to run: about {todo:.2f} USD list (phase A {a_mean:.3f}/task, per arm "
        f"{ {k: round(v, 3) for k, v in arm_mean.items()} }); spent {claude_spent():.4f}; "
        f"stop at {CLAUDE_STOP:.2f}, ceiling {CLAUDE_TOTAL:.2f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("estimate", "run", "recollect"))
    parser.add_argument("--arms", default="N,R")
    parser.add_argument("--tasks", default="")
    parser.add_argument("--workers", type=int, default=WORKERS)
    args = parser.parse_args(argv)
    arms = [a for a in args.arms.split(",") if a]
    if any(a not in ARMS for a in arms):
        raise SystemExit(f"arms are {ARMS}")
    names = [f"t{i + 1:02d}-{gen.DOMAINS[i][0]}" for i in range(gen.N_TASKS)]
    chosen = [t for t in names if t in args.tasks.split(",")] if args.tasks else names[:TASKS_RUN]
    print(estimate(arms, TASKS_RUN), flush=True)
    if args.action == "estimate":
        return 0
    if args.action == "recollect":
        recollect()
        return 0
    import round3

    if chosen and set(chosen) <= set(round3.TASKS):
        use_round3_budget()
        print(f"round 3 budget: spent {round3.spent():.4f} USD (true cost), stop "
              f"{round3.CLAUDE_STOP:.2f}", flush=True)  # fmt: skip
    elif set(chosen) & set(round3.TASKS):
        raise SystemExit("mix of round-3 and earlier tasks: run t07-t12 on their own")
    plugin = prepare()
    keyfile = keyfile_for(arms)
    before = marketplaces()
    gate = Gate()
    try:
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, WORKERS))) as pool:
            list(pool.map(lambda t: one_task(t, arms, gate, plugin, keyfile), chosen))
    finally:
        if keyfile is not None:
            keyfile.unlink(missing_ok=True)
        added = sorted(set(marketplaces()) - set(before))
        for name in added:
            subprocess.run(["claude", "plugin", "marketplace", "remove", name],
                           capture_output=True, text=True)  # fmt: skip
        print(json.dumps({"marketplaces_added_and_removed": added}), flush=True)
    note = "STOPPED at a cap" if gate.stopped else "done"
    print(f"{note}: claude {claude_spent():.4f} USD list, jev {jev_spent():.5f} USD", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
