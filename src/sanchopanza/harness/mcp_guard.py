"""The MCP guard's record: what the `actions` point reads before an MCP tool call runs (A3).

The installed hook judged shell commands, delegations and searches, and let every MCP call
(`mcp__<server>__<tool>`) through with no decision: on ATBench-Codex, whose risks live in MCP
calls (payments, repositories, CRMs, databases), it flagged 0 of 250 unsafe trajectories
(docs/results/2026-09-28-claude-code-broad). `points.actions` judged the same set at 78 %
offline, reading the whole trajectory. Here it reads what a PreToolUse hook can know: the
session so far, from Claude Code's transcript, and the pending call last.

The record uses the point's own labels (`USER`, `AGENT THOUGHT`, `AGENT ACTION`, `ENVIRONMENT`,
as `actions.render_record` writes them) so the question reads the same shape it was measured
on. Every request of the session is kept, not only the last: "yes, go ahead" means nothing
without what it answers. A record over `limit` keeps the first request and the most recent
lines, so the pending call always reaches the decider (`text.truncate` would cut it off).

Which calls are judged (`HarnessConfig.guards_mcp`): every `mcp__` tool except our own servers
and those named in `SANCHOPANZA_GUARD_MCP_SKIP`. With the `jev` provider the record leaves the
machine, tool results included; `Guardian._before_mcp` masks secret-looking strings first
(`redact.mask`). Its size, `SANCHOPANZA_GUARD_MCP_CHARS`, is also its price: about 520 tokens
plus one per three characters (fit on ATBench-Codex, docs/results/2026-10-16-a3-mcp/dry.json).
Standard library only: the hook imports this before it knows whether it has anything to decide.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

PREFIX = "mcp__"
# Our own MCP servers (`install_defaults`, `install_hooks`, `install`): reads of this project or
# of pages, never an action on the world. Compared after `server_key`.
OWN_SERVERS = frozenset(
    {"sanchopanza", "sanchopanza-fetch", "sanchopanza-knowledge", "sanchopanza-archive"}
)
RECORD_CHARS = 24_000  # `actions.RECORD_LIMIT`: what the point was measured with
RESULT_CHARS = 1_500  # a tool result's head, as `claude_code.TOOL_RESULT_LIMIT`
HEAD_CHARS = 2_000  # the first request, kept when the record is cut
GAP = "[...]"


def server_key(name: str) -> str:
    """A server name compared without case or punctuation (`sanchopanza-fetch` and
    `sanchopanza_fetch` are one)."""
    return "".join(c if c.isalnum() else "_" for c in name.strip().lower())


def server_of(name: str) -> str | None:
    """The server of an MCP tool name, or None when `name` is not `mcp__<server>__<tool>`."""
    if not name.startswith(PREFIX):
        return None
    server, sep, tool = name[len(PREFIX) :].partition("__")
    return server if server and sep and tool else None


def action_line(name: str, arguments: Mapping[str, Any] | None) -> str:
    """The pending call as the point reads an action."""
    body = json.dumps(dict(arguments or {}), ensure_ascii=False, sort_keys=True, default=str)
    return f"AGENT ACTION: {name}({body})"


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(b.get("text") or b.get("content") or "") if isinstance(b, Mapping) else str(b)
            for b in content
            if not isinstance(b, Mapping) or b.get("type") in ("text", None)
        )
    return ""


def _is_request(entry: Mapping[str, Any], content: Any) -> bool:
    if entry.get("isMeta") or entry.get("isCompactSummary"):
        return False
    if isinstance(content, str):
        return bool(content.strip())
    if not isinstance(content, list):
        return False
    if any(isinstance(b, Mapping) and b.get("type") == "tool_result" for b in content):
        return False
    return bool(_text(content).strip())


def _user_lines(entry: Mapping[str, Any], content: Any, result_chars: int) -> list[str]:
    if _is_request(entry, content):
        return [f"USER: {_text(content).strip()}"]
    if not isinstance(content, list):
        return []
    return [
        f"ENVIRONMENT: {_text(b.get('content'))[:result_chars]}"
        for b in content
        if isinstance(b, Mapping) and b.get("type") == "tool_result"
    ]


def _assistant_lines(content: Any) -> list[tuple[str, str]]:
    """(line, tool_use id or "") per block."""
    if not isinstance(content, list):
        return []
    out: list[tuple[str, str]] = []
    for b in content:
        if not isinstance(b, Mapping):
            continue
        if b.get("type") == "text" and str(b.get("text") or "").strip():
            out.append((f"AGENT THOUGHT: {str(b['text']).strip()}", ""))
        elif b.get("type") == "tool_use":
            arguments = b.get("input") if isinstance(b.get("input"), Mapping) else {}
            out.append((action_line(str(b.get("name") or ""), arguments), str(b.get("id") or "")))
    return out


def lines_of(entries: Iterable[Mapping[str, Any]], *, result_chars: int = RESULT_CHARS,
             skip_id: str = "") -> list[str]:  # fmt: skip
    """The record's lines from transcript entries, in order. A tool use with id `skip_id` (the
    pending call, already written to the transcript) is left out: it goes last, once."""
    lines: list[str] = []
    for entry in entries:
        content = (entry.get("message") or {}).get("content")
        if entry.get("type") == "user":
            lines.extend(_user_lines(entry, content, result_chars))
        elif entry.get("type") == "assistant":
            lines.extend(line for line, tid in _assistant_lines(content)
                         if not (skip_id and tid == skip_id))  # fmt: skip
    return lines


def fit(lines: list[str], pending: str, limit: int = RECORD_CHARS) -> str:
    """`lines` then `pending`, within `limit` characters: when they do not fit, the first
    request (at most HEAD_CHARS) and the most recent lines that do, with a gap between."""
    if lines and lines[-1] == pending:
        lines = lines[:-1]  # the transcript already ends on the pending call
    whole = "\n".join([*lines, pending])
    if len(whole) <= limit:
        return whole
    if len(pending) + len(GAP) + 1 >= limit:
        return pending[:limit]  # the call alone, its name and first arguments
    first = next((i for i, x in enumerate(lines) if x.startswith("USER: ")), None)
    head = lines[first][:HEAD_CHARS] if first is not None else ""
    room = limit - len(pending) - len(head) - len(GAP) - 3
    rest = lines[first + 1 :] if first is not None else lines
    tail: list[str] = []
    for line in reversed(rest):
        if len(line) + 1 > room:
            break
        tail.insert(0, line)
        room -= len(line) + 1
    return "\n".join(x for x in (head, GAP, *tail, pending) if x)


def _entries(path: Path) -> list[Mapping[str, Any]]:
    out: list[Mapping[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, Mapping):
            out.append(entry)
    return out


def record_from_transcript(
    path: Path | str | None,
    name: str,
    arguments: Mapping[str, Any] | None,
    *,
    tool_use_id: str = "",
    limit: int = RECORD_CHARS,
) -> str:
    """The session so far and the pending call, for the `actions` point. A transcript that is
    missing or unreadable leaves the call to be judged alone."""
    pending = action_line(name, arguments)
    try:
        entries = _entries(Path(path)) if path else []
    except OSError:
        entries = []
    return fit(lines_of(entries, skip_id=tool_use_id), pending, limit)


def with_pending(record: str, name: str, arguments: Mapping[str, Any] | None,
                 limit: int = RECORD_CHARS) -> str:  # fmt: skip
    """A record already built (or none) with the pending call last, within `limit`."""
    return fit(record.splitlines() if record else [], action_line(name, arguments), limit)
