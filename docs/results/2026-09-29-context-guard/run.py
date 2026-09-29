"""The compaction guard inside Claude Code, end to end: native summary (N) against the native
summary plus the guard (G, rule; GJ, one Jev tournament when the facts do not fit).

    python run.py build                    # free: tasks under ~/.cache/sanchopanza/context-guard
    python run.py check                    # free: hidden tests, one-shot tools, the rule absent
    python run.py dry                      # free: the guard hooks on a recorded native session
    python run.py estimate                 # free: expected cost per plan
    python run.py run --model haiku --tasks t01 --arms N,G,GJ --stop-usd 2.00 [--env-file P]  # pays
    python run.py collect                  # free: runs.jsonl -> analysis.json

Per model and task: phase A once (no hooks), the work copy snapshotted, then every arm forks
phase A (`--resume A --fork-session`) with the phase-B prompt from the same snapshot, in an
order rotated by task. Claude Code's own auto-compaction fires in the middle of phase B
(CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000, CLAUDE_AUTOCOMPACT_PCT_OVERRIDE per model). Sessions
run one after another; a gate reads the true cost of every finished session and refuses to start
one that could pass `--stop-usd`. Evidence stays under ~/.cache/sanchopanza/context-guard; this
folder gets rows of numbers, personal paths scrubbed.

Built on the lean run's evidence reader (`../2026-09-28-context-lean/evidence.py`, imported).
"""

# ruff: noqa: E501
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import arms  # noqa: E402
import tasks as gen  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


evidence = _load("guard_lean_evidence", HERE.parent / "2026-09-28-context-lean" / "evidence.py")

ROOT = arms.ROOT
TASKS_DIR = ROOT / "tasks"
A_ROWS = HERE / "phase-a.jsonl"
B_ROWS = HERE / "runs.jsonl"
INVALID_ROWS = HERE / "runs-invalid.jsonl"
TIMEOUT = 1500
TASK_NAMES = [f"t{i + 1:02d}-{gen.lean.DOMAINS[i][0]}" for i in range(gen.N_TASKS)]


def prompt_a(rule_ref: str) -> str:
    return (
        "You are onboarding onto this repository. Use the Bash tool for shell commands. Do these "
        "steps in order.\n"
        "1. Read README.md. Then read the first eight modules of the reading order it describes, "
        "one file per Read call: README.md names the first module and the first line of each "
        "module names the next. Do not read the other modules yet.\n"
        "2. Run `python tools/issue_token.py` exactly once. It issues this release's token and can "
        "only be run once.\n"
        "3. Run `python -m pytest -q tests`. One test fails; the test is right. Fix the bug in "
        "pkg/, then run the tests again until they pass.\n"
        "4. Run `python tools/probe.py` exactly once. It runs the calibration probe, which is "
        "expected to report a failure, and can only be run once.\n"
        f"Project rule, for this session and for every later request in it: every exception "
        f"message written in this repository must end with `[ref {rule_ref}]`.\n"
        "Do not run tools/build_report.py and do not change any other file. Finish with a status "
        "report of at most three lines that does not repeat values from the tool output."
    )


PROMPT_B = (
    f"{evidence.B_MARK}. Use the Bash tool for shell commands. Do these steps in order.\n"
    "1. Run `python tools/build_report.py` exactly once, first. It prints the build log with "
    "every check and can only be run once; note which check failed.\n"
    "2. Continue the reading order from where you stopped: read every module under pkg/ that "
    "you have not read yet, one file per Read call, following the first line of each module, "
    "until a module says it is the last.\n"
    "3. In pkg/release.py set RELEASE_TOKEN to the release token that tools/issue_token.py "
    "issued earlier in this session (it cannot be issued again).\n"
    "4. In pkg/buildcheck.py implement check_build(): raise BuildError with a message that "
    "contains the id of the check that failed in the build report and its expected value.\n"
    "5. In pkg/calibration.py set DRIFT_TOLERANCE to the drift tolerance that tools/probe.py "
    "reported earlier in this session (it cannot run again), and implement check_drift as its "
    "docstring says.\n"
    "6. In pkg/admission.py implement admit(count): True when count is at most the package's "
    "batch ceiling (the constant already defined in pkg/), False otherwise.\n"
    "7. Run `python -m pytest -q tests` and keep it passing.\n"
    "Never guess a value you cannot find: say so instead. Finish with at most three lines."
)


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text("utf-8").splitlines() if x.strip()]


def append(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(evidence.scrub(row)) + "\n")


def spent(model: str | None = None) -> float:
    """Every session this driver ever started, at its counted cost, invalid rows included."""
    every = rows(A_ROWS) + rows(B_ROWS) + rows(INVALID_ROWS)
    chosen = [r for r in every if model is None or r.get("model") == model]
    return round(sum(r["cost"]["counted_usd"] for r in chosen), 6)


class Gate:
    def __init__(self, stop_usd: float) -> None:
        self.stop_usd = stop_usd
        self.stopped: str | None = None

    def allow(self, cap: float, what: str) -> bool:
        now = spent()
        if self.stopped or now + cap > self.stop_usd:
            self.stopped = self.stopped or (
                f"gate: refused {what}: spent {now:.4f} + cap {cap:.2f} > stop {self.stop_usd:.2f}"
            )
            print(self.stopped, flush=True)
            return False
        return True


def counted(true_usd: float | None, from_calls: float, cap: float) -> dict[str, Any]:
    if true_usd is not None and true_usd > 0:
        return {"counted_usd": round(true_usd, 6), "source": "result_json"}
    if from_calls > 0:
        return {"counted_usd": round(from_calls, 6), "source": "transcript_calls"}
    return {"counted_usd": cap, "source": "cap_unknown_cost"}


def session(cmd: list[str], cwd: Path, env: dict[str, str], out: Path) -> dict[str, Any]:
    started = time.time()
    status = "done"
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                              encoding="utf-8", timeout=TIMEOUT, stdin=subprocess.DEVNULL)  # fmt: skip
        stdout, stderr, code = proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired as error:
        status, code = "timeout", None
        stdout = error.stdout.decode("utf-8", "replace") if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = "timeout"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(stdout, encoding="utf-8")
    out.with_suffix(".stderr.txt").write_text(stderr, encoding="utf-8")
    try:
        result = json.loads(stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        result = {}
        status = status if status != "done" else "no_result_json"
    return {"status": status, "exit": code, "seconds": round(time.time() - started, 1),
            "result": result, "stderr_tail": evidence.neutral(stderr[-400:])}  # fmt: skip


def facts_of(task: str) -> dict[str, Any]:
    return gen.load_facts(TASKS_DIR)[task]


def phase_a(model: arms.Model, task: str, gate: Gate, version: str) -> dict[str, Any] | None:
    done = {r["task"]: r for r in rows(A_ROWS) if r["model"] == model.key}
    if task in done:
        return done[task]
    base = arms.tree(model.key)
    work, snap, ev = base / "work" / task, base / "snap" / task, base / "runs" / task / "A"
    for path in (work, snap, ev):
        shutil.rmtree(path, ignore_errors=True)
    shutil.copytree(TASKS_DIR / "repos" / task, work)
    cfg = arms.config("phaseA", model.key, ev)
    if not gate.allow(model.cap, f"{model.key} {task} phase A"):
        return None
    f = facts_of(task)
    s = session(arms.argv(prompt_a(f["rule_ref"]), model, cfg), work, cfg.env, ev / "result.json")
    res = s["result"]
    tr_path = evidence.find(res.get("session_id"))
    if tr_path:
        shutil.copy(tr_path, ev / "session.jsonl")
    info = evidence.phase_a(tr_path, model.prices)
    tools = work / "tools"
    consumed = {"token": not (tools / ".token_seed").exists(), "probe": not (tools / ".probe_state").exists(),
                "build_report": not (tools / ".build_state").exists()}  # fmt: skip
    tests = gen.run_tests(work, TASKS_DIR / "hidden" / task)
    text_a = json.dumps([b for e in evidence.entries(tr_path) if e.get("type") == "assistant"
                         for b in evidence.tr._blocks(e) if b.get("type") == "text"])  # fmt: skip
    valid = (s["status"] == "done" and res.get("subtype") == "success" and consumed["token"]
             and consumed["probe"] and not consumed["build_report"] and bool(res.get("session_id")))  # fmt: skip
    row = {
        "model": model.key, "task": task, "status": s["status"], "exit": s["exit"],
        "subtype": res.get("subtype"), "turns": res.get("num_turns"), "seconds": s["seconds"],
        "session_id": res.get("session_id"), "claude_version": version,
        "cost": {**counted(res.get("total_cost_usd"), info["usage"]["usd_from_calls"], model.cap),
                 "true_usd": res.get("total_cost_usd")},
        "transcript": info, "consumed": consumed, "valid": valid,
        "visible_pass": gen.facts_passed(tests["tests"])["visible"],
        "in_model_text": {k: f[k] in text_a for k in ("token", "probe_code", "tolerance", "rule_ref")},
        "final_answer": evidence.safe_answer(res.get("result")), "stderr_tail": s["stderr_tail"],
    }  # fmt: skip
    shutil.copytree(work, snap)
    append(A_ROWS, row)
    print(json.dumps({"phase": "A", "model": model.key, "task": task, "valid": valid,
                      "usd": row["cost"]["counted_usd"], "last_context": info["last_context"],
                      "spent": spent()}), flush=True)  # fmt: skip
    return row


def guard_stats(ev: Path) -> dict[str, Any]:
    events = rows(ev / "guard-events.jsonl")
    log = rows(ev / "guard-log.jsonl")
    pre = [x for x in log if x.get("event") == "PreCompact"]
    # K builds its guard at the SessionStart (after the summary): its choices are logged there
    built = [x for x in log if x.get("event") == "SessionStart" and x.get("origin") == "built"]
    pre = [x for x in pre if not x.get("deferred")] + built
    return {
        "events": len(events),
        "precompact": sum(x.get("event") == "PreCompact" for x in log), "session_start": sum(x.get("event") == "SessionStart" for x in log),
        "echoes": sum(x.get("event") == "PostToolUse" and x.get("echo") for x in log),
        "errors": [x.get("error") for x in log if x.get("event") == "error"],
        "choosers": [x.get("chooser") for x in pre], "candidates": [x.get("candidates") for x in pre],
        "facts": [x.get("facts") for x in pre], "block_chars": [x.get("block_chars") for x in pre],
        "notes_chars": [x.get("notes_chars") for x in built],
        "hook_seconds_max": max((x.get("seconds", 0) for x in events), default=0),
    }  # fmt: skip


def invalid_reasons(arm: str, b: dict[str, Any], s: dict[str, Any]) -> list[str]:
    out = []
    if s["status"] != "done":
        out.append(s["status"])
    if not b["b_found"]:
        out.append("phase B prompt not found in the transcript")
    if not b["compaction"]["boundaries"]:
        out.append("no compaction happened")
    if arm in ("G", "GJ", "K"):
        g = b.get("guard") or {}
        if not g.get("precompact") or not g.get("session_start"):
            out.append("the guard's PreCompact or SessionStart never ran")
    return out


def one_arm(model: arms.Model, task: str, arm: str, order: int, a: dict[str, Any], gate: Gate,
            version: str, keyfile: Path | None) -> dict[str, Any] | None:  # fmt: skip
    base = arms.tree(model.key)
    work, ev = base / "work" / task, base / "runs" / task / arm
    shutil.rmtree(ev, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(base / "snap" / task, work)  # same path as phase A: `--resume` finds it
    cfg = arms.config(arm, model.key, ev, keyfile)
    if not gate.allow(model.cap, f"{model.key} {task} arm {arm}"):
        return None
    s = session(arms.argv(PROMPT_B, model, cfg, resume=a["session_id"]), work, cfg.env, ev / "b.json")
    res = s["result"]
    tr_path = evidence.find(res.get("session_id"))
    if tr_path:
        shutil.copy(tr_path, ev / "session.jsonl")
    f = facts_of(task)
    b = evidence.phase_b(tr_path, ev, f["chain"], model.prices)
    b["guard"] = guard_stats(ev)
    a_result = json.loads((base / "runs" / task / "A" / "result.json").read_text("utf-8").strip().splitlines()[-1])
    true = evidence.true_split(a_result, res) if res.get("total_cost_usd") is not None else {"usd": None, "input": None}
    tests = gen.run_tests(work, TASKS_DIR / "hidden" / task)
    reasons = invalid_reasons(arm, b, s)
    row = {
        "model": model.key, "task": task, "arm": arm, "order": order, "status": s["status"],
        "exit": s["exit"], "subtype": res.get("subtype"), "is_error": res.get("is_error"),
        "turns": res.get("num_turns"), "seconds": s["seconds"], "claude_version": version,
        "a_session": a["session_id"], "session_id": res.get("session_id"),
        "cost": {**counted(true["usd"], b["usage"]["usd_from_calls"], model.cap),
                 "true_usd": true["usd"], "true_input": true["input"]},
        **b, "config": cfg.notes,
        "tests": tests["tests"], "facts": gen.facts_passed(tests["tests"]),
        "success": tests["passed"], "valid": not reasons, "invalid_reasons": reasons,
        "final_answer": evidence.safe_answer(res.get("result")), "stderr_tail": s["stderr_tail"],
    }  # fmt: skip
    append(B_ROWS if not reasons else INVALID_ROWS, row)
    print(json.dumps({"model": model.key, "task": task, "arm": arm, "valid": row["valid"],
                      "reasons": reasons, "success": row["success"], "facts": row["facts"],
                      "compactions": b["compaction"]["boundaries"], "guard": b["guard"],
                      "usd": row["cost"]["counted_usd"], "spent": spent()}), flush=True)  # fmt: skip
    return row


def key_from(env_file: Path) -> str:
    for line in env_file.read_text("utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == "TYPESAFE_API_KEY" and value.strip():
            return value.strip().strip('"').strip("'")
    raise SystemExit(f"no TYPESAFE_API_KEY in {env_file}")


def run(model: arms.Model, chosen: list[str], arm_list: list[str], stop_usd: float,
        env_file: Path | None, phase_a_only: bool) -> int:  # fmt: skip
    prepare()
    version = arms.claude_version()
    keyfile = None
    if "GJ" in arm_list or "K" in arm_list:
        if env_file is None:
            raise SystemExit("arms GJ and K need --env-file with TYPESAFE_API_KEY")
        keyfile = ROOT / ".jev-key"
        keyfile.write_text(key_from(env_file), encoding="utf-8")
    gate = Gate(stop_usd)
    print(json.dumps({"model": model.id, "tasks": chosen, "arms": arm_list, "spent": spent(),
                      "stop_usd": stop_usd, "claude": version}), flush=True)  # fmt: skip
    done = {(r["model"], r["task"], r["arm"]) for r in rows(B_ROWS)}
    retried = {(r["model"], r["task"], r["arm"]) for r in rows(INVALID_ROWS)}
    try:
        for task in chosen:
            a = phase_a(model, task, gate, version)
            if a is None:
                break
            if not a["valid"]:
                print(json.dumps({"task": task, "excluded": "phase A invalid"}), flush=True)
                continue
            if phase_a_only:
                continue
            k = TASK_NAMES.index(task) % len(arm_list)
            for order, arm in enumerate(arm_list[k:] + arm_list[:k]):
                key = (model.key, task, arm)
                if key in done:
                    print(json.dumps({"task": task, "arm": arm, "skipped": "row exists"}), flush=True)
                    continue
                row = one_arm(model, task, arm, order, a, gate, version, keyfile)
                if row is None:
                    break
                if not row["valid"] and key not in retried:  # prereg: one re-run of an invalid row
                    retried.add(key)
                    if one_arm(model, task, arm, order, a, gate, version, keyfile) is None:
                        break
            if gate.stopped:
                break
    finally:
        if keyfile is not None:
            keyfile.unlink(missing_ok=True)
    print(f"{'STOPPED: ' + gate.stopped if gate.stopped else 'done'}; spent {spent():.4f} USD", flush=True)
    return 3 if gate.stopped else 0


def prepare() -> None:
    if not (TASKS_DIR / "facts.json").exists():
        gen.build(TASKS_DIR)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "check", "dry", "estimate", "run", "collect"))
    parser.add_argument("--model", choices=tuple(arms.MODELS), default="haiku")
    parser.add_argument("--tasks", default="", help="t01,t02,... (default: the model's plan)")
    parser.add_argument("--arms", default="", help="default: the model's plan")
    parser.add_argument("--stop-usd", type=float, default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--phase-a-only", action="store_true", help="calibration pilot")
    args = parser.parse_args(argv)
    if args.action == "build":
        gen.build(TASKS_DIR)
        print(gen.tree_digest(TASKS_DIR / "repos"))
        return 0
    if args.action == "check":
        table = gen.check(TASKS_DIR)
        print(json.dumps({t: [k for k, v in r["ok"].items() if not v] for t, r in table.items()}, indent=1))
        return 0 if all(r["passed"] for r in table.values()) else 1
    if args.action == "dry":
        import dry

        return dry.main()
    if args.action == "estimate":
        import estimate

        return estimate.main()
    if args.action == "collect":
        import analyze

        return analyze.main()
    model = arms.MODELS[args.model]
    if args.stop_usd is None:
        raise SystemExit("run needs --stop-usd: the ceiling on everything this driver has spent")
    plan = TASK_NAMES[: model.tasks]
    chosen = [t for t in plan if not args.tasks or t.split("-")[0] in args.tasks.split(",") or t in args.tasks.split(",")]
    arm_list = [a for a in (args.arms.split(",") if args.arms else model.arms) if a]
    if any(a not in arms.ARMS for a in arm_list):
        raise SystemExit(f"arms are {arms.ARMS}")
    return run(model, chosen, arm_list, args.stop_usd, args.env_file, args.phase_a_only)


if __name__ == "__main__":
    sys.exit(main())
