"""PreToolUse hook of the offline h2h suites (BrowseComp-Plus, long documents), both arms: the
evidence is the session's own folder and the retrieval server, nothing else.

Those suites take WebSearch and WebFetch away from both arms (`--disallowedTools`). This hook
shuts the other two ways out:

- the network from a shell: a Bash or PowerShell command with a URL or a downloader in it
  (curl, wget, Invoke-WebRequest, urllib, requests, ...);
- the rest of the disk: a file tool whose path is outside the session's working folder, or a
  shell command with `..`, `~`, a home variable or an absolute path outside it (the set's
  answers, the corpus and other sessions' transcripts are all on this disk).

MCP tools (the suite's retrieval server and the S install's local servers) and subagent launches
pass: a subagent's own tool calls come through this hook again. Two kinds of MCP call do not: S's
fetch server (`fetch_passages` reads the web, it is WebFetch by another name) and any MCP call
with a URL in its input. A denial is logged to `H2H_DENY_LOG`
by tool name. Heuristic, on purpose loose towards denial; the reason names no benchmark.
"""

from __future__ import annotations

import json
import ntpath
import os
import re
import sys
from collections.abc import Mapping
from typing import Any

REASON = "This environment is offline and limited to the working folder."
SHELLS = ("Bash", "PowerShell")
FILE_KEYS = ("file_path", "path", "notebook_path")
_NET = re.compile(
    r"https?://|ftp://|\bcurl\b|\bwget\b|invoke-webrequest|invoke-restmethod|\biwr\b|\birm\b|"
    r"net\.webclient|urllib|\brequests\b|\bhttpx\b|\baiohttp\b|\bsocket\b|\bssh\b|\bscp\b|"
    r"git\s+clone|pip\s+install|\bnpm\b|\bnpx\b|\bnc\b|start-bitstransfer",
    re.I,
)
_HOME = re.compile(
    r"(?:^|[\s\"'=(])~|\$home\b|\$\{home\}|%userprofile%|\$env:|\.\.[\\/]|[\\/]\.\.", re.I
)
_ABS = re.compile(r"(?i)(?<![\w.])(?:[a-z]:[\\/]|/[a-z]/|\\\\|/)[^\s\"'|;&<>()]*")
_SAFE_POSIX = ("/dev/null", "/tmp/", "/tmp")
WEB_MCP = ("mcp__sanchopanza-fetch__",)
_URL = re.compile(r"(?:https?|ftp)://", re.I)


def _norm(path: str) -> str:
    """A Windows path, lower-cased, with Git Bash's /c/ spelled C:/."""
    found = re.match(r"^/([a-zA-Z])/(.*)$", path)
    if found:
        path = f"{found.group(1)}:/{found.group(2)}"
    return ntpath.normcase(ntpath.abspath(path))


def inside(path: str, cwd: str) -> bool:
    if not path:
        return True
    full = path if ntpath.isabs(path) or re.match(r"^/[a-zA-Z]/", path) else ntpath.join(cwd, path)
    target, root = _norm(full), _norm(cwd)
    return target == root or target.startswith(root.rstrip("\\") + "\\")


def shell_denied(command: str, cwd: str) -> bool:
    if _NET.search(command) or _HOME.search(command):
        return True
    for token in _ABS.findall(command):
        if token.startswith("/") and not re.match(r"^/[a-zA-Z]/", token):
            if token == "/" or not token.startswith(_SAFE_POSIX):
                return True
            continue
        if not inside(token, cwd):
            return True
    return False


def denied(tool: str, tool_input: Mapping[str, Any], cwd: str) -> bool:
    if tool.startswith("mcp__"):
        return tool.startswith(WEB_MCP) or bool(_URL.search(json.dumps(tool_input)))
    if tool in ("Task", "Agent", "TodoWrite"):
        return False
    if tool in ("WebSearch", "WebFetch"):
        return True
    if tool in SHELLS:
        return shell_denied(str(tool_input.get("command") or ""), cwd)
    paths = [str(tool_input[k]) for k in FILE_KEYS if tool_input.get(k)]
    if any(not inside(p, cwd) for p in paths):
        return True
    pattern = str(tool_input.get("pattern") or "") if tool == "Glob" else ""
    return bool(_HOME.search(pattern)) or (bool(pattern) and not inside(pattern.split("*")[0], cwd))


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
    tool = str(event.get("tool_name") or "")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}
    cwd = str(event.get("cwd") or os.getcwd())
    if not denied(tool, tool_input, cwd):
        return 0
    log = os.environ.get("H2H_DENY_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as sink:
            sink.write(json.dumps({"tool": tool}) + "\n")
    print(json.dumps(decision()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
