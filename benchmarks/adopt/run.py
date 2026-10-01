"""Claude Code alone (N) against Claude Code with `sanchopanza install` (S), on long sessions.

    python benchmarks/adopt/run.py plan  [--split dev]           # free: tasks, arms, caps
    python benchmarks/adopt/run.py run   --chains a,b --ceiling 6.0 [--model haiku]
    python benchmarks/adopt/run.py grade --chains a,b            # Docker, free
    ... --arms Nf,Sf                                             # other arms (ARM_SPECS)

One chain = one Claude Code session per arm: the chain's bugs are asked one after another, each
as its own `claude -p` call resuming the same session. Both arms get the same working copy (the
chain's image exported, one commit), the same model, tools, budget and prompts, and the same
`runtests` command. S differs by what `sanchopanza install --scope project --write` writes in
its working copy, run through `hook_env.py` for state per session and the TypeSafe key.

Other arms (`--arms`, `ARM_SPECS`): `Nf` and `Sf` ask each request in a NEW session in the
same working copy (Claude Code alone; with the default install plus `--memory`), and `Sm`
keeps one session with the default install plus `--memory` and a 100k context budget, so
memory between messages works after the compactions that budget causes. `Sfn` and `Sb` are
their controls without memory (the default install fresh; the 100k budget alone). N and S are
as they were.

Caps (list price, subscription): `--max-budget-usd` per call (`--call-cap`, CALL_CAP_USD by
default); `--chain-cap` per chain and arm (CHAIN_CAP_USD); `--ceiling` for everything under
RUNS, earlier runs included, charged with each call's cap before it starts and settled with its
reported cost after. Held-out and combined chains (and any with `--whole`) go all or nothing:
the chain cap of every arm is held before any arm starts, or the chain is not run. Held-out
chains run only once the confirmation is sealed (`confirm.seal_holds`); combined chains only
when named, with `--model`. No retries: a call that fails is recorded as it ended.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))

import docker_env  # noqa: E402

PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
# The sanchopanza the S arms install and run: the editable development one unless ADOPT_SANCHO
# names a frozen copy (`freeze.py`), which held-out tasks require.
SANCHO = Path(os.environ.get("ADOPT_SANCHO") or REPO / ".venv" / "Scripts" / "sanchopanza.exe")
ROOT = Path.home() / ".cache" / "sanchopanza" / "adopt"
RUNS = ROOT / "runs"
WORK = ROOT / "work"
BIN = ROOT / "bin"
MODELS = {"haiku": "claude-haiku-4-5-20251001", "sonnet": "claude-sonnet-5-5"}
ARMS = ("N", "S")
# What held-out tasks run with, as `prereg-confirm.md` fixes it, enforced here and not left to
# the command line: the frozen sanchopanza, phase A's model and caps, and Claude Code's version.
HELD_COMMIT = "eebdfa692f53ce4198b467649b7ae1845f0d68fc"
HELD_MODEL, HELD_CALL_CAP, HELD_CHAIN_CAP = "haiku", 1.50, 6.00
CLAUDE_VERSION = "2.1.285"


@dataclass(frozen=True)
class Arm:
    install: tuple[str, ...] | None  # None: Claude Code alone; else extra `install` flags
    fresh: bool = False  # each request in a new session


ARM_SPECS = {
    "N": Arm(None),
    "S": Arm(()),
    "Nf": Arm(None, fresh=True),
    "Sf": Arm(("--memory",), fresh=True),
    "Sm": Arm(("--memory", "--context-budget", "100000")),
    # Controls, so that a difference can be put down to memory alone: Sf against Sfn, Sm against Sb.
    "Sfn": Arm((), fresh=True),
    "Sb": Arm(("--context-budget", "100000")),
}
# Chains that run only when named, on a model named (combined.py, long.py): a default run must
# not spend them on the wrong model, since a chain never runs twice.
NAMED_ONLY = ("combined", "long")
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


def set_caps(call: float, chain: float) -> None:
    """The run's caps, from the command line (the defaults above unless given). A call cap
    above the chain cap could never let a call start, so it is refused."""
    global CALL_CAP_USD, CHAIN_CAP_USD
    if not 0 < call <= chain:
        raise SystemExit(f"caps must satisfy 0 < call ({call}) <= chain ({chain})")
    CALL_CAP_USD, CHAIN_CAP_USD = call, chain


# ---- setup -------------------------------------------------------------------------------------


def chains() -> dict[str, dict[str, Any]]:
    return json.loads((ROOT / "chains-validated.json").read_text(encoding="utf-8"))


def chain_digest(chain: dict[str, Any]) -> str:
    """sha256 of what a chain's sessions and grade read from the cache: image, tag and bugs
    (prompts, patches, FAIL_TO_PASS, PASS_TO_PASS*). The sealed summary keeps it."""
    body = {k: chain.get(k) for k in ("image", "tag", "bugs")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def summary_digest(name: str) -> str | None:
    summary = json.loads((HERE / "chains-validated-summary.json").read_text(encoding="utf-8"))
    return summary.get(name, {}).get("sha256")


def claude_version() -> str:
    try:
        done = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=60,
                              shell=os.name == "nt")  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return done.stdout.strip().split(" ", 1)[0]


def held_refusal(model: str | None, call_cap: float, chain_cap: float) -> str | None:
    """Why held-out tasks may not run with these settings, or None."""
    stamp = frozen_stamp() or {}
    if not sealed():
        return "held-out tasks run only once the confirmation is sealed"
    if stamp.get("commit") != HELD_COMMIT:
        return f"held-out tasks run the frozen sanchopanza {HELD_COMMIT[:12]}: set ADOPT_SANCHO"
    if (model or HELD_MODEL) != HELD_MODEL:
        return f"held-out tasks run on {HELD_MODEL}"
    if call_cap > HELD_CALL_CAP or chain_cap > HELD_CHAIN_CAP:
        return f"held-out caps are {HELD_CALL_CAP} per call and {HELD_CHAIN_CAP} per chain and arm"
    if (found := claude_version()) != CLAUDE_VERSION:
        return f"held-out tasks run Claude Code {CLAUDE_VERSION}, found {found or 'none'}"
    return None


def stale_held(known: dict[str, dict[str, Any]], names: list[str]) -> list[str]:
    """Held-out chains whose cache entry is not the one the sealed summary hashed."""
    return [n for n in names if known[n]["split"] == "held"
            and chain_digest(known[n]) != summary_digest(n)]  # fmt: skip


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
    # DISABLE_AUTOUPDATER: Claude Code must not update itself in the middle of a batch.
    return {**env, "PATH": path, "ADOPT_TAG": tag, "ADOPT_BASE": base, "ADOPT_SANCHO": str(SANCHO),
            "DISABLE_AUTOUPDATER": "1"}  # fmt: skip


def install_sancho(
    work: Path, evidence: Path, keyfile: Path, extra: tuple[str, ...] = ()
) -> Path:
    """`sanchopanza install --scope project --write [extra]` as a user would run it, then each
    hook and the MCP server through hook_env.py (state per session, the key out of the agent's
    reach)."""
    env = child_env("", "")
    done = subprocess.run([str(SANCHO), "install", "--scope", "project", "--write", *extra],
                          cwd=work, env=env, capture_output=True, text=True)  # fmt: skip
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
    snapshot_install(work, evidence)
    return mcp


INSTALL_COPY = "install"  # under the evidence: the install files as written, to check against


def install_files(work: Path) -> list[Path]:
    return sorted(p for p in [*(work / ".claude").rglob("*"), work / ".mcp.json"] if p.is_file())


def snapshot_install(work: Path, evidence: Path) -> None:
    for path in install_files(work):
        copy = evidence / INSTALL_COPY / path.relative_to(work)
        copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, copy)


def restore_install(work: Path, evidence: Path) -> list[str]:
    """Put back any install file the agent changed or removed (a `git checkout .` or a clean
    in development batch 2 left an S arm without hooks mid-chain), and say which."""
    saved = evidence / INSTALL_COPY
    restored = []
    for copy in sorted(p for p in saved.rglob("*") if p.is_file()):
        target = work / copy.relative_to(saved)
        if not target.is_file() or target.read_bytes() != copy.read_bytes():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(copy, target)
            restored.append(copy.relative_to(saved).as_posix())
    return restored


# Windows caps a command line at 32,767 characters: a longer prompt failed CreateProcess
# (pydantic-2's second issue, 34,215, phase A). Over this it goes through stdin, the same text.
ARGV_PROMPT_MAX = 16_000


def stdin_for(prompt: str) -> bytes | None:
    return prompt.encode("utf-8") if len(prompt) > ARGV_PROMPT_MAX else None


def command(model: str, prompt: str, session: str | None, mcp: Path | None) -> list[str]:
    asked = [] if stdin_for(prompt) else [prompt]
    cmd = ["claude", "-p", *asked, "--model", model, "--max-budget-usd", f"{CALL_CAP_USD:.2f}",
           "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
           "--strict-mcp-config", "--permission-mode", "bypassPermissions",
           "--disallowedTools", *DISALLOWED]  # fmt: skip
    if mcp is not None:
        cmd += ["--mcp-config", str(mcp)]
    if session:
        cmd += ["--resume", session]
    return cmd


# ---- money ---------------------------------------------------------------------------------------


def reserve(ceiling: float, amount: float | None = None) -> bool:
    """Hold `amount` (a call's cap by default) against the ceiling, or say it does not fit."""
    amount = CALL_CAP_USD if amount is None else amount
    with _lock:
        if _ledger["spent"] + _ledger["reserved"] + amount > ceiling:
            return False
        _ledger["reserved"] += amount
        return True


def release(amount: float) -> None:
    with _lock:
        _ledger["reserved"] -= amount


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
            # An API or usage-limit error, not a cap: `error_max_budget_usd` and
            # `error_max_turns` also carry is_error, and those requests did run.
            "api_error": bool(result.get("is_error"))
            and result.get("subtype") in ("success", "error_during_execution"),
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


def call_cost(
    seen: dict[str, Any], rows: list[dict[str, Any]], *, fresh: bool, code: int
) -> dict[str, Any]:
    """`seen` with this call's own cost. A resumed session reports its cost so far, not this
    call's (pilot, 2026-09-30); a fresh session reports its own. A call cut before its result
    (timeout) is charged its cap."""
    earlier = (r.get("cost_cumulative", 0.0) for r in rows)
    before = 0.0 if fresh else max(earlier, default=0.0)
    if seen["cost_usd"]:
        return {**seen, "cost_cumulative": seen["cost_usd"],
                "cost_usd": round(max(seen["cost_usd"] - before, 0.0), 6)}  # fmt: skip
    if code == -9:
        # Charged its cap, and counted as spent in the session's running total: the next call
        # of a resumed session reports the cut call's partial cost inside its cumulative one,
        # which would otherwise be charged a second time.
        return {**seen, "cost_cumulative": before + CALL_CAP_USD, "cost_usd": CALL_CAP_USD}
    return {**seen, "cost_cumulative": before, "cost_usd": 0.0}


def harness_failed(code: int, seen: dict[str, Any]) -> bool:
    """`claude -p` exited without opening a session: no session id, no result, nothing spent.
    Not a result of the arm: recorded NOT RUN (harness), its stderr kept, for `--continue`."""
    return code not in (0, -9) and not seen["session"] and seen["subtype"] is None and not (
        seen["cost_usd"]
    )


def not_run(row: dict[str, Any]) -> bool:
    return str(row.get("status", "")).startswith("NOT RUN")


CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"


def projects_dir(work: Path) -> Path:
    """Where Claude Code keeps the sessions of a working copy; memory catches up from it."""
    return CLAUDE_PROJECTS / "".join(c if c.isascii() and c.isalnum() else "-" for c in str(work))


def held_start_refusal(chain: dict[str, Any], work: Path, previous: dict[str, Any] | None) -> str:
    """Amendment 2. A held-out arm an error result stopped is set aside and run whole, never
    continued (a cut request leaves its context and edits behind); and no held-out arm starts
    over sessions an earlier attempt left in its Claude Code folder (pydantic-2 Sm, phase A: its
    memory caught up the crashed attempt's session of the same chain)."""
    if chain["split"] != "held":
        return ""
    if previous and any(c.get("status") == "NOT RUN (error result)" for c in previous["calls"]):
        return "an error result stopped it: set the attempt aside and run it whole"
    if not previous and any(projects_dir(work).glob("*.jsonl")):
        return f"earlier sessions in {projects_dir(work)}: set them aside first"
    return ""


def one_chain(
    chain: dict[str, Any], arm: str, model: str, ceiling: float, keyfile: Path,
    carry_on: bool = False,
    rep: int = 1,
) -> None:  # fmt: skip
    """The chain's requests in one session. With `carry_on`, a chain whose later requests were
    NOT RUN (a cap) goes on from the first of them, in the same session and working copy."""
    name = run_name(chain["chain"], rep)
    spec = ARM_SPECS[arm]
    evidence = RUNS / name / arm
    work = WORK / f"{name}-{arm}"
    done_row = evidence / "row.json"
    rows: list[dict[str, Any]] = []
    session: str | None = None
    previous = json.loads(done_row.read_text(encoding="utf-8")) if done_row.exists() else None
    if previous and (not carry_on or not any(not_run(r) for r in previous["calls"])):
        return  # done before: never run twice
    if why := held_start_refusal(chain, work, previous):
        raise RuntimeError(f"{name} {arm}: {why}")
    if previous:
        rows = [r for r in previous["calls"] if not not_run(r)]
        session, base = previous["session"], previous["base"]
        mcp = work / ".mcp.json" if spec.install is not None else None
    else:
        if chain["split"] == "held" and evidence.exists():
            # A held-out arm started before and left no row (a crash): never run again, its
            # spend would go uncounted and the pair would mix attempts. Look at it by hand.
            raise RuntimeError(f"{name} {arm}: evidence of an earlier attempt and no row.json")
        docker_env.remove_tree(evidence)
        evidence.mkdir(parents=True)
        docker_env.remove_tree(work)
        base = docker_env.export(chain["tag"], work)
        mcp = None
        if spec.install is not None:
            mcp = install_sancho(work, evidence, keyfile, spec.install)
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
        if spec.fresh:
            session = None  # a new session per request, in the same working copy
        restored = restore_install(work, evidence) if spec.install is not None else []
        if restored:
            print(f"{name} {arm} request {k}: install files restored {restored}", flush=True)
        began = time.time()
        err = evidence / f"stream-{k}.err"
        with stream.open("wb") as out, err.open("wb") as errors:
            try:
                code = subprocess.run(command(model, prompt, session, mcp), cwd=work, env=env,
                                      input=stdin_for(prompt), stdout=out, stderr=errors,
                                      timeout=CALL_TIMEOUT_S).returncode  # fmt: skip
            except subprocess.TimeoutExpired:
                code = -9
            except OSError as exc:  # could not even start `claude`: the harness, not the arm
                errors.write(f"{type(exc).__name__}: {exc}".encode())
                code = -1
        observed = facts(stream)
        if harness_failed(code, observed):
            settle(0.0)  # its reservation back: nothing was spent
            tail = err.read_text(encoding="utf-8", errors="replace")[-400:]
            rows.extend({"request": j, "instance_id": b["instance_id"], "exit": code,
                         "status": "NOT RUN (harness)", "cost_usd": 0.0, "stderr": tail}
                        for j, b in enumerate(chain["bugs"][k - 1:], start=k))  # fmt: skip
            print(f"{name} {arm} request {k}: claude -p did not start (exit {code}); the arm "
                  "stops here, --continue goes on from it", flush=True)  # fmt: skip
            break
        seen = call_cost(observed, rows, fresh=spec.fresh, code=code)
        settle(seen["cost_usd"])
        session = seen["session"] or session
        if seen["api_error"]:
            # An API or usage-limit error reported as a result: not a request the arm ran. Its
            # cost is kept; the arm stops here, as when `claude -p` does not start.
            rows.append({"request": k, "instance_id": bug["instance_id"], "exit": code,
                         "status": "NOT RUN (error result)", **seen})  # fmt: skip
            rows.extend({"request": j, "instance_id": b["instance_id"], "cost_usd": 0.0,
                         "status": "NOT RUN (harness)"}
                        for j, b in enumerate(chain["bugs"][k:], start=k + 1))  # fmt: skip
            print(f"{name} {arm} request {k}: error result, the arm stops here", flush=True)
            break
        (evidence / f"diff-{k}.patch").write_text(docker_env.agent_diff(work, base),
                                                   encoding="utf-8", newline="\n")  # fmt: skip
        rows.append({"request": k, "instance_id": bug["instance_id"], "exit": code,
                     "wall_s": round(time.time() - began, 1), "install_restored": restored,
                     **seen})  # fmt: skip
        print(f"{name} {arm} request {k}: {seen['subtype']} {seen['cost_usd']:.3f} USD "
              f"{len(seen['compactions'])} compactions", flush=True)
    final = docker_env.agent_diff(work, base)
    (evidence / "final.patch").write_text(final, encoding="utf-8", newline="\n")
    sessions = list(dict.fromkeys(r["session"] for r in rows if r.get("session")))
    for n, one in enumerate(sessions, start=1):
        found = next(Path.home().joinpath(".claude", "projects").glob(f"*/{one}.jsonl"), None)
        if found:
            suffix = "" if len(sessions) == 1 else f"-{n}"
            shutil.copy(found, evidence / f"transcript{suffix}.jsonl")
    row = {"chain": name, "arm": arm, "model": model, "base": base, "session": session,
           "wall_s": round(sum(r.get("wall_s") or 0.0 for r in rows), 1),
           "jev_usd": jev_usd(evidence), "sanchopanza": provenance(),
           "claude_version": claude_version(), "calls": rows}  # fmt: skip
    (evidence / "row.json").write_text(json.dumps(row, indent=1), encoding="utf-8")


# ---- grading -------------------------------------------------------------------------------------


def run_name(chain: str, rep: int) -> str:
    """Repetition 1 keeps the chain's name (the pilot); later ones get `-r<rep>`."""
    return chain if rep == 1 else f"{chain}-r{rep}"


def grade_chain(chain: dict[str, Any], arm: str, rep: int = 1) -> dict[str, Any]:
    evidence = RUNS / run_name(chain["chain"], rep) / arm
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
    seal = REPO / "docs" / "results" / "2026-09-30-adopt" / "prereg-confirm.sha256"
    grade = {**grade, "seal": seal.read_text(encoding="utf-8").strip() if seal.exists() else None}
    (evidence / "grade.json").write_text(json.dumps(grade, indent=1), encoding="utf-8")
    return grade


# ---- entry -----------------------------------------------------------------------------------


def frozen_stamp() -> dict[str, Any] | None:
    """The stamp of the frozen copy SANCHO belongs to, or None for the editable one."""
    stamp = SANCHO.parents[1] / "stamp.json"
    return json.loads(stamp.read_text(encoding="utf-8")) if stamp.exists() else None


def provenance() -> dict[str, Any]:
    return {"exe": str(SANCHO), "frozen": frozen_stamp()}


def sealed() -> bool:
    import confirm

    return confirm.seal_holds()


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
    parser.add_argument("--model", default=None, choices=sorted(MODELS),
                        help="haiku by default; required for combined chains")
    parser.add_argument("--ceiling", type=float, default=0.0)
    parser.add_argument("--rep", type=int, default=1, help="repetition of the chains (1..)")
    parser.add_argument("--arms", default=",".join(ARMS), help="arms of ARM_SPECS to run")
    parser.add_argument("--continue", dest="carry_on", action="store_true",
                        help="go on with chains whose later requests were NOT RUN")
    parser.add_argument("--call-cap", type=float, default=CALL_CAP_USD,
                        help="USD per call (a larger model or context needs more)")
    parser.add_argument("--chain-cap", type=float, default=CHAIN_CAP_USD,
                        help="USD per chain and arm")
    parser.add_argument("--whole", action="store_true",
                        help="all or nothing per chain (always on for held-out and combined)")
    args = parser.parse_args(argv)
    set_caps(args.call_cap, args.chain_cap)
    known = chains()
    arms = tuple(a for a in args.arms.split(",") if a)
    if unknown := [a for a in arms if a not in ARM_SPECS]:
        raise SystemExit(f"unknown arms {unknown}; known: {sorted(ARM_SPECS)}")
    named = [c for c in args.chains.split(",") if c]
    # NAMED_ONLY chains run only when named, on a model named.
    wanted = named or [n for n, c in known.items()
                       if c["split"] == args.split and c.get("kind") not in NAMED_ONLY]  # fmt: skip
    if args.action == "run" and args.model is None and any(
        known[n].get("kind") in NAMED_ONLY for n in wanted
    ):
        raise SystemExit("a combined or long chain needs --model")
    model = MODELS[args.model or "haiku"]
    if args.action == "plan":
        for n in wanted:
            c = known[n]
            print(n, c["split"], "valid" if c["valid"] else "INVALID", len(c["bugs"]), "bugs")
        print(f"arms {arms}; per call {CALL_CAP_USD} USD; per chain and arm {CHAIN_CAP_USD} USD; "
              f"spent so far {spent_so_far():.2f} USD")  # fmt: skip
        return 0
    held_named = [n for n in wanted if known[n]["split"] == "held"]
    if held_named and args.action in ("run", "grade"):
        if args.action == "grade" and not sealed():
            raise SystemExit("held-out chains are graded only once the confirmation is sealed")
        if stale := stale_held(known, held_named):
            raise SystemExit(f"cache entries differ from the sealed summary: {stale}")
    if args.action == "grade":
        for n in wanted:
            for arm in arms:
                if (RUNS / run_name(n, args.rep) / arm / "final.patch").exists():
                    g = grade_chain(known[n], arm, args.rep)
                    print(n, arm, g["resolved"], "of", len(g["bugs"]))
        return 0
    if args.ceiling <= 0:
        raise SystemExit("--ceiling is required and must be positive")
    if held_named and (why := held_refusal(args.model, CALL_CAP_USD, CHAIN_CAP_USD)):
        raise SystemExit(why)
    with _lock:
        _ledger["spent"] = spent_so_far()
    keyfile = keyfile_from_indagis()
    try:
        for n in wanted:
            chain = known[n]
            if not chain["valid"]:
                print(f"{n}: invalid, skipped")
                continue
            # All or nothing (held-out and combined chains always): every arm's whole chain cap
            # is held before any arm starts, so no pair ever has one arm run and not the other
            # (the shared ledger let one arm take the room of another in development).
            whole = args.whole or chain["split"] == "held" or chain.get("kind") in NAMED_ONLY
            hold = CHAIN_CAP_USD * len(arms) if whole else 0.0
            if whole and not reserve(args.ceiling, hold):
                print(f"{n}: not run, its arms' chain caps ({hold:.2f} USD) do not fit")
                continue
            ceiling = float("inf") if whole else args.ceiling  # bounded by the chain caps
            try:
                with ThreadPoolExecutor(max_workers=len(arms)) as pool:
                    list(pool.map(lambda arm, c=chain, top=ceiling: one_chain(
                        c, arm, model, top, keyfile, args.carry_on, args.rep), arms))
            finally:
                release(hold)
    finally:
        keyfile.unlink(missing_ok=True)
    print(f"spent {_ledger['spent']:.2f} USD (list price)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
