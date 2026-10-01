"""v6: what a request changed, read from the git working tree (`context.worktree`).

At a request's start (UserPromptSubmit) the hook keeps a snapshot of the tree; at its Stop it
compares, and keeps beside the request's record the files the request wrote and the prints of the
lines it added; `with_tree` merges them into the record when records are saved. A request
claims only files it wrote: an Edit/Write/MultiEdit/NotebookEdit path, or a file a Bash or
PowerShell command writes (`context.shell.written`), matched by whole path. A file it only read
while another session or the person changed it is not its own (review of v6, H2). A request
interrupted before its Stop is finished at the next prompt. Everything here fails open: the
records stay as the transcript makes them.

Files, in the project's store: `tree/<session>.json`, the open request's start snapshot
(removed when it is finished), and `tree/<session>-<index>.json`, what that request changed
(prints only, never text). Both are removed with the records after `episodes.KEEP_DAYS`.
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

from .. import _env
from ..context import episodes as ep
from ..context.archive import safe_name

TREE = "tree"
FILE_TOOLS = ("Edit", "MultiEdit", "Write", "NotebookEdit")
SHELL_TOOLS = ("Bash", "PowerShell")
DEADLINE = 4.0  # seconds a Stop may spend on the tree before it gives what it found


def tree_on() -> bool:
    return str(_env.get("MEMORY_TREE", "") or "on").strip().lower() not in ("off", "0")


def tree_path(store: Path, session: str, index: int | None = None) -> Path:
    name = safe_name(session) if index is None else f"{safe_name(session)}-{index:03d}"
    return store / TREE / f"{name}.json"


def _fold(path: str) -> str:
    clean = path.replace("\\", "/")
    return clean.casefold() if os.name == "nt" or sys.platform == "darwin" else clean


def _absolute(path: str) -> bool:
    return path.startswith(("/", "\\")) or (len(path) > 1 and path[1] == ":")


def _bash_drive(path: str) -> str:
    """A Git Bash `/c/x` path as `c:/x` on Windows."""
    drive = len(path) > 2 and path[0] == "/" and path[2] == "/" and path[1].isalpha()
    if os.name == "nt" and drive:
        return f"{path[1]}:{path[2:]}"
    return path


def wrote_paths(group: Sequence[Mapping[str, Any]], cwd: str) -> list[str]:
    """Absolute paths the request wrote: file tools' paths and shell commands' targets."""
    from ..context import shell
    from ..context.transcript import blocks_of

    out: list[str] = []
    for message in group:
        for block in blocks_of(message):
            if not (isinstance(block, Mapping) and block.get("type") == "tool_use"):
                continue
            data = block.get("input") if isinstance(block.get("input"), Mapping) else {}
            name, base, raws = block.get("name"), cwd, []
            if name in FILE_TOOLS:
                raws = [data.get("file_path") or data.get("notebook_path")]
            elif name in SHELL_TOOLS:
                command = data.get("command")
                raws = shell.written(command)
                _, _, base = shell.view(command, {}, cwd)
            for raw in raws:
                if isinstance(raw, str) and raw.strip():
                    raw = _bash_drive(raw.strip())
                    out.append(raw if _absolute(raw) else f"{base.rstrip('/')}/{raw}")
    return out


def _under(path: str, root: str) -> str | None:
    """`path` relative to `root` when it lies under it (folded), else None."""
    clean, base = _fold(os.path.normpath(path)), _fold(os.path.normpath(root)).rstrip("/") + "/"
    return clean[len(base):] if clean.startswith(base) else None


def start_tree(store: Path, session: str, cwd: str, index: int) -> None:
    """At a request's start: the working tree, for `finish_tree` to compare against."""
    if not tree_on() or not cwd:
        return
    from ..context import worktree

    snap = worktree.snapshot(cwd)
    if snap is not None:
        payload = {"index": index, "cwd": cwd, **snap.to_dict()}
        ep.write_private(tree_path(store, session), json.dumps(payload))


def open_request(store: Path, session: str) -> int | None:
    """The request whose start snapshot is kept and not finished yet (no Stop ran)."""
    try:
        start = json.loads(tree_path(store, session).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return start.get("index") if isinstance(start, dict) else None


def finish_tree(
    store: Path, session: str, entries: Sequence[Mapping[str, Any]], index: int | None = None
) -> bool:
    """At request `index`'s end (default: the transcript's last request): what it wrote in the
    tree since its start, kept beside its record. True when something was kept."""
    if not tree_on():
        return False
    try:
        start = json.loads(tree_path(store, session).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    groups = ep.split_requests(entries).groups
    index = len(groups) if index is None else index
    if not isinstance(start, dict) or start.get("index") != index or not 0 < index <= len(groups):
        return False  # the snapshot is of another request (a prompt whose hook did not run)
    from ..context import worktree

    cwd = str(start["cwd"])
    before = worktree.Snapshot.from_dict(start)
    real = os.path.realpath(cwd)
    claimed: dict[str, bool] = {}
    for path in wrote_paths(groups[index - 1], cwd):
        rel = _under(path, before.root)
        if rel is None and _under(path, cwd) is not None:  # through a symlinked folder
            rel = _under(f"{real}/{_under(path, cwd)}", before.root)
        if rel:
            claimed[rel] = True
    payload: dict[str, Any] = {"changed": [], "wrote": []}
    if claimed:
        deadline = time.monotonic() + DEADLINE
        found = worktree.changes(before, worktree.snapshot(cwd), only=list(claimed),
                                 deadline=deadline)  # fmt: skip
        kept = [(_session_path(before.root, rel, cwd, real), prints) for rel, prints in found]
        payload = {"changed": [r for r, _ in kept], "wrote": [[r, list(p)] for r, p in kept]}
    ep.write_private(tree_path(store, session, index), json.dumps(payload))
    with contextlib.suppress(OSError):
        tree_path(store, session).unlink()
    return bool(payload["changed"])


def _session_path(root: str, rel: str, cwd: str, real: str) -> str:
    """A root-relative path as the session's records spell paths: relative to where it
    started, through a symlinked or junction folder too (review of v6, M3)."""
    full = f"{root.replace(chr(92), '/').rstrip('/')}/{rel}"
    for base in (real, cwd):
        under = _under(full, base)
        if under is not None:
            return full[len(full) - len(under):]
    return full


def with_tree(store: Path, episode: ep.Episode) -> ep.Episode:
    """The record with what the tree says its request changed, beside what its tools did."""
    try:
        data = json.loads(tree_path(store, episode.session, episode.index).read_text("utf-8"))
    except (OSError, ValueError):
        return episode
    from ..redact import mask

    extra = [str(x) for x in data.get("changed") or []]
    if not extra:
        return episode
    raw = list(dict.fromkeys([*episode.changed_raw, *extra]))[: ep.FILES_MAX]
    shown = list(dict.fromkeys([*episode.changed, *(mask(x) for x in extra)]))[: ep.FILES_MAX]
    wrote = {rel: list(prints) for rel, prints in episode.wrote or ()}
    for rel, prints in data.get("wrote") or []:
        wrote[str(rel)] = list(dict.fromkeys([*wrote.get(str(rel), []), *prints]))
    return replace(episode, changed=tuple(shown), changed_raw=tuple(raw),
                   wrote=tuple((r, tuple(x)) for r, x in wrote.items()))  # fmt: skip


def prune(store: Path, keep_days: int = ep.KEEP_DAYS) -> None:
    """Tree files older than the records' retention go with them."""
    cutoff = time.time() - keep_days * 86_400
    for path in (store / TREE).glob("*.json"):
        with contextlib.suppress(OSError):
            if path.stat().st_mtime < cutoff:
                path.unlink()


def forget_open(store: Path, session: str) -> None:
    """SessionEnd: the open request's start snapshot is not needed any more."""
    with contextlib.suppress(OSError):
        tree_path(store, session).unlink()
