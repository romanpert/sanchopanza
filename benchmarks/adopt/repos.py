"""The repositories the long-session tasks come from, each at a fixed snapshot commit."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

APPS = Path(r"C:\Users\roman\Desktop\proyectos\apps")


@dataclass(frozen=True)
class Repo:
    name: str
    path: Path
    snapshot: str  # the commit the bugs are put back into
    python: Path  # an interpreter with the test dependencies
    pythonpath: tuple[str, ...]  # relative to the worktree, so tests import the worktree's code
    code_prefixes: tuple[str, ...]  # where code lives (tests aside)


REPOS = {
    "sanchopanza": Repo(
        name="sanchopanza",
        path=APPS / "sanchopanza",
        snapshot="dc80311",  # the last commit before this study's own changes
        python=APPS / "sanchopanza" / ".venv" / "Scripts" / "python.exe",
        pythonpath=("src",),
        code_prefixes=("src/",),
    ),
    "indagis": Repo(
        name="indagis",
        path=APPS / "indagis",
        snapshot="1ebe456",
        python=APPS / "indagis" / ".venv" / "Scripts" / "python.exe",
        pythonpath=(".",),
        code_prefixes=("agent/", "indagis/"),
    ),
}
