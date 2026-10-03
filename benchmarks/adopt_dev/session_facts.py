"""What one probe session did, beyond `run.facts`: deferral, the tools the model saw, prompt
caching per API call, start latency and the hooks' time. Pure parsing, no Docker, no API."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

FIND_TOOL = "mcp__sanchopanza__find_in_repo"
WATCHED = ("ToolSearch", FIND_TOOL, "Skill")


class Clock:
    """Arrival times (epoch seconds) of the stream's milestones, as the driver reads its lines."""

    def __init__(self, started: float) -> None:
        self.started = started
        self.marks: dict[str, float] = {}
        self.hooks: list[dict[str, Any]] = []
        self.init: dict[str, Any] = {}

    def see(self, event: dict[str, Any], now: float) -> None:
        kind, sub = event.get("type"), event.get("subtype")
        self.marks.setdefault("first_line", now)
        if kind == "system" and sub == "init":
            self.marks.setdefault("init", now)
            self.init = {"tools": event.get("tools") or [],
                         "mcp_servers": event.get("mcp_servers") or [],
                         "claude_code_version": event.get("claude_code_version")}  # fmt: skip
        elif kind == "system" and sub in ("hook_started", "hook_response"):
            self.hooks.append({"subtype": sub, "event": event.get("hook_event"),
                               "name": event.get("hook_name"),
                               "t": round(now - self.started, 3)})  # fmt: skip
        elif kind == "assistant":
            self.marks.setdefault("first_assistant", now)
        elif kind == "result":
            self.marks.setdefault("result", now)

    def latency(self) -> dict[str, float | None]:
        """Seconds from process start to each milestone (None when it never came)."""
        names = ("first_line", "init", "first_assistant", "result")
        return {f"to_{n}_s": (round(self.marks[n] - self.started, 3) if n in self.marks else None)
                for n in names}  # fmt: skip


def _lines(path: Path) -> list[dict[str, Any]]:
    out = []
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _when(stamp: str | None) -> float | None:
    if not stamp:
        return None
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


def deferral(transcript: Path) -> dict[str, Any]:
    """Every `deferred_tools_delta` attachment's added names, and whether find was among them."""
    deltas = [e["attachment"] for e in _lines(transcript)
              if (e.get("attachment") or {}).get("type") == "deferred_tools_delta"]  # fmt: skip
    first = deltas[0].get("addedNames", []) if deltas else []
    added = sorted({n for d in deltas for n in d.get("addedNames", [])})
    return {"deltas": len(deltas), "first_added": first, "added": added,
            "find_deferred": FIND_TOOL in added}  # fmt: skip


def api_calls(transcript: Path) -> list[dict[str, Any]]:
    """One entry per API response (assistant entries share their message id), in order, with its
    usage as last written, and when the transcript recorded it."""
    calls: dict[str, dict[str, Any]] = {}
    for e in _lines(transcript):
        message = e.get("message") or {}
        if e.get("type") != "assistant" or not message.get("id") or e.get("isSidechain"):
            continue
        usage = message.get("usage") or {}
        calls[message["id"]] = {
            "id": message["id"],
            "t": calls.get(message["id"], {}).get("t") or e.get("timestamp"),
            "input": int(usage.get("input_tokens") or 0),
            "cache_read": int(usage.get("cache_read_input_tokens") or 0),
            "cache_write": int(usage.get("cache_creation_input_tokens") or 0),
            "output": int(usage.get("output_tokens") or 0),
        }
    return list(calls.values())


def caching(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Prompt caching from the second call on: calls that read nothing, and breaks (a call that
    reads under half of what the call before it read and wrote: the prefix was invalidated)."""
    zero = [i for i, c in enumerate(calls, start=1) if i > 1 and c["cache_read"] == 0]
    breaks = [i for i, (a, b) in enumerate(zip(calls, calls[1:], strict=False), start=2)
              if b["cache_read"] < 0.5 * (a["cache_read"] + a["cache_write"])]  # fmt: skip
    return {"api_calls": len(calls), "cache_read_by_call": [c["cache_read"] for c in calls],
            "cache_write_by_call": [c["cache_write"] for c in calls],
            "zero_read_after_first": zero, "breaks": breaks,
            "ok": bool(calls) and not zero and not breaks}  # fmt: skip


def transcript_latency(transcript: Path, started: float) -> dict[str, float | None]:
    """From the transcript's own timestamps: process start to the first user entry and to the
    first assistant entry (the first response's arrival)."""
    first: dict[str, float] = {}
    for e in _lines(transcript):
        kind = e.get("type")
        if kind in ("user", "assistant") and kind not in first:
            t = _when(e.get("timestamp"))
            if t is not None:
                first[str(kind)] = t
    return {f"to_first_{k}_entry_s": (round(first[k] - started, 3) if k in first else None)
            for k in ("user", "assistant")}  # fmt: skip


def hook_seconds(evidence: Path) -> dict[str, Any]:
    """`hooks.jsonl` (hook_env.py) by event: count, total and largest seconds; the first
    UserPromptSubmit's and SessionStart's own seconds; whether the MCP server started."""
    by: dict[str, dict[str, float]] = defaultdict(lambda: {"n": 0, "seconds": 0.0, "max": 0.0})
    firsts: dict[str, float] = {}
    server = []
    for e in _lines(evidence / "hooks.jsonl"):
        if e.get("sub", "").endswith("-mcp"):
            server.append(e.get("event"))
            continue
        name, secs = str(e.get("event")), float(e.get("seconds") or 0.0)
        slot = by[name]
        by[name] = {"n": slot["n"] + 1, "seconds": round(slot["seconds"] + secs, 2),
                    "max": max(slot["max"], secs)}  # fmt: skip
        firsts.setdefault(name, secs)
    return {"by_event": dict(by), "server": server,
            "session_start_s": firsts.get("SessionStart", 0.0),
            "first_user_prompt_submit_s": firsts.get("UserPromptSubmit", 0.0)}  # fmt: skip


def watched_calls(tools: dict[str, int]) -> dict[str, int]:
    return {name: int(tools.get(name, 0)) for name in WATCHED}


def describe(
    clock: Clock, transcript: Path, evidence: Path, tools: dict[str, int]
) -> dict[str, Any]:
    calls = api_calls(transcript)
    return {
        "init": clock.init,
        "find_in_init_tools": FIND_TOOL in clock.init.get("tools", []),
        "deferral": deferral(transcript),
        "watched_calls": watched_calls(tools),
        "caching": caching(calls),
        "latency": {**clock.latency(), **transcript_latency(transcript, clock.started)},
        "stream_hooks": clock.hooks,
        "hooks": hook_seconds(evidence),
    }
