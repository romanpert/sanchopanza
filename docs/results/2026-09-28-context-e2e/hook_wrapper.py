"""The command the autopilot's settings run for every hook in round 2: `sanchopanza hook`, logged.

    "command": "<python> hook_wrapper.py <evidence-dir> <keyfile>"

Claude Code pipes the hook event on stdin; this passes it to the installed `sanchopanza hook`
unchanged, with the TypeSafe key (read from `<keyfile>`) in that child's environment only, the
journal in `<evidence-dir>`, and `SANCHOPANZA_SESSION_MAX_USD`. Exit code, stdout and stderr are
the hook's own. One line per event goes to `<evidence-dir>/hooks.jsonl`: the event, the tool,
the exit code, the seconds, whether the output replaced the tool output (and the lengths
before and after) or added context (and how much). No event text is logged.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SANCHO = str(REPO / ".venv" / "Scripts" / "sanchopanza.exe")
SESSION_MAX_USD = 0.08  # per Claude Code session, for all the autopilot's decisions


def child_env(evidence: Path, keyfile: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ANTHROPIC_", "TYPESAFE_"))}
    key = Path(keyfile).read_text(encoding="utf-8").strip() if Path(keyfile).exists() else ""
    env = {
        **env,
        "SANCHOPANZA_JOURNAL": str(evidence / "journal.jsonl"),
        "SANCHOPANZA_SESSION_MAX_USD": str(SESSION_MAX_USD),
    }
    return {**env, "TYPESAFE_API_KEY": key} if key else env


def _length(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False)) if value is not None else 0


def summary(event: dict[str, Any], stdout: str) -> dict[str, Any]:
    try:
        out = json.loads(stdout) if stdout.strip() else {}
    except json.JSONDecodeError:
        out = {}
    specific = out.get("hookSpecificOutput") or {} if isinstance(out, dict) else {}
    updated = specific.get("updatedToolOutput")
    context = specific.get("additionalContext")
    return {
        "event": event.get("hook_event_name"),
        "tool": event.get("tool_name"),
        "response_chars": _length(event.get("tool_response")),
        "updated": updated is not None,
        "updated_chars": _length(updated) if updated is not None else None,
        "context_chars": len(context) if isinstance(context, str) else 0,
        "decision": out.get("decision") if isinstance(out, dict) else None,
        "permission": specific.get("permissionDecision"),
    }


def main(argv: list[str]) -> int:
    evidence, keyfile = Path(argv[0]), argv[1]
    evidence.mkdir(parents=True, exist_ok=True)
    payload = sys.stdin.buffer.read()
    try:
        event = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        event = {}
    started = time.time()
    proc = subprocess.run(
        [SANCHO, "hook"], input=payload, capture_output=True, env=child_env(evidence, keyfile)
    )
    stdout = proc.stdout.decode("utf-8", "replace")
    stderr = proc.stderr.decode("utf-8", "replace")
    line = {**summary(event, stdout), "exit": proc.returncode,
            "seconds": round(time.time() - started, 2), "stderr": stderr[-300:]}  # fmt: skip
    with (evidence / "hooks.jsonl").open("a", encoding="utf-8") as log:
        log.write(json.dumps(line) + "\n")
    sys.stdout.write(stdout)
    sys.stderr.write(stderr)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
