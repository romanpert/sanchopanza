"""The command every sanchopanza hook of the scene runs: `sanchopanza <sub>`, with Jev's key.

    "command": "<python> hook_key.py <evidence-dir> <keyfile> hook|candor-hook"

Claude Code pipes the hook event on stdin; this passes it on unchanged, with the TypeSafe key
(read from `<keyfile>`) in that child's environment only, so the agent's own shell never sees
it. The journal goes to `<evidence-dir>`, with a per-session Jev cap. Exit code, stdout and
stderr are the hook's own. One line per event goes to `<evidence-dir>/hooks.jsonl` (event,
tool, exit, seconds), no event text.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SANCHO = str(REPO / ".venv" / "Scripts" / "sanchopanza.exe")
SESSION_MAX_USD = "0.05"  # Jev, per Claude Code session


def main(argv: list[str]) -> int:
    evidence, keyfile, sub = Path(argv[0]), Path(argv[1]), argv[2]
    evidence.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "TYPESAFE_"))}
    key = keyfile.read_text(encoding="utf-8").strip() if keyfile.exists() else ""
    env = {**env, "SANCHOPANZA_JOURNAL": str(evidence / "journal.jsonl"),
           "SANCHOPANZA_SESSION_MAX_USD": SESSION_MAX_USD,
           **({"TYPESAFE_API_KEY": key} if key else {})}  # fmt: skip
    payload = sys.stdin.buffer.read()
    try:
        event = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        event = {}
    started = time.time()
    proc = subprocess.run([SANCHO, sub], input=payload, capture_output=True, env=env)
    line = {"sub": sub, "event": event.get("hook_event_name"), "tool": event.get("tool_name"),
            "exit": proc.returncode, "seconds": round(time.time() - started, 2),
            "stderr": proc.stderr.decode("utf-8", "replace")[-300:]}  # fmt: skip
    with (evidence / "hooks.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(line) + "\n")
    sys.stdout.write(proc.stdout.decode("utf-8", "replace"))
    sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
