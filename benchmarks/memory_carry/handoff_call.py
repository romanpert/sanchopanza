"""One `claude -p` call of the F2 runner (`handoff.py`) and what is read from it.

- `agent_env`: carry's clean-user environment without PYTHONPATH (the sealed worktree's path is
  not the agent's business; S's hooks set their own through `carry_hook.py`).
- `call`: one process, its stream in `<tag>.jsonl`; on timeout the whole process tree is killed
  by the child's own PID (`taskkill /T /F /PID`, never by name).
- `stream_extra`: what `carry.read_stream` leaves out (full result text, whether a cost was
  reported, usage, prompt sizes, subagent calls).
- `limit_text`: the weekly or usage limit said in a short or error result, beside carry's
  `limited` events.
- `first_prompt_in_transcript`: the first user message Claude Code stored for a session, to
  check that H's session 2 got the handoff byte for byte.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import carry

# Harness files an agent could open beside its repository (reported, never deciding): S's
# installed settings and server, the hook launcher, Claude Code's own configuration, S's store.
TOUCH = {
    ".claude": re.compile(r"(^|[\\/\s'\"=])\.claude[\\/]"),
    ".mcp.json": re.compile(r"\.mcp\.json"),
    "carry_hook": re.compile(r"carry_hook"),
    "claude-config": re.compile(r"claude-config"),
    "store": re.compile(r"(^|[\\/\s'\"=])store([\\/]|$|[\s'\"])"),
    # W17: what lies beside the arm's own folder (the run's other arms, the pair's other arm),
    # the run's key and Jev files, and S's own logs.
    "../..": re.compile(r"\.\.[\\/]+\.\."),
    "typesafe.key": re.compile(r"typesafe\.key"),
    "jev-": re.compile(r"jev-(cap|ledger)"),
    "hooks.jsonl": re.compile(r"hooks\.jsonl"),
    "journal.jsonl": re.compile(r"journal\.jsonl"),
}
LIMIT_WORDS = ("usage limit", "hit your limit", "weekly limit")
LIMIT_SHORT = 400  # characters: a longer successful answer that mentions a limit is not one
WIN_CMDLINE = 32_767  # Windows' CreateProcess limit on a command line


def agent_env(config: Path | None) -> dict[str, str]:
    return {k: v for k, v in carry.environment(config).items() if k.upper() != "PYTHONPATH"}


def kill_tree(proc: subprocess.Popen[Any]) -> None:
    """The timed-out process and its children, by the child's own PID (still held, so it cannot
    have been reused)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       check=False)  # fmt: skip
    else:
        proc.kill()
    try:
        proc.wait(timeout=60)
    except subprocess.TimeoutExpired:
        proc.kill()


def call(run: Path, cwd: Path, cmd: list[str], tag: str, config: Path | None,
         timeout: int) -> dict[str, Any]:  # fmt: skip
    started = time.time()
    stream = run / f"{tag}.jsonl"
    with stream.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(cmd, cwd=cwd, env=agent_env(config), stdout=out,
                                stderr=subprocess.PIPE, text=True)  # fmt: skip
        try:
            _, err = proc.communicate(timeout=timeout)
            code, late = proc.returncode, False
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            code, err, late = None, "", True
    seen = {**carry.read_stream(stream), **stream_extra(stream, Path(cwd).parent.name)}
    limit = bool(seen.get("limit_hit")) or limit_text(seen, err or "")
    return {**seen, "returncode": code, "stderr": (err or "")[-300:], "timeout": late,
            "tag": tag, "started": started, "seconds": round(time.time() - started, 1),
            "limit_hit": limit}  # fmt: skip


def limit_text(seen: dict[str, Any], stderr: str) -> bool:
    text = str(seen.get("text") or "")
    short = seen.get("is_error") or len(text) < LIMIT_SHORT
    said = any(w in text.lower() for w in LIMIT_WORDS) and short
    return said or any(w in stderr.lower() for w in LIMIT_WORDS)


def stream_extra(path: Path, own: str = "") -> dict[str, Any]:
    text, reported, usage, prompts, agents = "", False, {}, [], 0
    touched: set[str] = set()
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    for line in raw.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if event.get("type") == "result":
            text = str(event.get("result") or "")
            reported = isinstance(event.get("total_cost_usd"), (int, float))
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
        message = event.get("message")
        if event.get("type") == "assistant" and isinstance(message, dict):
            used = message.get("usage") or {}
            kinds = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
            prompts.append(sum(int(used.get(k) or 0) for k in kinds))
            content = message.get("content") or []
            uses = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
            agents += sum(1 for b in uses if b.get("name") in ("Task", "Agent"))
            touched |= touches([json.dumps(b.get("input") or {}) for b in uses], own)
    return {"text": text, "cost_reported": reported, "tokens": tokens_of(usage),
            "first_prompt": prompts[0] if prompts else None,
            "last_prompt": prompts[-1] if prompts else None, "subagents": agents,
            "touched": sorted(touched)}  # fmt: skip


SIBLING = re.compile(r"(?<![A-Za-z0-9])t\d\d-[abc](?![A-Za-z0-9])")


def touches(inputs: list[str], own: str = "") -> set[str]:
    """Which harness files (TOUCH) the tool calls' inputs name; JSON escapes undone first.
    "sibling" (only with `own`): an arm folder's name (`t<NN>-<x>`) other than `own`."""
    found: set[str] = set()
    for raw in inputs:
        try:
            text = " ".join(str(v) for v in json.loads(raw).values())
        except (ValueError, AttributeError):
            text = raw
        found |= {label for label, pattern in TOUCH.items() if pattern.search(text)}
        if own and any(m != own for m in SIBLING.findall(text)):
            found.add("sibling")
    return found


def tokens_of(usage: dict[str, Any]) -> dict[str, int]:
    return {"input": int(usage.get("input_tokens") or 0),
            "output": int(usage.get("output_tokens") or 0),
            "cache_read": int(usage.get("cache_read_input_tokens") or 0),
            "cache_write": int(usage.get("cache_creation_input_tokens") or 0)}  # fmt: skip


def first_prompt_in_transcript(config: Path | None, sid: str | None) -> str | None:
    """The first user message (not a meta one) of session `sid` in the configuration's
    transcripts; None when the transcript or the message is not found."""
    if config is None or not sid:
        return None
    for path in sorted((config / "projects").glob(f"*/{sid}.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if not isinstance(event, dict) or event.get("type") != "user" or event.get("isMeta"):
                continue
            content = (event.get("message") or {}).get("content")
            if isinstance(content, str):
                return content
            texts = [b.get("text") for b in content or [] if isinstance(b, dict)
                     and b.get("type") == "text"]  # fmt: skip
            if texts:
                return str(texts[0])
    return None
