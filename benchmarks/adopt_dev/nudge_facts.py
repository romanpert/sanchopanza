"""What one nudge-probe session did with find: its calls (and at which API call), the nudge's
firings, and how many searches came before the first Read of a gold file. Pure parsing of the
evidence folder (transcript, journal, hooks.jsonl); no Docker, no API."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from sanchopanza.harness.find_nudge import EDIT_TOOLS, is_search

FIND_TOOL = "mcp__sanchopanza__find_in_repo"
READ_TOOLS = frozenset({"Read"})


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def tool_calls(transcript: Path) -> list[dict[str, Any]]:
    """Every tool call of the main thread in order, with the 1-based index of the API call
    (distinct assistant message id) that made it."""
    calls: list[dict[str, Any]] = []
    ids: list[str] = []
    for e in _lines(transcript):
        message = e.get("message") or {}
        if e.get("type") != "assistant" or e.get("isSidechain") or not message.get("id"):
            continue
        if message["id"] not in ids:
            ids.append(message["id"])
        for block in message.get("content") or []:
            if isinstance(block, Mapping) and block.get("type") == "tool_use":
                calls.append({"api_call": ids.index(message["id"]) + 1,
                              "name": str(block.get("name")),
                              "input": block.get("input") or {}})  # fmt: skip
    return calls


def _is_gold(path: str, gold: Iterable[str]) -> bool:
    tail = path.replace("\\", "/")
    return any(tail == g or tail.endswith("/" + g) for g in gold)


def before_gold(calls: list[dict[str, Any]], gold: list[str]) -> dict[str, Any]:
    """Searches and find calls before the first Read of a gold file (None: never read)."""
    searches = finds = 0
    for n, call in enumerate(calls, start=1):
        name, args = call["name"], call["input"]
        if name in READ_TOOLS and _is_gold(str(args.get("file_path", "")), gold):
            return {"searches": searches, "finds": finds, "read_at_call": n}
        searches += is_search(name, args)
        finds += name == FIND_TOOL
    return {"searches": None, "finds": None, "read_at_call": None}


def firings(evidence: Path) -> dict[str, Any]:
    journal = [e["data"] for e in _lines(evidence / "journal.jsonl")
               if e.get("kind") == "find_nudge"]  # fmt: skip
    hooks = [e for e in _lines(evidence / "hooks.jsonl") if e.get("sub") == "find-hook"]
    return {"journal": journal,
            "hook_events": len(hooks),
            "hook_outputs": sum(1 for e in hooks if e.get("out_chars")),
            "hook_seconds": round(sum(float(e.get("seconds") or 0) for e in hooks), 2)}  # fmt: skip


def describe(evidence: Path, gold: list[str]) -> dict[str, Any]:
    calls = tool_calls(evidence / "transcript.jsonl")
    finds = [{"api_call": c["api_call"], "call": n, "query": c["input"].get("query"),
              "kind": c["input"].get("kind", "code")}
             for n, c in enumerate(calls, start=1) if c["name"] == FIND_TOOL]  # fmt: skip
    edit = next((n for n, c in enumerate(calls, start=1) if c["name"] in EDIT_TOOLS), None)
    return {"tool_calls": len(calls), "find_calls": finds, "first_edit_call": edit,
            "searches_before_edit": sum(is_search(c["name"], c["input"])
                                        for c in calls[: (edit or len(calls) + 1) - 1]),
            "before_gold_read": before_gold(calls, gold), "nudge": firings(evidence),
            "gold": gold}  # fmt: skip
