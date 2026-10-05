"""Phase D's grading path, end to end, on one validated instance. Free: Docker only, no session.

    python benchmarks/adopt_d/run_d.py selftest <instance>

What a session's outcome goes through, with the gold patch standing in for the agent:

1. **The grade.** The image's working copy exported as the runner does (`docker_env.export`), the
   gold patch applied to it, the diff taken as from a session (`docker_env.agent_diff`) and graded
   by `run_d.grade_arm`, exactly as a session's: it must resolve.
2. **The agents' test command.** A second export with the dataset's test patch applied, then the
   instance's FAIL_TO_PASS tests run through the `runtests` shim (`runtests.cmd`, as PowerShell
   finds it on the agents' PATH) in the environment `run.child_env` gives the sessions: they must
   fail without the gold patch and pass with it.

Everything is written under `adopt/d-selftest/<instance>/` (`selftest.json`), the harness's run
folder moved there too, so that phase D's disjointness check (`draw.py check`, which skips that
folder) finds no drawn id elsewhere. The image is dropped afterwards if this pulled it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import run_d
from run_d import docker_env, log, run, singles_run

OUT = run.ROOT / "d-selftest"
MIN_DISK_GB = 25.0
DJANGO_TEST = re.compile(r"^(\w+) \(([\w.]+)\)$")  # "test_x (module.Class)"


def dataset_row(name: str) -> dict[str, Any]:
    import pyarrow.parquet as pq

    columns = ["instance_id", "patch", "test_patch", "FAIL_TO_PASS"]
    table = pq.read_table(Path.home() / ".cache" / "sanchopanza" / "find" / "swebench" /
                          "verified.parquet", columns=columns)  # fmt: skip
    found = [r for r in table.to_pylist() if r["instance_id"] == name]
    if not found:
        raise SystemExit(f"{name} is not in verified.parquet")
    return {**found[0], "FAIL_TO_PASS": json.loads(found[0]["FAIL_TO_PASS"])}


def test_args(repo: str, tests: list[str], test_patch: str) -> list[str]:
    """The FAIL_TO_PASS tests as `runtests` arguments: Django's runner takes
    `module.Class.test`; pytest takes node ids, or `-k` over the files the test patch touches."""
    if repo == "django/django":
        return [f"{m.group(2)}.{m.group(1)}" for t in tests if (m := DJANGO_TEST.match(t))]
    if all("::" in t for t in tests):
        return list(tests)
    files = sorted(set(re.findall(r"^\+\+\+ b/(\S+)", test_patch, re.M)))
    return [*files, "-k", " or ".join(t.split("::")[-1] for t in tests)]


def git_apply(work: Path, patch: str) -> None:
    done = subprocess.run(["git", "-C", str(work), "apply", "--whitespace=nowarn", "-"],
                          input=patch.encode("utf-8"), capture_output=True)  # fmt: skip
    if done.returncode != 0:
        raise RuntimeError(f"git apply: {done.stderr.decode('utf-8', 'replace')[-400:]}")


def runtests(work: Path, base: str, row: dict[str, Any], args: list[str], log_to: Path) -> int:
    """`runtests <args>` through the shim, in the sessions' environment, from the working copy."""
    command = singles_run.test_command(row["repo"])
    env = {**run.child_env(row["image"], base), "ADOPT_PREFIX": singles_run.CONDA,
           "ADOPT_TEST_CMD": command}  # fmt: skip
    shim = shutil.which("runtests", path=env["PATH"])
    if not shim:
        raise RuntimeError("the runtests shim is not on the sessions' PATH")
    with log_to.open("wb") as out:
        return subprocess.run(["cmd", "/c", shim, *args], cwd=work, env=env, stdout=out,
                              stderr=subprocess.STDOUT, timeout=1800).returncode  # fmt: skip


def grade_gold(name: str, row: dict[str, Any], gold: str, folder: Path) -> bool | None:
    work, evidence = folder / "work-grade", folder / "grade"
    docker_env.remove_tree(work)
    docker_env.remove_tree(evidence)
    evidence.mkdir(parents=True)
    base = docker_env.export(row["image"], work)
    git_apply(work, gold)
    (evidence / "final.patch").write_text(docker_env.agent_diff(work, base), encoding="utf-8",
                                          newline="\n")  # fmt: skip
    resolved = run_d.grade_arm(name, evidence, "selftest")
    (folder / "harness").mkdir(exist_ok=True)
    swe = singles_run.SWE  # its run folders and run reports, out of draw.py's scan
    for logs in [*(swe / "logs" / "run_evaluation").glob("adopt-d-selftest-*"),
                 *swe.glob("adopt-d-selftest.*.json")]:  # fmt: skip
        shutil.move(str(logs), str(folder / "harness" / logs.name))
    docker_env.remove_tree(work)
    return resolved


def f2p(row: dict[str, Any], data: dict[str, Any], folder: Path) -> dict[str, Any]:
    work = folder / "work-tests"
    docker_env.remove_tree(work)
    base = docker_env.export(row["image"], work)
    git_apply(work, data["test_patch"])
    args = test_args(row["repo"], data["FAIL_TO_PASS"], data["test_patch"])
    if not args:
        raise RuntimeError(f"no FAIL_TO_PASS test could be named: {data['FAIL_TO_PASS']}")
    without = runtests(work, base, row, args, folder / "runtests-without-gold.txt")
    git_apply(work, data["patch"])
    with_gold = runtests(work, base, row, args, folder / "runtests-with-gold.txt")
    docker_env.remove_tree(work)
    return {"args": args, "exit_without_gold": without, "exit_with_gold": with_gold}


def validated(name: str) -> bool:
    data = json.loads(run_d.VALIDATED.read_text(encoding="utf-8")) if run_d.VALIDATED.exists() \
        else {}  # fmt: skip
    return any(r.get("instance_id") == name and r.get("pass") for r in data.get("results", []))


def selftest(name: str) -> dict[str, Any]:
    if not validated(name):
        raise SystemExit(f"{name} has not passed validate_d.py")
    if (free := docker_env.disk_free_gb()) < MIN_DISK_GB:
        raise SystemExit(f"{free:.1f} GB free on C:, under {MIN_DISK_GB}")
    row, data = singles_run.rows()[name], dataset_row(name)
    folder = OUT / name
    folder.mkdir(parents=True, exist_ok=True)
    pulled = docker_env.docker("image", "inspect", row["image"]).returncode != 0
    began = time.time()
    try:
        docker_env.pull(row["image"])
        resolved = grade_gold(name, row, data["patch"], folder)
        tests = f2p(row, data, folder)
    finally:
        if pulled:
            docker_env.drop(row["image"])
    out = {"instance": name, "gold_resolved_by_grade_arm": resolved, **tests,
           "ok": resolved is True and tests["exit_without_gold"] != 0
           and tests["exit_with_gold"] == 0,
           "seconds": round(time.time() - began), "image_pulled_here": pulled}  # fmt: skip
    (folder / "selftest.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    return out


def main(name: str | None) -> int:
    if not name:
        raise SystemExit("selftest needs an instance")
    out = selftest(name)
    log(f"SELFTEST {'OK' if out['ok'] else 'FAILED'}: {json.dumps(out)}")
    return 0 if out["ok"] else 1
