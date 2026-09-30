"""Labels by code for memory between sessions: which earlier request a new request builds on.

An edit's `old_string` carries unchanged context lines, so only lines that really go count as
removed, and only lines that really appear count as written. Short lines (`}`, `return None`)
are in every file and would join unrelated requests: a line counts at MIN_LINE characters.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sanchopanza.context.transcript import blocks_of

MIN_LINE = 16


@dataclass(frozen=True)
class Edit:
    path: str
    removed: frozenset[str]
    added: frozenset[str]


def _lines(text: Any) -> set[str]:
    if not isinstance(text, str):
        return set()
    out = set()
    for raw in text.split("\n"):
        line = " ".join(raw.split())
        if len(line) >= MIN_LINE and any(c.isalnum() for c in line):
            out.add(line)
    return out


def _relative(path: str, cwd: str) -> str:
    clean = path.replace("\\", "/")
    base = cwd.replace("\\", "/").rstrip("/") + "/"
    return clean[len(base):] if cwd and clean.lower().startswith(base.lower()) else clean


def _pairs(name: str, data: Mapping[str, Any]) -> list[tuple[str, str]]:
    if name == "Edit":
        return [(data.get("old_string", ""), data.get("new_string", ""))]
    if name == "MultiEdit":
        return [(e.get("old_string", ""), e.get("new_string", ""))
                for e in data.get("edits") or [] if isinstance(e, Mapping)]  # fmt: skip
    if name == "Write":
        return [("", data.get("content", ""))]
    return []


def edits_of(messages: Iterable[Mapping[str, Any]], cwd: str) -> list[Edit]:
    """Every Edit, MultiEdit and Write the agent asked for in these messages."""
    out = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for block in blocks_of(message):
            if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                continue
            data = block.get("input") or {}
            path = data.get("file_path")
            if not isinstance(path, str):
                continue
            for old, new in _pairs(str(block.get("name")), data):
                before, after = _lines(old), _lines(new)
                out.append(Edit(_relative(path, cwd), frozenset(before - after),
                                frozenset(after - before)))  # fmt: skip
    return out


TOUCHING = ("Read", "Edit", "MultiEdit", "Write", "NotebookEdit")


def touched_of(messages: Iterable[Mapping[str, Any]], cwd: str) -> list[list[str]]:
    """[tool, path] of every call that opens or changes a file, in the order they were made."""
    out = []
    for message in messages:
        if message.get("role") != "assistant":
            continue
        for block in blocks_of(message):
            if (isinstance(block, Mapping) and block.get("type") == "tool_use"
                    and block.get("name") in TOUCHING):  # fmt: skip
                path = (block.get("input") or {}).get("file_path") or (
                    block.get("input") or {}).get("notebook_path")
                if isinstance(path, str):
                    out.append([str(block["name"]), _relative(path, cwd)])
    return out


def written_lines(edits: Sequence[Edit]) -> set[str]:
    return {line for e in edits for line in e.added}


def lineage(removed: Iterable[str], written: Iterable[str]) -> bool:
    """The new request takes out or rewrites a line the earlier request wrote."""
    return bool(set(removed) & set(written))
