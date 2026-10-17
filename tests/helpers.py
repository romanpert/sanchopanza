"""Shared helpers for the tests. No test here calls a paid provider."""

from __future__ import annotations

import hashlib
import os
import subprocess
from collections.abc import Callable
from pathlib import Path, PureWindowsPath
from typing import Any

from sanchopanza import Answer, Decision, Thresholds, _env, truth
from sanchopanza.journal import MemoryJournal
from sanchopanza.squire import Squire


def decision(point: str, **answers: Answer) -> Decision:
    return Decision(point=point, answers=answers, provider="test", model="t")


def score(value: float, confidence: float) -> Answer:
    return Answer(kind="score", score=value, confidence=confidence)


def choice(value: str, confidence: float, **probabilities: float) -> Answer:
    return Answer(kind="choice", choice=value, confidence=confidence, probabilities=probabilities)


def yes(p: float) -> Answer:
    return truth(p)


def thresholds(**changes: Any) -> Thresholds:
    return Thresholds().with_(**changes)


def squire(decider: Any, **changes: Any) -> tuple[Squire, MemoryJournal]:
    journal = MemoryJournal()
    return Squire(
        decider, thresholds=thresholds(**changes), journal=journal, brief="brief"
    ), journal


DATASET_FILES = {
    "HOTPOT": "hotpot.jsonl",
    "QASPER": "qasper-test.jsonl",
    "CODEX": "atbench-codex-test.json",
}


def bench_module(folder: Any, name: str) -> Any:
    """Import benchmark module `name` from `folder` without leaving the folder's modules in
    `sys.modules`: benchmark folders reuse names (`labels`, `score`, `run`) and a later test of
    another benchmark would import the wrong one."""
    import importlib
    import pathlib
    import sys

    path = str(folder)
    own = {p.stem for p in pathlib.Path(path).glob("*.py")}
    # another benchmark's module of the same name, imported earlier, must not answer for ours
    saved = {n: sys.modules.pop(n) for n in own if n in sys.modules}
    before = set(sys.modules)
    sys.path.insert(0, path)
    try:
        module = importlib.import_module(name)
    finally:
        sys.path.remove(path)
        for added in set(sys.modules) - before:
            source = str(getattr(sys.modules[added], "__file__", "") or "")
            if source.startswith(path):
                del sys.modules[added]
        sys.modules.update(saved)
    return module


def dataset(name: str) -> str:
    """A local dataset that is not redistributed: `SANCHOPANZA_<name>` (or the old
    `SANCHO_<name>`), else its file in `~/.cache/sanchopanza` (or the old `~/.cache/sancho`)
    when it is there, else "" and the test skips."""
    value = _env.get(name)
    if value:
        return value
    candidate = _env.cache_dir() / DATASET_FILES[name]
    return str(candidate) if candidate.exists() else ""


def registered_digest(tree_digest: Callable[[Path], str], root: Path) -> str:
    """`tree_digest(root)` in the order the context runs registered it in (2026-09-28). It sorts
    Path objects, and Windows compares them without case: elsewhere the same files come in
    another order (README.md before pkg/) and give another digest, so there they are sorted as
    Windows paths. The bytes hashed are the same."""
    if os.name == "nt":
        return tree_digest(root)
    h = hashlib.sha256()
    files = [p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    for path in sorted(files, key=lambda p: PureWindowsPath(p.relative_to(root))):
        h.update(path.relative_to(root).as_posix().encode() + b"\0" + path.read_bytes() + b"\0")
    return h.hexdigest()


def main_venv() -> Path:
    """`Scripts` of the main checkout's `.venv`, where the long runs' launchers take Python from:
    the folder above git's common directory, which a sibling worktree shares with the main
    checkout (only that checkout has a `.venv`). The tests that need it skip when it is absent."""
    root = Path(__file__).resolve().parents[1]
    try:
        done = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=False,
        )  # fmt: skip
        common = done.stdout.strip() if done.returncode == 0 else ""
    except OSError:
        common = ""
    checkout = Path(common).parent if common else root
    return checkout / ".venv" / "Scripts"


def missing_commits(*commits: str) -> list[str]:
    """The commits of `commits` this clone does not hold: CI checks out one commit (depth 1),
    so the sealed commits the launch tests look up are only in a full clone."""
    root = Path(__file__).resolve().parents[1]
    return [
        c
        for c in commits
        if subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", f"{c}^{{commit}}"],
            capture_output=True,
        ).returncode
        != 0
    ]
