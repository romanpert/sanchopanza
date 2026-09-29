"""Free: the guard's hook command, run as Claude Code runs it, on a recorded native session.

Takes the recorded Haiku session of `2026-09-28-context-e2e` t01 arm N (a native `/compact`
after phase A, then phase B), writes the G arm's settings into a scratch evidence folder, and
runs the exact hook command line through `bash -c` (Claude Code runs command hooks through a
POSIX shell) with the three events it would send: PreCompact (auto), SessionStart (compact) and
a PostToolUse for a re-run of the probe. Checks the stdout shape of each and prints what the
model would receive. No model, no key, no network.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import arms  # noqa: E402

GIT_BASH = r"C:\Program Files\Git\bin\bash.exe"  # the shell Claude Code uses on Windows
SESSION = Path.home() / ".cache" / "sanchopanza" / "context-e2e" / "runs" / "t01-orders" / "N" / "session.jsonl"


def call(command: str, event: dict) -> subprocess.CompletedProcess:
    return subprocess.run([GIT_BASH, "-c", command], input=json.dumps(event), capture_output=True,
                          text=True, encoding="utf-8", timeout=120)  # fmt: skip


def main() -> int:
    if not SESSION.exists():
        print(f"no recorded session at {SESSION}")
        return 1
    ev = arms.ROOT / "dry"
    shutil.rmtree(ev, ignore_errors=True)
    settings = json.loads(arms.guard_settings((ev.mkdir(parents=True) or ev), "rule", None).read_text("utf-8"))
    command = settings["hooks"]["PreCompact"][0]["hooks"][0]["command"]
    base = {"session_id": "dry-session", "transcript_path": str(SESSION).replace("\\", "/"), "cwd": str(ev)}
    pre = call(command, {**base, "hook_event_name": "PreCompact", "trigger": "auto", "custom_instructions": None})
    start = call(command, {**base, "hook_event_name": "SessionStart", "source": "compact"})
    rerun = call(command, {**base, "hook_event_name": "PostToolUse", "tool_name": "Bash",
                           "tool_input": {"command": "python tools/probe.py"},
                           "tool_response": {"stdout": "error: probe state already consumed"}})  # fmt: skip
    checks = {
        "precompact_exit_0": pre.returncode == 0,
        "precompact_note": pre.stdout.startswith("The harness will attach"),
        "session_start_json": start.returncode == 0
        and json.loads(start.stdout or "{}").get("hookSpecificOutput", {}).get("hookEventName") == "SessionStart",
        "block_has_probe_code": "PRB-9015" in start.stdout,
        "block_has_token": "RT-6Z4FRFLG7W" in start.stdout,
        "echo_json": rerun.returncode == 0 and "additionalContext" in rerun.stdout,
        "no_stderr": not (pre.stderr or start.stderr or rerun.stderr),
        "log_written": (ev / "guard-log.jsonl").exists() and (ev / "guard-events.jsonl").exists(),
    }
    context = json.loads(start.stdout)["hookSpecificOutput"]["additionalContext"] if checks["session_start_json"] else ""
    print(json.dumps({"checks": checks, "block_chars": len(context)}, indent=1))
    print("---- what the model would receive after the summary ----")
    print(context)
    print("---- echo on a re-run ----")
    print(json.loads(rerun.stdout)["hookSpecificOutput"]["additionalContext"] if checks["echo_json"] else rerun.stdout)
    if pre.stderr or start.stderr or rerun.stderr:
        print("stderr:", pre.stderr, start.stderr, rerun.stderr)
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
