"""`sanchopanza install` by default (2026-09-30): the guard, a context budget, find_in_repo and the
skill, each owned by its flag and never taking what belongs to the owner."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sanchopanza import cli
from sanchopanza.harness import install_defaults as defaults


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    settings = tmp_path / "proj" / ".claude" / "settings.json"
    return settings, tmp_path / "proj" / ".mcp.json", settings.parent / "skills"


def _install(settings: Path, *flags: str) -> int:
    return cli.main(["install", "--path", str(settings), *flags, "--write"])


def test_the_default_install_wires_guard_budget_find_and_skill(tmp_path: Path) -> None:
    settings, mcp_file, skills = _paths(tmp_path)
    assert _install(settings) == 0
    data = json.loads(settings.read_text("utf-8"))
    assert data["env"][defaults.WINDOW] == "193000"
    assert data["env"][defaults.BUDGET] == "160000"
    assert set(data["hooks"]) >= {"PreCompact", "SessionStart", "PreToolUse", "PostToolUse"}
    assert data["enabledMcpjsonServers"] == ["sanchopanza"]
    server = json.loads(mcp_file.read_text("utf-8"))["mcpServers"]["sanchopanza"]
    assert server == {"command": "sanchopanza", "args": ["find-mcp"]}
    skill = (skills / "sanchopanza-code" / "SKILL.md").read_text("utf-8")
    assert skill.startswith("---\nname: sanchopanza-code\n")


def test_the_owner_window_is_kept_and_the_budget_not_marked(tmp_path: Path) -> None:
    settings, _, _ = _paths(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"env": {defaults.WINDOW: "400000"}}), "utf-8")
    assert _install(settings) == 0
    env = json.loads(settings.read_text("utf-8"))["env"]
    assert env[defaults.WINDOW] == "400000" and defaults.BUDGET not in env
    assert _install(settings, "--context-budget", "0") == 0
    assert json.loads(settings.read_text("utf-8"))["env"][defaults.WINDOW] == "400000"


def test_a_zero_budget_takes_ours_out(tmp_path: Path) -> None:
    settings, _, _ = _paths(tmp_path)
    assert _install(settings, "--context-budget", "120000") == 0
    env = json.loads(settings.read_text("utf-8"))["env"]
    assert env[defaults.WINDOW] == "153000"
    assert _install(settings, "--context-budget", "0") == 0
    env = json.loads(settings.read_text("utf-8")).get("env", {})
    assert defaults.WINDOW not in env and defaults.BUDGET not in env


def test_a_budget_below_the_floor_is_refused(tmp_path: Path) -> None:
    settings, _, _ = _paths(tmp_path)
    assert _install(settings, "--context-budget", "50000") == 2
    assert not settings.exists()


def test_no_find_takes_our_server_out_and_keeps_others(tmp_path: Path) -> None:
    settings, mcp_file, _ = _paths(tmp_path)
    mcp_file.parent.mkdir(parents=True)
    mcp_file.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), "utf-8")
    assert _install(settings) == 0
    assert set(json.loads(mcp_file.read_text("utf-8"))["mcpServers"]) == {"other", "sanchopanza"}
    assert _install(settings, "--no-find") == 0
    assert set(json.loads(mcp_file.read_text("utf-8"))["mcpServers"]) == {"other"}
    assert "enabledMcpjsonServers" not in json.loads(settings.read_text("utf-8"))


def test_a_malformed_mcp_json_leaves_find_out_without_failing(tmp_path: Path) -> None:
    settings, mcp_file, _ = _paths(tmp_path)
    mcp_file.parent.mkdir(parents=True)
    mcp_file.write_text("{ not json", "utf-8")
    assert _install(settings) == 0
    assert mcp_file.read_text("utf-8") == "{ not json"
    assert "enabledMcpjsonServers" not in json.loads(settings.read_text("utf-8"))


def test_no_skill_removes_our_copy_but_not_an_edited_one(tmp_path: Path) -> None:
    settings, _, skills = _paths(tmp_path)
    target = skills / "sanchopanza-code" / "SKILL.md"
    assert _install(settings) == 0 and target.exists()
    assert _install(settings, "--no-skill") == 0 and not target.exists()
    assert _install(settings) == 0
    target.write_text(target.read_text("utf-8") + "\nmy note\n", "utf-8")
    assert _install(settings, "--no-skill") == 0 and target.exists()


def test_the_install_is_idempotent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    settings, _, _ = _paths(tmp_path)
    assert _install(settings) == 0
    capsys.readouterr()
    assert _install(settings) == 0
    out = capsys.readouterr().out
    assert "already wired" in out and "skill written" not in out


def test_the_find_server_command_follows_the_hook_command() -> None:
    entry = defaults.find_server_entry("C:/venv/python.exe -m sanchopanza hook")
    assert entry == {"command": "C:/venv/python.exe", "args": ["-m", "sanchopanza", "find-mcp"]}
