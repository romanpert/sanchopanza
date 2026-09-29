"""Reading one phase-B session: what the model received, call by call, and what happened.

Built on `../2026-09-28-context-e2e/transcripts.py` (imported). Two rules from 2026-09-28:

- Under `--resume` / `--fork-session`, `total_cost_usd` and `modelUsage` in the result JSON are
  cumulative over the conversation, phase A included. The invocation's true cost is the
  difference against phase A's cumulative total (`costs.py` of the e2e run).
- After a compaction, transcript entries may chain to parents from before the boundary, so a
  `--resume` rebuilt from the file is not what the model saw. What the model received is read
  from each API call's own `usage` (one per assistant `message.id`, in file order), never from
  the entries that follow the boundary.
"""

# ruff: noqa: E501
from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from statistics import median
from typing import Any

HERE = Path(__file__).resolve().parent
E2E = HERE.parent / "2026-09-28-context-e2e"


def _load(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, E2E / file)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


tr = _load("e2e_transcripts", "transcripts.py")
costs = _load("e2e_costs", "costs.py")

B_MARK = "Phase B of the release"
CLEARED = "[Old tool result content cleared]"
STUB_PREFIX = "[sanchopanza pruned this "
ARRIVAL_MARKS = ("[sanchopanza cut this ", "sanchopanza cut")
ONE_SHOT = {"issue_token": "issue_token.py", "build_report": "build_report.py"}
ARCHIVE = ".sanchopanza/archive"

neutral = tr._neutral
find = tr.find
entries = tr.entries
hook_outcome = tr.hook_outcome


def b_start(items: list[dict[str, Any]]) -> int:
    for index, e in enumerate(items):
        if e.get("type") != "user":
            continue
        content = (e.get("message") or {}).get("content")
        text = content if isinstance(content, str) else " ".join(
            str(b.get("text", "")) for b in content or [] if isinstance(b, dict))  # fmt: skip
        if B_MARK in text:
            return index
    return len(items)


def _usage(entry: dict[str, Any]) -> dict[str, int]:
    u = (entry.get("message") or {}).get("usage") or {}
    creation = u.get("cache_creation") or {}
    return {
        "input": int(u.get("input_tokens") or 0),
        "cache_read": int(u.get("cache_read_input_tokens") or 0),
        "cache_creation": int(u.get("cache_creation_input_tokens") or 0),
        "cache_creation_1h": int(creation.get("ephemeral_1h_input_tokens") or 0),
        "cache_creation_5m": int(creation.get("ephemeral_5m_input_tokens") or 0),
        "output": int(u.get("output_tokens") or 0),
    }


def sequence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """API calls (one per message id, the last entry's usage) and compact boundaries, in file
    order. A call's `context` is what the model received: input + cache read + cache creation."""
    out: list[dict[str, Any]] = []
    where: dict[str, int] = {}
    for e in items:
        if e.get("type") == "system" and e.get("subtype") == "compact_boundary":
            out.append({"kind": "boundary", "meta": e.get("compactMetadata")})
            continue
        if e.get("type") != "assistant":
            continue
        msg = e.get("message") or {}
        u = _usage(e)
        context = u["input"] + u["cache_read"] + u["cache_creation"]
        if not context:
            continue  # streaming placeholders carry zero usage (probe p6)
        mid = msg.get("id") or f"anon-{len(out)}"
        row = {"kind": "call", "id": mid, "context": context, **u}
        if mid in where:
            out[where[mid]] = row
        else:
            where[mid] = len(out)
            out.append(row)
    return out


def usage_totals(seq: list[dict[str, Any]], prices: dict[str, float]) -> dict[str, Any]:
    calls = [c for c in seq if c["kind"] == "call"]
    keys = ("input", "cache_read", "cache_creation", "cache_creation_1h", "cache_creation_5m", "output")
    total = {k: sum(c[k] for c in calls) for k in keys}
    input_all = total["input"] + total["cache_read"] + total["cache_creation"]
    five = total["cache_creation"] - total["cache_creation_1h"]
    usd = (total["input"] * prices["in"] + total["cache_read"] * prices["cr"]
           + total["cache_creation_1h"] * prices["cw1h"] + five * prices["cw5m"]
           + total["output"] * prices["out"]) / 1e6  # fmt: skip
    return {**total, "calls": len(calls), "input_all": input_all,
            "cache_read_share": round(total["cache_read"] / input_all, 4) if input_all else None,
            "usd_from_calls": round(usd, 6)}  # fmt: skip


def compaction(seq: list[dict[str, Any]], items: list[dict[str, Any]], marker: list[str]) -> dict[str, Any]:
    """Each boundary with the last call's context before it and the first after it."""
    events = []
    for i, x in enumerate(seq):
        if x["kind"] != "boundary":
            continue
        before = next((c["context"] for c in reversed(seq[:i]) if c["kind"] == "call"), None)
        # entries the engine copies after a compaction carry zero usage: skip them
        after = next((c["context"] for c in seq[i + 1 :] if c["kind"] == "call" and c["context"]), None)
        calls_before = sum(1 for c in seq[:i] if c["kind"] == "call")
        events.append({"before": before, "after": after, "calls_before": calls_before,
                       "trigger": (x.get("meta") or {}).get("trigger"),
                       "pre_tokens": (x.get("meta") or {}).get("preTokens")})  # fmt: skip
    summaries = sum(1 for e in items if e.get("isCompactSummary"))
    text = json.dumps([b.get("content") for e in items for b in tr._blocks(e) if b.get("type") == "tool_result"])
    return {
        "boundaries": len(events), "events": events, "summaries": summaries,
        "cleared_stubs": text.count(CLEARED), "index_stubs": text.count(" Holds: "),
        "sancho_stubs": text.count(STUB_PREFIX),
        "marker_lines": [neutral(m)[:240] for m in marker],
        "fired": bool(events),
    }  # fmt: skip


def _tool_uses_by_message(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in items:
        if e.get("type") != "assistant":
            continue
        mid = (e.get("message") or {}).get("id") or id(e)
        for b in tr._blocks(e):
            if b.get("type") == "tool_use":
                groups.setdefault(str(mid), []).append(b)
    return list(groups.values())


def behaviour(items: list[dict[str, Any]], chain: list[str]) -> dict[str, Any]:
    """Phase B's tool calls: reads against the reading order, one-shot re-runs, archive use."""
    groups = _tool_uses_by_message(items)
    uses = [u for g in groups for u in g]
    reads = [tr.rel(u["input"].get("file_path", "")) for u in uses if u["name"] == "Read"]
    commands = [str(u["input"].get("command", "")) for u in uses if u["name"] in ("Bash", "PowerShell")]
    b_modules = [p.lower() for p in chain[8:]]
    runs = {k: sum(v in c for c in commands) for k, v in ONE_SHOT.items()}
    return {
        "tool_calls": len(uses),
        "parallel_batches": sum(len(g) > 1 for g in groups),
        "reads": len(reads),
        "b_modules_read": sum(m in reads for m in b_modules),
        "b_modules_unread": [m for m in b_modules if m not in reads],
        "first_log_call": next((i for i, u in enumerate(uses) if ONE_SHOT["build_report"] in str(u["input"])), None),
        "build_report_runs": runs["build_report"],
        "one_shot_reruns": max(0, runs["build_report"] - 1) + runs["issue_token"],
        "search_archive_calls": sum(u["name"].endswith("__search_archive") for u in uses),
        "archive_reads": sum(ARCHIVE in r for r in reads) + sum(ARCHIVE in c.replace("\\", "/") for c in commands),
        "greps": sum(u["name"] in ("Grep", "Glob") for u in uses),
        "edits": sum(u["name"] in ("Edit", "Write") for u in uses),
        "denied_tools": sorted({u["name"] for u in uses if u["name"] not in (
            "Bash", "Read", "Write", "Edit", "Glob", "Grep") and not u["name"].endswith("__search_archive")}),
    }  # fmt: skip


def arrival_in_transcript(items: list[dict[str, Any]]) -> int:
    return sum(
        any(m in json.dumps(b.get("content")) for m in ARRIVAL_MARKS)
        for e in items for b in tr._blocks(e) if b.get("type") == "tool_result"
    )  # fmt: skip


def hook_stats(ev: Path) -> dict[str, Any]:
    """From `hooks.jsonl` (the e2e hook_wrapper's log); after `run_round2.hook_stats`."""
    lines = [json.loads(x) for x in tr._lines(ev / "hooks.jsonl")]
    post = [x for x in lines if x.get("event") == "PostToolUse"]
    cuts = [x for x in post if x.get("updated")]
    return {
        "events": len(lines),
        "by_event": {k: sum(x.get("event") == k for x in lines) for k in sorted({x.get("event") for x in lines})},
        "post_tool_use": len(post),
        "over_6000": sum(x.get("response_chars", 0) > 6000 for x in post),
        "arrival_cuts": len(cuts),
        "arrival_cut_tools": sorted({x.get("tool") for x in cuts}),
        "chars_saved": sum(x["response_chars"] - (x.get("updated_chars") or 0) for x in cuts),
        "context_injections": sum(x.get("context_chars", 0) > 0 for x in lines),
        "nonzero_exits": sum(x.get("exit") != 0 for x in lines),
        "hook_seconds_median": median(x["seconds"] for x in lines) if lines else 0,
    }  # fmt: skip


def phase_b(path: Path | None, ev: Path, chain: list[str], prices: dict[str, float]) -> dict[str, Any]:
    everything = entries(path)
    start = b_start(everything)
    items = everything[start:]
    seq = sequence(items)
    marker = tr._lines(ev / "marker.txt")
    calls = [c["context"] for c in seq if c["kind"] == "call"]
    return {
        "b_found": start < len(everything),
        "usage": usage_totals(seq, prices),
        "context_per_call": [c["context"] if c["kind"] == "call" else "BOUNDARY" for c in seq],
        "first_context": calls[0] if calls else 0, "peak_context": max(calls) if calls else 0,
        "compaction": compaction(seq, items, marker),
        "plugin": hook_outcome(ev),
        "behaviour": behaviour(items, chain),
        "arrival_in_transcript": arrival_in_transcript(items),
    }  # fmt: skip


def phase_a(path: Path | None, prices: dict[str, float]) -> dict[str, Any]:
    items = entries(path)
    seq = sequence(items)
    calls = [c["context"] for c in seq if c["kind"] == "call"]
    uses = tr.tool_uses(items)
    return {
        "usage": usage_totals(seq, prices), "last_context": calls[-1] if calls else 0,
        "tool_calls": len(uses), "boundaries": sum(c["kind"] == "boundary" for c in seq),
        "reads": [tr.rel(u["input"].get("file_path", "")) for u in uses if u["name"] == "Read"],
        "build_report_runs": sum("build_report" in str(u["input"]) for u in uses),
    }  # fmt: skip


def true_split(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """B's own cost and input by difference of the cumulative result JSON (`costs.split`)."""
    s = costs.split(a, {}, b)
    return {"usd": s["b_usd"], "input": s["b_input"], "cumulative_usd": s["total_usd"]}


def scrub(value: Any) -> Any:
    return json.loads(neutral(json.dumps(value)))


def safe_answer(text: str) -> str:
    return re.sub(r"\s+", " ", neutral(text or ""))[:600]
