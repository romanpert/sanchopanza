"""`sanchopanza install --passages`: the passages hook and its two settings, wired only on ask."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from sanchopanza import cli
from sanchopanza.harness.install_passages import (
    PASSAGES_COMMAND,
    PASSAGES_ENV,
    PASSAGES_HOOKS,
)


def _settings(tmp_path: Path) -> Path:
    path = tmp_path / "settings.json"
    theirs = {"matcher": "Read", "hooks": [{"type": "command", "command": "theirs"}]}
    path.write_text(json.dumps({"hooks": {"PostToolUse": [theirs]}, "env": {"KEEP": "1"}}), "utf-8")
    return path


def _ours(doc: dict) -> list[dict]:
    return [e for e in doc.get("hooks", {}).get("PostToolUse", [])
            if any(h.get("command") == PASSAGES_COMMAND for h in e["hooks"])]  # fmt: skip


def _install(path: Path, *extra: str) -> int:
    return cli.main(["install", "--path", str(path), "--no-skill", "--no-find", *extra, "--write"])


def test_off_by_default(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    assert _install(path) == 0
    doc = json.loads(path.read_text("utf-8"))
    assert not _ours(doc) and not any(k in doc.get("env", {}) for k in PASSAGES_ENV)


def test_the_flag_wires_one_hook_and_its_settings_once(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    assert _install(path, "--passages") == 0
    doc = json.loads(path.read_text("utf-8"))
    [entry] = _ours(doc)
    assert entry["matcher"] == PASSAGES_HOOKS["PostToolUse"]
    assert doc["env"]["SANCHOPANZA_PASSAGES_FRACTION"] == "0.25"
    assert doc["env"]["SANCHOPANZA_PASSAGES_TOKENS"] == "2000"
    assert doc["env"]["KEEP"] == "1" and any(
        h["command"] == "theirs" for e in doc["hooks"]["PostToolUse"] for h in e["hooks"])
    assert _install(path, "--passages") == 0
    assert len(_ours(json.loads(path.read_text("utf-8")))) == 1


def test_the_tenth_arm_and_removal(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    assert _install(path, "--passages", "--passages-fraction", "0.10") == 0
    assert json.loads(path.read_text("utf-8"))["env"]["SANCHOPANZA_PASSAGES_FRACTION"] == "0.1"
    assert _install(path) == 0
    doc = json.loads(path.read_text("utf-8"))
    assert not _ours(doc) and "SANCHOPANZA_PASSAGES_FRACTION" not in doc["env"]
    assert doc["env"]["KEEP"] == "1"


def test_bad_values_and_the_autopilot_are_refused(tmp_path: Path, capsys) -> None:
    path = _settings(tmp_path)
    assert _install(path, "--passages", "--passages-fraction", "1.5") == 2
    assert _install(path, "--passages", "--passages-tokens", "10") == 2
    assert _install(path, "--passages", "--autopilot") == 2
    assert "--autopilot" in capsys.readouterr().err
    assert not _ours(json.loads(path.read_text("utf-8")))


def test_the_matcher_reaches_shell_and_read_only() -> None:
    matcher = re.compile(PASSAGES_HOOKS["PostToolUse"])
    for tool in ("Bash", "PowerShell", "Read"):
        assert matcher.fullmatch(tool), tool
    for tool in ("Grep", "Edit", "WebFetch", "mcp__x__read", "BashOutput"):
        assert not matcher.fullmatch(tool), tool


def test_the_installed_command_runs_the_hook(tmp_path: Path) -> None:
    """The command the settings name, run as Claude Code runs it: JSON on stdin, no provider."""
    from tests.test_passages_cut import pytest_log

    transcript = tmp_path / "t.jsonl"
    ask = {"type": "user", "message": {"role": "user", "content": "why does test_add fail"}}
    transcript.write_text(json.dumps(ask) + "\n", encoding="utf-8")
    log = pytest_log()
    event = {"hook_event_name": "PostToolUse", "session_id": "s", "cwd": str(tmp_path),
             "tool_name": "Bash", "tool_use_id": "toolu_1",
             "tool_input": {"command": "pytest -v"},
             "tool_response": {"stdout": log, "stderr": "", "interrupted": False},
             "transcript_path": str(transcript)}  # fmt: skip
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("SANCHOPANZA_") and k != "TYPESAFE_API_KEY"}  # fmt: skip
    env.update({"SANCHOPANZA_PROVIDER": "null", "SANCHOPANZA_ARCHIVE": str(tmp_path / "a"),
                "SANCHOPANZA_JOURNAL": str(tmp_path / "j.jsonl")})  # fmt: skip
    run = subprocess.run([sys.executable, "-m", "sanchopanza", "passages-hook"],
                         input=json.dumps(event), capture_output=True, text=True,
                         encoding="utf-8", env=env, timeout=60, check=False)  # fmt: skip
    assert run.returncode == 0, run.stderr
    stdout = json.loads(run.stdout)["hookSpecificOutput"]["updatedToolOutput"]["stdout"]
    assert "E       assert -1 == 3" in stdout and len(stdout) < len(log) / 2
    journal = [json.loads(line) for line in (tmp_path / "j.jsonl").read_text("utf-8").splitlines()]
    assert any(e["kind"] == "passages" and e["data"]["acted"] for e in journal)
