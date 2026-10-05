"""Phase D of the adoption study: the held-out singles, three repetitions of N and S. Paid.

    python benchmarks/adopt_d/run_d.py check    # free: every refusal, the plan and the ledger
    python benchmarks/adopt_d/run_d.py ledger   # free: list price spent so far, per root
    python benchmarks/adopt_d/run_d.py run      # the batch, resumable (start it with run-d.cmd)
    python benchmarks/adopt_d/run_d.py grade    # Docker, free: grades what ran, starts nothing
    python benchmarks/adopt_d/run_d.py selftest <id>  # Docker, free: the grading path (selftest_d)

As `docs/results/2026-10-03-adopt-d/prereg.md` fixes it ("Arms, model, sessions", "Caps, in
code", "The runner", items 1-5). Phase A's modules are imported as a library and never edited:
`run` reads ADOPT_SANCHO when imported, so D's frozen copy is set here first, and the private
Claude Code 2.1.285 goes first on PATH for this process and its children.

- One session per instance, repetition and arm, each in a fresh working copy at
  `run.WORK/<id>-r<k>-<arm>`, its evidence at `singles-d/<id>/r<k>/<arm>`, its key at
  `run.arm_keyfile(key, "<id>-r<k>", "S")`. N and S of a repetition start together; an instance's
  three pairs run before the next instance; its image is pulled once and dropped after its
  sessions are graded. Instances in a seeded order interleaving the strata (`order`, seed
  20261005), computed from `singles-validated.json`.
- Before each pair: D's seal holds, and the inputs both arms load that no seal covers
  (`~/.claude/CLAUDE.md`, `~/.claude/rules/*.md`, the harness's `verified-rows.json` and
  `run_swe.py`) still have the hashes recorded at the batch's start (logged, and kept in every
  row; `run_swe.py`'s in every grade.json). One batch at a time (`singles-d/batch.lock`).
- Money (list price): `--max-budget-usd 1.50` per call; an instance's six sessions' caps (9.00)
  held against the absolute ceiling before it starts, all or nothing; the ledger is every row
  under `adopt/runs/`, `adopt/singles/`, `adopt/singles-d/` and the development probes' roots.
- Phase A's refusals stay: a session that started (its stream exists) and left no row is never
  run again (its pair is missing); a working copy whose Claude Code folder already holds a session.
- Run again whole, since no outcome was seen: an instance with a usage-limit error result (a 429
  or the weekly limit named in the result), a session `claude -p` never started (no session, no
  result, nothing spent) or a folder with no row and no stream. Its sessions are set aside under
  `singles-d/<id>-limit<k>/` (counted in the ledger, read by no verdict) and the batch stops.
- The batch also stops (a pause: `run` again resumes it, grading for free what already ran) on:
  any other error result (it counts as run and is graded); an S session failing a systemic
  treatment criterion ((a) to (e), (g), or D's commit), or (f) in 2 of the last 3 S sessions; a
  changed seal or input; the ceiling; under 15 GB free. No retries. Ctrl+C is ignored.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ADOPT = REPO / "benchmarks" / "adopt"
ROOT = Path.home() / ".cache" / "sanchopanza" / "adopt"

# ---- to fill in at sealing (the runner refuses while either is unset) ----------------------------
# The frozen commit phase D runs (`freeze.py <commit>`, extras jev and mcp): the full sha.
D_COMMIT = "7a39a1f0d4ff8e9cf5c99046ee0aa818ffe955d9"
# Everything spent at sealing under adopt/runs, adopt/singles, adopt/singles-d and the development
# probes' roots (`run_d.py ledger`); the absolute ceiling is this plus CEILING_ADDED_USD.
CEILING_BASE_USD: float | None = None
CEILING_ADDED_USD = 110.00

FROZEN = ROOT / "frozen" / f"{D_COMMIT[:12] or 'unset'}-jev-mcp"
D_EXE = FROZEN / "Scripts" / "sanchopanza.exe"
CLAUDE_DIR = ROOT / "claude-2.1.285"

_given = os.environ.get("ADOPT_SANCHO")
if _given and Path(_given).resolve() != D_EXE.resolve():
    raise RuntimeError(f"ADOPT_SANCHO={_given} is not phase D's frozen copy {D_EXE}")
os.environ["ADOPT_SANCHO"] = str(D_EXE)
os.environ["DISABLE_AUTOUPDATER"] = "1"
_path = os.environ.get("PATH", "").split(os.pathsep)
if not _path or Path(_path[0]) != CLAUDE_DIR:
    os.environ["PATH"] = os.pathsep.join([str(CLAUDE_DIR), *_path])
sys.path.insert(0, str(ADOPT))
sys.path.append(str(HERE))

import confirm  # noqa: E402
import docker_env  # noqa: E402
import guard_d  # noqa: E402
import hook_env  # noqa: E402
import run  # noqa: E402
import singles_run  # noqa: E402
from plan_d import VALIDATED, instances, order  # noqa: E402,F401  (run_d.instances, .order)

if run.SANCHO != D_EXE or Path(hook_env.SANCHO) != D_EXE:
    # `run` was imported before this module, with another ADOPT_SANCHO.
    raise RuntimeError(f"phase A's modules run {run.SANCHO}, not phase D's copy {D_EXE}")

__all__ = ["confirm", "docker_env", "hook_env", "run", "singles_run"]  # phase A's, unchanged

D_MODEL = "claude-haiku-4-5-20251001"
CALL_CAP_USD = 1.50
CLAUDE_VERSION = "2.1.285"
DECIDER = "JevDecider"
EXTRAS = ("jev", "mcp")
ARMS = ("N", "S")
REPS = 3
HOLD_USD = CALL_CAP_USD * len(ARMS) * REPS  # an instance's six sessions, 9.00
RUNS_D = run.ROOT / "singles-d"
# The development probes' outputs (`benchmarks/adopt_dev/common.py`, PROFILES), read only.
DEV_ROOTS = (ROOT / "dev-alwaysload", ROOT / "dev-need", ROOT / "dev-nudge")
PREREG = REPO / "docs" / "results" / "2026-10-03-adopt-d"
A_MANIFEST = REPO / "docs" / "results" / "2026-09-30-adopt" / "prereg-confirm.manifest.json"
FIND_TOOL = "mcp__sanchopanza__find_in_repo"
NOT_RUN_ERROR = "NOT RUN (error result)"  # a usage limit: run again whole
NOT_RUN_HARNESS = "NOT RUN (harness)"  # `claude -p` never started: run again whole
ERROR_OTHER = "error result (not a usage limit)"  # ran: graded on its diff, and the batch stops
# What makes an error result a usage limit: the 429 the API reports, or the limit named in the
# result's text ("You've hit your weekly limit", phase A's ten).
LIMIT_TEXT = re.compile(r"\b429\b|usage limit|weekly limit|rate limit|hit your [\w ]*limit", re.I)
EMPTY_DIFF = "empty diff"
MIN_DISK_GB = 15.0
CLAUDE_HOME = Path.home() / ".claude"
# Treatment criteria whose failure says the install or the harness is broken for every session to
# come: the batch stops at the first. (f), Jev's error rate, can be one bad session: it excludes
# that session, and stops the batch only when it fails in F_STOP of the last F_WINDOW S sessions.
SYSTEMIC = ("commit", "a", "b", "c", "d", "e", "g")
F_STOP, F_WINDOW = 2, 3
# What D's seal must name, besides every file of benchmarks/adopt_d/*.py, *.json and
# benchmarks/adopt/*.py as they are now.
REQUIRED = (
    "docs/results/2026-10-03-adopt-d/prereg.md",
    "benchmarks/adopt_d/run_d.py",
    "benchmarks/adopt_d/confirm_d.py",
    "benchmarks/adopt_d/validate_d.py",
    "benchmarks/adopt_d/singles-validated.json",
    "benchmarks/adopt/run.py",
    "benchmarks/adopt/singles_run.py",
    "benchmarks/adopt/docker_env.py",
    "benchmarks/adopt/hook_env.py",
    "benchmarks/adopt/confirm.py",
    "benchmarks/candor/seal.py",
)
SEALED_GLOBS = ("benchmarks/adopt_d/*.py", "benchmarks/adopt_d/*.json", "benchmarks/adopt/*.py")


class Stop(Exception):
    """The batch ends here without a fault: a usage limit, a cap, find not visible, the disk."""


def log(text: str) -> None:
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {text}", flush=True)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---- the seal and the refusals -------------------------------------------------------------------


def _seal_module() -> Any:
    spec = importlib.util.spec_from_file_location("adopt_d_seal", REPO / "benchmarks" / "candor" /
                                                  "seal.py")  # fmt: skip
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seal_refusal(
    folder: Path | None = None, repo: Path | None = None, phase_a: Path | None = None
) -> str | None:
    """Why D's seal does not hold, or None: `prereg.sha256` is the hash of its manifest, the
    manifest names REQUIRED and every file the globs reach now, each file still has its hash, and
    phase A's files still have the hashes of phase A's own manifest (unchanged since A)."""
    folder, repo = folder or PREREG, repo or REPO
    phase_a = phase_a or A_MANIFEST
    seal, manifest_path = folder / "prereg.sha256", folder / "prereg.manifest.json"
    if not seal.exists() or not manifest_path.exists():
        return "phase D is not sealed: no prereg.sha256 (or no manifest)"
    manifest = read_json(manifest_path)
    now = {p.relative_to(repo).as_posix() for g in SEALED_GLOBS for p in repo.glob(g)
           if p.is_file()}  # fmt: skip
    if unnamed := sorted((set(REQUIRED) | now) - set(manifest)):
        return f"the seal does not name {unnamed}"
    digest = _seal_module().digest
    for path, value in manifest.items():
        if not (repo / path).exists() or digest(repo / path) != value:
            return f"{path} changed since the seal"
    sealed_a = read_json(phase_a) if phase_a.exists() else {}
    for path, value in manifest.items():
        if path.startswith("benchmarks/adopt/") and sealed_a.get(path) != value:
            return f"{path} is not phase A's sealed file"
    combined = hashlib.sha256("".join(f"{k} {v}\n" for k, v in manifest.items()).encode())
    if combined.hexdigest() != seal.read_text(encoding="utf-8").strip():
        return "prereg.sha256 does not match its manifest"
    return None


def d_refusal(keyfile: Path, model: str = D_MODEL) -> str | None:
    """Why phase D may not run (prereg, "Caps, in code"), or None. The decider probe is last:
    it is the only check that starts a process of the frozen copy (free, no question asked)."""
    if not D_COMMIT:
        return "D_COMMIT is not filled in (the frozen commit, at sealing)"
    if CEILING_BASE_USD is None:
        return "CEILING_BASE_USD is not filled in (the ledger at sealing)"
    if why := seal_refusal():
        return why
    stamp = run.frozen_stamp() or {}
    if stamp.get("commit") != D_COMMIT:
        return f"the frozen copy is {stamp.get('commit')}, phase D runs {D_COMMIT[:12]}: freeze it"
    if missing := [e for e in EXTRAS if e not in (stamp.get("extras") or [])]:
        return f"the frozen copy was installed without {missing}"
    if model != D_MODEL or run.MODELS["haiku"] != D_MODEL:
        return f"phase D runs {D_MODEL}"
    if run.CALL_CAP_USD != CALL_CAP_USD:
        return f"phase D's call cap is {CALL_CAP_USD}, run has {run.CALL_CAP_USD}"
    if (found := run.claude_version()) != CLAUDE_VERSION:
        return f"phase D runs Claude Code {CLAUDE_VERSION}, found {found or 'none'}"
    if (found := run.decider_probe(keyfile)) != DECIDER:
        return f"the S arms' hooks would build {found}, not {DECIDER}"
    return None


# ---- the plan ------------------------------------------------------------------------------------


def evidence_of(name: str, rep: int, arm: str) -> Path:
    return RUNS_D / name / f"r{rep}" / arm


def work_of(name: str, rep: int, arm: str) -> Path:
    return run.WORK / f"{name}-r{rep}-{arm}"


def key_name(name: str, rep: int) -> str:
    """The name `run.arm_keyfile` keys an S session's key path by: one per repetition."""
    return f"{name}-r{rep}"


# ---- what no seal covers: inputs both arms load, and one batch at a time -----------------------


def unsealed_inputs() -> dict[str, str | None]:
    return guard_d.inputs(CLAUDE_HOME, singles_run.SWE)


def pair_refusal(recorded: dict[str, str | None]) -> str | None:
    """Why the next pair may not start: the seal, or an input changed since the batch started."""
    if why := seal_refusal():
        return why
    if moved := guard_d.changed(recorded, unsealed_inputs()):
        return f"inputs changed since the batch started: {moved}"
    return None


def take_lock() -> Path:
    return guard_d.take_lock(RUNS_D / "batch.lock", log)


# ---- money ---------------------------------------------------------------------------------------


def row_cost(path: Path) -> float:
    row = read_json(path)
    return sum(c.get("cost_usd", 0.0) for c in row["calls"]) + row.get("jev_usd", 0.0)


def spent_d(root: Path | None = None) -> float:
    """Every row under singles-d (set-aside `<id>-limit<k>` folders too), Jev included; an
    evidence folder with a stream and no row (a crash) is charged what its stream reports, or
    its cap when it reports nothing."""
    root = RUNS_D if root is None else root
    total = 0.0
    for evidence in (p for p in root.glob("*/*/*") if p.is_dir()):
        if (evidence / "row.json").exists():
            total += row_cost(evidence / "row.json")
        elif (stream := evidence / "stream-1.jsonl").exists():
            total += (run.facts(stream)["cost_usd"] or CALL_CAP_USD) + run.jev_usd(evidence)
    return total


def spent_dev(roots: tuple[Path, ...] = DEV_ROOTS) -> float:
    """The development probes' rows and abandoned attempts, as `probe_alwaysload.spent`."""
    total = 0.0
    for root in roots:
        total += sum(row_cost(p) for p in root.glob("*/*/row.json"))
        for path in root.glob("*/*/abandoned.json"):
            aside = read_json(path)
            total += aside["charged_usd"] + aside.get("jev_usd", 0.0)
    return total


def ledger_parts() -> dict[str, float]:
    return {"runs": run.spent_so_far(), "singles": singles_run.spent_singles(),
            "singles-d": spent_d(), "dev": spent_dev()}  # fmt: skip


def ledger() -> float:
    return round(sum(ledger_parts().values()), 6)


def ceiling() -> float:
    if CEILING_BASE_USD is None:
        raise SystemExit("CEILING_BASE_USD is not filled in")
    return CEILING_BASE_USD + CEILING_ADDED_USD


# ---- evidence (g) --------------------------------------------------------------------------------


def find_hidden(evidence: Path) -> str:
    """Why find_in_repo was not visible to the session (prereg (g)), or "" when it was: in the
    init line's tools, the transcript copied, named by no `deferred_tools_delta` attachment of
    it (its `addedNames` and `addedLines`), and the copied mcp.json registering its server with
    `"alwaysLoad": true`."""
    stream = evidence / "stream-1.jsonl"
    events = confirm.events(stream) if stream.exists() else []
    init = next((e for e in events if e.get("type") == "system" and e.get("subtype") == "init"),
                None)  # fmt: skip
    if init is None:
        return "no init line"
    if FIND_TOOL not in (init.get("tools") or []):
        return "not in the init line's tools"
    transcript = evidence / "transcript.jsonl"
    if not transcript.exists():
        return "transcript not copied"
    for entry in confirm.events(transcript):
        attachment = entry.get("attachment")
        if not isinstance(attachment, dict) or attachment.get("type") != "deferred_tools_delta":
            continue
        added = [*(attachment.get("addedNames") or []), *(attachment.get("addedLines") or [])]
        if any(FIND_TOOL in str(name) for name in added):
            return "deferred: a deferred_tools_delta adds it"
    mcp = evidence / "mcp.json"
    if not mcp.exists():
        return "no copied mcp.json"
    server = (read_json(mcp).get("mcpServers") or {}).get("sanchopanza") or {}
    if server.get("alwaysLoad") is not True:
        return "its server has no alwaysLoad in mcp.json"
    return ""


def find_visible(evidence: Path) -> bool:
    return not find_hidden(evidence)


# ---- one session (singles_run.one with the repetition in its paths) ------------------------------


def one(row: dict[str, Any], arm: str, rep: int, keyfile: Path) -> None:
    name = row["instance_id"]
    evidence, work = evidence_of(name, rep, arm), work_of(name, rep, arm)
    if (evidence / "row.json").exists():
        return
    if evidence.exists():
        # An earlier attempt left no row: never started here; the runner sets it aside first.
        raise RuntimeError(f"{name} r{rep} {arm}: evidence of an earlier attempt and no row.json")
    if any(run.projects_dir(work).glob("*.jsonl")):  # amendment 2
        raise RuntimeError(f"{name} r{rep} {arm}: earlier sessions in {run.projects_dir(work)}")
    probes: list[str] = []
    if arm == "S":  # amendment 5: the session's own key path, and what its hooks would build
        keyfile = run.arm_keyfile(keyfile, key_name(name, rep), arm)
        probes = [run.decider_probe(keyfile)]
        if probes[-1] != DECIDER:
            raise RuntimeError(f"{name} r{rep} S: its hooks would build {probes[-1]}")
    evidence.mkdir(parents=True)
    docker_env.remove_tree(work)
    base = docker_env.export(row["image"], work)
    mcp = run.install_sancho(work, evidence, keyfile) if arm == "S" else None
    command = singles_run.test_command(row["repo"])
    env = {**run.child_env(row["image"], base), "ADOPT_PREFIX": singles_run.CONDA,
           "ADOPT_TEST_CMD": command}  # fmt: skip
    prompt = singles_run.PROMPT.format(issue=row["problem_statement"].strip(), command=command)
    started = time.time()
    call = session_call(run.command(D_MODEL, prompt, None, mcp), work, env, prompt, evidence)
    log(f"{name} r{rep} {arm}: {call.get('status') or call.get('subtype')} "
        f"{call['cost_usd']:.3f} USD turns {call.get('turns')}")  # fmt: skip
    (evidence / "final.patch").write_text(docker_env.agent_diff(work, base), encoding="utf-8",
                                          newline="\n")  # fmt: skip
    session = call.get("session")
    source = next(run.CLAUDE_PROJECTS.glob(f"*/{session}.jsonl"), None) if session else None
    if source:
        shutil.copy(source, evidence / "transcript.jsonl")
    record = {"instance": name, "rep": rep, "arm": arm, "model": D_MODEL, "image": row["image"],
              "base": base, "started": started, "jev_usd": run.jev_usd(evidence),
              "sanchopanza": run.provenance(), "claude_version": run.claude_version(),
              "inputs": unsealed_inputs(),
              "transcript": {"source": str(source) if source else None, "copied": bool(source)},
              **({"decider": probes, "find_hidden": find_hidden(evidence)} if probes else {}),
              "calls": [call]}  # fmt: skip
    (evidence / "row.json").write_text(json.dumps(record, indent=1), encoding="utf-8")


def limit_error(stream: Path) -> bool:
    """An error result that names a usage limit: the API's 429, or the limit in its text."""
    result = next((e for e in reversed(confirm.events(stream)) if e.get("type") == "result"), {})
    return result.get("api_error_status") == 429 or bool(
        LIMIT_TEXT.search(str(result.get("result") or ""))
    )


def session_call(
    cmd: list[str], work: Path, env: dict[str, str], prompt: str, evidence: Path
) -> dict[str, Any]:
    """The `claude -p` call as singles_run.one makes it (stderr kept beside the stream)."""
    # The instance's hold (HOLD_USD) is what bounds the call against the ceiling; it is
    # reserved and settled as in singles_run.one so the in-process ledger moves with it, and
    # settled whatever happens.
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
        return {**call, "status": NOT_RUN_HARNESS}
    if seen.get("api_error"):
        # A usage limit is not a result of the arm; any other error result ran (graded on its
        # diff) and stops the batch so that it is looked at.
        return {**call, "status": NOT_RUN_ERROR if limit_error(stream) else ERROR_OTHER}
    return call


# ---- grading (singles_run.grade's harness call, on an evidence path) -----------------------------


def grade_arm(name: str, evidence: Path, label: str) -> bool | None:
    """The official harness on the session's final diff; None (and no grade.json) when the
    harness gives no report: missing, not a loss. An empty diff is not resolved, without the
    harness (prereg, "Measures"): swebench drops an empty prediction before running it and writes
    no report, and the official leaderboard counts it unresolved. Every grade.json records the
    sha256 of `run_swe.py`."""
    swe = singles_run.SWE
    wrapper = {"run_swe_sha256": guard_d.file_sha(swe / "run_swe.py")}
    patch = (evidence / "final.patch").read_text(encoding="utf-8")
    if patch == "":  # the harness's own test: `model_patch in ["", None]`
        (evidence / "grade.json").write_text(json.dumps({"resolved": False, "reason": EMPTY_DIFF,
                                                         **wrapper}),
                                             encoding="utf-8")  # fmt: skip
        return False
    model = f"adopt-d-{label}"
    preds = evidence / "preds.jsonl"
    preds.write_text(json.dumps({"instance_id": name, "model_name_or_path": model,
                                 "model_patch": patch}) + "\n",
                     encoding="utf-8", newline="\n")  # fmt: skip
    run_id = f"{model}-{int(time.time())}"
    subprocess.run([str(singles_run.SWE_PYTHON), str(swe / "run_swe.py"), "-d",
                    "SWE-bench/SWE-bench_Verified", "-p", str(preds), "-i", name,
                    "--max_workers", "1", "-id", run_id], cwd=swe, capture_output=True,
                   env={**os.environ, "PYTHONUTF8": "1"}, timeout=3600)  # fmt: skip
    report = swe / "logs" / "run_evaluation" / run_id / model / name / "report.json"
    if not report.exists():
        log(f"{name} {label}: no report from the harness, not graded")
        return None
    resolved = bool(read_json(report).get(name, {}).get("resolved"))
    (evidence / "grade.json").write_text(json.dumps({"resolved": resolved, "report": str(report),
                                                     **wrapper}),
                                         encoding="utf-8")  # fmt: skip
    return resolved


def grade(name: str, rep: int) -> dict[str, bool]:
    """Both sessions of a repetition; one already graded keeps its grade."""
    out: dict[str, bool] = {}
    for arm in ARMS:
        evidence = evidence_of(name, rep, arm)
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
    return any(gradable(e := evidence_of(name, rep, arm))
               and (e / "final.patch").read_text(encoding="utf-8") != ""
               for rep in range(1, REPS + 1) for arm in ARMS)  # fmt: skip


def ungraded(name: str) -> list[int]:
    return [rep for rep in range(1, REPS + 1) for arm in ARMS
            if gradable(evidence_of(name, rep, arm))]  # fmt: skip


def grade_instance(name: str) -> None:
    """Grades what waits; the log says that it graded, never what (no outcome is seen live)."""
    for rep in dict.fromkeys(ungraded(name)):
        try:
            grade(name, rep)
            log(f"graded {name} r{rep}")
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            log(f"{name} r{rep}: grading failed ({exc}); `run` or `grade` again grades it")


# ---- state, set-aside, the stops -----------------------------------------------------------------


def state(name: str, rep: int, arm: str) -> str:
    """absent (never started); missing (its stream exists and no row: a crash after it started,
    never run again); rerun (a usage limit, a `claude -p` that never started, or a folder with no
    row and no stream: no outcome seen, set aside and run again whole); or done."""
    evidence = evidence_of(name, rep, arm)
    if not (evidence / "row.json").exists():
        if not evidence.exists():
            return "absent"
        return "missing" if (evidence / "stream-1.jsonl").exists() else "rerun"
    status = str(read_json(evidence / "row.json")["calls"][0].get("status", ""))
    return "rerun" if status in (NOT_RUN_ERROR, NOT_RUN_HARNESS) else "done"


def states(name: str, rep: int) -> dict[str, str]:
    return {arm: state(name, rep, arm) for arm in ARMS}


def missing_reps(name: str) -> list[int]:
    """Repetitions with a session that started and left no row: never run again."""
    return [rep for rep in range(1, REPS + 1) if "missing" in states(name, rep).values()]


def todo(name: str) -> list[tuple[int, list[str]]]:
    """Per repetition, the sessions never started, outside the missing repetitions."""
    out = []
    for rep in range(1, REPS + 1):
        now = states(name, rep)
        if "missing" not in now.values() and (arms := [a for a in ARMS if now[a] == "absent"]):
            out.append((rep, arms))
    return out


def set_aside_limit(name: str) -> Path | None:
    """A session to run again (any repetition, the missing ones included): every repetition of
    the instance, with the Claude Code folders of its working copies, moves to `<id>-limit<k>`
    (counted in the ledger, read by no verdict) and the instance runs again whole. A missing
    repetition stays where it is (never run again), all but its sessions to run again."""
    missing = missing_reps(name)
    found = [(rep, arm, state(name, rep, arm)) for rep in range(1, REPS + 1) for arm in ARMS]
    if not any(s == "rerun" for _, _, s in found):
        return None
    moving = [(rep, arm) for rep, arm, s in found
              if s == "rerun" or (rep not in missing and s != "absent")]  # fmt: skip
    k = 1
    while (RUNS_D / f"{name}-limit{k}").exists():
        k += 1
    aside = RUNS_D / f"{name}-limit{k}"
    for rep, arm in moving:
        target = aside / f"r{rep}" / arm
        target.parent.mkdir(parents=True, exist_ok=True)
        evidence_of(name, rep, arm).rename(target)
        projects = run.projects_dir(work_of(name, rep, arm))
        if projects.exists():
            shutil.move(str(projects), str(target / "claude-projects"))
    log(f"{name}: {[f'r{r}/{a}' for r, a in moving]} set aside as {aside.name}, run again whole")
    return aside


def last_s_sessions(n: int) -> list[Path]:
    """The last `n` S sessions of the batch that ran to a row, by start (set-asides excluded)."""
    done = [e for e in RUNS_D.glob("*/r*/S") if "-limit" not in e.parent.parent.name
            and (e / "row.json").exists()]  # fmt: skip
    started = {e: read_json(e / "row.json").get("started") or (e / "row.json").stat().st_mtime
               for e in done}  # fmt: skip
    return sorted(done, key=started.__getitem__)[-n:]


def treatment_stop(name: str, rep: int) -> str:
    """Why the batch stops after this pair's S session (prereg, the treatment's criteria): a
    systemic criterion failed, or (f) failed here and in F_STOP of the last F_WINDOW."""
    import confirm_d  # the verdicts' own reading of the criteria (it imports this module)

    failed = [c for c, ok in confirm_d.criteria(evidence_of(name, rep, "S")).items() if not ok]
    if systemic := [c for c in failed if c in SYSTEMIC]:
        return f"{name} r{rep} S fails the treatment's {systemic}"
    if "f" in failed:
        recent = last_s_sessions(F_WINDOW)
        bad = sum(not confirm_d.criteria(e)["f"] for e in recent)
        if bad >= F_STOP:
            return f"(f) Jev's errors in {bad} of the last {len(recent)} S sessions"
    return ""


def run_pair(
    row: dict[str, Any], rep: int, arms: list[str], keyfile: Path, inputs: dict[str, str | None]
) -> None:
    """N and S of one repetition, started together; then the stops a pair can call."""
    name = row["instance_id"]
    if why := pair_refusal(inputs):
        raise Stop(f"{name} r{rep} not started: {why}")
    if "S" in arms and (found := run.decider_probe(run.arm_keyfile(keyfile, key_name(name, rep),
                                                                   "S"))) != DECIDER:  # fmt: skip
        raise Stop(f"{name} r{rep}: the S arm's hooks would build {found}")
    if len(arms) < len(ARMS):
        log(f"{name} r{rep}: {arms} alone, the other session ran before")
    log(f"{name} r{rep}: start {arms} ({ledger():.2f} USD spent)")
    with ThreadPoolExecutor(max_workers=len(arms)) as pool:
        list(pool.map(lambda arm: one(row, arm, rep, keyfile), arms))
    now = {arm: state(name, rep, arm) for arm in arms}
    rows = {arm: evidence_of(name, rep, arm) / "row.json" for arm in arms}
    statuses = {arm: str(read_json(path)["calls"][0].get("status", "")) if path.exists()
                else "no row" for arm, path in rows.items()}  # fmt: skip
    if "rerun" in now.values():
        set_aside_limit(name)
        raise Stop(f"{name} r{rep}: a usage limit or a session that never started {statuses}")
    if ERROR_OTHER in statuses.values():
        raise Stop(f"{name} r{rep}: an error result that is not a usage limit {statuses}")
    if "S" in arms and (why := treatment_stop(name, rep)):
        raise Stop(why)


def run_instance(
    row: dict[str, Any], keyfile: Path, top: float, inputs: dict[str, str | None]
) -> None:
    name = row["instance_id"]
    set_aside_limit(name)  # a session to run again that an earlier run left in place
    if missing := missing_reps(name):
        log(f"{name}: repetitions {missing} have a session with no row: their pairs are missing")
    plan = todo(name)
    if not plan and not ungraded(name):
        return
    if not plan and not needs_harness(name):
        grade_instance(name)  # only empty diffs wait: graded without the image
        return
    held = 0.0
    try:
        if plan:
            if docker_env.disk_free_gb() < MIN_DISK_GB:
                raise Stop(f"under {MIN_DISK_GB} GB free on C:")
            with run._lock:
                run._ledger["spent"] = ledger()
            if not run.reserve(top, HOLD_USD):  # all or nothing: its six sessions' caps
                spent = run._ledger["spent"]
                raise Stop(f"{name}: its sessions' caps ({HOLD_USD:.2f} USD) do not fit under "
                           f"the ceiling ({spent:.2f} of {top:.2f} spent)")  # fmt: skip
            held = HOLD_USD
        docker_env.pull(row["image"])
        try:
            for rep, arms in plan:
                run_pair(row, rep, arms, keyfile, inputs)
        finally:
            grade_instance(name)  # what ran is graded even when the batch stops here
            docker_env.drop(row["image"])
    finally:
        run.release(held)


# ---- the batch -----------------------------------------------------------------------------------


def plan_rows() -> list[dict[str, Any]]:
    """The validated instances in run order (`order`) with their `singles_run.rows()` row (image
    and statement); refuses an image other than the one validated."""
    known = singles_run.rows()
    out = []
    for item in order(instances()):
        name = item["instance_id"]
        if name not in known:
            raise SystemExit(f"{name} has no row in singles_run.rows()")
        if (image := item.get("image")) and image != known[name]["image"]:
            raise SystemExit(f"{name}: validated {image}, rows() gives {known[name]['image']}")
        out.append(known[name])
    return out


def batch() -> None:
    lock = take_lock()
    try:
        rows = plan_rows()
        keyfile = run.keyfile_from_indagis()
        try:
            if why := d_refusal(keyfile):
                raise SystemExit(why)
            top, inputs = ceiling(), unsealed_inputs()
            log(f"D START {len(rows)} instances x {REPS} repetitions; spent {ledger():.2f} USD, "
                f"ceiling {top:.2f}; order {[r['instance_id'] for r in rows]}")  # fmt: skip
            log(f"D INPUTS {json.dumps(inputs)}")
            for row in rows:
                run_instance(row, keyfile, top, inputs)
        finally:
            keyfile.unlink(missing_ok=True)
            run.drop_arm_keys()
    finally:
        lock.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("check", "ledger", "run", "grade", "selftest"))
    parser.add_argument("instance", nargs="?", help="selftest: one validated instance")
    args = parser.parse_args(argv)
    if args.action == "ledger":
        print(json.dumps({**ledger_parts(), "total": ledger()}, indent=1))
        return 0
    if args.action == "selftest":
        import selftest_d

        return selftest_d.main(args.instance)
    if args.action == "check":
        keyfile = run.keyfile_from_indagis()
        try:
            print(d_refusal(keyfile) or "phase D may run")
        finally:
            keyfile.unlink(missing_ok=True)
            run.drop_arm_keys()
        plan = {"order": [r["instance_id"] for r in plan_rows()], "spent": ledger(),
                "ceiling": None if CEILING_BASE_USD is None else ceiling(),
                "inputs": unsealed_inputs()}  # fmt: skip
        print(json.dumps(plan, indent=1))
        return 0
    if args.action == "grade":
        if why := seal_refusal():
            raise SystemExit(why)
        for row in plan_rows():
            if not ungraded(row["instance_id"]):
                continue
            if not needs_harness(row["instance_id"]):
                grade_instance(row["instance_id"])  # only empty diffs wait: no image
                continue
            docker_env.pull(row["image"])
            try:
                grade_instance(row["instance_id"])
            finally:
                docker_env.drop(row["image"])
        return 0
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # a stray Ctrl+C killed phase A mid-grade
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, signal.SIG_IGN)
    try:
        batch()
    except SystemExit as why:  # a refusal: nothing ran
        log(f"D REFUSED: {why}")
        return 2
    except Stop as why:
        log(f"D STOP: {why} (spent {ledger():.2f} USD)")
        return 0
    except Exception as exc:  # noqa: BLE001  (logged with its trace; the watcher greps for it)
        traceback.print_exc()
        log(f"D FAILED: {type(exc).__name__}: {exc} (spent {ledger():.2f} USD)")
        return 1
    log(f"D DONE (spent {ledger():.2f} USD)")
    return 0


if __name__ == "__main__":
    # One module, not two: confirm_d and selftest_d import `run_d`, which must be this one.
    sys.modules["run_d"] = sys.modules[__name__]
    raise SystemExit(main())
