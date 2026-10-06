"""One call of a long chain: its command line, the process (killed with its whole tree on a
timeout), and what its stream and the session's transcript say it did and cost.

The command is the same in every arm but for the session it resumes: `--setting-sources
project` (an arm differs only by what its working copy's `.claude/settings.json` holds), an
`.mcp.json` passed in every arm (empty for N and N-early), and permissions by `--allowedTools`
with `--permission-mode default`, as `carry.py` does. Never `bypassPermissions` (owner's rule):
every call's `init` must report the same mode, or the chain stops (`long_guard`).

Cost: the stream's per-block usage is partial (B2's N streams sum to 7.99 of 8.74 USD), so a
call is metered from the transcript's requests it added (deduplicated by message id) and
reconciled with its `modelUsage` delta, which counts a compaction call the transcript leaves
out (B2: S 0.224 USD, Sm 0.340 USD over two and four compactions). Both price bases are kept:
the owner's (the ledger and the caps) and Claude Code's (its `costUSD`, checked against ours).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.append(str(HERE.parent))  # appended: benchmarks/ holds names like agentdojo
sys.path.insert(0, str(HERE.parent / "memory_carry"))

import carry  # noqa: E402
import long_guard  # noqa: E402
import long_window  # noqa: E402
import meter  # noqa: E402
import run  # noqa: E402

PERMISSION_MODE = "default"
# carry.TOOLS plus what a coding session uses besides, and sanchopanza's servers by name (an
# allow rule for a server that is not there changes nothing, so N's command is S's).
ALLOWED = (*carry.TOOLS, "MultiEdit", "NotebookEdit", "TodoWrite", "Task", "Agent", "Skill",
           "mcp__sanchopanza", "mcp__sanchopanza-fetch", "mcp__sanchopanza-knowledge")  # fmt: skip


def command(claude: tuple[str, ...], model: str, prompt: str, session: str | None,
            cap_cc: float, mcp: Path, debug: Path | None = None) -> list[str]:  # fmt: skip
    """`debug`: where the session writes its autocompact lines (`long_window`), in every arm."""
    asked = [] if run.stdin_for(prompt) else [prompt]
    cmd = [*claude, "-p", *asked, "--model", model, "--max-budget-usd", f"{cap_cc:.2f}",
           "--output-format", "stream-json", "--verbose", "--setting-sources", "project",
           "--strict-mcp-config", "--mcp-config", str(mcp),
           "--permission-mode", PERMISSION_MODE, "--allowedTools", *ALLOWED,
           "--disallowedTools", *run.DISALLOWED,
           *(long_window.flags(debug) if debug else [])]  # fmt: skip
    return [*cmd, "--resume", session] if session else cmd


POLL_S = 5.0


def invoke(cmd: list[str], cwd: Path, env: dict[str, str], prompt: str, stream: Path,
           timeout_s: float, idle_s: float = 1200.0) -> tuple[int, float, str]:  # fmt: skip
    """(exit code, seconds, why it was cut). -9: cut at the timeout or after the stream sat idle
    for `idle_s`, with its whole process tree; -1: it never started."""
    began = time.time()
    err = stream.with_suffix(".err")
    with stream.open("wb") as out, err.open("wb") as errors:
        try:
            child = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=out, stderr=errors,
                                     stdin=subprocess.PIPE)  # fmt: skip
        except OSError as exc:
            errors.write(f"{type(exc).__name__}: {exc}".encode())
            return -1, 0.0, "did not start"
        feed(child, run.stdin_for(prompt))
        why = wait(child, stream, began + timeout_s, idle_s)
        if why:
            long_guard.kill_tree(child.pid)
            child.wait(timeout=120)
    return (-9 if why else child.returncode), round(time.time() - began, 1), why


def feed(child: subprocess.Popen, data: bytes | None) -> None:
    """The prompt through stdin when it is too long for the command line, then stdin closed."""
    assert child.stdin is not None
    try:
        if data:
            child.stdin.write(data)
    finally:
        child.stdin.close()


def wait(child: subprocess.Popen, stream: Path, deadline: float, idle_s: float) -> str:
    """"" when the process ended by itself; else "timeout" or "idle"."""
    while True:
        try:
            child.wait(timeout=max(0.05, min(POLL_S, deadline - time.time())))
            return ""
        except subprocess.TimeoutExpired:
            now = time.time()
            if now >= deadline:
                return "timeout"
            if now - stream.stat().st_mtime > idle_s:
                return "idle"


def events(stream: Path) -> list[dict[str, Any]]:
    out = []
    text = stream.read_text(encoding="utf-8", errors="replace") if stream.exists() else ""
    for line in text.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            out.append(event)
    return out


def stream_facts(stream: Path) -> dict[str, Any]:
    """What the call's stream says: its init, result, tools, compactions, limits, denials."""
    found = events(stream)
    init = next((carry.init_facts(e) for e in found
                 if e.get("type") == "system" and e.get("subtype") == "init"), {})  # fmt: skip
    result = next((e for e in reversed(found) if e.get("type") == "result"), {})
    tools: Counter[str] = Counter()
    for e in found:
        content = (e.get("message") or {}).get("content") if e.get("type") == "assistant" else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools[str(block.get("name"))] += 1
    compactions = [_compaction(e) for e in found
                   if e.get("type") == "system" and e.get("subtype") == "compact_boundary"]
    limits = sorted({k for e in found if (k := long_guard.limit_event(e))})
    return {"init": init, "session": str(result.get("session_id") or next(
                (e.get("session_id") for e in found if e.get("session_id")), "") or ""),
            "subtype": result.get("subtype"), "is_error": bool(result.get("is_error")),
            "cost_cc_cumulative": float(result.get("total_cost_usd") or 0.0),
            "model_usage": result.get("modelUsage") or {}, "tools": dict(tools),
            "tool_uses": sum(tools.values()), "compactions": compactions, "limits": limits,
            "denials": len(result.get("permission_denials") or []),
            "turns": result.get("num_turns"),
            "result_tail": str(result.get("result") or "")[-RESULT_TAIL:]}  # fmt: skip


RESULT_TAIL = 600  # the end of the final answer, kept in the row (a give-up says so there)


def _compaction(event: dict[str, Any]) -> dict[str, Any]:
    meta = event.get("compact_metadata") or event.get("compactMetadata") or {}
    return {"trigger": meta.get("trigger"), "pre": meta.get("pre_tokens", meta.get("preTokens")),
            "post": meta.get("post_tokens", meta.get("postTokens"))}  # fmt: skip


def transcript_of(root: Path, session: str) -> Path | None:
    return next(root.glob(f"*/{session}.jsonl"), None) if session else None


USAGE_KEYS = ("inputTokens", "outputTokens", "cacheReadInputTokens", "cacheCreationInputTokens")


def usage_of(requests: tuple[meter.Request, ...]) -> dict[str, dict[str, int]]:
    """Requests summed per model in `modelUsage`'s terms."""
    out: dict[str, dict[str, int]] = {}
    for r in requests:
        row = out.get(r.model, dict.fromkeys(USAGE_KEYS, 0))
        values = (r.input, r.output, r.read, r.write_5m + r.write_1h)
        out = {**out, r.model: {k: row[k] + v for k, v in zip(USAGE_KEYS, values, strict=True)}}
    return out


def usage_sum(a: dict[str, Any], b: dict[str, Any]) -> dict[str, dict[str, int]]:
    models = set(a) | set(b)
    return {m: {k: int((a.get(m) or {}).get(k) or 0) + int((b.get(m) or {}).get(k) or 0)
                for k in USAGE_KEYS} for m in models}  # fmt: skip


def new_requests(transcript: Path | None, seen: frozenset[str]) -> tuple[meter.Request, ...]:
    found = meter.transcript_requests(transcript) if transcript else ()
    return tuple(r for r in found if r.id not in seen)


def metered(new: tuple[meter.Request, ...], usage_now: dict[str, Any],
            usage_before: dict[str, Any]) -> dict[str, Any]:  # fmt: skip
    """The call's own requests (the transcript's not seen before) reconciled with its
    `modelUsage` delta, in both price bases."""
    delta = meter.usage_delta(usage_now, usage_before)
    owner = meter.reconcile(new, delta, meter.OWNER_RATES)
    cc = meter.reconcile(new, delta, meter.CLAUDE_CODE_RATES)
    peak = max((r.context for r in new), default=0)
    over = sum(r.cost(meter.OWNER_RATES) for r in new if r.context > 200_000)
    return {"owner_usd": owner["total_usd"], "cc_usd": cc["total_usd"],
            "unlogged_owner_usd": owner["unlogged_usd"], "requests": len(new),
            "peak_context": peak, "owner_usd_over_200k": round(over, 6),
            "first_request": meter.first_write_flags(new), "models": owner["models"],
            "not_in_model_usage": owner["not_in_model_usage"]}  # fmt: skip


def charged_cap(owner_cap: float, cc_cap: float) -> dict[str, Any]:
    """A call cut before its result is charged its caps (run.call_cost does the same)."""
    return {"owner_usd": owner_cap, "cc_usd": cc_cap, "unlogged_owner_usd": 0.0, "requests": 0,
            "peak_context": 0, "owner_usd_over_200k": 0.0, "charged_cap": True}  # fmt: skip
