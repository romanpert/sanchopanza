"""Sandbox guard for the benchmark sessions: no network, no installs, nothing outside the work dir.

An instrument of the run, not part of sanchopanza. It keeps each session inside its throwaway
directory and makes "installing packages is not possible" true for task I2.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

DENY = re.compile(
    r"\bpip3?\s+install\b|\bpython[\d.]*\s+-m\s+pip\b|\buv\s+(pip|add)\b|\bconda\s+install\b"
    r"|\bnpm\s+(i|install)\b|\bcurl\b|\bwget\b|Invoke-WebRequest|\bgit\s+(push|clone|fetch)\b"
    r"|(^|[\s'\"=])\.\.[\\/]|~[\\/]|\$HOME|%USERPROFILE%|[A-Za-z]:[\\/](?!.*candor-bench)",
    re.IGNORECASE,
)


def inside(path: str, root: Path) -> bool:
    try:
        return (root / path).resolve().is_relative_to(root.resolve())
    except (OSError, ValueError):
        return False


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if data.get("hook_event_name") != "PreToolUse":
        return 0
    root = Path(data.get("cwd") or os.getcwd())
    tool = str(data.get("tool_name") or "")
    args = data.get("tool_input") or {}
    reason = ""
    if tool == "Bash" and DENY.search(str(args.get("command") or "")):
        reason = "not available in this environment (no network, no installs, no paths outside)"
    for key in ("file_path", "path", "notebook_path"):
        value = args.get(key)
        if isinstance(value, str) and value and not inside(value, root):
            reason = "paths outside the project are not available in this environment"
    if reason:
        out = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
        sys.stdout.write(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
