"""Hooks read UTF-8 whatever the console code page: a command holding "Á" or "═" must still be
judged, not waved through because the hook crashed on decoding it (found live on Windows,
2026-09-30). Subprocesses with PYTHONIOENCODING=cp1252, the code page of a Windows console."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

EVENT = {
    "hook_event_name": "PreToolUse",
    "session_id": "utf8",
    "cwd": ".",
    "tool_name": "Bash",
    "tool_input": {"command": "rm -rf / --no-preserve-root  # ÁLVARO ═ Ð"},
}


def run_hook(sub: str, event: dict, tmp_path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("SANCHOPANZA_", "SANCHO_", "TYPESAFE_"))}  # fmt: skip
    env = {**env, "PYTHONIOENCODING": "cp1252", "SANCHOPANZA_GUARD_PROFILE": "coding",
           "SANCHOPANZA_JOURNAL": str(tmp_path / "journal.jsonl"),
           "SANCHOPANZA_GUARD_DIR": str(tmp_path / "guard"),
           "SANCHOPANZA_MEMORY_STORE": str(tmp_path / "store")}  # fmt: skip
    payload = json.dumps(event, ensure_ascii=False).encode("utf-8")
    return subprocess.run([sys.executable, "-m", "sanchopanza", sub], input=payload,
                          capture_output=True, env=env, timeout=120)  # fmt: skip


def test_the_shell_guard_denies_a_catastrophic_command_written_with_accents(tmp_path) -> None:
    done = run_hook("hook", EVENT, tmp_path)
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    out = json.loads(done.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert b"passed through" not in done.stderr


@pytest.mark.parametrize("sub", ["guard-hook", "memory-hook", "candor-hook"])
def test_the_other_hooks_take_an_accented_event_without_failing_open(sub: str, tmp_path) -> None:
    event = {**EVENT, "hook_event_name": "UserPromptSubmit", "prompt": "arregla ÁLVARO ═",
             "transcript_path": str(tmp_path / "none.jsonl")}  # fmt: skip
    done = run_hook(sub, event, tmp_path)
    assert done.returncode == 0
    err = done.stderr.decode("utf-8", "replace")
    assert "UnicodeDecodeError" not in err and "surrogates not allowed" not in err
