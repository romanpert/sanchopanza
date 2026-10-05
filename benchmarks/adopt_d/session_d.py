"""Phase D's sessions: set up, run, record and grade one session. Part of `run_d.py`, which
re-exports every name here; this module reads run_d's names when called, not when imported.

- `prepare`: the working copy exported, the S arm's install and key, D's decider probed, the
  evidence folder created; nothing spent. Runs for an instance's six sessions one at a time,
  before any session starts (`run_d.setup_all`), and cleans up after itself when it fails, so a
  setup fault leaves no folder that reads as a session.
- `one`: the `claude -p` call (`session_call`) on a prepared copy, its patch, transcript and row.
- `grade_arm` and friends: `singles_run.grade`'s harness call on an evidence path.
- `write_json`: row.json and grade.json are written whole or not at all (temp file, os.replace).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import run_d  # registered by run_d itself (run_d imports this module)


def write_json(path: Path, data: Any) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
    os.replace(tmp, path)


# ---- setup, before anything is spent -------------------------------------------------------------


def prepare(row: dict[str, Any], arm: str, rep: int, keyfile: Path) -> dict[str, Any]:
    """One session's working copy, install and key, without starting it. Phase A's refusals: a
    session that started before (its stream exists) and left no row, a working copy whose Claude
    Code folder already holds a session. A folder with no stream is an earlier setup that never
    reached its session: removed and done again."""
    name = row["instance_id"]
    evidence, work = run_d.evidence_of(name, rep, arm), run_d.work_of(name, rep, arm)
    if (evidence / "row.json").exists() or (evidence / "stream-1.jsonl").exists():
        raise RuntimeError(f"{name} r{rep} {arm}: an earlier session is there ({evidence})")
    if any(run_d.run.projects_dir(work).glob("*.jsonl")):  # amendment 2
        raise RuntimeError(f"{name} r{rep} {arm}: earlier sessions in "
                           f"{run_d.run.projects_dir(work)}")  # fmt: skip
    probes: list[str] = []
    if arm == "S":  # amendment 5: the session's own key path, and what its hooks would build
        keyfile = run_d.run.arm_keyfile(keyfile, run_d.key_name(name, rep), arm)
        probes = [run_d.run.decider_probe(keyfile)]
        if probes[-1] != run_d.DECIDER:
            raise RuntimeError(f"{name} r{rep} S: its hooks would build {probes[-1]}")
    run_d.docker_env.remove_tree(evidence)
    try:
        evidence.mkdir(parents=True)
        run_d.docker_env.remove_tree(work)
        base = run_d.docker_env.export(row["image"], work)
        mcp = run_d.run.install_sancho(work, evidence, keyfile) if arm == "S" else None
    except BaseException:
        discard({"evidence": evidence, "work": work})
        raise
    return {"row": row, "arm": arm, "rep": rep, "evidence": evidence, "work": work, "base": base,
            "mcp": mcp, "probes": probes}  # fmt: skip


def discard(setup: dict[str, Any]) -> None:
    """Undo a setup whose session never started: no folder is left to read as a session."""
    for path in (setup["evidence"], setup["work"]):
        try:
            run_d.docker_env.remove_tree(path)
        except RuntimeError as exc:
            run_d.log(f"could not remove {path} after a setup fault: {exc}")


# ---- one session ---------------------------------------------------------------------------------


def one(setup: dict[str, Any]) -> None:
    row, arm, rep = setup["row"], setup["arm"], setup["rep"]
    name, evidence, work = row["instance_id"], setup["evidence"], setup["work"]
    command = run_d.singles_run.test_command(row["repo"])
    env = {**run_d.run.child_env(row["image"], setup["base"]),
           "ADOPT_PREFIX": run_d.singles_run.CONDA, "ADOPT_TEST_CMD": command}  # fmt: skip
    prompt = run_d.singles_run.PROMPT.format(issue=row["problem_statement"].strip(),
                                             command=command)  # fmt: skip
    started = time.time()
    call = session_call(run_d.run.command(run_d.D_MODEL, prompt, None, setup["mcp"]), work, env,
                        prompt, evidence)  # fmt: skip
    run_d.log(f"{name} r{rep} {arm}: {call.get('status') or call.get('subtype')} "
              f"{call['cost_usd']:.3f} USD turns {call.get('turns')}")  # fmt: skip
    (evidence / "final.patch").write_text(run_d.docker_env.agent_diff(work, setup["base"]),
                                          encoding="utf-8", newline="\n")  # fmt: skip
    session = call.get("session")
    source = next(run_d.run.CLAUDE_PROJECTS.glob(f"*/{session}.jsonl"), None) if session else None
    if source:
        shutil.copy(source, evidence / "transcript.jsonl")
    probes = setup["probes"]
    write_json(evidence / "row.json", {
        "instance": name, "rep": rep, "arm": arm, "model": run_d.D_MODEL, "image": row["image"],
        "base": setup["base"], "started": started, "jev_usd": run_d.run.jev_usd(evidence),
        "sanchopanza": run_d.run.provenance(), "claude_version": run_d.run.claude_version(),
        "inputs": run_d.unsealed_inputs(),
        "transcript": {"source": str(source) if source else None, "copied": bool(source)},
        **({"decider": probes, "find_hidden": run_d.find_hidden(evidence)} if probes else {}),
        "calls": [call]})  # fmt: skip


def limit_error(stream: Path) -> bool:
    """An error result that names a usage limit or an overload: the API's 429 or 529, or the
    limit or the overload in its text. No outcome was seen, so running it again is unbiased."""
    result = next((e for e in reversed(run_d.confirm.events(stream)) if e.get("type") == "result"),
                  {})  # fmt: skip
    return result.get("api_error_status") in (429, 529) or bool(
        run_d.LIMIT_TEXT.search(str(result.get("result") or ""))
    )


def session_call(
    cmd: list[str], work: Path, env: dict[str, str], prompt: str, evidence: Path
) -> dict[str, Any]:
    """The `claude -p` call as singles_run.one makes it (stderr kept beside the stream)."""
    run = run_d.run
    # The instance's hold (HOLD_USD) is what bounds the call against the ceiling; it is
    # reserved and settled as in singles_run.one so the in-process ledger moves with it, and
    # settled whatever happens (run's ledger takes its own lock: safe across threads).
    if not run.reserve(float("inf")):
        return {"request": 1, "status": "NOT RUN (ceiling)", "cost_usd": 0.0}
    stream, began, cost = evidence / "stream-1.jsonl", time.time(), 0.0
    try:
        with stream.open("wb") as out, (evidence / "stream-1.err").open("wb") as err:
            try:
                code = subprocess.run(cmd, cwd=work, env=env, input=run.stdin_for(prompt),
                                      stdout=out, stderr=err,
                                      timeout=run.CALL_TIMEOUT_S).returncode  # fmt: skip
            except subprocess.TimeoutExpired:
                code = -9
            except OSError as exc:  # could not even start `claude`: the harness, not the arm
                err.write(f"{type(exc).__name__}: {exc}".encode())
                code = -1
        seen = run.facts(stream)
        # A call cut by the timeout is charged its cap (a fresh session: nothing to take a
        # difference from).
        cost = seen["cost_usd"] or (run.CALL_CAP_USD if code == -9 else 0.0)
    finally:
        run.settle(cost)
    call = {"request": 1, "exit": code, "wall_s": round(time.time() - began, 1), **seen,
            "cost_usd": cost}  # fmt: skip
    if code == -1 or run.harness_failed(code, seen):
        return {**call, "status": run_d.NOT_RUN_HARNESS}
    if seen.get("api_error"):
        # A usage limit or an overload is not a result of the arm; any other error result ran
        # (graded on its diff) and stops the batch so that it is looked at.
        return {**call, "status": run_d.NOT_RUN_ERROR if limit_error(stream) else run_d.ERROR_OTHER}
    return call


# ---- grading (singles_run.grade's harness call, on an evidence path) -----------------------------


def grade_arm(name: str, evidence: Path, label: str) -> bool | None:
    """The official harness on the session's final diff; None (and no grade.json) when the
    harness gives no report: missing, not a loss. An empty diff is not resolved, without the
    harness (prereg, "Measures"): swebench drops an empty prediction before running it and writes
    no report, and the official leaderboard counts it unresolved. Every grade.json records the
    sha256 of `run_swe.py`."""
    swe = run_d.singles_run.SWE
    wrapper = {"run_swe_sha256": run_d.guard_d.file_sha(swe / "run_swe.py")}
    patch = (evidence / "final.patch").read_text(encoding="utf-8")
    if patch == "":  # the harness's own test: `model_patch in ["", None]`
        write_json(evidence / "grade.json", {"resolved": False, "reason": run_d.EMPTY_DIFF,
                                             **wrapper})  # fmt: skip
        return False
    model = f"adopt-d-{label}"
    preds = evidence / "preds.jsonl"
    preds.write_text(json.dumps({"instance_id": name, "model_name_or_path": model,
                                 "model_patch": patch}) + "\n",
                     encoding="utf-8", newline="\n")  # fmt: skip
    run_id = f"{model}-{int(time.time())}"
    subprocess.run([str(run_d.singles_run.SWE_PYTHON), str(swe / "run_swe.py"), "-d",
                    "SWE-bench/SWE-bench_Verified", "-p", str(preds), "-i", name,
                    "--max_workers", "1", "-id", run_id], cwd=swe, capture_output=True,
                   env={**os.environ, "PYTHONUTF8": "1"}, timeout=3600)  # fmt: skip
    report = swe / "logs" / "run_evaluation" / run_id / model / name / "report.json"
    if not report.exists():
        run_d.log(f"{name} {label}: no report from the harness, not graded")
        return None
    resolved = bool(run_d.read_json(report).get(name, {}).get("resolved"))
    write_json(evidence / "grade.json", {"resolved": resolved, "report": str(report), **wrapper})
    return resolved


def grade(name: str, rep: int) -> dict[str, bool]:
    """Both sessions of a repetition; one already graded keeps its grade."""
    out: dict[str, bool] = {}
    for arm in run_d.ARMS:
        evidence = run_d.evidence_of(name, rep, arm)
        if not gradable(evidence):
            continue
        if (resolved := grade_arm(name, evidence, f"{arm}-r{rep}")) is not None:
            out[arm] = resolved
    return out


def gradable(evidence: Path) -> bool:
    """A final diff with no grade yet, empty or not (an empty one is graded without Docker)."""
    return (evidence / "final.patch").exists() and not (evidence / "grade.json").exists()


def needs_harness(name: str) -> bool:
    """Some session of the instance waits for the harness: a non-empty diff with no grade."""
    return any(gradable(e := run_d.evidence_of(name, rep, arm))
               and (e / "final.patch").read_text(encoding="utf-8") != ""
               for rep in range(1, run_d.REPS + 1) for arm in run_d.ARMS)  # fmt: skip


def ungraded(name: str) -> list[int]:
    return [rep for rep in range(1, run_d.REPS + 1) for arm in run_d.ARMS
            if gradable(run_d.evidence_of(name, rep, arm))]  # fmt: skip


def grade_instance(name: str) -> None:
    """Grades what waits; the log says that it graded, never what (no outcome is seen live)."""
    for rep in dict.fromkeys(ungraded(name)):
        try:
            grade(name, rep)
            run_d.log(f"graded {name} r{rep}")
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            run_d.log(f"{name} r{rep}: grading failed ({exc}); `run` or `grade` again grades it")
