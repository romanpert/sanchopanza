"""Real Playwright MCP snapshots, taken by talking to the server directly (no model, free).

python benchmarks/browse/snapshots.py --server PATH/TO/playwright-mcp URL [URL ...]

Writes each tool result, as the agent would receive it, to `fixtures/browse-snapshots/`. Used to
check the snapshot parser against the real format and to size what a page costs an agent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "fixtures" / "browse-snapshots"


def slug(url: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", url.lower().split("://", 1)[-1]).strip("-")[:80]


async def take(server: str, urls: list[str]) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command=server, args=["--headless", "--isolated"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        OUT.mkdir(parents=True, exist_ok=True)
        for url in urls:
            result = await session.call_tool("browser_navigate", {"url": url})
            text = "\n".join(b.text for b in result.content if getattr(b, "type", "") == "text")
            (OUT / f"{slug(url)}.txt").write_text(text, encoding="utf-8")
            print(json.dumps({"url": url, "chars": len(text)}))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--server", required=True)
    ap.add_argument("urls", nargs="+")
    args = ap.parse_args()
    asyncio.run(take(args.server, args.urls))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
