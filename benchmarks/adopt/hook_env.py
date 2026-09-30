"""What every sanchopanza hook and MCP server of the benchmark runs: `sanchopanza <sub>` with the
session's own state and the TypeSafe key, which the agent's shell never sees.

    "command": "<python> hook_env.py <evidence-dir> <keyfile> <sub> [args...]"

`sanchopanza install` writes `sanchopanza hook`, `sanchopanza guard-hook` and, in `.mcp.json`,
`sanchopanza find-mcp`; the runner puts this in front of each, and changes nothing else. Hooks get
their event on stdin and give their output back unchanged; the MCP server keeps the stdio of the
client, since it lives for the whole session. One line per hook event goes to
`<evidence-dir>/hooks.jsonl` (event, tool, exit, seconds, output size), with no event text.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SANCHO = str(REPO / ".venv" / "Scripts" / "sanchopanza.exe")
SESSION_MAX_USD = "0.10"  # Jev, per Claude Code session


def environment(evidence: Path, keyfile: Path) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "TYPESAFE_"))}
    key = keyfile.read_text(encoding="utf-8").strip() if keyfile.exists() else ""
    return {**env, "SANCHOPANZA_JOURNAL": str(evidence / "journal.jsonl"),
            "SANCHOPANZA_GUARD_DIR": str(evidence / "guard"),
            "SANCHOPANZA_SESSION_MAX_USD": SESSION_MAX_USD,
            "SANCHOPANZA_CANDOR_LOCK": str(evidence / "candor-lock.json"),
            "SANCHOPANZA_CANDOR_DIR": str(evidence / "candor"),
            **({"TYPESAFE_API_KEY": key} if key else {})}  # fmt: skip


def main(argv: list[str]) -> int:
    evidence, keyfile, sub, rest = Path(argv[0]), Path(argv[1]), argv[2], argv[3:]
    evidence.mkdir(parents=True, exist_ok=True)
    env = environment(evidence, keyfile)
    if sub.endswith("-mcp"):  # a server: the client's stdio, for as long as it runs
        return subprocess.run([SANCHO, sub, *rest], env=env).returncode
    payload = sys.stdin.buffer.read()
    try:
        event = json.loads(payload.decode("utf-8"))
    except ValueError:
        event = {}
    started = time.time()
    done = subprocess.run([SANCHO, sub, *rest], input=payload, capture_output=True, env=env)
    with (evidence / "hooks.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps({"sub": sub, "event": event.get("hook_event_name"),
                              "source": event.get("source"), "tool": event.get("tool_name"),
                              "exit": done.returncode, "seconds": round(time.time() - started, 2),
                              "out_chars": len(done.stdout)}) + "\n")  # fmt: skip
    sys.stdout.buffer.write(done.stdout)
    sys.stderr.buffer.write(done.stderr)
    return done.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
