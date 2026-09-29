"""A conversation as Messages-API messages, and the tool calls inside it.

Two inputs reach the pruner. A Claude Code transcript (`~/.claude/projects/<p>/<session>.jsonl`)
is read by `messages_from_claude_code`; a harness that already holds Messages-API messages
passes them as they are. Both end up as a list of `{"role", "content": [blocks]}` dicts, the
shape every other function in this package reads.

Claude Code writes one JSONL entry per content block: an assistant turn with three tool calls
is three `assistant` entries sharing one `message.id`, and their three results are three `user`
entries. The Messages API wants them as one assistant message and one user message, so
consecutive entries of the same role are merged. Entries that are not conversation (summaries,
file snapshots, system notices, meta entries) and subagent sidechains are left out, and a
`compact_boundary` starts the conversation again, because that is what the model saw after it.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

Message = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Call:
    """One tool call with its result: the unit the pruner keeps, stubs or asks about.

    `use_msg` and `result_msg` are indexes into the message list the call was read from.
    A tool_use with no tool_result yet (a call in flight) is not a `Call`: there is nothing
    to prune.
    """

    id: str
    tool: str
    input: Mapping[str, Any] = field(default_factory=dict)
    result: str = ""
    is_error: bool = False
    use_msg: int = 0
    result_msg: int = 0

    @property
    def chars(self) -> int:
        return len(self.result)


def blocks_of(message: Mapping[str, Any]) -> list[Any]:
    """The content of a message as a list of blocks; a bare string is one text block."""
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    return list(content) if isinstance(content, list) else []


def text_of(content: Any) -> str:
    """The text a tool_result carries: a string, or its text blocks joined.

    Non-text blocks (an image a Read returned) count as a short marker, so a result made of
    an image is not mistaken for an empty one.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if not isinstance(block, Mapping):
            continue
        if block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
        else:
            parts.append(f"[{block.get('type', 'block')}]")
    return "\n".join(parts)


def message_text(message: Mapping[str, Any]) -> str:
    """The text blocks of a message joined; tool blocks and thinking are not text."""
    return "\n".join(
        str(b.get("text") or "")
        for b in blocks_of(message)
        if isinstance(b, Mapping) and b.get("type") == "text"
    ).strip()


def is_prompt(message: Mapping[str, Any]) -> bool:
    """A user message the person wrote: it has text and carries no tool result."""
    if message.get("role") != "user":
        return False
    blocks = blocks_of(message)
    has_result = any(isinstance(b, Mapping) and b.get("type") == "tool_result" for b in blocks)
    return not has_result and bool(message_text(message))


def _entries(path: Path) -> list[Mapping[str, Any]]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # a line cut by a crash is not a reason to lose the session
        if isinstance(entry, Mapping):
            out.append(entry)
    return out


def _is_boundary(entry: Mapping[str, Any]) -> bool:
    return entry.get("type") == "system" and entry.get("subtype") == "compact_boundary"


def _conversational(entry: Mapping[str, Any]) -> bool:
    if entry.get("type") not in ("user", "assistant"):
        return False
    if entry.get("isSidechain") or entry.get("isMeta"):
        return False
    message = entry.get("message")
    return isinstance(message, Mapping) and message.get("role") in ("user", "assistant")


def merge_consecutive(messages: Iterable[Mapping[str, Any]]) -> list[Message]:
    """One message per run of the same role, blocks in order. New dicts; inputs untouched."""
    out: list[Message] = []
    for message in messages:
        role, blocks = message.get("role"), blocks_of(message)
        if out and out[-1]["role"] == role:
            out[-1] = {**out[-1], "content": [*out[-1]["content"], *blocks]}
        else:
            out.append({"role": role, "content": blocks})
    return [m for m in out if m["content"]]


def messages_from_claude_code(path: Path | str) -> list[Message]:
    """A Claude Code JSONL transcript as Messages-API messages, oldest first."""
    kept: list[Mapping[str, Any]] = []
    for entry in _entries(Path(path)):
        if _is_boundary(entry):
            kept = []  # what came before was replaced by the summary that follows
        elif _conversational(entry):
            kept.append(entry["message"])
    return merge_consecutive(kept)


def history_from_claude_code(path: Path | str) -> tuple[list[Message], int]:
    """The whole session, compactions included, and where the last compaction falls.

    Every conversational entry in file order, the summaries a compaction wrote left out (they
    are not the conversation, they replace it). The second value is the index of the first
    message after the last `compact_boundary` (0 when there was none): what came before it is
    what the model no longer sees verbatim. Used by the compaction guard
    (`context.guard`), which needs what the summary replaced.
    """
    before: list[Mapping[str, Any]] = []
    after: list[Mapping[str, Any]] = []
    for entry in _entries(Path(path)):
        if _is_boundary(entry):
            before, after = [*before, *after], []
        elif _conversational(entry) and not entry.get("isCompactSummary"):
            after.append(entry["message"])
    merged_before = merge_consecutive(before)
    return [*merged_before, *merge_consecutive(after)], len(merged_before)


def last_compact_summary(path: Path | str) -> str:
    """The text of the summary the latest compaction wrote, or "" when there was none."""
    found = ""
    for entry in _entries(Path(path)):
        if entry.get("isCompactSummary") and isinstance(entry.get("message"), Mapping):
            found = message_text(entry["message"])
    return found


def calls(messages: Sequence[Mapping[str, Any]]) -> list[Call]:
    """Every tool_use paired with its tool_result by id, in the order the calls were made."""
    results: dict[str, tuple[int, Mapping[str, Any]]] = {}
    for index, message in enumerate(messages):
        for block in blocks_of(message):
            if isinstance(block, Mapping) and block.get("type") == "tool_result":
                results[str(block.get("tool_use_id"))] = (index, block)
    out: list[Call] = []
    for index, message in enumerate(messages):
        for block in blocks_of(message):
            if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                continue
            found = results.get(str(block.get("id")))
            if found is None:
                continue
            where, result = found
            arguments = block.get("input")
            out.append(
                Call(
                    id=str(block.get("id")),
                    tool=str(block.get("name") or ""),
                    input=dict(arguments) if isinstance(arguments, Mapping) else {},
                    result=text_of(result.get("content")),
                    is_error=bool(result.get("is_error")),
                    use_msg=index,
                    result_msg=where,
                )
            )
    return out


def task_of(messages: Sequence[Mapping[str, Any]]) -> str:
    """The first real prompt and the latest one: what the work is, and where it is now."""
    prompts = [message_text(m) for m in messages if is_prompt(m)]
    if not prompts:
        return ""
    if len(prompts) == 1:
        return prompts[0]
    return f"First request: {prompts[0]}\n\nLatest request: {prompts[-1]}"


def chars(messages: Sequence[Mapping[str, Any]]) -> int:
    """Characters of text, tool input and tool output: what compaction is measured in."""
    total = 0
    for message in messages:
        for block in blocks_of(message):
            if not isinstance(block, Mapping):
                continue
            kind = block.get("type")
            if kind == "text":
                total += len(str(block.get("text") or ""))
            elif kind == "tool_use":
                total += len(json.dumps(block.get("input"), ensure_ascii=False, default=str))
            elif kind == "tool_result":
                total += len(text_of(block.get("content")))
    return total
