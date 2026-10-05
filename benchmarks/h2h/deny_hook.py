"""PreToolUse hook of every h2h session, both arms: no tool call may reach the hosts that serve
the benchmark's answers.

A WebFetch deny rule in the session's settings stops WebFetch alone; with Bash allowed, `curl`
or a Python one-liner would reach the same hosts. This hook reads the call's whole input and
denies it when a denied host appears anywhere in it, and appends the tool's name to the file in
`H2H_DENY_LOG` so the runner counts it. The reason given to the agent names no benchmark.
"""

from __future__ import annotations

import json
import os
import re
import sys

DENIED_HOSTS = (
    "huggingface.co", "hf.co", "datasets-server.huggingface.co", "raw.githubusercontent.com",
    "kaggle.com", "www.kaggle.com",
)  # fmt: skip
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


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if not denied(event.get("tool_input")):
        return 0
    log = os.environ.get("H2H_DENY_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as sink:
            sink.write(json.dumps({"tool": event.get("tool_name")}) + "\n")
    print(json.dumps(decision()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
