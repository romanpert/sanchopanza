"""`sanchopanza install --prune`: the snapshot-pruning hook wired once, taken out cleanly, beside
other people's hooks and beside memory's PostToolUse entry on `Read`."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from sanchopanza.harness.generic import HarnessConfig
from sanchopanza.harness.install import (
    MEMORY_COMMAND,
    PRUNE_COMMAND,
    PRUNE_HOOKS,
    apply,
    plan,
)


def _settings(tmp_path: Path) -> Path:
    path = tmp_path / "settings.json"
    theirs = {"matcher": "Read", "hooks": [{"type": "command", "command": "theirs"}]}
    path.write_text(json.dumps({"hooks": {"PostToolUse": [theirs]}, "env": {"KEEP": "1"}}), "utf-8")
    return path


def _commands(doc: dict, event: str) -> list[str]:
    return [h["command"] for e in doc["hooks"].get(event, []) for h in e["hooks"]]


def test_install_prune_wires_one_hook_once_and_keeps_theirs(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), prune=True))
    doc = json.loads(path.read_text("utf-8"))
    for event, matcher in PRUNE_HOOKS.items():
        ours = [e for e in doc["hooks"][event] if e["hooks"][0]["command"] == PRUNE_COMMAND]
        assert len(ours) == 1 and ours[0]["matcher"] == matcher
    assert "theirs" in _commands(doc, "PostToolUse") and doc["env"]["KEEP"] == "1"
    again = plan(path, HarnessConfig(), prune=True)
    assert not again.added and not again.removed


def test_the_matcher_reaches_what_the_confirmed_arm_saw_on_any_server() -> None:
    """3p and 3r measured inline snapshots of `mcp__playwright__browser_*`. `Read` stays out:
    memory's hook chooses records by the lines a read returns, and a replaced read would leave
    it choosing by lines the agent never saw (indagis-70, 2026-10-03)."""
    matcher = re.compile(PRUNE_HOOKS["PostToolUse"])
    for tool in ("mcp__playwright__browser_snapshot", "mcp__playwright__browser_click",
                 "mcp__plugin_playwright_playwright__browser_navigate"):  # fmt: skip
        assert matcher.fullmatch(tool), tool
    for tool in ("Read", "Bash", "Edit", "WebFetch", "mcp__github__get_file_contents"):
        assert not matcher.fullmatch(tool), tool


def test_prune_is_off_unless_asked(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig()))
    assert PRUNE_COMMAND not in path.read_text("utf-8")


def test_install_without_prune_takes_ours_out_and_keeps_theirs(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), prune=True))
    removal = plan(path, HarnessConfig(), prune=False)
    assert any("(prune)" in line for line in removal.removed)
    apply(removal)
    doc = json.loads(path.read_text("utf-8"))
    assert PRUNE_COMMAND not in json.dumps(doc)
    assert "theirs" in _commands(doc, "PostToolUse")


def test_prune_and_memory_share_post_tool_use_without_stepping_on_each_other(
    tmp_path: Path,
) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), prune=True, memory=True))
    after = _commands(json.loads(path.read_text("utf-8")), "PostToolUse")
    assert after.count(PRUNE_COMMAND) == 1 and after.count(MEMORY_COMMAND) == 1
    apply(plan(path, HarnessConfig(), prune=False, memory=True))
    after = _commands(json.loads(path.read_text("utf-8")), "PostToolUse")
    assert PRUNE_COMMAND not in after and after.count(MEMORY_COMMAND) == 1
    apply(plan(path, HarnessConfig(), prune=True, memory=False))
    after = _commands(json.loads(path.read_text("utf-8")), "PostToolUse")
    assert MEMORY_COMMAND not in after and after.count(PRUNE_COMMAND) == 1


def test_the_installed_command_runs_the_browse_hook(tmp_path: Path) -> None:
    """The command the settings name prunes a large inline snapshot (BM25, no provider)."""
    transcript = tmp_path / "t.jsonl"
    ask = {"type": "user", "message": {"role": "user", "content": "Open Item number 377"}}
    transcript.write_text(json.dumps(ask) + "\n", encoding="utf-8")
    rows = "\n".join(f'- link "Item number {i} of the catalogue" [ref=e{i}]' for i in range(600))
    text = f"### Page state\n- Page URL: https://example.com/\n```yaml\n{rows}\n```"
    event = {"hook_event_name": "PostToolUse", "session_id": "s", "cwd": str(tmp_path),
             "tool_name": "mcp__playwright__browser_snapshot", "tool_input": {},
             "tool_response": [{"type": "text", "text": text}],
             "transcript_path": str(transcript)}  # fmt: skip
    env = {k: v for k, v in os.environ.items()
           if not k.startswith("SANCHOPANZA_") and k != "TYPESAFE_API_KEY"}  # fmt: skip
    env.update({"SANCHOPANZA_PROVIDER": "null","SANCHOPANZA_ARCHIVE": str(tmp_path / "a"),
                "SANCHOPANZA_JOURNAL": str(tmp_path / "j.jsonl")})  # fmt: skip
    run = subprocess.run(
        [sys.executable, "-m", "sanchopanza", "browse-hook"],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    out = json.loads(run.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PostToolUse"
    kept = json.dumps(out["updatedToolOutput"])
    assert len(kept) < len(text) / 2 and "Item number 377 of" in kept
