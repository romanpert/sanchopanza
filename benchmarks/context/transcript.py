"""A Claude Code session split at its compactions, for the context bench only.

`sanchopanza.context.transcript` reads a session as the model sees it now: everything before
the last `compact_boundary` is gone. The bench needs every context of the session (a cut that
reached across a compaction would label results the model could no longer see), so this file
splits at the boundaries and hands each stretch to the package's own `merge_consecutive`. It
also normalizes blocks for storage: thinking is dropped, a tool_result's content becomes text
(`text_of`), so a screenshot is `[image]` and not a million characters.

Entries kept follow the package: main-thread `user` and `assistant` turns, no sidechains, no
meta entries, no API-error placeholders.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sanchopanza.context.transcript import merge_consecutive, text_of


def _block(raw: Mapping[str, Any]) -> dict[str, Any] | None:
    kind = raw.get("type")
    if kind == "text":
        return {"type": "text", "text": str(raw.get("text", ""))}
    if kind == "tool_use":
        return {
            "type": "tool_use",
            "id": str(raw.get("id", "")),
            "name": str(raw.get("name", "")),
            "input": dict(raw.get("input") or {}),
        }
    if kind == "tool_result":
        return {
            "type": "tool_result",
            "tool_use_id": str(raw.get("tool_use_id", "")),
            "content": text_of(raw.get("content")),
            "is_error": bool(raw.get("is_error", False)),
        }
    if kind == "image":
        return {"type": "text", "text": "[image]"}
    return None  # thinking, redacted_thinking, anything new


def normalized(message: Mapping[str, Any]) -> dict[str, Any]:
    content = message.get("content")
    if isinstance(content, str):
        blocks = [{"type": "text", "text": content}] if content else []
    else:
        raw = content if isinstance(content, list) else []
        blocks = [b for r in raw if isinstance(r, Mapping) if (b := _block(r)) is not None]
    return {"role": message.get("role"), "content": blocks}


def _conversational(entry: Mapping[str, Any]) -> bool:
    if entry.get("type") not in ("user", "assistant"):
        return False
    if entry.get("isSidechain") or entry.get("isMeta") or entry.get("isApiErrorMessage"):
        return False
    message = entry.get("message")
    return isinstance(message, Mapping) and message.get("role") in ("user", "assistant")


def is_boundary(entry: Mapping[str, Any]) -> bool:
    return entry.get("type") == "system" and entry.get("subtype") == "compact_boundary"


def segments(path: Path | str) -> list[list[dict[str, Any]]]:
    """One message list per context of the session, oldest first."""
    parts: list[list[dict[str, Any]]] = [[]]
    with Path(path).open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, Mapping):
                continue
            if is_boundary(entry):
                parts.append([])
            elif _conversational(entry) and not entry.get("isCompactSummary"):
                parts[-1].append(normalized(entry["message"]))
    return [m for part in parts if (m := merge_consecutive(part))]
