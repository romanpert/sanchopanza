"""`sanchopanza install --candor`: candor's five hooks and its snapshot, wired once, taken out
cleanly, beside other people's hooks and the compaction guard."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from sanchopanza.harness.generic import HarnessConfig
from sanchopanza.harness.install import (
    CANDOR_COMMAND,
    CANDOR_ENV,
    CANDOR_HOOKS,
    GUARD_COMMAND,
    apply,
    plan,
)


def _settings(tmp_path: Path) -> Path:
    path = tmp_path / "settings.json"
    theirs = {"matcher": "*", "hooks": [{"type": "command", "command": "theirs"}]}
    path.write_text(json.dumps({"hooks": {"PreToolUse": [theirs]}, "env": {"KEEP": "1"}}), "utf-8")
    return path


def test_install_candor_wires_five_hooks_and_the_snapshot_once(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), candor=True))
    doc = json.loads(path.read_text("utf-8"))
    for event, matcher in CANDOR_HOOKS.items():
        ours = [e for e in doc["hooks"][event] if e["hooks"][0]["command"] == CANDOR_COMMAND]
        assert len(ours) == 1 and ours[0]["matcher"] == matcher
    assert doc["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "theirs"
    assert all(doc["env"][k] == v for k, v in CANDOR_ENV.items()) and doc["env"]["KEEP"] == "1"
    again = plan(path, HarnessConfig(), candor=True)
    assert not again.added and not again.removed


def test_install_without_candor_takes_ours_out_and_keeps_theirs(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), candor=True))
    removal = plan(path, HarnessConfig(), candor=False)
    assert any("(candor)" in line for line in removal.removed)
    apply(removal)
    doc = json.loads(path.read_text("utf-8"))
    flat = json.dumps(doc)
    assert CANDOR_COMMAND not in flat and "theirs" in flat
    assert not any(k in doc.get("env", {}) for k in CANDOR_ENV) and doc["env"]["KEEP"] == "1"


def test_candor_and_the_guard_share_post_tool_use_without_stepping_on_each_other(
    tmp_path: Path,
) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), candor=True, guard=True))
    post = json.loads(path.read_text("utf-8"))["hooks"]["PostToolUse"]
    commands = [e["hooks"][0]["command"] for e in post]
    assert commands.count(CANDOR_COMMAND) == 1 and commands.count(GUARD_COMMAND) == 1
    apply(plan(path, HarnessConfig(), candor=False, guard=True))
    post = json.loads(path.read_text("utf-8"))["hooks"]["PostToolUse"]
    commands = [e["hooks"][0]["command"] for e in post]
    assert CANDOR_COMMAND not in commands and commands.count(GUARD_COMMAND) == 1


def test_the_installed_command_runs_the_candor_hook(tmp_path: Path) -> None:
    """The command the settings name answers a prompt with the status-block request."""
    event = {"hook_event_name": "UserPromptSubmit", "session_id": "s", "cwd": str(tmp_path),
             "prompt": "fix the parser"}  # fmt: skip
    env = {**os.environ, "SANCHOPANZA_CANDOR_DIR": str(tmp_path / "state"),
           "SANCHOPANZA_CANDOR_LOCK": str(tmp_path / "lock.json")}  # fmt: skip
    run = subprocess.run(
        [sys.executable, "-m", "sanchopanza", "candor-hook"],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    context = json.loads(run.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "STATUS: done | partial | blocked" in context
