"""The guard-pointers lot's seal (docs/results/2026-10-16-guard-pointers/prereg.md, section 15), as
the sibling lots do it (benchmarks/a3_mcp/w17_replay.py, benchmarks/jev114/lot.py). Free: git and
hashes only.

    python benchmarks/adopt/guardptr_seal.py seal    # writes prereg.manifest.json and prereg.sha256
    python benchmarks/adopt/guardptr_seal.py check   # the seal's state now, as JSON

The seal is the sha256 over the prereg, every instrument file (`SEALED`, the package's sources)
and the launcher with its local values read as placeholders (`LOCAL_VALUES`). The instrument is
committed first (its commit is `<SEAL>`, the frozen copy's commit); the sealing commit, its only
child, adds the manifest and the sha256 and nothing else, and names `<SEAL>` in its message.
Before anything is spent `long_launch.py` asks `require_seal`:
- HEAD is the sealing commit (the last commit that touched prereg.sha256), with one parent,
  changing only the seal files, and the tree is clean;
- the prereg, the instrument and the launcher hash to the sealed value;
- the copy of the launcher that ran (`ADOPT_LAUNCHER`, which it sets; not a SANCHOPANZA_ name, so
  no scrub drops it) equals the tracked one but for its local values;
- the frozen copy's commit given to the launcher is HEAD's parent.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
LOT = "docs/results/2026-10-16-guard-pointers"
PREREG, SHA, MANIFEST = f"{LOT}/prereg.md", f"{LOT}/prereg.sha256", f"{LOT}/prereg.manifest.json"
LAUNCHER = "guard-pointers-run.cmd"
LAUNCHER_VAR = "ADOPT_LAUNCHER"
# The launcher's local values: the tracked file holds placeholders, the filled copy lives in the
# run folder, and both hash the same.
LOCAL_VALUES = re.compile(r'^(set "(?:PY|WT)=)[^"\n]*(")', re.MULTILINE)
CHAINS = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1", "conan-io__conan-long60-2",
          "getmoto__moto-long60-1", "getmoto__moto-long60-2")  # fmt: skip
SEALED = (
    *(f"benchmarks/adopt/{name}.py" for name in (
        "guardptr_seal", "guardptr_power", "long_pointers", "long_pointers_read", "long_run",
        "long_launch", "long_guard", "long_start", "long_money", "long_call", "long_resume",
        "long_window", "long_compact", "long_report", "long_compare", "long_pilot", "long",
        "hook_env", "run", "arm_files", "docker_env", "perbug", "freeze", "costmodel",
        "runtests")),
    "benchmarks/memory_carry/carry.py",
    "benchmarks/meter.py",
    *(f"benchmarks/adopt/long60/{chain}.json" for chain in CHAINS),
    f"{LOT}/power.json",
    "tests/test_adopt_long_pointers.py",
    "tests/test_adopt_long_pointers_launch.py",
    "tests/test_adopt_guardptr_seal.py",
    "tests/fixtures/long_fake/fake_claude.py",
)  # fmt: skip


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def launcher_text(path: Path) -> bytes:
    """A launcher with LF ends and its local values as placeholders."""
    text = path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    return LOCAL_VALUES.sub(r"\1<LOCAL>\2", text).encode("utf-8")


def manifest(repo: Path = REPO) -> dict[str, str]:
    """Path -> sha256 of every sealed file (LF ends), the launcher masked. A missing one refuses."""
    package = sorted(p.relative_to(repo).as_posix() for p in (repo / "src").rglob("*")
                     if p.suffix in (".py", ".md") and "__pycache__" not in p.parts)  # fmt: skip
    missing = [p for p in (PREREG, LAUNCHER, *SEALED) if not (repo / p).is_file()]
    if missing:
        raise SystemExit(f"the seal names files that are not there: {missing}")
    found = {PREREG: _digest(repo / PREREG)}
    found |= {p: _digest(repo / p) for p in (*SEALED, *package)}
    return found | {LAUNCHER: hashlib.sha256(launcher_text(repo / LAUNCHER)).hexdigest()}


def combined(found: Mapping[str, str]) -> str:
    return hashlib.sha256("".join(f"{k} {v}\n" for k, v in found.items()).encode()).hexdigest()


def seal(repo: Path = REPO) -> str:
    found = manifest(repo)
    value = combined(found)
    sha = repo / SHA
    if sha.exists() and sha.read_text(encoding="utf-8").strip() not in ("", value):
        raise SystemExit("prereg.sha256 already holds another seal: nothing written")
    (repo / MANIFEST).write_text(json.dumps(found, indent=1) + "\n", encoding="utf-8",
                                 newline="\n")  # fmt: skip
    sha.write_text(value + "\n", encoding="utf-8", newline="\n")
    return value


def seal_state(repo: Path = REPO) -> dict[str, Any]:
    sha = repo / SHA
    sealed = sha.read_text(encoding="utf-8").strip() if sha.exists() else ""
    if not sealed:
        return {"sealed": None, "combined_now": None, "matches_seal": False}
    now = combined(manifest(repo))
    return {"sealed": sealed, "combined_now": now, "matches_seal": now == sealed}


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    if done.returncode:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()[:200]}")
    return done.stdout.strip()


def require_seal_commit(repo: Path = REPO) -> str:
    """HEAD is the sealing commit (the last that touched prereg.sha256), with one parent, changing
    only the seal files, and the tree is clean. Returns HEAD."""
    head, sealed = _git(repo, "rev-parse", "HEAD"), _git(repo, "log", "-1", "--format=%H", "--",
                                                          SHA)  # fmt: skip
    if not sealed or head != sealed:
        raise SystemExit(f"HEAD {head[:9]} is not the sealing commit {sealed[:9] or '(none)'}: "
                         "nothing spent")  # fmt: skip
    if len(_git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()) != 2:
        raise SystemExit("the sealing commit has not exactly one parent: nothing spent")
    changed = set(_git(repo, "diff", "--name-only", "HEAD^", "HEAD").split())
    if not changed <= {SHA, MANIFEST}:
        raise SystemExit(f"the sealing commit changes {sorted(changed)}: nothing spent")
    if _git(repo, "status", "--porcelain"):
        raise SystemExit("the worktree is not clean: nothing spent")
    return head


def require_launcher(ran: str, repo: Path = REPO) -> None:
    """The copy that ran equals the tracked launcher but for its local values."""
    if not ran or not Path(ran).is_file():
        raise SystemExit(f"not started by the lot's launcher ({LAUNCHER_VAR} unset): nothing spent")
    if launcher_text(Path(ran)) != launcher_text(repo / LAUNCHER):
        raise SystemExit(f"{ran} differs from the sealed {LAUNCHER}: nothing spent")


def require_seal(ran: str, instrument: str, repo: Path = REPO) -> str:
    """Everything above, in order; returns HEAD (the sealing commit)."""
    head = require_seal_commit(repo)
    if not seal_state(repo)["matches_seal"]:
        raise SystemExit("the prereg, the instrument or the launcher differ from the seal: "
                         "nothing spent")  # fmt: skip
    require_launcher(ran, repo)
    parent = _git(repo, "rev-parse", "HEAD^")
    given = _git(repo, "rev-parse", "--verify", f"{instrument}^{{commit}}") if instrument else ""
    if given != parent:
        raise SystemExit(f"the frozen copy's commit {instrument!r} is not the instrument "
                         f"{parent[:9]} (HEAD's parent): nothing spent")  # fmt: skip
    return head


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("seal", "check"))
    parser.add_argument("--repo", default=str(REPO))
    args = parser.parse_args(argv)
    repo = Path(args.repo)
    if args.action == "seal":
        print(seal(repo))
        return 0
    print(json.dumps(seal_state(repo), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
