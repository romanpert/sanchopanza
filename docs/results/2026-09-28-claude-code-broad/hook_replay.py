"""Part H of `prereg.md`: labelled tool calls through the Claude Code hook process, real Jev.

    python hook_replay.py build   --sandbox <dir> --atbench <test.json> --rjudge <clone>
    python hook_replay.py plan    --sandbox <dir>                  # free: counts and estimate
    python hook_replay.py run     --sandbox <dir> --env-file <.env> [--workers 6]
    python hook_replay.py latency --sandbox <dir> --env-file <.env>
    python hook_replay.py collect --sandbox <dir>                  # -> this dir, no network

Each hook input goes to its own process, as Claude Code runs it: `recording_hook.py` (the
`sanchopanza hook` entry point with the provider's answers written down) with exactly the
environment `sanchopanza install --provider jev --scan-content --content-tools
Read,WebFetch,WebSearch --check-done` writes. The Jev key is read from the environment or
`--env-file`, handed only to child processes, never printed or written.
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

import cases as case_builder  # noqa: E402

VENV = REPO / ".venv" / "Scripts"
PYTHON = str(VENV / "python.exe")
SANCHO = str(VENV / "sanchopanza.exe")
WRAPPER = str(HERE / "recording_hook.py")
FIXTURE = REPO / "fixtures" / "claude-code-broad-jev.jsonl"
JEV_STOP = 0.09  # prereg.md: all Jev spend of this run together, hook level and sessions
INSTALLED_ENV = {
    "SANCHOPANZA_PROVIDER": "jev",
    "SANCHOPANZA_SCAN_CONTENT": "1",
    "SANCHOPANZA_CONTENT_TOOLS": "Read,WebFetch,WebSearch",
    "SANCHOPANZA_CHECK_DONE": "1",
}
SET_ORDER = ("guard", "atbench", "rjudge", "inject-own", "inject-ad", "control", "stop")
LATENCY_PER_KIND = 10
DRY_KEY = "dry-run-no-provider"


def typesafe_key(env_file: str | None) -> str:
    if os.environ.get("TYPESAFE_API_KEY"):
        return os.environ["TYPESAFE_API_KEY"]
    if env_file:
        for line in Path(env_file).read_text(encoding="utf-8").splitlines():
            if line.startswith("TYPESAFE_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("set TYPESAFE_API_KEY or pass --env-file with a TYPESAFE_API_KEY= line")


def hook_env(key: str, journal: Path, record: Path | None) -> dict[str, str]:
    drop = {"ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN"}
    base = {k: v for k, v in os.environ.items() if k not in drop and not k.startswith("SANCHO")}
    env = {**base, **INSTALLED_ENV, "TYPESAFE_API_KEY": key, "SANCHOPANZA_JOURNAL": str(journal)}
    if key == DRY_KEY:  # the free pipeline check: no provider, nothing leaves the machine
        env = {**env, "SANCHOPANZA_PROVIDER": "null"}
    return {**env, "RECORD_OUT": str(record)} if record else env


def safe_name(case: dict[str, Any]) -> str:
    return (case["set"] + "__" + "".join(ch if ch.isalnum() else "-" for ch in case["id"]))[-180:]


def load_cases(sandbox: Path) -> list[dict[str, Any]]:
    path = sandbox / "hook-cases.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def kind_of(event: str, stdout: str) -> str:
    """What the hook told Claude Code: deny, block, note, or nothing."""
    if not stdout.strip():
        return "none"
    try:
        output = json.loads(stdout)
    except json.JSONDecodeError:
        return "unparsed"
    specific = output.get("hookSpecificOutput") or {}
    if specific.get("permissionDecision") == "deny":
        return "deny"
    if output.get("decision") == "block":
        return "block"
    if specific.get("additionalContext"):
        return "note"
    return "other"


def decisions(journal: Path) -> list[dict[str, Any]]:
    if not journal.exists():
        return []
    out = []
    for line in journal.read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("kind") != "decision":
            continue
        d = event["data"]
        outcome = d.get("outcome") or {}
        keep = ("denied", "origin", "probability", "flagged", "done", "complete", "windows")
        out.append(
            {
                "point": d.get("point"),
                "provider": d.get("provider"),
                "model": d.get("model"),
                "error": d.get("error"),
                "cost_usd": d.get("cost_usd") or 0.0,
                "latency_ms": d.get("latency_ms"),
                "input_tokens": d.get("input_tokens"),
                "outcome": {k: outcome[k] for k in keep if k in outcome},
                "answer": _truth(d.get("answers") or {}),
            }
        )
    return out


def _truth(answers: dict[str, Any]) -> float | None:
    for answer in answers.values():
        if isinstance(answer, dict) and answer.get("truth") is not None:
            return answer["truth"]
    return None


def one_case(case: dict[str, Any], sandbox: Path, key: str) -> dict[str, Any]:
    name = safe_name(case)
    journal = sandbox / "journals" / f"{name}.jsonl"
    record = sandbox / "record" / f"{name}.jsonl"
    for path in (journal, record):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)
    env = hook_env(key, journal, record)
    calls = []
    for call in case["calls"]:
        started = time.perf_counter()
        proc = subprocess.run(
            [PYTHON, WRAPPER], input=json.dumps(call), capture_output=True, text=True,
            encoding="utf-8", env=env, timeout=300,
        )  # fmt: skip
        calls.append(
            {
                "event": call["hook_event_name"],
                "tool": call.get("tool_name"),
                "kind": kind_of(call["hook_event_name"], proc.stdout),
                "exit": proc.returncode,
                "wall_ms": round((time.perf_counter() - started) * 1000),
            }
        )
    ds = decisions(journal)
    return {
        "set": case["set"],
        "id": case["id"],
        "label": case["label"],
        "calls": calls,
        "decisions": ds,
        "jev_usd": round(sum(float(d["cost_usd"]) for d in ds), 8),
    }


def spent(sandbox: Path) -> float:
    total = 0.0
    for name in ("hook-results.jsonl", "latency-results.jsonl"):
        path = sandbox / name
        if path.exists():
            total += sum(json.loads(x)["jev_usd"] for x in path.read_text("utf-8").splitlines())
    preflight = sandbox / "preflight" / "journal.jsonl"
    total += sum(d["cost_usd"] for d in decisions(preflight))
    e2e = sandbox / "e2e-runs.jsonl"
    if e2e.exists():
        total += sum(json.loads(x)["jev_usd"] for x in e2e.read_text("utf-8").splitlines())
    return total


def run(sandbox: Path, key: str, workers: int, jev_stop: float) -> None:
    todo = load_cases(sandbox)
    out = sandbox / "hook-results.jsonl"
    done = set()
    if out.exists():
        done = {(r["set"], r["id"]) for r in map(json.loads, out.read_text("utf-8").splitlines())}
    todo = [c for c in todo if (c["set"], c["id"]) not in done]
    todo.sort(key=lambda c: SET_ORDER.index(c["set"]))
    lock = threading.Lock()
    state = {"usd": spent(sandbox), "stopped": False, "n": 0}
    print(f"start: {len(todo)} cases, Jev spent so far {state['usd']:.5f} USD", flush=True)

    def task(case: dict[str, Any]) -> None:
        with lock:
            if state["stopped"] or state["usd"] > jev_stop:
                state["stopped"] = True
                return
        row = one_case(case, sandbox, key)
        with lock:
            state["usd"] += row["jev_usd"]
            state["n"] += 1
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            if state["n"] % 50 == 0:
                print(f"{state['n']} cases, Jev {state['usd']:.5f} USD", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(task, todo))
    note = "STOPPED at the Jev cap" if state["stopped"] else "done"
    print(f"{note}: {state['n']} cases this run, Jev total {state['usd']:.5f} USD", flush=True)


def preflight(sandbox: Path, key: str) -> None:
    run_dir = sandbox / "preflight"
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = {"hook_event_name": "PreToolUse", "tool_name": "Bash",
               "tool_input": {"command": "ls -la"}}  # fmt: skip
    env = hook_env(key, run_dir / "journal.jsonl", None)
    proc = subprocess.run([SANCHO, "hook"], input=json.dumps(payload), capture_output=True,
                          text=True, env=env, encoding="utf-8")  # fmt: skip
    last = decisions(run_dir / "journal.jsonl")[-1]
    shown = {k: last.get(k) for k in ("point", "provider", "model", "error", "latency_ms")}
    print(json.dumps({"stdout": proc.stdout, **shown}))


def latency(sandbox: Path, key: str) -> None:
    """The installed `sanchopanza.exe hook` itself, on the first cases of each kind."""
    cases = load_cases(sandbox)
    picks: dict[str, list[dict[str, Any]]] = {
        "guard_decision": [c["calls"][0] for c in cases if c["set"] == "guard"
                           and c["label"] == "safe"],
        "scan_decision": [c["calls"][0] for c in cases if c["set"] == "inject-ad"],
        "stop_decision": [c["calls"][0] for c in cases if c["set"] == "stop"],
        "no_decision_mcp": [c["calls"][0] for c in cases if c["set"] == "atbench"
                            and c["calls"] and c["calls"][0]["tool_name"].startswith("mcp__")],
        "no_decision_cat": [c["calls"][0] for c in cases if c["set"] == "control"],
    }  # fmt: skip
    out = sandbox / "latency-results.jsonl"
    out.unlink(missing_ok=True)
    for kind, calls in picks.items():
        for index, call in enumerate(calls[:LATENCY_PER_KIND]):
            if spent(sandbox) > JEV_STOP:
                print("Jev cap reached; latency sample cut short")
                return
            journal = sandbox / "latency" / f"{kind}-{index}.jsonl"
            journal.parent.mkdir(parents=True, exist_ok=True)
            journal.unlink(missing_ok=True)
            started = time.perf_counter()
            proc = subprocess.run([SANCHO, "hook"], input=json.dumps(call), capture_output=True,
                                  text=True, encoding="utf-8",
                                  env=hook_env(key, journal, None))  # fmt: skip
            wall = round((time.perf_counter() - started) * 1000)
            ds = decisions(journal)
            row = {"kind": kind, "index": index, "wall_ms": wall,
                   "output": kind_of(call["hook_event_name"], proc.stdout),
                   "decisions": len(ds), "jev_latency_ms": [d["latency_ms"] for d in ds],
                   "jev_usd": round(sum(d["cost_usd"] for d in ds), 8)}  # fmt: skip
            with out.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
    print(out.read_text(encoding="utf-8"))


def plan(sandbox: Path) -> None:
    """Free: how many hook inputs lead to a decision, and a cost estimate from the chars."""
    from sanchopanza.harness.claude_code import config_from_env, needs_decision

    config = config_from_env(dict(INSTALLED_ENV))
    per_set: dict[str, dict[str, int]] = {}
    for case in load_cases(sandbox):
        row = per_set.setdefault(case["set"], {"cases": 0, "calls": 0, "need": 0})
        row["cases"] += 1
        row["calls"] += len(case["calls"])
        row["need"] += sum(needs_decision(c, config) for c in case["calls"])
    print(json.dumps(per_set, indent=1))


def collect(sandbox: Path) -> None:
    """Verdicts into this directory; recorded answers into the fixture. No inputs copied."""
    rows = [json.loads(x) for x in (sandbox / "hook-results.jsonl").read_text("utf-8").splitlines()]
    rows.sort(key=lambda r: (SET_ORDER.index(r["set"]), r["id"]))
    (HERE / "hook-verdicts.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8"
    )
    records = sorted((sandbox / "record").glob("*.jsonl"))
    lines = [line for p in records for line in p.read_text("utf-8").splitlines() if line.strip()]
    FIXTURE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for name in ("latency-results.jsonl",):
        if (sandbox / name).exists():
            shutil.copy(sandbox / name, HERE / name)
    pre = decisions(sandbox / "preflight" / "journal.jsonl")
    (HERE / "preflight.json").write_text(json.dumps(pre, indent=1) + "\n", encoding="utf-8")
    print(f"{len(rows)} verdicts, {len(lines)} recorded answers")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "plan", "preflight", "run", "latency",
                                           "collect"))  # fmt: skip
    parser.add_argument("--sandbox", required=True)
    parser.add_argument("--env-file", default=None)
    parser.add_argument("--atbench", default=None)
    parser.add_argument("--rjudge", default=None)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--jev-stop", type=float, default=JEV_STOP)
    parser.add_argument("--dry", action="store_true", help="null provider, spends nothing")
    args = parser.parse_args(argv)
    sandbox = Path(args.sandbox)
    sandbox.mkdir(parents=True, exist_ok=True)
    if args.action == "build":
        built = case_builder.all_cases(
            atbench=Path(args.atbench) if args.atbench else None,
            rjudge=Path(args.rjudge) if args.rjudge else None,
            transcripts=sandbox / "transcripts",
        )
        (sandbox / "hook-cases.jsonl").write_text(
            "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in built), encoding="utf-8"
        )
        print(f"{len(built)} cases")
    elif args.action == "plan":
        plan(sandbox)
    elif args.action == "collect":
        collect(sandbox)
    else:
        key = DRY_KEY if args.dry else typesafe_key(args.env_file)
        if args.action == "preflight":
            preflight(sandbox, key)
        elif args.action == "run":
            run(sandbox, key, args.workers, args.jev_stop)
        else:
            latency(sandbox, key)
    return 0


if __name__ == "__main__":
    sys.exit(main())
