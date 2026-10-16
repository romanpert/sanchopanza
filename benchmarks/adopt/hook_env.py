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
# The runner passes the sanchopanza it installed (a frozen copy for held-out tasks).
SANCHO = os.environ.get("ADOPT_SANCHO") or str(REPO / ".venv" / "Scripts" / "sanchopanza.exe")
SESSION_MAX_USD = "0.10"  # Jev, per Claude Code session (phases A and B)
# The runner's ceiling for a session it resumes call after call (long chains: 0.50 per chain).
# 0.10 held for the whole resumed session, and past it the hooks failed open in silence
# (long-session pre-mortem, f).
CEILING_VAR = "ADOPT_JEV_MAX_USD"
# The guard-pointers lot (docs/results/2026-10-16-guard-pointers): its arms are the default install,
# whose pointer guard archives one-shot output beside the project (`<cwd>/.sanchopanza/archive`)
# and tells the agent to Read it there. With this variable set to 1 the archive is left where the
# install puts it (not the evidence folder, outside the agent's working copy), and the guard's own
# log (`SANCHOPANZA_GUARD_LOG`: chooser and block size per compaction) goes to the evidence.
GUARD_LOT_VAR = "ADOPT_GUARD_LOT"


def environment(
    evidence: Path, keyfile: Path, base: dict[str, str] | None = None
) -> dict[str, str]:
    """The hooks' environment over `base` (this process's by default: Claude Code's, which the
    runner built with `run.child_env`; the decider probe passes that same one)."""
    source = os.environ if base is None else base
    env = {k: v for k, v in source.items() if not k.startswith(("ANTHROPIC_", "TYPESAFE_"))}
    key = keyfile.read_text(encoding="utf-8").strip() if keyfile.exists() else ""
    lot = source.get(GUARD_LOT_VAR) == "1"
    archive = ({"SANCHOPANZA_GUARD_LOG": str(evidence / "guard.jsonl")} if lot else
               {"SANCHOPANZA_ARCHIVE": str(evidence / "archive")})  # fmt: skip
    return {**env, "SANCHOPANZA_JOURNAL": str(evidence / "journal.jsonl"),
            "SANCHOPANZA_GUARD_DIR": str(evidence / "guard"),
            "SANCHOPANZA_SESSION_MAX_USD": source.get(CEILING_VAR) or SESSION_MAX_USD,
            "SANCHOPANZA_CANDOR_LOCK": str(evidence / "candor-lock.json"),
            "SANCHOPANZA_CANDOR_DIR": str(evidence / "candor"),
            "SANCHOPANZA_MEMORY_STORE": str(evidence / "memory"),
            "SANCHOPANZA_MEMORY_STORE_LOG": str(evidence / "memory.jsonl"),
            # The S line's other state, per session too (S-SEAL-DRAFT: else ~/.sancho)
            "SANCHOPANZA_CRAWL_DIR": str(evidence / "crawl"),
            "SANCHOPANZA_FETCH_DIR": str(evidence / "fetch"),
            **archive, **({"TYPESAFE_API_KEY": key} if key else {})}  # fmt: skip


def main(argv: list[str]) -> int:
    evidence, keyfile, sub, rest = Path(argv[0]), Path(argv[1]), argv[2], argv[3:]
    evidence.mkdir(parents=True, exist_ok=True)
    env = environment(evidence, keyfile)
    key = "TYPESAFE_API_KEY" in env  # amendment 5: positive evidence the decider could be built
    if sub.endswith("-mcp"):  # a server: the client's stdio, for as long as it runs
        with (evidence / "hooks.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"sub": sub, "event": "server start", "key": key}) + "\n")
        code = subprocess.run([SANCHO, sub, *rest], env=env).returncode
        with (evidence / "hooks.jsonl").open("a", encoding="utf-8") as log:
            end = {"sub": sub, "event": "server end", "key": key, "exit": code}
            log.write(json.dumps(end) + "\n")
        return code
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
                              "out_chars": len(done.stdout), "key": key,
                              # amendment 5: "no decider" was said here, and nobody kept it
                              **({"stderr": done.stderr.decode("utf-8", "replace")[-500:]}
                                 if done.stderr else {})}) + "\n")  # fmt: skip
    sys.stdout.buffer.write(done.stdout)
    sys.stderr.buffer.write(done.stderr)
    return done.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
