"""`sanchopanza install` run more than once, against odd files, and interrupted.

Findings of the 2026-09-25 review, each pinned by a test that failed before the fix:
running `install` then `install --scan-content` left two PostToolUse entries (every Task
result reviewed twice); the second `--write` overwrote the only backup of the original file;
a settings file holding a JSON list crashed with AttributeError; the write was not atomic;
tool names went into the matcher regex unescaped; and nothing turned scanning off again.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from sanchopanza.harness import HarnessConfig
from sanchopanza.harness.install import COMMAND, apply, matchers, merge, plan

SCANNING = HarnessConfig(scan_content=True)


def _ours(entries: list[dict]) -> list[dict]:
    return [e for e in entries if any(h.get("command") == COMMAND for h in e.get("hooks", []))]


def _write(path: Path, config: HarnessConfig, **kw) -> Path | None:
    return apply(plan(path, config, **kw))


def test_install_then_scan_content_leaves_one_entry_per_event(tmp_path):
    path = tmp_path / "settings.json"
    _write(path, HarnessConfig())
    _write(path, SCANNING)
    hooks = json.loads(path.read_text(encoding="utf-8"))["hooks"]
    for event in ("PreToolUse", "PostToolUse"):
        assert len(_ours(hooks[event])) == 1, hooks[event]
    assert _ours(hooks["PostToolUse"])[0]["matcher"] == matchers(SCANNING)["PostToolUse"]


def test_rerunning_without_scan_content_turns_it_off(tmp_path):
    path = tmp_path / "settings.json"
    _write(path, SCANNING)
    settings = plan(path, HarnessConfig())
    assert settings.changed
    assert any("SANCHOPANZA_SCAN_CONTENT" in line for line in settings.removed)
    apply(settings)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert "SANCHOPANZA_SCAN_CONTENT" not in written.get("env", {})
    post = _ours(written["hooks"]["PostToolUse"])
    assert len(post) == 1 and "WebFetch" not in post[0]["matcher"]


def test_a_custom_content_tools_list_is_dropped_with_scanning(tmp_path):
    path = tmp_path / "settings.json"
    _write(path, HarnessConfig(scan_content=True, content_tools=frozenset({"Fetch"})))
    assert (
        json.loads(path.read_text(encoding="utf-8"))["env"]["SANCHOPANZA_CONTENT_TOOLS"] == "Fetch"
    )
    _write(path, HarnessConfig())
    env = json.loads(path.read_text(encoding="utf-8")).get("env", {})
    assert "SANCHOPANZA_CONTENT_TOOLS" not in env


def test_the_same_install_twice_changes_nothing(tmp_path):
    path = tmp_path / "settings.json"
    _write(path, SCANNING)
    assert not plan(path, SCANNING).changed


def test_other_hooks_and_other_env_are_left_alone(tmp_path):
    path = tmp_path / "settings.json"
    mine = {"matcher": "Edit", "hooks": [{"type": "command", "command": "mine"}]}
    shared = {
        "matcher": "Agent|Task",
        "hooks": [
            {"type": "command", "command": "mine-too"},
            {"type": "command", "command": COMMAND},
        ],
    }
    path.write_text(
        json.dumps(
            {"hooks": {"PreToolUse": [mine], "PostToolUse": [shared]}, "env": {"KEEP": "1"}}
        ),
        encoding="utf-8",
    )
    _write(path, SCANNING)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert mine in written["hooks"]["PreToolUse"]
    post = written["hooks"]["PostToolUse"]
    assert {"matcher": "Agent|Task", "hooks": [{"type": "command", "command": "mine-too"}]} in post
    assert len(_ours(post)) == 1
    assert written["env"]["KEEP"] == "1"


def test_the_original_file_survives_any_number_of_writes(tmp_path):
    path = tmp_path / "settings.json"
    original = {"model": "opus"}
    path.write_text(json.dumps(original), encoding="utf-8")
    first = _write(path, HarnessConfig())
    second = _write(path, SCANNING)
    third = _write(path, HarnessConfig())
    assert first == tmp_path / "settings.json.bak"
    assert json.loads(first.read_text(encoding="utf-8")) == original
    assert second is not None and third is not None and len({first, second, third}) == 3
    # each later backup holds what the write before it produced
    assert "SANCHOPANZA_SCAN_CONTENT" not in json.loads(second.read_text(encoding="utf-8")).get(
        "env", {}
    )
    assert json.loads(third.read_text(encoding="utf-8"))["env"]["SANCHOPANZA_SCAN_CONTENT"] == "1"


def test_a_new_file_needs_no_backup(tmp_path):
    assert _write(tmp_path / "fresh" / "settings.json", HarnessConfig()) is None


@pytest.mark.parametrize("content", ["[]", "[1, 2]", '"text"', "3", "null"])
def test_settings_that_are_not_an_object_are_refused(tmp_path, content):
    path = tmp_path / "settings.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="not a JSON object"):
        plan(path, HarnessConfig())
    assert path.read_text(encoding="utf-8") == content


def test_merge_refuses_a_non_mapping():
    with pytest.raises(ValueError, match="not a JSON object"):
        merge([], HarnessConfig())  # type: ignore[arg-type]


def test_a_failed_write_leaves_the_file_and_no_temp_behind(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    settings = plan(path, HarnessConfig())

    def boom(src, dst):  # noqa: ANN001
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="disk full"):
        apply(settings)
    assert json.loads(path.read_text(encoding="utf-8")) == {"model": "opus"}
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".settings.json")]
    assert leftovers == []


def test_tool_names_are_escaped_in_the_matcher():
    config = HarnessConfig(
        delegate_tools=frozenset({"Task", "mcp.run(x)"}),
        search_tools=frozenset({"Web+Search"}),
        shell_tools=frozenset({"Bash"}),
    )
    pre = matchers(config)["PreToolUse"]
    pattern = re.compile(f"^(?:{pre})$")
    assert pattern.match("mcp.run(x)") and pattern.match("Web+Search")
    assert not pattern.match("mcpXrun(x)") and not pattern.match("WebbSearch")


def test_the_cli_reports_removals_and_the_real_backup(tmp_path, capsys):
    from sanchopanza.cli import main

    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert main(["install", "--path", str(path), "--scan-content", "--write"]) == 0
    assert "settings.json.bak)" in capsys.readouterr().out
    assert main(["install", "--path", str(path), "--write"]) == 0
    out = capsys.readouterr().out
    assert "- env: SANCHOPANZA_SCAN_CONTENT" in out and "settings.json.bak." in out
    assert main(["install", "--path", str(path), "--write"]) == 0
    assert "already wired" in capsys.readouterr().out
    path.write_text("[]", encoding="utf-8")
    assert main(["install", "--path", str(path), "--write"]) == 2
    assert "not a JSON object" in capsys.readouterr().err


def test_hook_commands_use_forward_slashes_on_windows():
    """A backslash path in a hook command never runs on Windows, silently: Claude Code hands
    the command to a POSIX shell (measured end to end, 0 events of 1)."""
    from sanchopanza.harness.install import portable_command

    raw = r"C:\venv\Scripts\python.exe C:\repo\hook.py"
    assert portable_command(raw, windows=True) == "C:/venv/Scripts/python.exe C:/repo/hook.py"
    assert portable_command(raw, windows=False) == raw
