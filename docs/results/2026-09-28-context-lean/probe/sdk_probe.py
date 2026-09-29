"""Mechanics probe through the Claude Agent SDK (Python): the same chained reads as probe.py.

    python sdk_probe.py <label>

One `query()` under one `asyncio.run`, with the compaction plugin passed as a local plugin,
auto-compaction forced low through the session's environment, and the masking command as in
probe.py (`--mask-turns 3`: a mechanics check, not the experiment's setting). Afterwards the
transcript is read with probe.read's logic: if the context of the first call after each
compaction is smaller than the last before it, the SDK path applies the masking too.
Needs `python probe.py build` first; spends at most CAP dollars of the subscription.
"""

from __future__ import annotations

import asyncio
import json
import sys

import probe
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, query


async def session(label: str) -> dict:
    evidence = probe.ROOT / label
    evidence.mkdir(parents=True, exist_ok=True)
    options = ClaudeAgentOptions(
        model=probe.MODEL,
        max_budget_usd=probe.CAP,
        cwd=str(probe.ROOT / "work"),
        allowed_tools=["Read"],
        tools=["Read"],
        permission_mode="dontAsk",
        setting_sources=["project"],
        strict_mcp_config=True,
        plugins=[{"type": "local", "path": str(probe.ROOT / "plugin")}],
        env=probe.env_for(evidence),
    )
    result: dict = {"assistant_messages": 0}
    async for message in query(prompt=probe.PROMPT, options=options):
        if isinstance(message, AssistantMessage):
            result["assistant_messages"] += 1
        if isinstance(message, ResultMessage):
            result.update(
                session_id=message.session_id,
                cost=message.total_cost_usd,
                subtype=message.subtype,
                answer=str(message.result)[:200],
            )
    (evidence / "live.json").write_text(json.dumps(result) + "\n", encoding="utf-8")
    return result


def main(argv: list[str]) -> int:
    probe.PCT = "55"  # the SDK session starts at ~6k, not ~38k: 44,000 tokens
    if len(argv) > 1:
        probe.STUB = " --stub-style " + argv[1]
    print(json.dumps(asyncio.run(session(argv[0]))))
    probe.read(argv[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
