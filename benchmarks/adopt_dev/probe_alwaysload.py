"""Does Haiku call find_in_repo once its server is registered with alwaysLoad? A development
probe on SWE-bench Verified singles, one request per session. Paid (subscription, list price).

    python -m benchmarks.adopt_dev.probe_alwaysload check     # free: see check_alwaysload.py
    python -m benchmarks.adopt_dev.probe_alwaysload run       # the probe (resumable)
    python -m benchmarks.adopt_dev.probe_alwaysload summary   # tables from the rows, free

Arm S is `sanchopanza install --scope project --write` from the frozen copy of 1ea9302 (extras
jev and mcp), wired through `hook_env.py` exactly as the sealed runner does (`run.install_sancho`),
with the per-arm key path of amendment 5; arm N is Claude Code alone. Both run Claude Code 2.1.285
(the private copy first on PATH, DISABLE_AUTOUPDATER=1), Haiku 4.5, `run.command`'s flags and a
1.50 USD cap per call. A session starts only if the rows' cost so far plus its cap fits under
TOTAL_CAP_USD (8.00). Grading is the official SWE-bench harness, as `singles_run.grade`.

The session loop is this module's own (not `singles_run.one`) only to timestamp stream lines as
they arrive: process start, init line, first assistant message. With the prompt in argv, stdin is
closed (DEVNULL) so `claude -p` does not wait 3 s for it.

Writes only under ~/.cache/sanchopanza/adopt/dev-alwaysload/ (evidence, rows, grades) and
work-dal/ (working copies). Log lines that end a run: `PROBE DONE`, `PROBE STOP: <why>` (a cap,
a usage limit, find deferred) or `PROBE FAILED: <why>`.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import threading
import time
import traceback
from pathlib import Path
from typing import Any

from .common import (
    CALL_CAP_USD,
    CLAUDE_VERSION,
    FROZEN_COMMIT,
    MODEL,
    OUT,
    PLAN,
    SINGLES,
    TOTAL_CAP_USD,
    WORK,
    docker_env,
    plan_refusal,
    read_json,
    run,
    singles_run,
)
from .session_facts import Clock, describe

MIN_DISK_GB = 15.0
NOT_RUN_ERROR = "NOT RUN (error result)"  # an API or usage-limit error: run again on resume
# Called with each new row after its log line (probe_nudge.py adds the nudge's facts).
AFTER_SESSION: list[Any] = []


class Stop(Exception):
    """The probe ends here without a fault: a cap, a usage limit, find deferred."""


def log(text: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}", flush=True)


def kill_tree(pid: int) -> None:
    """By PID only, with its children (hooks, the MCP server)."""
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


# ---- money ---------------------------------------------------------------------------------------


def spent() -> float:
    """List price so far, Jev's included: every row's calls (set-aside `<arm>-notrun<N>` rows
    too, the glob reaches them), and the charge of every abandoned attempt."""
    total = 0.0
    for path in OUT.glob("*/*/row.json"):
        row = read_json(path)
        total += sum(c.get("cost_usd", 0.0) for c in row["calls"]) + row.get("jev_usd", 0.0)
    for path in OUT.glob("*/*/abandoned.json"):
        aside = read_json(path)
        total += aside["charged_usd"] + aside.get("jev_usd", 0.0)
    return round(total, 6)


def charge_for(code: int, aborted: str, seen: dict[str, Any]) -> float:
    """What a session costs when its stream reports no cost: its cap when it was cut (timeout,
    abort) or ended without a result line (subtype None), since it may have spent; else 0."""
    return CALL_CAP_USD if (code == -9 or aborted or seen.get("subtype") is None) else 0.0


def set_aside(evidence: Path) -> None:
    """An attempt that left no row (a crash): moved aside and charged what its stream reports,
    its cap when it reports nothing, or nothing if `claude -p` never started."""
    stream = evidence / "stream-1.jsonl"
    launched = stream.exists()  # no stream: it never reached `claude -p`, nothing was spent
    charged = (run.facts(stream)["cost_usd"] or CALL_CAP_USD) if launched else 0.0
    aside = evidence.with_name(f"{evidence.name}-abandoned-{int(time.time())}")
    evidence.rename(aside)
    jev = run.jev_usd(aside)
    (aside / "abandoned.json").write_text(json.dumps({"charged_usd": charged, "jev_usd": jev}),
                                          encoding="utf-8")  # fmt: skip
    log(f"{evidence.parent.name} {evidence.name}: earlier attempt without a row set aside, "
        f"charged {charged:.2f} USD")  # fmt: skip


# ---- one session ---------------------------------------------------------------------------------


def stream_session(
    cmd: list[str], work: Path, env: dict[str, str], data: bytes | None, evidence: Path,
    clock: Clock, refuse_init: Any,
) -> tuple[int, str]:  # fmt: skip
    """`claude -p` with each stdout line written to stream-1.jsonl and timed on arrival. Returns
    (exit code, abort reason). -9: the call timeout. A non-empty reason from `refuse_init(init)`
    kills the session at its init line. The lines are read on a thread, so a child that keeps the
    pipe open after `claude` exits cannot hold the probe."""
    reason: list[str] = []
    stream, errors = evidence / "stream-1.jsonl", evidence / "stream-1.err"
    with stream.open("wb") as out, errors.open("wb") as err:
        proc = subprocess.Popen(cmd, cwd=work, env=env, stdout=subprocess.PIPE, stderr=err,
                                stdin=subprocess.PIPE if data else subprocess.DEVNULL)  # fmt: skip

        def feed() -> None:
            assert proc.stdin is not None
            proc.stdin.write(data or b"")
            proc.stdin.close()

        def read() -> None:
            assert proc.stdout is not None
            for raw in proc.stdout:
                now = time.time()
                out.write(raw)
                out.flush()
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                clock.see(event, now)
                if event.get("subtype") == "init" and not reason and (why := refuse_init(event)):
                    reason.append(why)
                    kill_tree(proc.pid)

        if data:
            threading.Thread(target=feed, daemon=True).start()
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        try:
            code = proc.wait(timeout=run.CALL_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            kill_tree(proc.pid)
            proc.wait(timeout=120)
            code = -9
        reader.join(timeout=60)
        if reader.is_alive():
            log(f"{evidence.parent.name} {evidence.name}: stdout still open 60 s after exit")
    return code, (reason[0] if reason else "")


def find_refusal(init: dict[str, Any]) -> str:
    servers = {s.get("name"): s.get("status") for s in init.get("mcp_servers") or []}
    if servers.get("sanchopanza") != "connected":
        return f"find_in_repo's server is {servers.get('sanchopanza') or 'absent'} at init"
    return ""


def session(row: dict[str, Any], arm: str, keyfile: Path) -> dict[str, Any]:
    """One arm of one single: working copy, install (S), the session, its patch and record."""
    name = row["instance_id"]
    evidence = OUT / name / arm
    work = WORK / f"{name}-{arm}"
    probes: list[str] = []
    if arm == "S":
        keyfile = run.arm_keyfile(keyfile, f"dal-{name}", arm)
        probes = [run.decider_probe(keyfile)]
        if probes[-1] != run.HELD_DECIDER:
            raise RuntimeError(f"{name} S: its hooks would build {probes[-1]}")
    docker_env.remove_tree(evidence)
    evidence.mkdir(parents=True)
    docker_env.remove_tree(work)
    base = docker_env.export(row["image"], work)
    mcp = run.install_sancho(work, evidence, keyfile) if arm == "S" else None
    command = singles_run.test_command(row["repo"])
    env = {**run.child_env(row["image"], base), "ADOPT_PREFIX": singles_run.CONDA,
           "ADOPT_TEST_CMD": command}  # fmt: skip
    prompt = singles_run.PROMPT.format(issue=row["problem_statement"].strip(), command=command)
    began = time.time()
    clock = Clock(began)
    try:
        code, aborted = stream_session(run.command(MODEL, prompt, None, mcp), work, env,
                                       run.stdin_for(prompt), evidence, clock,
                                       find_refusal if arm == "S" else (lambda _e: ""))  # fmt: skip
    except OSError as exc:  # `claude` did not start: the harness, not the arm
        (evidence / "stream-1.err").write_text(f"{type(exc).__name__}: {exc}", encoding="utf-8")
        code, aborted = -1, ""
    seen = run.facts(evidence / "stream-1.jsonl")
    seen = {**seen, "cost_usd": seen["cost_usd"] or charge_for(code, aborted, seen)}
    call: dict[str, Any] = {"request": 1, "exit": code, "wall_s": round(time.time() - began, 1),
                            **seen}  # fmt: skip
    if aborted:
        call = {**call, "status": f"ABORTED ({aborted})"}
    elif code == -1 or (not seen["session"] and seen["subtype"] is None):
        call = {**call, "status": "NOT RUN (harness)"}
    elif seen.get("api_error"):
        call = {**call, "status": NOT_RUN_ERROR}
    (evidence / "final.patch").write_text(docker_env.agent_diff(work, base), encoding="utf-8",
                                          newline="\n")  # fmt: skip
    found = next(run.CLAUDE_PROJECTS.glob(f"*/{seen['session']}.jsonl"), None) \
        if seen["session"] else None  # fmt: skip
    transcript = evidence / "transcript.jsonl"
    if found:
        shutil.copy(found, transcript)
    record = {"instance": name, "arm": arm, "model": MODEL, "base": base,
              "jev_usd": run.jev_usd(evidence), "sanchopanza": run.provenance(),
              "claude_version": run.claude_version(), "started": began,
              **({"decider": probes} if probes else {}), "calls": [call],
              "probe": describe(clock, transcript, evidence, seen["tools"])}  # fmt: skip
    (evidence / "row.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def grade_arm(name: str, arm: str) -> bool | None:
    """The official harness on this arm's patch, as `singles_run.grade` (None: no report)."""
    evidence = OUT / name / arm
    if (evidence / "grade.json").exists():
        return bool(read_json(evidence / "grade.json")["resolved"])
    model = f"adopt-dal-{arm}"
    preds = evidence / "preds.jsonl"
    preds.write_text(json.dumps({"instance_id": name, "model_name_or_path": model,
                                 "model_patch": (evidence / "final.patch").read_text("utf-8")})
                     + "\n", encoding="utf-8", newline="\n")  # fmt: skip
    run_id = f"adopt-dal-{arm}-{int(time.time())}"
    swe = singles_run.SWE
    subprocess.run([str(singles_run.SWE_PYTHON), str(swe / "run_swe.py"), "-d",
                    "SWE-bench/SWE-bench_Verified", "-p", str(preds), "-i", name,
                    "--max_workers", "1", "-id", run_id], cwd=swe, capture_output=True,
                   env={**os.environ, "PYTHONUTF8": "1"}, timeout=3600)  # fmt: skip
    report = swe / "logs" / "run_evaluation" / run_id / model / name / "report.json"
    if not report.exists():
        log(f"{name} {arm}: no report from the harness, not graded")
        return None
    resolved = bool(read_json(report).get(name, {}).get("resolved"))
    (evidence / "grade.json").write_text(json.dumps({"resolved": resolved, "report": str(report)}),
                                         encoding="utf-8")  # fmt: skip
    return resolved


# ---- the probe -----------------------------------------------------------------------------------


def preflight() -> None:
    import confirm  # benchmarks/adopt is on the path (common.py)

    if not confirm.seal_holds():
        raise RuntimeError("the confirmation's seal does not hold: a sealed file changed")
    if why := plan_refusal():
        raise RuntimeError(why)
    if (found := run.claude_version()) != CLAUDE_VERSION:
        raise RuntimeError(f"Claude Code {CLAUDE_VERSION} expected first on PATH, found {found}")
    stamp = run.frozen_stamp() or {}
    if stamp.get("commit") != FROZEN_COMMIT or not {"jev", "mcp"} <= set(stamp.get("extras", [])):
        raise RuntimeError(f"ADOPT_SANCHO is not the frozen copy of {FROZEN_COMMIT[:12]} with "
                           f"jev and mcp: {stamp}")  # fmt: skip
    run.set_caps(CALL_CAP_USD, CALL_CAP_USD)


def report_session(record: dict[str, Any]) -> None:
    call, probe = record["calls"][0], record["probe"]
    log(f"{record['instance']} {record['arm']}: {call.get('status') or call['subtype']} "
        f"{call['cost_usd']:.3f} USD turns {call.get('turns')} calls {probe['watched_calls']} "
        f"find deferred {probe['deferral']['find_deferred']} cache ok {probe['caching']['ok']} "
        f"init {probe['latency']['to_init_s']} s first answer "
        f"{probe['latency']['to_first_assistant_s']} s")  # fmt: skip


def not_run(name: str, arm: str) -> bool:
    """A row whose session an API or usage-limit error stopped: run again on resume."""
    path = OUT / name / arm / "row.json"
    return path.exists() and read_json(path)["calls"][0].get("status") == NOT_RUN_ERROR


def todo_arms(name: str, arms: tuple[str, ...]) -> list[str]:
    return [a for a in arms if not (OUT / name / a / "row.json").exists() or not_run(name, a)]


def set_notrun_aside(evidence: Path) -> Path:
    """Move an error-result arm to `<arm>-notrun<N>`; `spent` still counts its row."""
    n = 1
    while (aside := evidence.with_name(f"{evidence.name}-notrun{n}")).exists():
        n += 1
    evidence.rename(aside)
    log(f"{evidence.parent.name} {evidence.name}: error-result row set aside as {aside.name}, "
        "run again")  # fmt: skip
    return aside


def one_instance(row: dict[str, Any], arms: tuple[str, ...], keyfile: Path) -> None:
    name = row["instance_id"]
    todo = todo_arms(name, arms)
    ungraded = [a for a in arms if a not in todo and gradable(name, a)]
    if not todo and not ungraded:
        return
    docker_env.pull(row["image"])
    try:
        for arm in todo:
            run_arm(row, arm, keyfile)
    finally:
        try:
            grade_done(name, arms)
        finally:
            docker_env.drop(row["image"])


def run_arm(row: dict[str, Any], arm: str, keyfile: Path) -> None:
    name = row["instance_id"]
    if not_run(name, arm):
        set_notrun_aside(OUT / name / arm)
    elif (OUT / name / arm).exists():
        set_aside(OUT / name / arm)
    if docker_env.disk_free_gb() < MIN_DISK_GB:
        raise Stop(f"under {MIN_DISK_GB} GB free on C:")
    if (so_far := spent()) + CALL_CAP_USD > TOTAL_CAP_USD:
        raise Stop(f"cap: {so_far:.2f} USD spent, a session's cap does not fit under "
                   f"{TOTAL_CAP_USD:.2f}")  # fmt: skip
    log(f"{name} {arm}: start ({so_far:.2f} USD spent)")
    record = session(row, arm, keyfile)
    report_session(record)
    for after in AFTER_SESSION:
        after(record)
    status = str(record["calls"][0].get("status", ""))
    if status.startswith("ABORTED") or status == "NOT RUN (harness)":
        raise RuntimeError(f"{name} {arm}: {status}")
    if status == NOT_RUN_ERROR:
        raise Stop(f"{name} {arm}: an API or usage-limit error result")
    if arm == "S" and record["probe"]["deferral"]["find_deferred"]:
        raise Stop(f"{name} S: find_in_repo was deferred despite alwaysLoad")


def gradable(name: str, arm: str) -> bool:
    """A session that ran (not aborted, not unrun) and has no grade yet."""
    path = OUT / name / arm / "row.json"
    if not path.exists() or (OUT / name / arm / "grade.json").exists():
        return False
    return not read_json(path)["calls"][0].get("status")


def grade_done(name: str, arms: tuple[str, ...]) -> None:
    for arm in arms:
        if not gradable(name, arm):
            continue
        try:
            log(f"{name} {arm}: resolved {grade_arm(name, arm)}")
        except (OSError, subprocess.SubprocessError) as exc:
            log(f"{name} {arm}: grading failed ({exc}); `run` again grades it")


def probe() -> int:
    preflight()
    known = singles_run.rows()
    keyfile = run.keyfile_from_indagis()
    try:
        for name, arms in PLAN:
            one_instance(known[name], arms, keyfile)
    finally:
        keyfile.unlink(missing_ok=True)
        run.drop_arm_keys()
    return 0


# ---- summary -------------------------------------------------------------------------------------


def n_reference(name: str) -> dict[str, Any] | None:
    """dev1's N row of a development single (read only)."""
    path = SINGLES / name / "N"
    if not (path / "row.json").exists():
        return None
    from .session_facts import api_calls, caching

    call = read_json(path / "row.json")["calls"][0]
    grade = read_json(path / "grade.json") if (path / "grade.json").exists() else {}
    cache = caching(api_calls(path / "transcript.jsonl"))
    return {"turns": call.get("turns"), "cost_usd": round(call.get("cost_usd", 0.0), 4),
            "resolved": grade.get("resolved"), "cache_ok": cache["ok"],
            "source": "dev1"}  # fmt: skip


def summary() -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for name, arms in PLAN:
        for arm in ("S", "N"):
            path = OUT / name / arm / "row.json"
            if arm not in arms:
                if ref := n_reference(name):
                    rows.append({"instance": name, "arm": "N", **ref})
                continue
            if not path.exists():
                continue
            record, grade = read_json(path), OUT / name / arm / "grade.json"
            call, probe_ = record["calls"][0], record["probe"]
            rows.append({"instance": name, "arm": arm, "turns": call.get("turns"),
                         "cost_usd": round(call.get("cost_usd", 0.0), 4),
                         "resolved": read_json(grade)["resolved"] if grade.exists() else None,
                         "cache_ok": probe_["caching"]["ok"], "source": "probe",
                         "status": call.get("status") or call.get("subtype"),
                         "calls": probe_["watched_calls"],
                         "find_deferred": probe_["deferral"]["find_deferred"],
                         "find_in_init": probe_["find_in_init_tools"],
                         "latency": probe_["latency"],
                         "hooks_session_start_s": probe_["hooks"]["session_start_s"],
                         "hooks_first_ups_s":
                             probe_["hooks"]["first_user_prompt_submit_s"]})  # fmt: skip
    out = {"spent_usd": spent(), "cap_usd": TOTAL_CAP_USD, "rows": rows}
    (OUT / "summary.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "run", "summary"))
    args = parser.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.action == "check":
        from .check_alwaysload import check

        return check()
    if args.action == "summary":
        print(json.dumps(summary(), indent=1))
        return 0
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # a stray Ctrl+C killed phase A mid-grade
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    log(f"PROBE START plan {[(n, a) for n, a in PLAN]} spent {spent():.2f} USD "
        f"cap {TOTAL_CAP_USD:.2f}")  # fmt: skip
    try:
        probe()
    except Stop as why:
        summary()
        log(f"PROBE STOP: {why} (spent {spent():.2f} USD)")
        return 0
    except Exception as exc:  # noqa: BLE001  (logged with its trace; the monitor greps for it)
        traceback.print_exc()
        log(f"PROBE FAILED: {type(exc).__name__}: {exc} (spent {spent():.2f} USD)")
        return 1
    done = summary()
    log(f"PROBE DONE: {len(done['rows'])} rows, spent {done['spent_usd']:.2f} USD")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
