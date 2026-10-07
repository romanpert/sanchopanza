"""The re-request record of the passages hook: did the agent ask again for what was cut?

rtk-style compression came out 7.6 % dearer when measured independently, because the agent ran
again what it missed (`docs/MAPA-HUECOS-ARNES.md`, 2). So every cut is remembered for the next
`WINDOW` calls the hook sees (Bash, PowerShell and Read: the calls it is wired on), and a call
that asks for the same thing again is journaled as `passages_rerequest`:

- **whole**: the same command again (whitespace aside), a `Read` of the same file with no offset
  or limit, or the archived text read or printed whole. A whole re-request is never cut again:
  cutting it twice is the loop that made compression cost more.
- **targeted**: the same file read with an offset or a limit, looked at from the shell (`sed -n`,
  `grep`; a `cat` of it is whole), or the archive searched or read in part. That is the
  recovery the header asks for, and it costs a fraction of a whole one. Approximate: running
  the file (`python settings.py`) also counts as a look, and `Grep` is not seen (not wired).

The risk measure of bet A is the share of cuts with a whole re-request (abort the arm past 0.5).
The record (`.sanchopanza/passages/<session>.json`, beside the archive, out of git) holds the
cut's command or path, the archive file and a call counter. The counter only advances while a
cut is inside the window. Two hooks running at once may each miss the other's write; the
journal event carries the `tool_use_id`, so an offline count from the transcript can redo it.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..context import archive as archive_mod

WINDOW = 5
FOLDER = "passages"
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})
_PRINTS_WHOLE = re.compile(r"^\s*(?:cat|type|Get-Content|gc|more|less)\b[^|]*$", re.I)


def path_key(raw: str) -> str:
    try:
        return os.path.normcase(str(Path(raw).resolve()))
    except (OSError, ValueError):
        return os.path.normcase(raw)


def call_key(tool: str, tool_input: Mapping[str, Any]) -> str:
    """What makes two calls the same request: the file of a `Read`, the words of a command."""
    if tool == "Read":
        return path_key(str(tool_input.get("file_path") or ""))
    return " ".join(str(tool_input.get("command") or "").split())


def _narrowed(tool_input: Mapping[str, Any]) -> bool:
    return any(tool_input.get(k) not in (None, "") for k in ("offset", "limit"))


def _path(root: Path, session: str) -> Path:
    return root.parent / FOLDER / f"{archive_mod.safe_name(session or 'session')}.json"


def read(root: Path, session: str) -> dict[str, Any]:
    try:
        value = json.loads(_path(root, session).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"calls": 0, "cuts": []}
    if not isinstance(value, dict) or not isinstance(value.get("cuts"), list):
        return {"calls": 0, "cuts": []}
    return value


def write(root: Path, session: str, state: Mapping[str, Any]) -> None:
    path = _path(root, session)
    with contextlib.suppress(OSError):
        archive_mod.keep_out_of_git(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_suffix(f".{os.getpid()}.tmp")
        partial.write_text(json.dumps(dict(state)), encoding="utf-8")
        partial.replace(path)  # a hook beside this one never reads half a file


def _match(cut: Mapping[str, Any], tool: str, tool_input: Mapping[str, Any]) -> str | None:
    """`whole`, `targeted` or None: how this call asks again for what `cut` left out."""
    archive = str(cut.get("archive") or "")
    if tool == "Read":
        target = path_key(str(tool_input.get("file_path") or ""))
        same = target == cut.get("key") and cut.get("tool") == "Read"
        if same or (archive and target == path_key(archive)):
            return "targeted" if _narrowed(tool_input) else "whole"
        return None
    command = str(tool_input.get("command") or "")
    if archive and (archive in command or Path(archive).name in command):
        return "whole" if _PRINTS_WHOLE.match(command) else "targeted"
    name = Path(str(cut.get("key") or "")).name if cut.get("tool") == "Read" else ""
    if name and re.search(rf"(?<![\w.-]){re.escape(name)}(?![\w.-])", command, re.I):
        return "whole" if _PRINTS_WHOLE.match(command) else "targeted"  # sed -n, grep, cat
    if cut.get("tool") in SHELL_TOOLS and call_key(tool, tool_input) == cut.get("key"):
        return "whole"
    return None


def note_call(
    state: Mapping[str, Any], tool: str, tool_input: Mapping[str, Any], use_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    """(the state after this call, the re-request events, whether one is whole). The state is
    returned unchanged when no cut is inside the window, and then need not be written."""
    calls = int(state.get("calls", 0))
    recent = [c for c in state.get("cuts", []) if calls + 1 - int(c.get("at", 0)) <= WINDOW]
    if not recent:
        return dict(state), [], False
    events = []
    for cut in recent:
        kind = _match(cut, tool, tool_input)
        after = calls + 1 - int(cut.get("at", 0))
        if kind:
            events.append({"cut": cut.get("id"), "tool_use_id": use_id, "tool": tool,
                           "after_calls": after, "kind": kind})  # fmt: skip
    whole = any(e["kind"] == "whole" for e in events)
    return {**state, "calls": calls + 1, "cuts": recent}, events, whole


def remember(state: Mapping[str, Any], cut: Mapping[str, Any]) -> dict[str, Any]:
    """The state with one more cut, made at the current count; cuts past the window dropped."""
    calls = int(state.get("calls", 0))
    live = [c for c in state.get("cuts", []) if calls - int(c.get("at", 0)) < WINDOW]
    return {**state, "calls": calls, "cuts": [*live, {**cut, "at": calls}]}
