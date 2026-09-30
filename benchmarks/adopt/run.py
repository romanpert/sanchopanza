"""Claude Code alone (N) against Claude Code with `sanchopanza install` (S), on long sessions.

    python benchmarks/adopt/run.py plan  [--split dev]           # free: tasks, arms, caps
    python benchmarks/adopt/run.py run   --chains a,b --ceiling 6.0 [--model haiku]
    python benchmarks/adopt/run.py grade --chains a,b            # Docker, free

One chain = one Claude Code session per arm: the chain's bugs are asked one after another, each
as its own `claude -p` call resuming the same session. Both arms get the same working copy (the
chain's image exported, one commit), the same model, tools, budget and prompts, and the same
`runtests` command. S differs by what `sanchopanza install --scope project --write` writes in
its working copy, run through `hook_env.py` for state per session and the TypeSafe key.

Caps (list price, subscription): `--max-budget-usd` per call; CHAIN_CAP_USD per chain and arm;
`--ceiling` for the whole run, charged with each call's cap before it starts and settled with
its reported cost after. No retries: a call that fails is recorded as it ended.
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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import docker_env  # noqa: E402

PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
SANCHO = REPO / ".venv" / "Scripts" / "sanchopanza.exe"
ROOT = Path.home() / ".cache" / "sanchopanza" / "adopt"
RUNS = ROOT / "runs"
WORK = ROOT / "work"
BIN = ROOT / "bin"
MODELS = {"haiku": "claude-haiku-4-5-20251001", "sonnet": "claude-sonnet-5-5"}
ARMS = ("N", "S")
CALL_CAP_USD = 1.50  # binds only on a runaway call: at 1.20 it cut a normal pilot request
CHAIN_CAP_USD = 6.00
CALL_TIMEOUT_S = 2700
DISALLOWED = ("WebFetch", "WebSearch")  # the fix is on the web: neither arm may look it up
PROMPT = (
    "{issue}\n\n"
    "Please fix this in the repository. The project's test environment is in Docker: run tests "
    "from the repository root with `runtests <pytest arguments>` (for example "
    "`runtests tests/test_module.py -k name`); it runs pytest on your current changes. "
    "Do not commit."
)

_lock = threading.Lock()
_ledger = {"spent": 0.0, "reserved": 0.0}


# ---- setup -------------------------------------------------------------------------------------


def chains() -> dict[str, dict[str, Any]]:
    return json.loads((ROOT / "chains-validated.json").read_text(encoding="utf-8"))


def shim() -> list[Path]:
    """`runtests` on the agents' PATH: a `#!` file for Git Bash, and `runtests.cmd` in a folder
    ahead of it for PowerShell, which treats the extensionless file as a document and makes
    Windows ask the person at the desk which program should open it (seen in the pilot)."""
    script = (HERE / "runtests.py").as_posix()
    BIN.mkdir(parents=True, exist_ok=True)
    (BIN / "runtests").write_text(f'#!/bin/sh\nexec "{PYTHON.as_posix()}" "{script}" "$@"\n',
                                  encoding="utf-8", newline="\n")  # fmt: skip
    windows = BIN / "win"
    windows.mkdir(exist_ok=True)
    (windows / "runtests.cmd").write_text(f'@"{PYTHON}" "{HERE / "runtests.py"}" %*\r\n',
                                          encoding="utf-8", newline="")  # fmt: skip
    return [windows, BIN]


def child_env(tag: str, base: str) -> dict[str, str]:
    """The subscription, not a key; nothing of the coordinating session; runtests configured."""
    drop = ("ANTHROPIC_", "CLAUDE_CODE_", "CLAUDE_EFFORT", "CLAUDECODE", "CLAUDE_AGENT_SDK",
            "CLAUDE_PID", "SANCHOPANZA_", "SANCHO_", "TYPESAFE_")  # fmt: skip
    env = {k: v for k, v in os.environ.items() if not k.startswith(drop)}
    # Not the sanchopanza venv: its `python` (pytest 9, no project deps) was on the agents' PATH
    # in the pilot and they ran the tests locally against it. Hooks use absolute paths.
    path = os.pathsep.join([*(str(p) for p in shim()), env.get("PATH", "")])
    return {**env, "PATH": path, "ADOPT_TAG": tag, "ADOPT_BASE": base}


def install_sancho(work: Path, evidence: Path, keyfile: Path) -> Path:
    """`sanchopanza install --scope project --write` as a user would run it, then each hook and
    the MCP server through hook_env.py (state per session, the key out of the agent's reach)."""
    env = child_env("", "")
    done = subprocess.run([str(SANCHO), "install", "--scope", "project", "--write"], cwd=work,
                          env=env, capture_output=True, text=True)  # fmt: skip
    (evidence / "install.txt").write_text(done.stdout + done.stderr, encoding="utf-8")
    if done.returncode != 0:
        raise RuntimeError(f"install failed: {done.stderr[-400:]}")
    prefix = " ".join(p.as_posix() for p in (PYTHON, HERE / "hook_env.py", evidence, keyfile))
    settings = work / ".claude" / "settings.json"
    text = settings.read_text(encoding="utf-8").replace('"sanchopanza ', f'"{prefix} ')
    settings.write_text(text, encoding="utf-8", newline="\n")
    mcp = work / ".mcp.json"
    data = json.loads(mcp.read_text(encoding="utf-8"))
    for server in data.get("mcpServers", {}).values():
        if server.get("command") == "sanchopanza":
            server["command"] = PYTHON.as_posix()
            server["args"] = [(HERE / "hook_env.py").as_posix(), evidence.as_posix(),
                              keyfile.as_posix(), *server.get("args", [])]  # fmt: skip
    mcp.write_text(json.dumps(data, indent=2), encoding="utf-8", newline="\n")
    shutil.copy(settings, evidence / "settings.json")
    shutil.copy(mcp, evidence / "mcp.json")
    return mcp


def command(model: str, prompt: str, session: str | None, mcp: Path | None) -> list[str]:
    cmd = ["claude", "-p", prompt, "--model", model, "--max-budget-usd", f"{CALL_CAP_USD:.2f}",
           "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
           "--strict-mcp-config", "--permission-mode", "bypassPermissions",
           "--disallowedTools", *DISALLOWED]  # fmt: skip
    if mcp is not None:
        cmd += ["--mcp-config", str(mcp)]
    if session:
        cmd += ["--resume", session]
    return cmd


# ---- money ---------------------------------------------------------------------------------------


def reserve(ceiling: float) -> bool:
    with _lock:
        if _ledger["spent"] + _ledger["reserved"] + CALL_CAP_USD > ceiling:
            return False
        _ledger["reserved"] += CALL_CAP_USD
        return True


def settle(cost: float) -> None:
    with _lock:
        _ledger["reserved"] -= CALL_CAP_USD
        _ledger["spent"] += cost


def spent_so_far() -> float:
    total = 0.0
    for row in RUNS.glob("*/*/row.json"):
        total += sum(c.get("cost_usd", 0.0) for c in json.loads(row.read_text("utf-8"))["calls"])
    return total


# ---- one call, one chain -------------------------------------------------------------------------


def facts(stream: Path) -> dict[str, Any]:
    """What a call did, from its stream: the result, tools, compactions, the session id."""
    result: dict[str, Any] = {}
    calls: Counter[str] = Counter()
    compactions: list[dict[str, Any]] = []
    session = ""
    for line in stream.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        session = str(event.get("session_id") or session)
        if event.get("type") == "result":
            result = event
        elif event.get("type") == "system" and event.get("subtype") == "compact_boundary":
            compactions.append(event.get("compact_metadata") or event.get("compactMetadata") or {})
        elif event.get("type") == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    calls[str(block.get("name"))] += 1
    usage = result.get("usage") or {}
    return {"session": session, "subtype": result.get("subtype"), "turns": result.get("num_turns"),
            "cost_usd": float(result.get("total_cost_usd") or 0.0),
            "duration_s": round(float(result.get("duration_ms") or 0) / 1000, 1),
            "input_tokens": int(usage.get("input_tokens") or 0),
            "cache_read": int(usage.get("cache_read_input_tokens") or 0),
            "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "tools": dict(calls), "compactions": compactions,
            "model_usage": result.get("modelUsage") or {}}  # fmt: skip


def jev_usd(evidence: Path) -> float:
    path = evidence / "journal.jsonl"
    total = 0.0
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                total += float((json.loads(line).get("data") or {}).get("cost_usd") or 0.0)
            except ValueError:
                continue
    return total


def not_run(row: dict[str, Any]) -> bool:
    return str(row.get("status", "")).startswith("NOT RUN")


def one_chain(
    chain: dict[str, Any], arm: str, model: str, ceiling: float, keyfile: Path,
    carry_on: bool = False,
) -> None:  # fmt: skip
    """The chain's requests in one session. With `carry_on`, a chain whose later requests were
    NOT RUN (a cap) goes on from the first of them, in the same session and working copy."""
    name = chain["chain"]
    evidence = RUNS / name / arm
    work = WORK / f"{name}-{arm}"
    done_row = evidence / "row.json"
    rows: list[dict[str, Any]] = []
    session: str | None = None
    if done_row.exists():
        previous = json.loads(done_row.read_text(encoding="utf-8"))
        if not carry_on or not any(not_run(r) for r in previous["calls"]):
            return  # done before: never run twice
        rows = [r for r in previous["calls"] if not not_run(r)]
        session, base = previous["session"], previous["base"]
        mcp = work / ".mcp.json" if arm == "S" else None
    else:
        docker_env.remove_tree(evidence)
        evidence.mkdir(parents=True)
        docker_env.remove_tree(work)
        base = docker_env.export(chain["tag"], work)
        mcp = install_sancho(work, evidence, keyfile) if arm == "S" else None
    env = child_env(chain["tag"], base)
    for k, bug in enumerate(chain["bugs"], start=1):
        if k <= len(rows):
            continue
        chain_cost = sum(r["cost_usd"] for r in rows)
        if chain_cost + CALL_CAP_USD > CHAIN_CAP_USD or not reserve(ceiling):
            rows.append({"request": k, "status": "NOT RUN (cap)", "cost_usd": 0.0})
            continue
        stream = evidence / f"stream-{k}.jsonl"
        prompt = PROMPT.format(issue=bug["problem_statement"].strip())
        began = time.time()
        with stream.open("wb") as out:
            try:
                code = subprocess.run(command(model, prompt, session, mcp), cwd=work, env=env,
                                      stdout=out, stderr=subprocess.PIPE,
                                      timeout=CALL_TIMEOUT_S).returncode  # fmt: skip
            except subprocess.TimeoutExpired:
                code = -9
        seen = facts(stream)
        # A resumed session reports its cost so far, not this call's (pilot, 2026-09-30).
        before = max((r.get("cost_cumulative", 0.0) for r in rows), default=0.0)
        if seen["cost_usd"]:
            seen = {**seen, "cost_cumulative": seen["cost_usd"],
                    "cost_usd": round(seen["cost_usd"] - before, 6)}  # fmt: skip
        else:  # no result: the call was cut; charge its cap
            seen = {**seen, "cost_cumulative": before,
                    "cost_usd": CALL_CAP_USD if code == -9 else 0.0}  # fmt: skip
        settle(seen["cost_usd"])
        session = seen["session"] or session
        (evidence / f"diff-{k}.patch").write_text(docker_env.agent_diff(work, base),
                                                   encoding="utf-8", newline="\n")  # fmt: skip
        rows.append({"request": k, "instance_id": bug["instance_id"], "exit": code,
                     "wall_s": round(time.time() - began, 1), **seen})  # fmt: skip
        print(f"{name} {arm} request {k}: {seen['subtype']} {seen['cost_usd']:.3f} USD "
              f"{len(seen['compactions'])} compactions", flush=True)
    final = docker_env.agent_diff(work, base)
    (evidence / "final.patch").write_text(final, encoding="utf-8", newline="\n")
    transcript = next(Path.home().joinpath(".claude", "projects").glob(f"*/{session}.jsonl"), None)
    if session and transcript:
        shutil.copy(transcript, evidence / "transcript.jsonl")
    row = {"chain": name, "arm": arm, "model": model, "base": base, "session": session,
           "wall_s": round(sum(r.get("wall_s") or 0.0 for r in rows), 1),
           "jev_usd": jev_usd(evidence), "calls": rows}  # fmt: skip
    (evidence / "row.json").write_text(json.dumps(row, indent=1), encoding="utf-8")


# ---- grading -------------------------------------------------------------------------------------


def grade_chain(chain: dict[str, Any], arm: str) -> dict[str, Any]:
    evidence = RUNS / chain["chain"] / arm
    patch = (evidence / "final.patch").read_text(encoding="utf-8")
    nodes = [n for b in chain["bugs"] for n in (*b["FAIL_TO_PASS"], *b["PASS_TO_PASS_STAR"])]
    outcome = docker_env.pytest(chain["tag"], patch, list(dict.fromkeys(nodes)))
    bugs = []
    for bug in chain["bugs"]:
        f2p = [outcome.get(t) == "PASSED" for t in bug["FAIL_TO_PASS"]]
        p2p = [outcome.get(t) == "PASSED" for t in bug["PASS_TO_PASS_STAR"]]
        bugs.append({"instance_id": bug["instance_id"], "resolved": all(f2p) and all(p2p),
                     "f2p_passed": sum(f2p), "f2p": len(f2p), "p2p_broken": p2p.count(False),
                     "patch_applied": "<patch>" not in outcome})  # fmt: skip
    grade = {"chain": chain["chain"], "arm": arm, "resolved": sum(b["resolved"] for b in bugs),
             "bugs": bugs}  # fmt: skip
    (evidence / "grade.json").write_text(json.dumps(grade, indent=1), encoding="utf-8")
    return grade


# ---- entry -----------------------------------------------------------------------------------


def keyfile_from_indagis() -> Path:
    """The TypeSafe key for the S arm's hooks, from the owner's Indagis .env; never printed."""
    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if not key:
        env_file = Path(r"C:\Users\roman\Desktop\proyectos\apps\indagis\.env")
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"')
    if not key:
        raise SystemExit("no TypeSafe key: the S arm would run without its decider")
    path = ROOT / "typesafe.key"
    path.write_text(key, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("plan", "run", "grade"))
    parser.add_argument("--chains", default="")
    parser.add_argument("--split", default="dev")
    parser.add_argument("--model", default="haiku", choices=sorted(MODELS))
    parser.add_argument("--ceiling", type=float, default=0.0)
    parser.add_argument("--continue", dest="carry_on", action="store_true",
                        help="go on with chains whose later requests were NOT RUN")
    args = parser.parse_args(argv)
    known = chains()
    wanted = [c for c in args.chains.split(",") if c] or [
        n for n, c in known.items() if c["split"] == args.split
    ]
    if args.action == "plan":
        for n in wanted:
            c = known[n]
            print(n, c["split"], "valid" if c["valid"] else "INVALID", len(c["bugs"]), "bugs")
        print(f"arms {ARMS}; per call {CALL_CAP_USD} USD; per chain and arm {CHAIN_CAP_USD} USD; "
              f"spent so far {spent_so_far():.2f} USD")  # fmt: skip
        return 0
    if args.action == "grade":
        for n in wanted:
            for arm in ARMS:
                if (RUNS / n / arm / "final.patch").exists():
                    g = grade_chain(known[n], arm)
                    print(n, arm, g["resolved"], "of", len(g["bugs"]))
        return 0
    if args.ceiling <= 0:
        raise SystemExit("--ceiling is required and must be positive")
    with _lock:
        _ledger["spent"] = spent_so_far()
    keyfile = keyfile_from_indagis()
    try:
        for n in wanted:
            chain = known[n]
            if not chain["valid"]:
                print(f"{n}: invalid, skipped")
                continue
            with ThreadPoolExecutor(max_workers=len(ARMS)) as pool:
                list(pool.map(lambda arm, c=chain: one_chain(c, arm, MODELS[args.model],
                                                             args.ceiling, keyfile,
                                                             args.carry_on), ARMS))
    finally:
        keyfile.unlink(missing_ok=True)
    print(f"spent {_ledger['spent']:.2f} USD (list price)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
