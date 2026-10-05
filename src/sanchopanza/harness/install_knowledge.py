"""What `sanchopanza install --knowledge` writes besides its hook: the knowledge server.

- The hook (`harness.knowledge_hook` on `PreToolUse` WebSearch|WebFetch) is a browse set in
  `install_hooks`, owned by the flag; it takes the `--fetch` hook's place on WebFetch.
- The server (`sanchopanza knowledge-mcp`, `harness.knowledge_tool`) goes, for a project or
  local install, into the project's `.mcp.json` with `alwaysLoad` (deferred behind tool search,
  find was called 0 times in 108 sessions), approved by name in `enabledMcpjsonServers`; a user
  install prints the `claude mcp add-json` line instead, as find does.
- `KNOWLEDGE_DEFAULT` decides whether a plain `install` wires it. False until the knowledge
  layer is confirmed in live sessions (docs/results/2026-10-05-knowledge/).
- With `--scan-content`, `CONTENT_TOOLS` join the scanned tools: what `read` and `pick` return
  reaches the model with no reader in between.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .knowledge_hook import PICK_TOOL, READ_TOOL, SEARCH_TOOL

KNOWLEDGE_DEFAULT = False
KNOWLEDGE_SERVER = "sanchopanza-knowledge"
CONTENT_TOOLS = frozenset({SEARCH_TOOL, READ_TOOL, PICK_TOOL})


def server_entry(command: str = "sanchopanza hook") -> dict[str, Any]:
    """The server's entry, from the hook command: `<x> hook` becomes `<x> knowledge-mcp`."""
    words = command.split()
    if words and words[-1] == "hook":
        words = words[:-1]
    words = words or ["sanchopanza"]
    return {"command": words[0], "args": [*words[1:], "knowledge-mcp"], "alwaysLoad": True}


def user_line(command: str = "sanchopanza hook") -> str:
    entry = json.dumps(server_entry(command), separators=(",", ":"))
    return f"claude mcp add-json --scope user {KNOWLEDGE_SERVER} '{entry}'"


def mcp_json_change(
    path: Path,
    planned: Mapping[str, Any] | None,
    on: bool,
    command: str = "sanchopanza hook",
) -> dict[str, Any] | None:
    """The `.mcp.json` content with our server in (`on`) or out, on top of what the install
    already planned (`planned`, None when it changes nothing). None when nothing changes.

    With the server wanted, a file that is not a JSON object of servers is refused (ValueError);
    without it, such a file holds nothing of ours and is left alone."""
    from .install import _read_mcp_json

    if on:
        current: dict[str, Any] | None = _read_mcp_json(path)
    else:
        current = read_current(path)
        if current is None:
            return None if planned is None else dict(planned)
    base = dict(planned) if planned is not None else dict(current)
    servers = dict(base.get("mcpServers", {}))
    if not on and KNOWLEDGE_SERVER not in servers:
        return None if planned is None else base
    if on:
        servers[KNOWLEDGE_SERVER] = server_entry(command)
    else:
        servers.pop(KNOWLEDGE_SERVER)
    new = {**base, "mcpServers": servers}
    if planned is None and new == current:
        return None
    return new


def read_current(path: Path) -> dict[str, Any] | None:
    """The `.mcp.json` as it is, `{}` when missing, None when it is not a JSON object of
    servers."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        return None
    return data
