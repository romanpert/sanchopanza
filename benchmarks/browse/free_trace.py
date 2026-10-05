"""Browse, development: what a free session's Claude Code transcript says, call by call.

Pure reading, no model and no money. Shared by the free-task calibration runner
(`free_calib.py`, which stores a session's cost trajectory beside its grade) and the offline
cut analysis (`free_cut.py`, which replays the trajectory against candidate cut rules).

A "call" is one API request of the agent: Claude Code writes one transcript entry per content
block, so the entries are merged by message id. Subagent transcripts (`subagents/*.jsonl`) are
merged in by timestamp: a session that delegates spends most of its money there.

The trajectory is the cumulative list cost after each call. Each call's own tokens are priced
at list rates; what the transcripts do not show - the Haiku reader inside WebSearch and
WebFetch, 40-57 % of a pilot session - is the gap between `modelUsage` and the transcript's
own sum, spread evenly over the web tool calls (it is spent when those tools run). The whole
is then scaled so it ends on the session's `total_cost_usd`. That spreading is an
approximation: a long page costs its reader more than a short one.
"""

from __future__ import annotations

import json
import pathlib
import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

PROJECTS = pathlib.Path.home() / ".claude" / "projects"
# USD per million tokens: input, 5-minute cache write, 1-hour cache write, cache read, output.
PRICES = {
    "haiku": (1.0, 1.25, 2.0, 0.1, 5.0),
    "sonnet": (2.0, 2.5, 4.0, 0.2, 10.0),
    "opus": (5.0, 6.25, 10.0, 0.5, 25.0),
}
WEB_TOOLS = ("WebSearch", "WebFetch")
BROWSER_PREFIX = "mcp__playwright"


def folder_of(workdir: str) -> pathlib.Path:
    return PROJECTS / re.sub(r"[^A-Za-z0-9]", "-", workdir)


def family(model: str) -> str:
    for name in PRICES:
        if name in (model or ""):
            return name
    return "sonnet"


def call_usd(model: str, usage: Mapping[str, Any]) -> float:
    p_in, p_w5, p_w1, p_read, p_out = PRICES[family(model)]
    split = usage.get("cache_creation") or {}
    written = int(usage.get("cache_creation_input_tokens") or 0)
    w1h = int(split.get("ephemeral_1h_input_tokens") or 0)
    w5m = written - w1h
    tokens = (
        int(usage.get("input_tokens") or 0) * p_in
        + w5m * p_w5
        + w1h * p_w1
        + int(usage.get("cache_read_input_tokens") or 0) * p_read
        + int(usage.get("output_tokens") or 0) * p_out
    )
    return tokens / 1_000_000


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    parts = []
    for block in content if isinstance(content, list) else []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(parts)


def parse_entries(entries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The calls of one transcript file, in order, each with the results of its tool uses."""
    calls: dict[str, dict[str, Any]] = {}
    owner: dict[str, str] = {}
    for entry in entries:
        message = entry.get("message") or {}
        content = message.get("content")
        if entry.get("type") == "assistant" and message.get("id"):
            call = calls.setdefault(
                message["id"],
                {
                    "ts": str(entry.get("timestamp") or ""),
                    "model": str(message.get("model") or ""),
                    "sidechain": bool(entry.get("isSidechain")),
                    "usage": {},
                    "tools": [],
                    "inputs": [],
                    "text": "",
                    "results": "",
                },
            )
            usage = message.get("usage") or {}
            if int(usage.get("output_tokens") or 0) >= int(call["usage"].get("output_tokens") or 0):
                call["usage"] = usage
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use":
                    call["tools"].append(str(block.get("name") or ""))
                    call["inputs"].append(block.get("input") or {})
                    owner[str(block.get("id"))] = message["id"]
                elif block.get("type") == "text":
                    call["text"] += str(block.get("text") or "") + "\n"
        elif entry.get("type") == "user" and isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    mine = owner.get(str(block.get("tool_use_id")))
                    if mine:
                        calls[mine]["results"] += _result_text(block.get("content")) + "\n"
    return list(calls.values())


def load_calls(folder: pathlib.Path) -> list[dict[str, Any]]:
    """Every call of a session, main agent and subagents, in time order."""
    out: list[dict[str, Any]] = []
    for path in sorted(folder.rglob("*.jsonl")) if folder.is_dir() else []:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        out.extend(parse_entries([json.loads(x) for x in lines if x.strip()]))
    return sorted(out, key=lambda c: c["ts"])


def trajectory(
    calls: Sequence[Mapping[str, Any]], total_usd: float, by_model: Mapping[str, float]
) -> list[float]:
    """Cumulative list USD after each call, ending on `total_usd` (see the module's note)."""
    own = [call_usd(c["model"], c["usage"]) for c in calls]
    seen: dict[str, float] = {}
    for call, usd in zip(calls, own, strict=True):
        seen[family(call["model"])] = seen.get(family(call["model"]), 0.0) + usd
    reported: dict[str, float] = {}
    for model, usd in by_model.items():
        reported[family(model)] = reported.get(family(model), 0.0) + float(usd)
    unseen = sum(max(0.0, usd - seen.get(f, 0.0)) for f, usd in reported.items())
    web = [sum(t in WEB_TOOLS for t in c["tools"]) for c in calls]
    n_web = sum(web)
    steps = [usd + (unseen * w / n_web if n_web else 0.0) for usd, w in zip(own, web, strict=True)]
    raw = sum(steps)
    scale = total_usd / raw if raw > 0 else 0.0
    out, running = [], 0.0
    for step in steps:
        running += step * scale
        out.append(running)
    return out


def tool_counts(calls: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for call in calls:
        for tool in call["tools"]:
            counts[tool] = counts.get(tool, 0) + 1
    return counts


def browser_opened(calls: Sequence[Mapping[str, Any]]) -> bool:
    return any(t.startswith(BROWSER_PREFIX) for c in calls for t in c["tools"])


def first_index(
    calls: Sequence[Mapping[str, Any]], found: Callable[[str], bool], field: str
) -> int | None:
    """0-based index of the first call whose `field` ("text" or "results") satisfies `found`."""
    return next((i for i, c in enumerate(calls) if c[field] and found(c[field])), None)


def summary(workdir: str, total_usd: float, by_model: Mapping[str, float]) -> dict[str, Any]:
    """What the calibration runner stores beside a session's grade: no transcript text."""
    calls = load_calls(folder_of(workdir))
    counts = tool_counts(calls)
    return {
        "api_calls": len(calls),
        "trajectory": [round(x, 4) for x in trajectory(calls, total_usd, by_model)],
        "web_search": counts.get("WebSearch", 0),
        "web_fetch": counts.get("WebFetch", 0),
        "browser_opened": browser_opened(calls),
    }
