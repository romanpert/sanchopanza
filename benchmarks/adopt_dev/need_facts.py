"""What one need-probe session did with find: whether find was visible, its calls (and at which
tool call and API call), ToolSearch calls, searches before the first Read of a gold file (the
need table's measure, `find_need.replay.reach`), the Agent calls and their failures, and the
evidence that the treatment ran (the decider the hooks built, the server at init, Jev's
decisions). Pure parsing of the evidence folder; no Docker, no API."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from benchmarks.find_need.replay import reach, result_text, stream_calls

FIND_TOOL = "mcp__sanchopanza__find_in_repo"
AGENT_TOOLS = frozenset({"Agent", "Task"})
ERROR_CHARS = 300


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def init_line(stream: Path) -> dict[str, Any] | None:
    return next((e for e in _lines(stream)
                 if e.get("type") == "system" and e.get("subtype") == "init"), None)  # fmt: skip


def find_hidden(evidence: Path) -> str:
    """Why find_in_repo was not visible to the session, or "" when it was: phase D's test (g),
    `run_d.find_hidden`, on the same files: in the init line's tools, the transcript copied, named
    by no `deferred_tools_delta` attachment, and mcp.json registering its server alwaysLoad."""
    init = init_line(evidence / "stream-1.jsonl")
    if init is None:
        return "no init line"
    if FIND_TOOL not in (init.get("tools") or []):
        return "not in the init line's tools"
    transcript = evidence / "transcript.jsonl"
    if not transcript.exists():
        return "transcript not copied"
    for entry in _lines(transcript):
        attachment = entry.get("attachment")
        if (isinstance(attachment, dict) and attachment.get("type") == "deferred_tools_delta"
                and FIND_TOOL in json.dumps(attachment)):  # fmt: skip
            return "deferred: a deferred_tools_delta names it"
    mcp = evidence / "mcp.json"
    if not mcp.exists():
        return "no copied mcp.json"
    server = (json.loads(mcp.read_text(encoding="utf-8")).get("mcpServers") or {}).get(
        "sanchopanza") or {}  # fmt: skip
    if server.get("alwaysLoad") is not True:
        return "its server has no alwaysLoad in mcp.json"
    return ""


def api_call_of_each(stream: Path) -> list[int]:
    """The 1-based API call (distinct main-thread assistant message id) of each main-thread tool
    use, in the order and with the deduplication of `replay.stream_calls`."""
    ids: list[str] = []
    seen: set[str] = set()
    out: list[int] = []
    for e in _lines(stream):
        message = e.get("message") or {}
        if e.get("type") != "assistant" or e.get("parent_tool_use_id"):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        mid = str(message.get("id") or "")
        if mid not in ids:
            ids.append(mid)
        for block in content:
            if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                continue
            if block.get("id") not in seen:
                seen.add(str(block.get("id")))
                out.append(ids.index(mid) + 1)
    return out


def treatment(evidence: Path, record: Mapping[str, Any]) -> dict[str, Any]:
    """That the S arm ran as installed: the decider its hooks build (probed before the session),
    the server's status at init, the server's start and the hooks' key in hooks.jsonl, and Jev's
    decisions in the journal (by provider, with errors)."""
    init = init_line(evidence / "stream-1.jsonl") or {}
    servers = {s.get("name"): s.get("status") for s in init.get("mcp_servers") or []}
    hooks = _lines(evidence / "hooks.jsonl")
    decisions = [e.get("data") or {} for e in _lines(evidence / "journal.jsonl")
                 if e.get("kind") == "decision"]  # fmt: skip
    return {
        "decider": list(record.get("decider") or []),
        "server_at_init": servers.get("sanchopanza"),
        "server_started": any(
            e.get("sub") == "find-mcp" and e.get("event") == "server start" for e in hooks
        ),  # fmt: skip
        "hook_lines": len(hooks),
        "hooks_without_key": sum(1 for e in hooks if e.get("key") is False),
        "find_hook_lines": sum(1 for e in hooks if e.get("sub") == "find-hook"),
        "decisions_by_provider": dict(Counter(str(d.get("provider")) for d in decisions)),
        "decision_errors": sum(1 for d in decisions if d.get("error")),
    }


def describe(evidence: Path, gold: list[str], record: Mapping[str, Any]) -> dict[str, Any]:
    stream = evidence / "stream-1.jsonl"
    _meta, calls = stream_calls(stream)
    api = api_call_of_each(stream)
    at = lambda i: api[i] if i < len(api) else None  # noqa: E731
    finds = [{"call": i + 1, "api_call": at(i), "query": c.input.get("query"),
              "kind": c.input.get("kind", "code"), "error": c.error}
             for i, c in enumerate(calls) if c.name == FIND_TOOL]  # fmt: skip
    searches = [{"call": i + 1, "api_call": at(i), "query": c.input.get("query")}
                for i, c in enumerate(calls) if c.name == "ToolSearch"]  # fmt: skip
    agents = [{"call": i + 1, "api_call": at(i),
               "subagent_type": c.input.get("subagent_type"), "error": c.error,
               "error_text": result_text(c.result)[:ERROR_CHARS] if c.error else ""}
              for i, c in enumerate(calls) if c.name in AGENT_TOOLS]  # fmt: skip
    need = reach(calls, gold)
    hidden = find_hidden(evidence)
    return {
        "gold": gold,
        "find_visible": not hidden,
        "find_hidden": hidden,
        "tool_calls": len(calls),
        "find_calls": finds,
        "toolsearch_calls": searches,
        "agent_calls": agents,
        "agent_failures": sum(1 for a in agents if a["error"]),
        "reach": need,
        "searches_before_gold_read": need["read_searches"],
        "treatment": treatment(evidence, record),
    }
