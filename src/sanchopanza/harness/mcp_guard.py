"""The MCP guard's record: what the `actions` point reads before an MCP tool call runs (A3).

The installed hook judged shell commands, delegations and searches, and let every MCP call
(`mcp__<server>__<tool>`) through with no decision: on ATBench-Codex, whose risks live in MCP
calls (payments, repositories, CRMs, databases), it flagged 0 of 250 unsafe trajectories
(docs/results/2026-09-28-claude-code-broad). `points.actions`, reading whole trajectories
offline with jev-1.13.0 at 0.5, flagged 213 of 250 unsafe ones (recall 85.2 %) and 73 of 250
safe ones (29.2 %). Here it reads what a PreToolUse hook can know: the session so far, from
Claude Code's transcript, and the pending call last.

The record uses the point's own labels (`USER`, `AGENT THOUGHT`, `AGENT ACTION`, `ENVIRONMENT`,
as `actions.render_record` writes them) so the question reads the same shape it was measured
on. Every request of the session is kept, not only the last: "yes, go ahead" means nothing
without what it answers. Each line is masked whole (`redact.mask_strict`: a token cut in two is
no longer a token), then cut: a tool result to its head, any line to LINE_CHARS (head and
tail), the pending call to PENDING_CHARS. A record over `limit` keeps the first request, the
most recent one and the most recent lines that fit, so one huge line (a 30,000-character Write)
cannot push the recent context out, and the pending call always reaches the decider.

The transcript is read from its head (up to the first request) and its last TAIL_FACTOR x
`limit` bytes: a long session's file is not parsed whole on every MCP call.

Which calls are judged (`HarnessConfig.guards_mcp`): every `mcp__` tool except our own servers
(`own_servers`) and those named in `SANCHOPANZA_GUARD_MCP_SKIP`. With the `jev` provider the
record leaves the machine, tool results included, masked as above. Its size,
`SANCHOPANZA_GUARD_MCP_CHARS` (at most `actions.RECORD_LIMIT`), is also its price: about 520
tokens plus one per three characters (fit on ATBench-Codex, docs/results/2026-10-16-a3-mcp/).
Light imports only: the hook imports this before it knows whether it has anything to decide.

After the call (W17, `SANCHOPANZA_GUARD_MCP_POST`): `record_after_result` renders the same
record with the call that ran and its result last (`ENVIRONMENT`, masked whole, then cut to
PENDING_CHARS), the shape of the offline reference's records, which end on the last tool result.
"""

from __future__ import annotations

import functools
import json
import os
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from ..redact import mask_strict

PREFIX = "mcp__"
RECORD_CHARS = 24_000  # `actions.RECORD_LIMIT`: what the point was measured with, and its cut
RESULT_CHARS = 1_500  # a tool result's head, as `claude_code.TOOL_RESULT_LIMIT`
LINE_CHARS = 2_000  # any line of the record, head and tail kept
PENDING_CHARS = 8_000  # the pending call, head and tail kept
TAIL_FACTOR = 16  # bytes of the transcript's end read per character of record
HEAD_LINES = 200  # lines read from the start looking for the first request
GAP = "[...]"

OnError = Callable[[str], None]


@functools.cache
def own_servers() -> frozenset[str]:
    """Our MCP servers, as `install` names them: reads of this project or of pages, never an
    action on the world. Imported only when an MCP call is about to be judged."""
    from .install import ARCHIVE_SERVER
    from .install_defaults import FETCH_SERVER, FIND_SERVER
    from .install_knowledge import KNOWLEDGE_SERVER

    return frozenset({FIND_SERVER, FETCH_SERVER, KNOWLEDGE_SERVER, ARCHIVE_SERVER})


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


def cap(text: str, limit: int) -> str:
    """`text` within `limit` characters: its head and its tail around a gap."""
    if len(text) <= limit:
        return text
    tail = limit // 4
    head = limit - tail - len(GAP) - 2
    return f"{text[:head]} {GAP} {text[-tail:]}" if tail > 0 else text[:limit]


def action_line(name: str, arguments: Mapping[str, Any] | None) -> str:
    """The pending call as the point reads an action, masked whole."""
    body = json.dumps(dict(arguments or {}), ensure_ascii=False, sort_keys=True, default=str)
    return f"AGENT ACTION: {name}({mask_strict(body)})"


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


def _content(entry: Mapping[str, Any]) -> Any:
    message = entry.get("message")
    return message.get("content") if isinstance(message, Mapping) else None


def _user_lines(entry: Mapping[str, Any], content: Any, skip_id: str = "") -> list[str]:
    if _is_request(entry, content):
        return [f"USER: {mask_strict(_text(content).strip())}"]
    if not isinstance(content, list):
        return []
    return [
        f"ENVIRONMENT: {mask_strict(_text(b.get('content')))[:RESULT_CHARS]}"
        for b in content
        if isinstance(b, Mapping)
        and b.get("type") == "tool_result"
        and not (skip_id and b.get("tool_use_id") == skip_id)
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
            out.append((f"AGENT THOUGHT: {mask_strict(str(b['text']).strip())}", ""))
        elif b.get("type") == "tool_use":
            arguments = b.get("input") if isinstance(b.get("input"), Mapping) else {}
            out.append((action_line(str(b.get("name") or ""), arguments), str(b.get("id") or "")))
    return out


def is_request(entry: Mapping[str, Any]) -> bool:
    return entry.get("type") == "user" and _is_request(entry, _content(entry))


def lines_of(entries: Iterable[Mapping[str, Any]], *, skip_id: str = "") -> list[str]:
    """The record's lines from transcript entries, in order, each masked whole and capped at
    LINE_CHARS. A tool use with id `skip_id` (the pending call, already in the transcript) is
    left out, and so is a result for it (after the call, should the transcript hold it already):
    they go last, once."""
    lines: list[str] = []
    for entry in entries:
        content = _content(entry)
        if entry.get("type") == "user":
            lines.extend(_user_lines(entry, content, skip_id))
        elif entry.get("type") == "assistant":
            lines.extend(line for line, tid in _assistant_lines(content)
                         if not (skip_id and tid == skip_id))  # fmt: skip
    return [cap(x, LINE_CHARS) for x in lines]


def _keep(lines: list[str], fixed: set[int], room: int) -> set[int]:
    """`fixed`, then the most recent lines that fit in `room` (one that does not is skipped,
    and older ones are still tried). Each line is costed with a possible gap before it."""
    kept = set(fixed)
    room -= sum(len(lines[i]) + len(GAP) + 2 for i in fixed)
    for i in range(len(lines) - 1, -1, -1):
        if i in kept:
            continue
        cost = len(lines[i]) + len(GAP) + 2
        if cost <= room:
            kept.add(i)
            room -= cost
    return kept


def fit(lines: list[str], pending: str, limit: int = RECORD_CHARS) -> str:
    """`lines` then `pending`, within `limit` characters: when they do not fit, the first and
    the most recent request, and the most recent lines that do, gaps marked."""
    pending = cap(pending, min(PENDING_CHARS, max(limit // 2, 1)))
    if lines and lines[-1] == pending:
        lines = lines[:-1]  # the transcript already ends on the pending call
    whole = "\n".join([*lines, pending])
    if len(whole) <= limit:
        return whole
    requests = [i for i, x in enumerate(lines) if x.startswith("USER: ")]
    fixed = {requests[0], requests[-1]} if requests else set()
    kept = sorted(_keep(lines, fixed, limit - len(pending) - 1))
    out: list[str] = []
    for n, i in enumerate(kept):
        if (n == 0 and i > 0) or (n > 0 and i != kept[n - 1] + 1):
            out.append(GAP)
        out.append(lines[i])
    if kept and kept[-1] != len(lines) - 1:
        out.append(GAP)
    return "\n".join([*out, pending])


def _parse(line: str) -> Mapping[str, Any] | None:
    try:
        entry = json.loads(line)
    except ValueError:
        return None
    return entry if isinstance(entry, Mapping) else None


def _entries(path: Path, limit: int) -> list[Mapping[str, Any]]:
    """The head up to the first request, then the last TAIL_FACTOR x `limit` bytes."""
    tail_bytes = TAIL_FACTOR * limit
    with path.open("rb") as handle:
        size = os.fstat(handle.fileno()).st_size
        if size <= tail_bytes:
            raw = handle.read().decode("utf-8", "replace").splitlines()
            return [e for e in map(_parse, raw) if e is not None]
        head: list[Mapping[str, Any]] = []
        for _ in range(HEAD_LINES):
            line = handle.readline()
            if not line or handle.tell() > size - tail_bytes:
                break
            entry = _parse(line.decode("utf-8", "replace"))
            if entry is not None and is_request(entry):
                head.append(entry)
                break
        handle.seek(size - tail_bytes)
        raw = handle.read().decode("utf-8", "replace").splitlines()[1:]  # the first is partial
    return [*head, *(e for e in map(_parse, raw) if e is not None)]


def record_from_transcript(
    path: Path | str | None,
    name: str,
    arguments: Mapping[str, Any] | None,
    *,
    tool_use_id: str = "",
    limit: int = RECORD_CHARS,
    on_error: OnError | None = None,
) -> str:
    """The session so far and the pending call, for the `actions` point. No transcript leaves
    the call to be judged alone; one that cannot be read too, and `on_error` is told why."""
    pending = action_line(name, arguments)
    entries: list[Mapping[str, Any]] = []
    if path:
        try:
            entries = _entries(Path(path), limit)
        except OSError as error:
            if on_error is not None:
                on_error(f"transcript unreadable: {error.__class__.__name__}")
    return fit(lines_of(entries, skip_id=tool_use_id), pending, limit)


def with_pending(record: str, name: str, arguments: Mapping[str, Any] | None,
                 limit: int = RECORD_CHARS) -> str:  # fmt: skip
    """A record already built (or none) with the pending call last, within `limit`."""
    lines = [cap(x, LINE_CHARS) for x in record.splitlines()] if record else []
    return fit(lines, action_line(name, arguments), limit)


# --- after the call (W17) ------------------------------------------------------------------------
# What the check after an MCP call reads: the session so far, the call that ran, and its result
# last, in the point's own label. That is the shape of the offline reference's records, which end
# on the last tool result (benchmarks/a3_mcp/w17_ceiling.py). The result arrives in the hook's
# input, not yet in the transcript; it is masked whole, then cut to PENDING_CHARS, head and tail.


def result_line(text: str) -> str:
    """A tool result as the point reads it, masked whole (not cut: `fit` cuts it)."""
    return f"ENVIRONMENT: {mask_strict(text)}"


def record_after_result(
    path: Path | str | None,
    name: str,
    arguments: Mapping[str, Any] | None,
    result: str,
    *,
    tool_use_id: str = "",
    limit: int = RECORD_CHARS,
    on_error: OnError | None = None,
) -> str:
    """The session so far, the call that ran and its result last, for the `actions` point."""
    entries: list[Mapping[str, Any]] = []
    if path:
        try:
            entries = _entries(Path(path), limit)
        except OSError as error:
            if on_error is not None:
                on_error(f"transcript unreadable: {error.__class__.__name__}")
    lines = lines_of(entries, skip_id=tool_use_id)
    return fit([*lines, cap(action_line(name, arguments), LINE_CHARS)], result_line(result), limit)


def with_result(record: str, name: str, arguments: Mapping[str, Any] | None, result: str,
                limit: int = RECORD_CHARS) -> str:  # fmt: skip
    """A record already built after the call (or none): kept when it ends on this result, else
    the call and its result are added last; within `limit`."""
    last = cap(result_line(result), min(PENDING_CHARS, max(limit // 2, 1)))
    ends = bool(record) and record.endswith(last)  # a result can hold newlines: not by line
    head = record[: len(record) - len(last)].rstrip("\n") if ends else record
    lines = [cap(x, LINE_CHARS) for x in head.splitlines()] if head else []
    if ends:
        return fit(lines, last, limit)
    return fit([*lines, cap(action_line(name, arguments), LINE_CHARS)], last, limit)
