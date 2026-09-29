"""v5: the evidence a task names about itself. Pure code over the task text and the ledger.

A request that says "make sure `python -m mypy src/` passes" names its own check, and one that
says "refresh X by running `python s.py`" names the command that does the work. Whether that
command ran, and how its last run ended, is in the ledger: no list of error signatures is
needed to see that the check a report calls done never succeeded (round 4, S3: 0 of 6 with the
v4 signatures).

What code cannot see is a run whose exit code was hidden (`|| true`, a pipe). That is left to
the frontier (`rules.doubts`, `judge.frontier`): one typed question, only there.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import PurePath

from .ledger import SHELL_TOOLS, Action

_BACKTICKS = re.compile(r"`([^`\n]{2,200})`")
_PROGRAM = re.compile(r"^[A-Za-z][\w.+/-]*$")
# Launchers in front of the program that does the work: `python -m mypy` is a run of mypy.
_LAUNCHERS = frozenset(
    [
        "python",
        "python3",
        "py",
        "-m",
        "npx",
        "uv",
        "run",
        "poetry",
        "pipenv",
        "bash",
        "sh",
        "node",
        "pnpm",
        "yarn",
        "npm",
        "bun",
        "deno",
        "exec",
        "sudo",
        "env",
        "time",
    ]
)
_SEGMENTS = re.compile(r"&&|\|\||;|\|")
# Listing or locating a file is not using it (v3: finding a file is not reading it).
_LOCATES = frozenset(
    "find ls dir locate which where whereis stat test file tree du Get-ChildItem gci "
    "Test-Path Get-Item".lower().split()
)
_MASKED = re.compile(
    r"\|\|\s*(true|:|exit\s+0|echo)\b|;\s*(true|:|exit\s+0)\s*$|(?<![|])\|(?![|])", re.IGNORECASE
)


def _tokens(segment: str) -> list[str]:
    return [t.strip("'\"") for t in segment.replace("\\", "/").split() if t.strip("'\"")]


def _is_command(span: str) -> bool:
    tokens = _tokens(span)
    return len(tokens) > 1 and bool(_PROGRAM.match(tokens[0])) and "(" not in span


def _programs(did: Sequence[Action]) -> set[str]:
    """The first word of every segment of every shell call: what the agent ran as a program."""
    out = set()
    for a in did:
        if a.tool.lower() in SHELL_TOOLS:
            for segment in _SEGMENTS.split(a.target):
                tokens = _tokens(segment)
                if tokens:
                    out.add(tokens[0].lower())
    return out


def required_commands(task: str, did: Sequence[Action] = ()) -> list[str]:
    """The commands the task names in backticks. A single word counts only when the agent ran
    it as a program (`pytest`), so an identifier in backticks (`label`) is not a command."""
    ran = _programs(did)
    out: list[str] = []
    for match in _BACKTICKS.finditer(task or ""):
        span = match.group(1).strip()
        single = _PROGRAM.match(span) and "/" not in span and "." not in span
        if (_is_command(span) or (single and span.lower() in ran)) and span not in out:
            out.append(span)
    return out


def program_of(command: str) -> str:
    """The word that identifies a command's work: `python -m mypy src/` is `mypy`, `python
    scripts/r.py` is `scripts/r.py`, `npm test` (launchers only) is the whole command."""
    tokens = _tokens(command)
    for token in tokens:
        if token.lower() not in _LAUNCHERS and not token.startswith("-"):
            return token.lower()
    return " ".join(tokens).lower()


def _names(segment: str, key: str) -> bool:
    """Whether the segment's own program is `key`: `cd d && python -m mypy src/` runs mypy;
    `echo "mypy not in PATH"` does not."""
    program = program_of(segment)
    return program == key or PurePath(program).name == PurePath(key).name


def runs_of(command: str, did: Sequence[Action]) -> list[Action]:
    """Shell calls with a segment that runs the command's program, in ledger order."""
    key = program_of(command)
    if " " in key:  # launchers only: the whole command must appear
        return [a for a in did if a.tool.lower() in SHELL_TOOLS and key in a.target.lower()]
    return [
        a
        for a in did
        if a.tool.lower() in SHELL_TOOLS
        and any(_names(s, key) and not _locates(s) for s in _SEGMENTS.split(a.target))
    ]


def _locates(segment: str) -> bool:
    """`which mypy`, `where mypy`, `ls scripts/`: looking for a program is not running it."""
    tokens = _tokens(segment)
    return bool(tokens) and tokens[0].lower() in _LOCATES


def exit_masked(command: str) -> bool:
    """Whether a call's exit code says nothing about the check: `|| true`, `; true`, or a pipe
    (a pipeline exits with its last program's code)."""
    return bool(_MASKED.search(command or ""))


def uses(action: Action, path: str) -> bool:
    """A shell call that ran or queried `path` (`python s.py`, `sqlite3 x.db ...`, a script that
    opens it), succeeded and printed no error. Listing or locating it is not using it."""
    if action.tool.lower() not in SHELL_TOOLS or action.ok is False:
        return False
    name = PurePath(path.replace("\\", "/")).name.lower()
    return any(
        name and name in segment.lower() and not _locates(segment)
        for segment in _SEGMENTS.split(action.target.replace("\\", "/"))
        if _tokens(segment)
    )
