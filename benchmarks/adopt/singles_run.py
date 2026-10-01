"""SWE-bench Verified single issues: one `claude -p` call per arm, graded by the official harness.

    python benchmarks/adopt/singles_run.py run   --ids a,b --ceiling 3.0 [--model haiku]
    python benchmarks/adopt/singles_run.py grade --ids a,b

Same arms, caps, tools and working-copy rules as the chains (`run.py`). The instance image is
pulled for the pair of sessions and removed once both are graded (the disk is nearly full).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import docker_env  # noqa: E402
import run  # noqa: E402

SWE = Path.home() / ".cache" / "sanchopanza" / "swe-eval"
SWE_PYTHON = SWE.parent / "swe-venv" / "Scripts" / "python.exe"
RUNS = run.ROOT / "singles"
CONDA = "source /opt/miniconda3/bin/activate && conda activate testbed && "
DJANGO = "./tests/runtests.py --settings=test_sqlite --parallel 1"
PYTEST = "python -m pytest -p no:cacheprovider"
PROMPT = (
    "{issue}\n\n"
    "Please fix this in the repository. The project's test environment is in Docker: run tests "
    "from the repository root with `runtests <arguments>`, which runs `{command}` with your "
    "arguments on your current changes. Do not commit."
)


def rows() -> dict[str, dict[str, Any]]:
    """The Verified rows (with their image names), cached as JSON beside the harness."""
    cache = SWE / "verified-rows.json"
    if not cache.exists():
        code = ("import json; from datasets import load_dataset; "
                "d = load_dataset('SWE-bench/SWE-bench_Verified', split='test'); "
                f"open(r'{cache}', 'w', encoding='utf-8').write(json.dumps("
                "{r['instance_id']: {k: r[k] for k in ('instance_id', 'repo', 'image', "
                "'problem_statement', 'base_commit')} for r in d}))")  # fmt: skip
        subprocess.run([str(SWE_PYTHON), "-c", code], check=True, capture_output=True)
    return json.loads(cache.read_text(encoding="utf-8"))


def test_command(repo: str) -> str:
    return DJANGO if repo == "django/django" else PYTEST


def one(
    row: dict[str, Any], arm: str, model: str, ceiling: float, keyfile: Path, held: bool = False
) -> None:
    name = row["instance_id"]
    evidence = RUNS / name / arm
    if (evidence / "row.json").exists():
        return
    if held and evidence.exists():
        # Started before and left no row (a crash): never run again, as with the chains.
        raise RuntimeError(f"{name} {arm}: evidence of an earlier attempt and no row.json")
    work = run.WORK / f"{name}-{arm}"
    if held and any(run.projects_dir(work).glob("*.jsonl")):  # amendment 2
        raise RuntimeError(f"{name} {arm}: earlier sessions in {run.projects_dir(work)}")
    docker_env.remove_tree(evidence)
    evidence.mkdir(parents=True)
    docker_env.remove_tree(work)
    base = docker_env.export(row["image"], work)
    mcp = run.install_sancho(work, evidence, keyfile) if arm == "S" else None
    env = {**run.child_env(row["image"], base), "ADOPT_PREFIX": CONDA,
           "ADOPT_TEST_CMD": test_command(row["repo"])}  # fmt: skip
    prompt = PROMPT.format(issue=row["problem_statement"].strip(),
                           command=test_command(row["repo"]))  # fmt: skip
    call: dict[str, Any]
    if not run.reserve(ceiling):
        call = {"status": "NOT RUN (ceiling)", "cost_usd": 0.0}
    else:
        stream = evidence / "stream-1.jsonl"
        began = time.time()
        with stream.open("wb") as out:
            try:
                code = subprocess.run(run.command(model, prompt, None, mcp), cwd=work, env=env,
                                      input=run.stdin_for(prompt),
                                      stdout=out, stderr=subprocess.PIPE,
                                      timeout=run.CALL_TIMEOUT_S).returncode  # fmt: skip
            except subprocess.TimeoutExpired:
                code = -9
            except OSError:  # could not even start `claude`: the harness, not the arm
                code = -1
        seen = run.facts(stream)
        # A call cut by the timeout is charged its cap in the row as in the ledger (a fresh
        # session: no cumulative cost to take a difference from).
        seen = {**seen, "cost_usd": seen["cost_usd"] or (run.CALL_CAP_USD if code == -9 else 0.0)}
        run.settle(seen["cost_usd"])
        call = {"request": 1, "exit": code, "wall_s": round(time.time() - began, 1), **seen}
        if code == -1:
            call = {**call, "status": "NOT RUN (harness)"}
        if seen.get("api_error"):
            call = {**call, "status": "NOT RUN (error result)"}  # an API error, not a result
        print(f"{name} {arm}: {seen['subtype']} {seen['cost_usd']:.3f} USD", flush=True)
    patch = docker_env.agent_diff(work, base)
    (evidence / "final.patch").write_text(patch, encoding="utf-8", newline="\n")
    session = call.get("session")
    transcript = next(Path.home().joinpath(".claude", "projects").glob(f"*/{session}.jsonl"), None)
    if session and transcript:
        shutil.copy(transcript, evidence / "transcript.jsonl")
    (evidence / "row.json").write_text(json.dumps({"instance": name, "arm": arm, "model": model,
                                                   "base": base, "jev_usd": run.jev_usd(evidence),
                                                   "sanchopanza": run.provenance(),
                                                   "claude_version": run.claude_version(),
                                                   "calls": [call]}, indent=1),
                                       encoding="utf-8")  # fmt: skip


def grade(name: str) -> dict[str, bool]:
    """Both arms through the official harness; the instance image is removed afterwards."""
    out: dict[str, bool] = {}
    for arm in run.ARMS:
        evidence = RUNS / name / arm
        patch_path = evidence / "final.patch"
        if not patch_path.exists():
            continue
        model = f"adopt-{arm}"
        preds = evidence / "preds.jsonl"
        preds.write_text(json.dumps({"instance_id": name, "model_name_or_path": model,
                                     "model_patch": patch_path.read_text("utf-8")}) + "\n",
                         encoding="utf-8", newline="\n")  # fmt: skip
        run_id = f"adopt-{arm}-{int(time.time())}"
        subprocess.run([str(SWE_PYTHON), str(SWE / "run_swe.py"), "-d",
                        "SWE-bench/SWE-bench_Verified", "-p", str(preds), "-i", name,
                        "--max_workers", "1", "-id", run_id], cwd=SWE, capture_output=True,
                       env={**os.environ, "PYTHONUTF8": "1"}, timeout=3600)  # fmt: skip
        report = SWE / "logs" / "run_evaluation" / run_id / model / name / "report.json"
        if not report.exists():
            # The harness failed (Docker, disk): missing, not a loss. No grade.json is written.
            print(f"{name} {arm}: no report from the harness, not graded", flush=True)
            continue
        resolved = bool(json.loads(report.read_text("utf-8")).get(name, {}).get("resolved"))
        (evidence / "grade.json").write_text(json.dumps({"resolved": resolved,
                                                         "report": str(report)}),
                                             encoding="utf-8")  # fmt: skip
        out[arm] = resolved
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("run", "grade"))
    parser.add_argument("--ids", required=True)
    parser.add_argument("--model", default="haiku", choices=sorted(run.MODELS))
    parser.add_argument("--ceiling", type=float, default=0.0)
    args = parser.parse_args(argv)
    known = rows()
    ids = [i for i in args.ids.split(",") if i]
    if args.action == "grade":
        for name in ids:
            print(name, grade(name), flush=True)
            docker_env.drop(known[name]["image"])
        return 0
    if args.ceiling <= 0:
        raise SystemExit("--ceiling is required and must be positive")
    held = {r["instance_id"] for r in json.loads((HERE / "singles-selected.json").read_text(
        encoding="utf-8")) if r["split"] == "held"}  # fmt: skip
    if held & set(ids) and (why := run.held_refusal(args.model, run.CALL_CAP_USD,
                                                     run.HELD_CHAIN_CAP)):  # fmt: skip
        raise SystemExit(why)
    with run._lock:
        run._ledger["spent"] = run.spent_so_far() + spent_singles()
    keyfile = run.keyfile_from_indagis()
    try:
        for name in ids:
            row = known[name]
            # All or nothing, as the chains: both arms' caps held before either starts.
            hold = run.CALL_CAP_USD * len(run.ARMS)
            if not run.reserve(args.ceiling, hold):
                print(f"{name}: not run, both arms' caps ({hold:.2f} USD) do not fit")
                continue
            docker_env.pull(row["image"])
            try:
                with ThreadPoolExecutor(max_workers=len(run.ARMS)) as pool:
                    list(pool.map(lambda arm, r=row, h=name in held: one(
                        r, arm, run.MODELS[args.model], float("inf"), keyfile, h), run.ARMS))
            finally:
                run.release(hold)
            print(name, grade(name), flush=True)
            docker_env.drop(row["image"])
    finally:
        keyfile.unlink(missing_ok=True)
    return 0


def spent_singles() -> float:
    total = 0.0
    for path in RUNS.glob("*/*/row.json"):
        total += sum(c.get("cost_usd", 0.0) for c in json.loads(path.read_text("utf-8"))["calls"])
    return total


if __name__ == "__main__":
    raise SystemExit(main())
