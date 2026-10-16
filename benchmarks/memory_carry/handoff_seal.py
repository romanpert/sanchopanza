"""F2's seal (docs/results/2026-10-16-memory-f2/prereg.md, "Seal") and the sealed checkout, and
the same for W17's memory lots on F2's runner (docs/results/2026-10-16-memory-w17/prereg.md):
`LOTS` names each lot's results folder and its fixed files.

`seal` writes `prereg.manifest.json` (sha256, LF bytes, of the prereg and every sealed file:
the launcher, pyproject.toml, every file of `benchmarks/memory_carry/`'s Python and every file
under `src/sanchopanza/`, not only its `.py`) and `prereg.sha256` (the sha256 of the manifest's
lines). A different seal already there is refused. `require_sealed_checkout` refuses a live run
unless the files match the seal, HEAD is the commit that last wrote `prereg.sha256`, and `git
status --porcelain` is empty.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
RESULTS = REPO / "docs" / "results" / "2026-10-16-memory-f2"
SEALED_FIXED = (
    "f2-night-run.cmd", "pyproject.toml", "benchmarks/meter.py",
    "benchmarks/memory_carry/handoff.py", "benchmarks/memory_carry/handoff_analyze.py",
    "benchmarks/memory_carry/handoff_call.py", "benchmarks/memory_carry/handoff_night.py",
    "benchmarks/memory_carry/handoff_preflight.py", "benchmarks/memory_carry/handoff_seal.py",
    "benchmarks/memory_carry/scenes_handoff.py",
    "tests/test_memory_carry_handoff.py", "tests/test_memory_carry_handoff_run.py",
    "tests/test_memory_carry_handoff_work.py",
)  # fmt: skip
RESULTS_W17 = REPO / "docs" / "results" / "2026-10-16-memory-w17"
SEALED_FIXED_W17 = (
    "memlot-night-run.cmd", "pyproject.toml", "benchmarks/meter.py",
    "benchmarks/memory_carry/handoff.py", "benchmarks/memory_carry/handoff_analyze.py",
    "benchmarks/memory_carry/handoff_call.py", "benchmarks/memory_carry/handoff_cost.py",
    "benchmarks/memory_carry/handoff_cost_ci.py", "benchmarks/memory_carry/handoff_night.py",
    "benchmarks/memory_carry/handoff_pairs.py", "benchmarks/memory_carry/handoff_preflight.py",
    "benchmarks/memory_carry/handoff_seal.py", "benchmarks/memory_carry/scenes_handoff.py",
    "benchmarks/memory_carry/carry.py", "benchmarks/memory_carry/carry_s.py",
    "benchmarks/memory_carry/carry_hook.py", "benchmarks/memory_carry/capped_sub.py",
    "tests/test_memory_carry_handoff.py", "tests/test_memory_carry_handoff_run.py",
    "tests/test_memory_carry_handoff_work.py", "tests/test_memory_carry_w17.py",
)  # fmt: skip
LOTS = {"f2": (RESULTS, SEALED_FIXED), "w17": (RESULTS_W17, SEALED_FIXED_W17)}
PATH_WORDS = {"w17": ("f2", "memory", "handoff", "memlot", "w17", "sonnet", "opus")}
SEALED_GLOBS = ("src/sanchopanza/**/*", "benchmarks/memory_carry/*.py")
NOT_CODE = ("__pycache__",)
SEALED_CHECKOUT_REFUSED = 11


def sealed_paths(repo: Path = REPO, fixed: tuple[str, ...] = SEALED_FIXED) -> tuple[str, ...]:
    found = {p.relative_to(repo).as_posix() for g in SEALED_GLOBS for p in repo.glob(g)
             if p.is_file() and not set(NOT_CODE) & set(p.parts)
             and p.suffix not in (".pyc", ".pyo")}  # fmt: skip
    return (*fixed, *sorted(found - set(fixed)))


def manifest(repo: Path = REPO, results: Path = RESULTS,
             fixed: tuple[str, ...] = SEALED_FIXED) -> dict[str, str]:  # fmt: skip
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()

    doc = (results / "prereg.md").relative_to(repo).as_posix()
    return {p: digest(repo / p) for p in (doc, *sealed_paths(repo, fixed))}


def combined(found: dict[str, str]) -> str:
    return hashlib.sha256("".join(f"{k} {v}\n" for k, v in found.items()).encode()).hexdigest()


def seal(repo: Path = REPO, results: Path = RESULTS,
         fixed: tuple[str, ...] = SEALED_FIXED) -> str:  # fmt: skip
    found = manifest(repo, results, fixed)
    value = combined(found)
    target = results / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value):
        raise SystemExit("prereg.sha256 already holds another seal: nothing written")
    (results / "prereg.manifest.json").write_text(json.dumps(found, indent=1) + "\n",
                                                  encoding="utf-8", newline="\n")  # fmt: skip
    target.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def seal_ok(repo: Path = REPO, results: Path = RESULTS,
            fixed: tuple[str, ...] = SEALED_FIXED) -> bool:  # fmt: skip
    target = results / "prereg.sha256"
    return target.exists() and target.read_text().strip() == combined(
        manifest(repo, results, fixed))  # fmt: skip


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=False)  # fmt: skip
    return done.stdout.strip() if done.returncode == 0 else f"<git failed: {done.stderr.strip()}>"


def checkout_refusal(repo: Path = REPO, results: Path = RESULTS,
                     fixed: tuple[str, ...] = SEALED_FIXED) -> str:  # fmt: skip
    """Why this checkout may not run the lot ("" when it may)."""
    if not seal_ok(repo, results, fixed):
        return "prereg.md or the code differ from the seal (or no seal)"
    sealed = git(repo, "log", "-1", "--format=%H", "--",
                 (results / "prereg.sha256").relative_to(repo).as_posix())  # fmt: skip
    head = git(repo, "rev-parse", "HEAD")
    if not sealed or sealed != head:
        return f"HEAD {head} is not the sealing commit {sealed or '(none)'}"
    dirty = git(repo, "status", "--porcelain")
    if dirty:
        return f"the checkout is not clean: {dirty.splitlines()[0]}"
    return ""


def path_refusal(lot: str, repo: Path = REPO) -> str:
    """W17: the checkout's own path may not name the lot (S's installed hooks show it to the
    agent); the launcher checks the same words."""
    named = [w for w in PATH_WORDS.get(lot, ()) if w in str(repo).lower()]
    return f"the checkout's path {repo} names the lot ({', '.join(named)})" if named else ""


def require_sealed_checkout(lot: str = "f2", repo: Path = REPO) -> None:
    results, fixed = LOTS[lot]
    why = path_refusal(lot, repo) or checkout_refusal(repo, results, fixed)
    if why:
        print(f"refused: {why}; nothing run", flush=True)
        raise SystemExit(SEALED_CHECKOUT_REFUSED)
