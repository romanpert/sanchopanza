"""Reading the evidence of one session: Claude Code's JSONL, the hook's logs, the journal.

Numbers only leave this module; the transcripts stay under `~/.claude/projects` and the run's
cache folder.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PROJECTS = Path.home() / ".claude" / "projects"
STUB_PREFIX = "[sanchopanza pruned this "
ONE_SHOT = ("issue_token.py", "probe.py")
B_MARK = "Next change, using what you learned earlier in this session"
LEFTOVER = "sanchopanza_index"  # only the hook's --out file (the whole conversation) has it


def find(session_id: str | None) -> Path | None:
    if not session_id:
        return None
    hits = sorted(PROJECTS.glob(f"*/{session_id}.jsonl"))
    return hits[0] if hits else None


def entries(path: Path | None) -> list[dict[str, Any]]:
    if path is None or not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def count(path: Path | None) -> int:
    return len(entries(path))


def _blocks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def tool_uses(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        b for e in items if e.get("type") == "assistant" for b in _blocks(e)
        if b.get("type") == "tool_use"
    ]  # fmt: skip


def _neutral(text: str) -> str:
    """The machine's home and this repo named neutrally: rows are published."""
    repo = Path(__file__).resolve().parents[3]
    for base, name in ((repo, "<repo>"), (Path.home(), "<home>")):
        for form in {str(base), str(base).replace("\\", "/"), str(base).replace("\\", "\\\\")}:
            text = text.replace(form, name)
    return text


def rel(path: str) -> str:
    """A file path as `pkg/x.py`, whatever absolute form the agent used."""
    p = str(path).replace("\\", "/")
    m = re.search(r"/work/[^/]+/(.+)$", p)
    return (m.group(1) if m else p.lstrip("./")).lower()


def _context(entry: dict[str, Any]) -> int:
    usage = (entry.get("message") or {}).get("usage") or {}
    return sum(
        int(usage.get(k) or 0)
        for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    )


def summary_a(path: Path) -> dict[str, Any]:
    items = entries(path)
    uses = tool_uses(items)
    assistants = [e for e in items if e.get("type") == "assistant" and _context(e)]
    return {
        "tool_calls": len(uses),
        "reads": sorted({rel(u["input"].get("file_path", "")) for u in uses if u["name"] == "Read"}),  # noqa: E501
        "bash": len([u for u in uses if u["name"] == "Bash"]),
        "last_context_tokens": _context(assistants[-1]) if assistants else 0,
        "result_chars": sum(
            len(json.dumps(b.get("content"))) for e in items for b in _blocks(e)
            if b.get("type") == "tool_result"
        ),
    }  # fmt: skip


def b_start(items: list[dict[str, Any]]) -> int:
    """Index of phase B's prompt: everything before it is phase A and the compaction."""
    for index, e in enumerate(items):
        if e.get("type") != "user":
            continue
        content = (e.get("message") or {}).get("content")
        text = (
            content
            if isinstance(content, str)
            else " ".join(str(b.get("text", "")) for b in content or [] if isinstance(b, dict))
        )
        if B_MARK in text:
            return index
    return len(items)


def compaction(path: Path) -> dict[str, Any]:
    """What the /compact left in the forked session, before phase B: a summary or stubs."""
    everything = entries(path)
    items = everything[: b_start(everything)]
    boundaries = [
        e for e in items if e.get("type") == "system" and e.get("subtype") == "compact_boundary"
    ]  # noqa: E501
    summaries = [e for e in items if e.get("isCompactSummary")]
    stubs = sum(
        json.dumps(b.get("content")).count(STUB_PREFIX)
        for e in items
        for b in _blocks(e)
        if b.get("type") == "tool_result"
    )
    kind = "none"
    if stubs:
        kind = "pruned"
    elif summaries:
        kind = "summary"
    elif boundaries:
        kind = "boundary_only"
    meta = [e.get("compactMetadata") for e in boundaries if e.get("compactMetadata")]
    return {
        "kind": kind, "boundaries": len(boundaries), "summaries": len(summaries),
        "stub_mentions": stubs, "summary_chars": sum(len(json.dumps(_blocks(e) or e.get("message")))
                                                     for e in summaries),
        "metadata": meta[-1] if meta else None,
    }  # fmt: skip


def summary_b(path: Path, a_path: Path | None) -> dict[str, Any]:
    """Phase B's own entries: re-reads, archive reads, one-shot re-runs, leftover hits."""
    everything = entries(path)
    items = everything[b_start(everything) :]
    uses = tool_uses(items)
    read_in_a = {rel(u["input"].get("file_path", "")) for u in tool_uses(entries(a_path))
                 if u["name"] == "Read"}  # fmt: skip
    reads = [rel(u["input"].get("file_path", "")) for u in uses if u["name"] == "Read"]
    commands = [str(u["input"].get("command", "")) for u in uses if u["name"] == "Bash"]
    assistants = [e for e in items if e.get("type") == "assistant" and _context(e)]
    return {
        "tool_calls": len(uses),
        "reads": len(reads),
        "re_reads": len([r for r in reads if r in read_in_a]),
        "archive_reads": len([r for r in reads if ".sanchopanza" in r]),
        "greps": len([u for u in uses if u["name"] in ("Grep", "Glob")]),
        "bash": len(commands),
        "one_shot_reruns": len([c for c in commands if any(t in c for t in ONE_SHOT)]),
        "shell_reads_of_pkg": len(
            [c for c in commands if re.search(r"\b(cat|type|head|tail|sed)\b.*pkg", c)]
        ),  # noqa: E501
        "leftover_hits": sum(
            json.dumps(b.get("content")).count(LEFTOVER) > 0
            for e in items
            for b in _blocks(e)
            if b.get("type") == "tool_result"
        ),
        "first_context_tokens": _context(assistants[0]) if assistants else 0,
        "turns": len(assistants),
    }


def hook_outcome(evidence: Path) -> dict[str, Any]:
    wrapper = [json.loads(x) for x in _lines(evidence / "wrapper.jsonl")]
    marker = _lines(evidence / "marker.txt")
    fallbacks = [m for m in marker if " fallback: " in m]
    pruned = [m for m in marker if " pruned " in m]
    reports = [w.get("report") or {} for w in wrapper]
    return {
        "loaded": any(m.endswith(" loaded") for m in marker),
        "compact_events": len([m for m in marker if " session.compact " in m]),
        "exits": [w["exit"] for w in wrapper],
        "pruned": len(pruned),
        "fallback": bool(fallbacks) or any(w["exit"] != 0 for w in wrapper) or not wrapper,
        "fallback_reasons": [_neutral(m.split(" fallback: ", 1)[1])[:200] for m in fallbacks],
        "reduction": [r.get("reduction") for r in reports],
        "actions": [r.get("actions") for r in reports],
        "reasons": [r.get("reasons") for r in reports],
        "decisions": sum(int(r.get("decisions") or 0) for r in reports),
        "failed_decisions": sum(int(r.get("failed_decisions") or 0) for r in reports),
        "hook_seconds": [w.get("seconds") for w in wrapper],
    }


def jev_cost(evidence: Path) -> float:
    total = 0.0
    for line in _lines(evidence / "journal.jsonl"):
        event = json.loads(line)
        if event.get("kind") == "decision":
            total += float((event.get("data") or {}).get("cost_usd") or 0.0)
    return total


def _lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [x for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def summary_keeps(path: Path, facts: dict[str, Any]) -> dict[str, bool]:
    """Which planted facts the compaction summary text carries, literally."""
    text = " ".join(
        json.dumps(e.get("message")) for e in entries(path) if e.get("isCompactSummary")
    )
    return {
        "token": facts["token"] in text, "code": facts["code"] in text,
        "tolerance": facts["tolerance"] in text, "helper": facts["helper"] in text,
        "window_home": facts["window_home"] in text,
    }  # fmt: skip


def constant_used(path: Path, facts: dict[str, Any]) -> str | None:
    """The package constant phase B's last edit of pkg/deadlines.py names, if any."""
    items = entries(path)
    edits = [
        u["input"]
        for u in tool_uses(items[b_start(items) :])
        if u["name"] in ("Edit", "Write") and "deadlines" in str(u["input"].get("file_path"))
    ]
    if not edits:
        return None
    text = str(edits[-1].get("new_string") or edits[-1].get("content") or "")
    found = re.findall(r"GRACE_[A-Z_]+|[A-Z_]+_DAYS", text)
    return found[0] if found else None
