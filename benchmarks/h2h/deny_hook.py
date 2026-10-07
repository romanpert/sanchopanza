"""PreToolUse hook of every h2h session, both arms: no tool call may reach the hosts that serve
the benchmark's answers.

A WebFetch deny rule in the session's settings stops WebFetch alone; with Bash allowed, `curl`
or a Python one-liner would reach the same hosts. This hook reads the call's whole input and
denies it when a denied host appears anywhere in it, and appends the tool's name to the file in
`H2H_DENY_LOG` so the runner counts it. The reason given to the agent names no benchmark.

WebSearch cannot be denied that way: the query is the question, and its results can list the
set's own pages (the smoke of 2026-10-05 got a result naming it; a probe search for the set
then listed a mirror on modelscope.cn). Every other WebSearch call is
let through with those hosts added to its `blocked_domains` (the search tool's own parameter),
unless the call already names `allowed_domains`, which the search API does not combine with it.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Mapping
from typing import Any

DENIED_HOSTS = (
    "huggingface.co", "hf.co", "datasets-server.huggingface.co", "raw.githubusercontent.com",
    "kaggle.com", "www.kaggle.com", "modelscope.cn", "hf-mirror.com",
)  # fmt: skip
# Hosts left out of every web search's results (subdomains are covered by the parent).
SEARCH_BLOCKED = ("huggingface.co", "hf.co", "kaggle.com", "modelscope.cn", "hf-mirror.com")
# github.com is open (some tasks ask about a repository's issues); only its raw file paths shut.
_GITHUB_RAW = re.compile(r"github\.com/[^\s\"']*?/raw/|gist\.githubusercontent\.com")
REASON = "Access to this host is blocked in this environment."


def denied(tool_input: object) -> bool:
    text = json.dumps(tool_input, ensure_ascii=False).lower()
    hosts = any(
        f"//{h}" in text or f".{h}" in text or f" {h}" in text or f'"{h}' in text
        for h in DENIED_HOSTS
    )
    return hosts or bool(_GITHUB_RAW.search(text))


def decision() -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": REASON,
        }
    }


def search_input(tool_input: Mapping[str, Any]) -> dict[str, Any] | None:
    """The WebSearch input with the set's hosts blocked, or None to leave it as it is."""
    if tool_input.get("allowed_domains"):
        return None
    current = list(tool_input.get("blocked_domains") or [])
    wanted = [*current, *(h for h in SEARCH_BLOCKED if h not in current)]
    return {**dict(tool_input), "blocked_domains": wanted}


def rewrite(updated: Mapping[str, Any]) -> dict[str, object]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": dict(updated),
        }
    }


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    tool_input = event.get("tool_input")
    if event.get("tool_name") == "WebSearch" and isinstance(tool_input, dict):
        updated = search_input(tool_input)
        if updated is not None:
            print(json.dumps(rewrite(updated)))
        return 0
    if not denied(tool_input):
        return 0
    log = os.environ.get("H2H_DENY_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as sink:
            sink.write(json.dumps({"tool": event.get("tool_name")}) + "\n")
    print(json.dumps(decision()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
