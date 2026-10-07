"""What the passages hook never cuts, decided by code: the gates of `harness.passages_hook`.

- a `Read` the agent narrowed (offset or limit): it already chose;
- a `Read` or command on the archive or on Claude Code's own `tool-results` folder: recovery;
- a diff (`git diff`, `git show`, `git log -p`, with `-C`, `-c` or `--no-pager` before the
  subcommand; `gh pr diff`, `svn diff`, `hg diff`, `diff -u`): a patch is applied or reviewed
  whole;
- a browser snapshot on stdout: the browse hook's;
- a file the agent edited in this context, or one its last words say it will edit (an edit verb
  and the file's name), whether it comes by `Read` or by a shell view of it (`cat`, `type`,
  `Get-Content`, `sed -n`, `head`, `tail`, `less`, `more`, `bat`): the agent will need the literal
  text around its change.

Pure code over the event and the transcript; no decider.
"""

from __future__ import annotations

import os
import re
import shlex
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from . import passages_state as state_mod

DIFF = re.compile(
    r"\bgit\s+(?:(?:-[Cc]\s+\S+|--no-pager|--\S+)\s+)*"
    r"(?:diff|show|format-patch|stash\s+show|log\b[^|;&]*\s-p\b)"
    r"|\bgh\s+pr\s+diff\b|\b(?:svn|hg)\s+diff\b|\bdiff\s+-\w*u|\binterdiff\b"
)
EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
WILL_EDIT = re.compile(
    r"\b(?:edit|fix|chang|modif|updat|patch|rewrit|refactor|replac|implement|editar|cambi"
    r"|arregl|corrig|toc)\w*",
    re.I,
)
VIEW = re.compile(r"^\s*(?:cat|type|Get-Content|gc|sed|head|tail|less|more|bat)\b", re.I)
PRINT_ONE = re.compile(r"^\s*(?:cat|type|Get-Content|gc)\s+[^|;&<>]+$", re.I)


def _input(event: Mapping[str, Any]) -> Mapping[str, Any]:
    value = event.get("tool_input")
    return value if isinstance(value, Mapping) else {}


def _under(target: str, folder: Path) -> bool:
    try:
        return Path(target).resolve().is_relative_to(folder.resolve())
    except (OSError, ValueError):
        return False


def _recovery_folders(event: Mapping[str, Any], root: Path) -> list[Path]:
    transcript = str(event.get("transcript_path") or "")
    saved = [Path(transcript).with_suffix("") / "tool-results"] if transcript else []
    return [root, *saved]


def why_not(event: Mapping[str, Any], tool: str, text: str, root: Path) -> str | None:
    """Why a large result passes whole, before the transcript is read; None to go on."""
    tool_input = _input(event)
    folders = _recovery_folders(event, root)
    if tool == "Read":
        if any(tool_input.get(k) not in (None, "") for k in ("offset", "limit")):
            return "a Read the agent narrowed (offset or limit)"
        if any(_under(str(tool_input.get("file_path") or ""), f) for f in folders):
            return "a Read of archived output: recovery"
        return None
    command = str(tool_input.get("command") or "")
    if any(str(f) in command or str(f).replace("\\", "/") in command for f in folders):
        return "a command on archived output: recovery"
    if DIFF.search(command):
        return "a diff: applied or reviewed whole"
    from ..browse import snapshot_block

    if snapshot_block(text) is not None:
        return "a browser snapshot: the browse hook's"
    return None


def _words(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return command.split()


def viewed_files(command: str) -> list[str]:
    """The file arguments of a shell view (`cat x.py`, `sed -n 1,80p x.py`): words with a dot
    or a slash that are not options."""
    if not VIEW.match(command):
        return []
    words = _words(command)[1:]
    return [w.strip("'\"") for w in words
            if not w.startswith("-") and ("." in w or "/" in w or "\\" in w)
            and not re.fullmatch(r"[\d,]+[pdq]?", w)]  # fmt: skip


def printed_file(command: str, cwd: str) -> str | None:
    """The one file a `cat`/`type`/`Get-Content` prints whole, resolved against `cwd`."""
    if not PRINT_ONE.match(command):
        return None
    files = viewed_files(command)
    if len(files) != 1:
        return None
    path = Path(files[0])
    return str(path if path.is_absolute() or not cwd else Path(cwd) / path)


def last_words(messages: Sequence[Mapping[str, Any]]) -> str:
    from ..context.transcript import message_text

    return next((message_text(m) for m in reversed(messages)
                 if m.get("role") == "assistant" and message_text(m)), "")  # fmt: skip


def _targets(tool: str, tool_input: Mapping[str, Any], cwd: str) -> list[str]:
    if tool == "Read":
        raw = str(tool_input.get("file_path") or "")
        return [raw] if raw else []
    files = viewed_files(str(tool_input.get("command") or ""))
    return [f if Path(f).is_absolute() or not cwd else str(Path(cwd) / f) for f in files]


def edits(messages: Sequence[Mapping[str, Any]], tool: str, tool_input: Mapping[str, Any],
          cwd: str = "") -> str:  # fmt: skip
    """Why a view of a file passes whole because the agent edited it in this context, or says
    it will edit it; "" when neither."""
    from ..context.transcript import calls

    targets = _targets(tool, tool_input, cwd)
    if not targets:
        return ""
    keys = {state_mod.path_key(t) for t in targets}
    names = {Path(t).name.lower() for t in targets}
    for call in calls(messages):
        raw = call.input.get("file_path") or call.input.get("notebook_path")
        if call.tool in EDIT_TOOLS and raw and state_mod.path_key(str(raw)) in keys:
            return "a file the agent edited in this context"
    words = last_words(messages)
    if WILL_EDIT.search(words) and any(name and name in words.lower() for name in names):
        return "a file the agent says it will edit"
    return ""
