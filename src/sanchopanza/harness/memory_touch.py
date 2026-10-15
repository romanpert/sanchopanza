"""Just in time (`memory_hook`, PostToolUse and PreToolUse): the record of an earlier request
whose lines the agent is looking at when it opens or changes a file. Code only, no decider. Split
out of `memory_hook` (review of F1); what it measured is told there.
"""

from __future__ import annotations

import contextlib
import json
import os
import posixpath
import re
import sys
from collections.abc import Mapping, Sequence
from typing import Any

from .. import _env
from ..context import episodes as ep
from . import memory_tree
from .memory_recall import CHARS, HEADER, pool_of, render

# Just in time: a file the agent opens or changes gives the records of earlier requests that
# changed it, the TOUCH_K newest, once per session. On the same data: 93 % of the requests with a
# related record had one in view, 57 % of what was given was related, 3.8 % of the requests with
# nothing related were given anything; 90 % arrived before the request's first edit.
TOUCH_TOOLS = ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit")
# v4 (SWE-chat development, 2026-10-01): at a Read, the one record whose written lines the
# agent sees most, and nothing when it sees none; at an edit, the record whose lines it edits,
# else the newest. Against v3 (the two newest): precision 0.643 -> 0.766 (lineage 0.150 ->
# 0.188), recall unchanged (0.932), 13 % fewer characters.
TOUCH_K = 1
# Records opened per touch: the newest that changed the file. A file changed by 300 requests
# made a touch 0.40 s (opening every record); the pools measured on SWE-chat never exceed 50.
TOUCH_LOAD = 30
TOUCH_HEADER = (
    "[sanchopanza memory, earlier work on {path}: verbatim records of earlier requests in this "
    "project that changed this file, written by code from the transcripts, oldest first]"
)


class _Hook:
    """`memory_hook`, looked up at call time: it imports this module, and its names are the one
    place tests and `benchmarks/memory_real` patch (`mh.choose_touched = ...`)."""

    def __getattr__(self, name: str) -> Any:
        from . import memory_hook

        return getattr(memory_hook, name)


mh = _Hook()


# ---- just in time: a file the agent opens or changes ------------------------------------------


_BASH_DRIVE = re.compile(r"^/([a-zA-Z])/")
_HEADER_UNSAFE = re.compile(r"[\[\]\r\n\u2028\u2029]")
PATH_IN_HEADER = 200


def _norm(path: str) -> str:
    """One spelling of a path: forward slashes, `.` and `..` resolved, a Git Bash `/c/` drive
    as `c:/`, and case folded where the file system folds it (Windows, macOS)."""
    clean = path.strip().replace("\\", "/")
    if os.name == "nt":
        clean = _BASH_DRIVE.sub(r"\1:/", clean)
    clean = posixpath.normpath(clean) if clean else clean
    return clean.casefold() if os.name == "nt" or sys.platform == "darwin" else clean


def _absolute(path: str) -> bool:
    return path.startswith(("/", "\\")) or bool(re.match(r"^[a-zA-Z]:", path))


def _wanted(raw: str, event_cwd: str, start: str) -> set[str]:
    """The spellings a record may hold for `raw`: relative to where the session started (as
    records are written), and absolute. A relative `raw` is resolved against the event's cwd
    (the agent may have changed directory since the session started)."""
    base = event_cwd or start
    full = raw if _absolute(raw) or not base else f"{base.rstrip('/').rstrip(chr(92))}/{raw}"
    full = _norm(full)
    anchor = start or event_cwd  # no state yet (no prompt seen): the event's own cwd
    rel = _norm(ep.relative(full, _norm(anchor))) if anchor else full
    return {full, rel}


def render_touch(
    chosen: Sequence[ep.Episode], path: str, cap: int = CHARS
) -> tuple[str, list[str]]:
    """The records under a header naming the file: one line, the path cleaned of brackets and
    line breaks and cut to PATH_IN_HEADER (the agent chose it), and the whole within `cap`."""
    shown_path = _HEADER_UNSAFE.sub(" ", path)[:PATH_IN_HEADER]
    header = TOUCH_HEADER.format(path=shown_path)
    text, keys = render(chosen, cap - max(0, len(header) - len(HEADER)))
    if not keys:
        return "", []
    return text.replace(HEADER, header, 1), keys


def touch(event: Mapping[str, Any]) -> dict[str, Any]:
    """PostToolUse on a file tool, or on Bash (v6): the record of an earlier request whose
    lines the agent is looking at, outside the live context and not given since the last
    compaction. Not inside a subagent (its context is thrown away, and it would use up the main
    agent's once). Code only: no decider."""
    if mh.mode() == "off" or str(_env.get("MEMORY_TOUCH", "") or "on").lower() in ("off", "0"):
        return {}
    tool = event.get("tool_name")
    if tool not in (*TOUCH_TOOLS, *SHELL_TOOLS) or event.get("agent_id"):
        return {}
    data = event.get("tool_input") if isinstance(event.get("tool_input"), Mapping) else {}
    if tool in SHELL_TOOLS:
        command = data.get("command")
        raws, seen, base = mh.bash_view(command, event.get("tool_response"),
                                     str(event.get("cwd") or ""),
                                     powershell=tool == "PowerShell")  # fmt: skip
        written = mh.shell_written(command) if mh.SHELL_EDIT_RULE else []
        given = _give(event, written, "Edit", seen, base) if written else {}
        if given or not mh.SHELL_READS:
            return given
        return _give(event, [r for r in raws if r not in written], "Read", seen, base)
    raw = data.get("file_path") or data.get("notebook_path")
    if not isinstance(raw, str) or not raw.strip():
        return {}
    return _give(event, [raw], str(tool), seen_prints(event), str(event.get("cwd") or ""))


def _give(
    event: Mapping[str, Any], raws: Sequence[str], rule: str, seen: set[str], base: str
) -> dict[str, Any]:  # fmt: skip
    """The record for files `raws` (spelt as the agent wrote them, relative to `base`) by the
    v4 rule of tool `rule`, with `seen` the prints of the lines in view."""
    if not raws:
        return {}
    session = str(event.get("session_id") or "session")
    store = mh.store_for(event)
    state = mh._state(store, session)
    start = str(state.get("cwd") or "")
    index = ep.index_of(store)
    per_raw = [(raw, _wanted(raw, base, start)) for raw in raws]
    changed = {k: {_norm(str(c)) for c in v.get("changed") or []} for k, v in index.items()}
    hits = [(raw, wanted) for raw, wanted in per_raw if any(wanted & c for c in changed.values())]
    if not hits:
        return {}
    wanted = {w for _, ws in hits for w in ws}
    found = [(float(index[k].get("at") or 0.0), k) for k, c in changed.items() if wanted & c]
    keys = [k for _, k in sorted(found, reverse=True)[:TOUCH_LOAD]]
    with ep.locked(mh._shown_path(store, session)):  # parallel tool calls: one gives, others see it
        boundaries, live = mh.live_at_last_prompt(store, session)
        shown = mh.shown_since_compaction(store, session, boundaries)
        loaded = ep.load_keys(store, keys)
        matching = pool_of(loaded, session, live, shown)
        chosen = mh.choose_touched(matching, rule, seen, mh._int("MEMORY_TOUCH_K", TOUCH_K), wanted,
                                loaded)  # fmt: skip
        named = next((raw for raw, ws in hits if chosen and ws & changed[chosen[0].key]),
                     hits[0][0])  # fmt: skip
        shown_as = ep.relative(named, start or base)
        text, given = render_touch(chosen, shown_as, mh._int("MEMORY_CHARS", CHARS))
        if text:
            with contextlib.suppress(OSError):
                mh.remember_shown(store, session, boundaries, given)
    mh._log({"event": "PostToolUse", "tool": event.get("tool_name"), "path": shown_as,
          "matching": [e.key for e in matching], "shown": given, "chars": len(text),
          "phase": "pre" if event.get("hook_event_name") == "PreToolUse" else "post"})  # fmt: skip
    if not text:
        return {}
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}}


SHELL_TOOLS = memory_tree.SHELL_TOOLS  # PowerShell: Claude Code on Windows
SHELL_EDIT_RULE = True  # a file the command writes takes the edit rule (newest, no line in view)
# v6.2: a shell READ gives nothing. Amendment 5: agents in auto mode read through `sed -n` and
# `grep -n` dozens of times per request and 196 of 258 records were unrelated, all from reads;
# B2 lost no recall without them (Sonnet's records arrive at its shell edits), and every record
# a shell write gave on the maintainer's sessions was of a file the request wrote. (v6.1's gate,
# no shell touch once a session edits with a file tool, only removed such records: gone.)
SHELL_READS = False


SHELL_FIRST_NOTE = (
    "[sanchopanza memory] Not run yet, and not refused: this command changes a file that an "
    "earlier request changed too, and its record is below so that you see it before the change "
    "rather than after. Run the same command again (or a changed one) to go on; this happens "
    "once per command."
)
DENIED = "denied"  # per-session, in the shown state: hashes of commands denied once


def shell_first_on() -> bool:
    """v6.3 candidate, off by default: `SANCHOPANZA_MEMORY_SHELL_FIRST=deny`."""
    return str(_env.get("MEMORY_SHELL_FIRST", "") or "off").strip().lower() == "deny"


def shell_first(event: Mapping[str, Any]) -> dict[str, Any]:
    """PreToolUse on Bash or PowerShell: when the command writes a file with a record this
    session was not given, deny it once with the record as the reason (Claude Code feeds the
    reason back to the agent, in every permission mode), so the record arrives before the
    change. The same command is never denied twice; a command that writes nothing with a
    record, a read, a file tool or a subagent's call is never denied."""
    if not shell_first_on() or event.get("tool_name") not in SHELL_TOOLS:
        return {}
    data = event.get("tool_input") if isinstance(event.get("tool_input"), Mapping) else {}
    command = data.get("command")
    if not isinstance(command, str) or not mh.shell_written(command) or event.get("agent_id"):
        return {}
    import hashlib

    digest = hashlib.sha1(command.encode("utf-8", "surrogateescape")).hexdigest()[:16]
    store, session = mh.store_for(event), str(event.get("session_id") or "session")
    if digest in (mh._state(store, session).get(DENIED) or []):
        return {}
    text = (mh.touch({**event, "tool_response": {}}).get("hookSpecificOutput") or {}).get(
        "additionalContext", "")  # fmt: skip
    if not text:
        return {}
    with contextlib.suppress(OSError), ep.locked(mh._shown_path(store, session)):
        state = mh._state(store, session)
        denied = [*(state.get(DENIED) or []), digest][-200:]
        ep.write_private(mh._shown_path(store, session), json.dumps({**state, DENIED: denied}))
    reason = f"{SHELL_FIRST_NOTE}\n\n{text}"
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}  # fmt: skip


def shell_written(command: Any) -> list[str]:
    from ..context import shell

    return shell.written(command)


def bash_view(
    command: Any, response: Any, cwd: str, powershell: bool = False
) -> tuple[list[str], set[str], str]:
    from ..context import shell

    return shell.view(command, response, cwd, powershell)


def seen_prints(event: Mapping[str, Any]) -> set[str]:
    """Prints of the lines the agent is looking at: what a Read returned, what an Edit or a
    MultiEdit replaces. Nothing for a Write (it replaces the file whole) or a notebook."""
    tool = event.get("tool_name")
    data = event.get("tool_input") if isinstance(event.get("tool_input"), Mapping) else {}
    if tool == "Read":
        response = event.get("tool_response")
        if isinstance(response, Mapping):
            file = response.get("file") if isinstance(response.get("file"), Mapping) else {}
            return ep.line_prints(file.get("content") or response.get("content"))
        return ep.line_prints(response)
    if tool == "Edit":
        return ep.line_prints(data.get("old_string"))
    if tool == "MultiEdit":
        return {p for e in data.get("edits") or [] if isinstance(e, Mapping)
                for p in ep.line_prints(e.get("old_string"))}  # fmt: skip
    return set()


def choose_touched(
    matching: Sequence[ep.Episode], tool: str, seen: set[str], k: int = TOUCH_K,
    wanted: set[str] | None = None, writers: Sequence[ep.Episode] = (),
) -> list[ep.Episode]:  # fmt: skip
    """The records whose written lines in this file are in view, most first (newest on a tie).
    A line belongs to the newest record that wrote it among `writers` (every record of the
    file, given or not): a request that rewrote a file takes over the lines it rewrote. With
    none in view: at an edit, the newest; at a Read, only records saved before v4, newest."""

    def newest(pool: Sequence[ep.Episode]) -> list[ep.Episode]:
        return sorted(pool, key=lambda e: (-e.at, e.session, -e.index))

    def lines(e: ep.Episode) -> set[str]:
        paths = wanted if wanted else {rel for rel, _ in e.wrote or ()}
        return {p for rel, prints in e.wrote or () if _norm(rel) in {_norm(x) for x in paths}
                for p in prints} & seen  # fmt: skip

    owner: dict[str, str] = {}
    for e in sorted({*writers, *matching}, key=lambda e: (e.at, e.session, e.index)):
        for p in lines(e):
            owner[p] = e.key
    overlap = {e.key: sum(1 for o in owner.values() if o == e.key) for e in matching}
    hits = [e for e in matching if e.wrote is not None and overlap[e.key] > 0]
    if hits:
        return sorted(newest(hits), key=lambda e: -overlap[e.key])[:k]
    if tool != "Read":
        return newest(matching)[:k]
    return newest([e for e in matching if e.wrote is None])[:k]
