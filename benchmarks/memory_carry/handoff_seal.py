"""F2's seal (docs/results/2026-10-16-memory-f2/prereg.md, "Seal") and the sealed checkout.

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
SEALED_GLOBS = ("src/sanchopanza/**/*", "benchmarks/memory_carry/*.py")
NOT_CODE = ("__pycache__",)
SEALED_CHECKOUT_REFUSED = 11


def sealed_paths(repo: Path = REPO) -> tuple[str, ...]:
    found = {p.relative_to(repo).as_posix() for g in SEALED_GLOBS for p in repo.glob(g)
             if p.is_file() and not set(NOT_CODE) & set(p.parts)
             and p.suffix not in (".pyc", ".pyo")}  # fmt: skip
    return (*SEALED_FIXED, *sorted(found - set(SEALED_FIXED)))


def manifest(repo: Path = REPO, results: Path = RESULTS) -> dict[str, str]:
    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()

    doc = (results / "prereg.md").relative_to(repo).as_posix()
    return {p: digest(repo / p) for p in (doc, *sealed_paths(repo))}


def combined(found: dict[str, str]) -> str:
    return hashlib.sha256("".join(f"{k} {v}\n" for k, v in found.items()).encode()).hexdigest()


def seal(repo: Path = REPO, results: Path = RESULTS) -> str:
    found = manifest(repo, results)
    value = combined(found)
    target = results / "prereg.sha256"
    if target.exists() and target.read_text().strip() not in ("", value):
        raise SystemExit("prereg.sha256 already holds another seal: nothing written")
    (results / "prereg.manifest.json").write_text(json.dumps(found, indent=1) + "\n",
                                                  encoding="utf-8", newline="\n")  # fmt: skip
    target.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def seal_ok(repo: Path = REPO, results: Path = RESULTS) -> bool:
    target = results / "prereg.sha256"
    return target.exists() and target.read_text().strip() == combined(manifest(repo, results))


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=False)  # fmt: skip
    return done.stdout.strip() if done.returncode == 0 else f"<git failed: {done.stderr.strip()}>"


def checkout_refusal(repo: Path = REPO, results: Path = RESULTS) -> str:
    """Why this checkout may not run the lot ("" when it may)."""
    if not seal_ok(repo, results):
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


def require_sealed_checkout(repo: Path = REPO, results: Path = RESULTS) -> None:
    why = checkout_refusal(repo, results)
    if why:
        print(f"refused: {why}; nothing run", flush=True)
        raise SystemExit(SEALED_CHECKOUT_REFUSED)
