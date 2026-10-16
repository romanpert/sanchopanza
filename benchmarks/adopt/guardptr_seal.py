"""The guard-pointers lot's seal (docs/results/2026-10-16-guard-pointers/prereg.md, section 15), as
the sibling lots do it (benchmarks/a3_mcp/w17_replay.py, benchmarks/jev114/lot.py). Free: git and
hashes only.

    python benchmarks/adopt/guardptr_seal.py seal    # writes prereg.manifest.json and prereg.sha256
    python benchmarks/adopt/guardptr_seal.py check   # the seal's state now, as JSON

The seal is the sha256 over the prereg, every instrument file (`sealed`: what the lot runs and
every repository module it imports, its data, the package, pyproject.toml) and the launcher with
its local values read as placeholders (`LOCAL_VALUES`). The instrument is
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
import ast
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
# What long_launch.py hands the runner so that it checks the seal again itself: the instrument
# commit and, in a dry run only, the sealed scratch repository it was checked against.
INSTRUMENT_VAR, REPO_VAR = "ADOPT_SEAL_INSTRUMENT", "ADOPT_SEAL_REPO"
# The launcher's local values (the python, the keys file with the subscription's token, the
# detached worktree): the tracked file holds placeholders, the filled copy lives in the run folder,
# and both hash the same (benchmarks/jev114/lot.py, benchmarks/a3_mcp/w17_replay.py).
LOCAL_VALUES = re.compile(r'^(set "(?:PY|SANCHOPANZA_KEYS_ENV|WT)=)[^"\n]*(")', re.MULTILINE)
CHAINS = ("conan-io__conan-long60-1", "pydantic__pydantic-long60-1", "conan-io__conan-long60-2",
          "getmoto__moto-long60-1", "getmoto__moto-long60-2")  # fmt: skip
# What the lot runs (scripts and entry modules) and what it reads besides code. Every repository
# module these import, at the top or inside a function, by name or by a string handed to
# `_optional`/`import_module`, is sealed with them (`imports_closure`); the package (src/, every
# file) and pyproject.toml too.
ENTRIES = (
    *(f"benchmarks/adopt/{name}.py" for name in (
        "long_launch", "long_run", "long_pointers_read", "guardptr_seal", "guardptr_power",
        "hook_env", "runtests", "freeze")),
    "tests/test_adopt_long_pointers.py",
    "tests/test_adopt_long_pointers_launch.py",
    "tests/test_adopt_guardptr_seal.py",
    "tests/fixtures/long_fake/fake_claude.py",
    "tests/fixtures/long_fake/dry_runner.py",
)  # fmt: skip
DATA = (
    *(f"benchmarks/adopt/long60/{chain}.json" for chain in CHAINS),
    f"{LOT}/power.json",
    "tests/fixtures/long_fake/b2-n-calls.json",
    "pyproject.toml",
)
# Where a plain `import name` of these scripts resolves (their sys.path, in order).
SEARCH = ("benchmarks/adopt", "benchmarks/memory_carry", "benchmarks")
DYNAMIC = ("_optional", "import_module")


def _imported(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            names.add(node.module)
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            func = node.func
            called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if called in DYNAMIC and isinstance(node.args[0].value, str):
                names.add(node.args[0].value)
    return names


def _resolve(name: str, repo: Path) -> str | None:
    """The repository file a module name resolves to (src/ is sealed whole: not listed here)."""
    parts = name.split(".")
    if parts[0] == "sanchopanza":
        return None
    for base in (*SEARCH, ""):
        for candidate in (Path(base, *parts).with_suffix(".py"), Path(base, *parts, "__init__.py")):
            if (repo / candidate).is_file():
                return candidate.as_posix()
    return None


def imports_closure(repo: Path = REPO, entries: tuple[str, ...] = ENTRIES) -> list[str]:
    """`entries` and every repository module they import, transitively."""
    seen: set[str] = set()
    todo = [e for e in entries if (repo / e).is_file()]
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        seen.add(rel)
        tree = ast.parse((repo / rel).read_text(encoding="utf-8"))
        todo += [f for n in _imported(tree) if (f := _resolve(n, repo)) and f not in seen]
    return sorted(seen)


def sealed(repo: Path = REPO) -> list[str]:
    """Every sealed file but the prereg and the launcher: the import closure, the data, src/."""
    package = sorted(p.relative_to(repo).as_posix() for p in (repo / "src").rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts)  # fmt: skip
    return sorted({*imports_closure(repo), *DATA, *package})


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def launcher_text(path: Path) -> bytes:
    """A launcher with LF ends and its local values as placeholders."""
    text = path.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")
    return LOCAL_VALUES.sub(r"\1<LOCAL>\2", text).encode("utf-8")


def manifest(repo: Path = REPO) -> dict[str, str]:
    """Path -> sha256 of every sealed file (LF ends), the launcher masked. A missing one refuses."""
    files = sealed(repo)
    missing = [p for p in (PREREG, LAUNCHER, *ENTRIES, *DATA) if not (repo / p).is_file()]
    if missing:
        raise SystemExit(f"the seal names files that are not there: {missing}")
    found = {PREREG: _digest(repo / PREREG)}
    found |= {p: _digest(repo / p) for p in files}
    return found | {LAUNCHER: hashlib.sha256(launcher_text(repo / LAUNCHER)).hexdigest()}


def frozen_refusal(exe: Path, found: Mapping[str, str]) -> str:
    """Why the frozen copy is not the sealed package ("" when it is): every sealed
    `src/sanchopanza/**/*.py` installed in its site-packages, byte for byte (LF ends); the other
    package files compared where the install carries them."""
    site = exe.parents[1] / "Lib" / "site-packages"
    prefix = "src/"
    wrong = []
    for rel, digest in found.items():
        if not rel.startswith(prefix + "sanchopanza/"):
            continue
        installed = site / rel[len(prefix):]
        if not installed.is_file():
            if rel.endswith(".py"):
                wrong.append(f"{rel} missing")
            continue
        if _digest(installed) != digest:
            wrong.append(f"{rel} differs")
    return f"the frozen copy is not the sealed package: {wrong[:5]}" if wrong else ""


def frozen_versions(exe: Path, names: tuple[str, ...] = ("mcp", "httpx", "sanchopanza")) -> str:
    """`pip freeze` of the frozen copy, the lines of `names` (for launch.log)."""
    done = subprocess.run([str(exe.parent / "python.exe"), "-m", "pip", "freeze"],
                          capture_output=True, text=True, timeout=120)  # fmt: skip
    keep = [line for line in done.stdout.splitlines()
            if line.split("=", 1)[0].split(" ", 1)[0].lower() in names]  # fmt: skip
    return "; ".join(keep) or f"pip freeze gave nothing ({done.returncode})"


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
