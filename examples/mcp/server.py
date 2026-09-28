"""sanchopanza's deliberate decision points as an MCP server over stdio.

    pip install sanchopanza[jev,mcp]
    TYPESAFE_API_KEY=... python examples/mcp/server.py

Claude Code:   claude mcp add sanchopanza -- python examples/mcp/server.py
Cursor:        .cursor/mcp.json -> {"mcpServers": {"sanchopanza":
                   {"command": "python", "args": ["examples/mcp/server.py"]}}}
Codex:         same shape in its MCP config.

Tools: verify_citation, evaluate_plan, align_entities, classify_field, triage_text.
"""

from __future__ import annotations

import os

from sanchopanza import JsonlJournal, Squire, _env
from sanchopanza.harness.mcp import build_server
from sanchopanza.providers import create

provider = "jev" if os.environ.get("TYPESAFE_API_KEY") else "null"
journal = JsonlJournal(_env.get("JOURNAL", "journal.jsonl"))
squire = Squire(create(provider), journal=journal)

if __name__ == "__main__":
    build_server(squire).run()
