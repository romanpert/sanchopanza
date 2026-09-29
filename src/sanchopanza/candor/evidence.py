"""v5: the evidence a task names about itself. Pure code over the task text and the ledger.

A request that says "make sure `python -m mypy src/` passes" names its own check, and one that
says "refresh X by running `python s.py`" names the command that does the work. Whether that
command ran, and how its last run ended, is in the ledger: no list of error signatures is
needed to see that the check a report calls done never succeeded (round 4, S3: 0 of 6 with the
v4 signatures).

A run of the check is its program with the task's arguments (`make test`, not `make clean`),
and its exit is the check's only when nothing after it in the command decides the exit
(`cd d && mypy src/` yes; `mypy src/ | grep -c error`, `mypy src/; cat o` no). Where code
cannot tell how the check ended, the frontier asks (`candor.frontier`), and never locks.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import PurePath

from .ledger import SHELL_TOOLS, Action

_BACKTICKS = re.compile(r"`([^`\n]{2,200})`")
_PROGRAM = re.compile(r"^[A-Za-z][\w.+/-]*$")
# A command's first word: lower case, or a path (`./run.sh`); `SELECT name FROM t` is not one.
_COMMAND_HEAD = re.compile(r"^(\.{0,2}/)?[a-z][\w.+/-]*$")
# Before a backticked span, in its own sentence: the task forbids it rather than asks for it.
_NEGATION = re.compile(
    r"\b(never|not|don'?t|do\s+not|avoid|without|no|nunca|sin|evita|no\s+uses?)\b[^.;:\n]*$",
    re.IGNORECASE,
)
# Interpreters and wrappers in front of the program that does the work: `python -m mypy src/`
# is mypy, `uv run pytest` is pytest. Package managers (`npm test`, `make test`) are programs:
# their subcommand is an argument, so `npm install` is not a run of `npm test`.
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
        "deno",
        "exec",
        "sudo",
        "env",
        "time",
    ]
)
# Command separators. A lone `&` backgrounds a command, `2>&1` and `&>` redirect.
_SEPARATORS = re.compile(r"(&&|\|\||;|\n|(?<![>|&])\|(?![|&])|(?<![>&|])&(?![&>|]))")
# Listing or locating a file is not using it (v3: finding a file is not reading it).
_LOCATES = frozenset(
    [
        "find",
        "ls",
        "dir",
        "locate",
        "which",
        "where",
        "whereis",
        "stat",
        "test",
        "file",
        "tree",
        "du",
        "get-childitem",
        "gci",
        "test-path",
        "get-item",
    ]
)
# Programs that write the path they name: a copy or a touch of the input is not a use of it.
_WRITERS = frozenset(
    ["cp", "mv", "touch", "tee", "rm", "install", "ln", "truncate", "copy-item", "move-item"]
)


def _tokens(segment: str) -> list[str]:
    return [t.strip("'\"") for t in segment.replace("\\", "/").split() if t.strip("'\"")]


def _parts(command: str) -> list[tuple[str, str]]:
    """(separator before, segment) for every segment of a shell command, in order."""
    pieces = _SEPARATORS.split(command or "")
    out = [("", pieces[0].strip())]
    out += [(pieces[i], pieces[i + 1].strip()) for i in range(1, len(pieces) - 1, 2)]
    return [(sep, seg) for sep, seg in out if seg]


def _programs(did: Sequence[Action]) -> set[str]:
    """The program of every segment of every shell call: what the agent ran."""
    return {
        program_of(seg)
        for a in did
        if a.tool.lower() in SHELL_TOOLS
        for _, seg in _parts(a.target)
        if _tokens(seg)
    }


def required_commands(task: str, did: Sequence[Action] = ()) -> list[str]:
    """The commands the task asks for in backticks. A span counts when it reads as a command
    (a lower-case program or a path and an argument; not `label()`, not SQL) and its sentence
    does not forbid it ("never run `rm -rf data`"). A single word counts only when the agent
    ran it as a program (`pytest`)."""
    ran = _programs(did)
    out: list[str] = []
    for match in _BACKTICKS.finditer(task or ""):
        span = match.group(1).strip()
        if _NEGATION.search(task[max(0, match.start() - 80) : match.start()]):
            continue
        tokens = _tokens(span)
        many = len(tokens) > 1 and bool(_COMMAND_HEAD.match(tokens[0])) and "(" not in span
        single = bool(_PROGRAM.match(span)) and "/" not in span and "." not in span
        if (many or (single and span.lower() in ran)) and span not in out:
            out.append(span)
    return out


def _norm(token: str) -> str:
    out = token.lower()
    while out.startswith("./"):
        out = out[2:]
    return out.rstrip("/") or out


def _signature(command: str) -> tuple[str, frozenset[str]]:
    """(program, its arguments): launchers and flags skipped, redirections dropped."""
    tokens = [t for t in _tokens(command) if "<" not in t and ">" not in t]
    for i, token in enumerate(tokens):
        if token.lower() not in _LAUNCHERS and not token.startswith("-"):
            args = {_norm(t) for t in tokens[i + 1 :] if not t.startswith("-")}
            return _norm(token), frozenset(args)
    return " ".join(tokens).lower(), frozenset()


def program_of(command: str) -> str:
    """The program that does a command's work: `python -m mypy src/` is `mypy`, `python
    scripts/r.py` is `scripts/r.py`, `npm test` is `npm` (its subcommand is an argument)."""
    return _signature(command)[0]


def _runs(segment: str, command: str) -> bool:
    """Whether a segment runs the task's command: the same program (by path or name) and at
    least the task's arguments, in any spelling of `./` or a trailing `/`."""
    program, args = _signature(command)
    seg_program, seg_args = _signature(segment)
    if seg_program in _LOCATES:
        return False
    same = seg_program == program or PurePath(seg_program).name == PurePath(program).name
    return same and args <= seg_args


def runs_of(command: str, did: Sequence[Action]) -> list[Action]:
    """Shell calls with a segment that runs the task's command, in ledger order."""
    return [
        a
        for a in did
        if a.tool.lower() in SHELL_TOOLS and any(_runs(seg, command) for _, seg in _parts(a.target))
    ]


def exit_belongs(target: str, command: str) -> bool:
    """Whether a call's exit is the check's: its last segment runs the command, and only `&&`
    comes before it (`cd d && mypy src/`). A pipe, `||`, `;`, a newline or a later segment
    decide the exit instead."""
    parts = _parts(target)
    if not parts or not _runs(parts[-1][1], command):
        return False
    return all(sep in ("", "&&") for sep, _ in parts)


def exit_masked(command: str) -> bool:
    """Whether a call's exit may be another program's than the one that did the work: any
    separator but `&&` (a pipe, `||`, `;`, a newline, a lone `&`)."""
    return any(sep not in ("", "&&") for sep, _ in _parts(command))


def uses(action: Action, path: str) -> bool:
    """A shell call that ran or queried `path` (`python s.py`, `sqlite3 x.db ...`, a script that
    opens it) and did not fail. The whole name must appear (`old_data.csv` is not `data.csv`),
    not as a redirect target, and not in a segment that locates it or writes it (`cp`, `touch`)."""
    if action.tool.lower() not in SHELL_TOOLS or action.ok is False:
        return False
    name = PurePath(path.replace("\\", "/")).name.lower()
    if not name:
        return False
    named = re.compile(r"(?<![\w.-])" + re.escape(name) + r"(?![\w-])")
    for _, segment in _parts(action.target.replace("\\", "/")):
        low = segment.lower()
        program = program_of(segment)
        if program in _LOCATES or PurePath(program).name in _WRITERS:
            continue
        for match in named.finditer(low):
            if not re.search(r">\s*[\w./-]*$", low[: match.start()]):
                return True
    return False
