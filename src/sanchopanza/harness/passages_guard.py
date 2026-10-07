"""The guard of the passages hook: no file is rewritten from a view the hook cut.

Review 2026-10-07, critical: an agent shown a cut `Read` (or a cut `cat` of a file) that then
`Write`s the file from what it saw deletes every line it was not shown. So a `PreToolUse` hook on
`Write`, `Edit`, `MultiEdit` and `NotebookEdit`:

- denies a `Write` to a file shown cut whose omitted lines the agent has not read since: by a
  whole `Read` the hook let through, or by `Read`s with offset and limit that cover every gap
  (`passages_state.see`, fed by the `PostToolUse` hook on every `Read`);
- denies any edit whose text carries one of our markers: the marker is not in the file, and an
  `old_string` holding one cannot match, while a `new_string` or a `Write` holding one would
  write it into the file;
- marks the recent cuts as edited, so a test run again after the edit is a new result
  (`passages_state.note_call`), not a re-request.

An `Edit` without a marker passes: it replaces text the agent saw, by content. Fails open: any
error here lets the call through, with the reason on stderr.
"""

from __future__ import annotations

import contextlib
import sys
from collections.abc import Mapping
from typing import Any

from . import autopilot
from . import passages_state as state_mod

TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
MARKERS = ("[sanchopanza: lines ", "[... sanchopanza omitted", "[sanchopanza cut this",
           "[sanchopanza: this output")  # fmt: skip
MARKED = (
    "sanchopanza: this edit carries an omission marker that sanchopanza put in a cut view; that "
    "text is not in the file. Read the lines the marker names (Read with offset and limit) and "
    "edit the file's real text."
)
PARTIAL = (
    "sanchopanza: {path} was shown to you as a partial view (lines {gaps} were left out). Do not "
    "rewrite this file with Write from that view: it would delete the lines you did not see. "
    "Read the rest first (Read with offset and limit for each range above), or change it with "
    "Edit on the lines you saw."
)
GAPS_SHOWN = 6


def _texts(tool_input: Mapping[str, Any]) -> list[str]:
    keys = ("content", "old_string", "new_string", "new_source")
    out = [str(tool_input.get(k) or "") for k in keys]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, Mapping):
            out += [str(edit.get("old_string") or ""), str(edit.get("new_string") or "")]
    return out


def _deny(reason: str) -> dict[str, Any]:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}  # fmt: skip


def _gaps(ranges: list[tuple[int, int]]) -> str:
    shown = [f"{a}-{b}" for a, b in ranges[:GAPS_SHOWN]]
    more = len(ranges) - len(shown)
    return ", ".join(shown) + (f" and {more} more" if more > 0 else "")


def pre_tool_use(event: Mapping[str, Any]) -> dict[str, Any]:
    """The guard's answer: a denial, or `{}` to let the call run. Never raises."""
    try:
        return _decide(event)
    except Exception as error:  # noqa: BLE001 - fail open, never silently
        with contextlib.suppress(Exception):  # stderr gone: nothing left to tell
            sys.stderr.write(f"sanchopanza passages guard: let through ({error!r})\n")
        return {}


def _decide(event: Mapping[str, Any]) -> dict[str, Any]:
    tool = str(event.get("tool_name", ""))
    if tool not in TOOLS:
        return {}
    tool_input = event.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, Mapping) else {}
    if any(marker in text for text in _texts(tool_input) for marker in MARKERS):
        return _deny(MARKED)
    root = autopilot._root(event, autopilot.config_from_env())
    session = autopilot._session(event)
    state = state_mod.read(root, session)
    path = str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")
    gaps = state_mod.unseen(state, path) if tool == "Write" and path else []
    if gaps:
        return _deny(PARTIAL.format(path=path, gaps=_gaps(gaps)))
    if state.get("cuts"):
        state_mod.write(root, session, state_mod.mark_edit(state))
    return {}
