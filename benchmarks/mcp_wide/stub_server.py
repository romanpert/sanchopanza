"""Minimal MCP stdio server that serves every tool in catalog.json and implements none.

Every tools/call answers with an error result, so an agent can see and pick a tool
from a large, realistic catalog without anything happening. Transport is JSON-RPC 2.0
over newline-delimited stdin/stdout, stdlib only.

    MCP_WIDE_SERVERS=slack,stripe python stub_server.py   # only those servers
    python stub_server.py                                  # the whole catalog

MCP_WIDE_CATALOG overrides the catalog path.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROTOCOL_VERSION = "2025-06-18"
UNAVAILABLE = "Error: this tool is not available in this environment."
CATALOG = Path(os.environ.get("MCP_WIDE_CATALOG", Path(__file__).with_name("catalog.json")))


def load_tools(catalog_path: Path, wanted: str | None) -> list[dict]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    selected = {s.strip() for s in wanted.split(",") if s.strip()} if wanted else None
    known = {s["server"] for s in catalog["servers"]}
    if selected is not None and not selected <= known:
        missing = ", ".join(sorted(selected - known))
        raise SystemExit(f"MCP_WIDE_SERVERS names unknown servers: {missing}")
    return [
        {"name": t["name"], "description": t["description"], "inputSchema": t["input_schema"]}
        for s in catalog["servers"]
        if selected is None or s["server"] in selected
        for t in s["tools"]
    ]


def result(msg_id, payload: dict) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": payload}


def error(msg_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle(msg: dict, tools: list[dict]) -> dict | None:
    method = msg.get("method")
    msg_id = msg.get("id")
    is_request = "id" in msg
    if method == "initialize":
        requested = (msg.get("params") or {}).get("protocolVersion")
        return result(
            msg_id,
            {
                "protocolVersion": requested or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "mcp-wide-stub", "version": "0.1.0"},
            },
        )
    if method == "ping":
        return result(msg_id, {})
    if method == "tools/list":
        return result(msg_id, {"tools": tools})
    if method == "tools/call":
        return result(msg_id, {"content": [{"type": "text", "text": UNAVAILABLE}], "isError": True})
    if not is_request:  # notifications/initialized, notifications/cancelled, ...
        return None
    return error(msg_id, -32601, f"Method not found: {method}")


def serve(tools: list[dict]) -> None:
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            reply = error(None, -32700, "Parse error")
        else:
            if isinstance(msg, list) or not isinstance(msg, dict):
                reply = error(None, -32600, "Invalid Request")
            else:
                reply = handle(msg, tools)
        if reply is not None:
            out.write(json.dumps(reply, ensure_ascii=False) + "\n")
            out.flush()


def main() -> None:
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    except AttributeError:
        pass
    serve(load_tools(CATALOG, os.environ.get("MCP_WIDE_SERVERS")))


if __name__ == "__main__":
    main()
