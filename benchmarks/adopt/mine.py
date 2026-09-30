"""Mine real bugs from a repository's own history, to put back into a recent snapshot. Free.

    python benchmarks/adopt/mine.py <repo-name>        # writes bugs-<repo-name>.jsonl

A commit is a candidate when it changes both code and tests (Python). At the snapshot commit,
its code change is reversed (the bug comes back) while the tests stay as they are: the tests of
the commit's test files that now fail, and pass at the snapshot, are its FAIL_TO_PASS, as in
SWE-bench. The bug is kept only if its code change and its test change both reverse cleanly at
the snapshot and at least one test fails without the fix. The agent later sees the snapshot with
both reversed (the tests that would show the fix stay hidden), and is graded by putting the
tests back.

Nothing is written to the source repository: every check runs in a throwaway worktree under
~/.cache/sanchopanza/adopt/mine/, removed afterwards.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from repos import REPOS, Repo  # noqa: E402

WORK = Path.home() / ".cache" / "sanchopanza" / "adopt" / "mine"
TEST_FILE = re.compile(r"(^|/)tests?/(.+/)?test_[^/]+\.py$")
RESULT = re.compile(r"^(PASSED|FAILED|ERROR) (\S+)", re.M)


def git(repo: Path, *args: str, check: bool = True, stdin: str | None = None) -> str:
    """Bytes on the pipes: in text mode Windows writes "\\n" to stdin as "\\r\\n", and no LF
    patch applies after that."""
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          input=stdin.encode("utf-8") if stdin is not None else None)  # fmt: skip
    if check and done.returncode != 0:
        err = done.stderr.decode("utf-8", "replace").strip()[:400]
        raise RuntimeError(f"git {' '.join(args)}: {err}")
    return done.stdout.decode("utf-8", "replace")


def candidates(repo: Repo) -> list[dict[str, Any]]:
    """Commits before the snapshot that change .py code and .py tests."""
    out = []
    log = git(repo.path, "log", "--no-merges", "--format=%H%x09%s", repo.snapshot)
    for line in log.splitlines():
        sha, _, subject = line.partition("\t")
        files = git(repo.path, "show", "--name-only", "--format=", sha).split()
        tests = [f for f in files if TEST_FILE.search(f)]
        code = [f for f in files if f.endswith(".py") and f not in tests
                and any(f.startswith(p) for p in repo.code_prefixes)]  # fmt: skip
        if tests and code:
            out.append({"sha": sha, "subject": subject, "tests": tests, "code": code})
    return out


def diff(repo: Path, sha: str, files: list[str]) -> str:
    return git(repo, "diff", "--binary", f"{sha}^", sha, "--", *files)


def worktree(repo: Repo, name: str) -> Path:
    where = WORK / repo.name / name
    if where.exists():
        git(repo.path, "worktree", "remove", "--force", str(where), check=False)
        shutil.rmtree(where, ignore_errors=True)
    where.parent.mkdir(parents=True, exist_ok=True)
    git(repo.path, "worktree", "add", "--detach", str(where), repo.snapshot)
    return where


def applies(where: Path, patch: str, reverse: bool) -> bool:
    args = ["apply", "--check", *(["-R"] if reverse else []), "-"]
    return subprocess.run(["git", "-C", str(where), *args], input=patch.encode("utf-8"),
                          capture_output=True).returncode == 0  # fmt: skip


def apply(where: Path, patch: str, reverse: bool) -> None:
    git(where, "apply", *(["-R"] if reverse else []), "-", stdin=patch)


def run_tests(repo: Repo, where: Path, files: list[str]) -> dict[str, str]:
    """node id -> PASSED/FAILED/ERROR for the given test files, run in `where`."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(str(where / p) for p in repo.pythonpath),
           "PYTHONDONTWRITEBYTECODE": "1"}  # fmt: skip
    for key in [k for k in env if k.startswith(("CLAUDE", "SANCHOPANZA_", "SANCHO_"))]:
        env.pop(key)
    present = [f for f in files if (where / f).exists()]
    if not present:
        return {}
    done = subprocess.run([str(repo.python), "-m", "pytest", "-q", "-rA", "-p", "no:cacheprovider",
                           "-x" if False else "--tb=no", *present], cwd=where, env=env,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=900)  # fmt: skip
    return {node: status for status, node in RESULT.findall(done.stdout)}


def local_clone(repo: Repo) -> Repo:
    """A clone under the cache: worktrees are registered there, never in the source repo."""
    clone = WORK / repo.name / "clone"
    if not (clone / ".git").exists():
        clone.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--quiet", "--no-checkout", "-c", "core.autocrlf=false",
                        str(repo.path), str(clone)], check=True)  # fmt: skip
    # The machine's autocrlf=true checks files out with CRLF, and no LF patch applies to them.
    git(clone, "config", "core.autocrlf", "false")
    return Repo(**{**repo.__dict__, "path": clone})


def mine(repo: Repo) -> list[dict[str, Any]]:
    repo = local_clone(repo)
    where = worktree(repo, "check")
    kept = []
    try:
        base_results: dict[str, dict[str, str]] = {}
        for cand in candidates(repo):
            code_patch = diff(repo.path, cand["sha"], cand["code"])
            test_patch = diff(repo.path, cand["sha"], cand["tests"])
            if not code_patch.strip() or not test_patch.strip():
                continue
            if not (applies(where, code_patch, True) and applies(where, test_patch, True)):
                continue
            key = "|".join(sorted(cand["tests"]))
            if key not in base_results:
                base_results[key] = run_tests(repo, where, cand["tests"])
            before = base_results[key]
            apply(where, code_patch, True)
            try:
                after = run_tests(repo, where, cand["tests"])
            finally:
                git(where, "checkout", "--", ".")
                git(where, "clean", "-fdq")
            f2p = sorted(n for n, s in after.items() if s != "PASSED" and before.get(n) == "PASSED")
            p2p = sorted(n for n, s in after.items() if s == "PASSED" and before.get(n) == "PASSED")
            if not f2p:
                continue
            kept.append({**cand, "repo": repo.name, "snapshot": repo.snapshot,
                         "code_patch": code_patch, "test_patch": test_patch,
                         "FAIL_TO_PASS": f2p, "PASS_TO_PASS": p2p})  # fmt: skip
            print(f"kept {cand['sha'][:8]} {len(f2p):3} f2p  {cand['subject'][:80]}", flush=True)
    finally:
        git(repo.path, "worktree", "remove", "--force", str(where), check=False)
    return kept


def main() -> int:
    name = sys.argv[1]
    repo = REPOS[name]
    bugs = mine(repo)
    out = HERE / f"bugs-{name}.jsonl"
    out.write_text("".join(json.dumps(b, ensure_ascii=False) + "\n" for b in bugs),
                   encoding="utf-8", newline="\n")  # fmt: skip
    print(f"{len(bugs)} bugs kept -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
