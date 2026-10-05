"""`sanchopanza install --knowledge`: the knowledge server (alwaysLoad) and its WebSearch/WebFetch
hook, owned by the flag, beside other people's hooks; ready to join the default install behind
`KNOWLEDGE_DEFAULT`."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from sanchopanza import cli
from sanchopanza.harness import install_knowledge
from sanchopanza.harness.generic import HarnessConfig
from sanchopanza.harness.install import FETCH_COMMAND, apply, plan
from sanchopanza.harness.knowledge_hook import (
    KNOWLEDGE_COMMAND,
    KNOWLEDGE_HOOKS,
    PICK_TOOL,
    READ_TOOL,
    SEARCH_TOOL,
)

SERVER = install_knowledge.KNOWLEDGE_SERVER


def _settings(tmp_path: Path) -> Path:
    path = tmp_path / "settings.json"
    theirs = {"matcher": "Bash", "hooks": [{"type": "command", "command": "theirs"}]}
    path.write_text(json.dumps({"hooks": {"PreToolUse": [theirs]}}), "utf-8")
    return path


def _commands(doc: dict, event: str) -> list[str]:
    return [h.get("command") for e in doc.get("hooks", {}).get(event, []) for h in e["hooks"]]


def _project(tmp_path: Path) -> tuple[Path, Path]:
    settings = tmp_path / "proj" / ".claude" / "settings.json"
    return settings, tmp_path / "proj" / ".mcp.json"


def _install(settings: Path, *flags: str) -> int:
    return cli.main(["install", "--path", str(settings), "--no-skill", "--context-budget", "0",
                     *flags, "--write"])  # fmt: skip


def test_knowledge_wires_one_hook_on_websearch_and_webfetch(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), knowledge=True))
    doc = json.loads(path.read_text("utf-8"))
    ours = [e for e in doc["hooks"]["PreToolUse"] if e["hooks"][0]["command"] == KNOWLEDGE_COMMAND]
    assert len(ours) == 1 and ours[0]["matcher"] == KNOWLEDGE_HOOKS["PreToolUse"]
    assert "theirs" in _commands(doc, "PreToolUse")
    again = plan(path, HarnessConfig(), knowledge=True)
    assert not again.added and not again.removed


def test_the_matcher_is_websearch_and_webfetch_only() -> None:
    matcher = re.compile(KNOWLEDGE_HOOKS["PreToolUse"])
    assert matcher.fullmatch("WebSearch") and matcher.fullmatch("WebFetch")
    assert not matcher.fullmatch("Bash")


def test_knowledge_takes_the_fetch_hooks_place(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), fetch=True))
    apply(plan(path, HarnessConfig(), fetch=True, knowledge=True))
    doc = json.loads(path.read_text("utf-8"))
    assert FETCH_COMMAND not in _commands(doc, "PreToolUse")
    assert KNOWLEDGE_COMMAND in _commands(doc, "PreToolUse")


def test_install_without_knowledge_takes_ours_out(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), knowledge=True))
    removal = plan(path, HarnessConfig())
    assert any("(knowledge)" in line for line in removal.removed)
    apply(removal)
    doc = json.loads(path.read_text("utf-8"))
    assert KNOWLEDGE_COMMAND not in json.dumps(doc) and "theirs" in _commands(doc, "PreToolUse")


def test_a_project_install_registers_the_server_always_loaded_and_approves_it(tmp_path) -> None:
    settings, mcp_file = _project(tmp_path)
    assert _install(settings, "--knowledge") == 0
    server = json.loads(mcp_file.read_text("utf-8"))["mcpServers"][SERVER]
    assert server == {"command": "sanchopanza", "args": ["knowledge-mcp"], "alwaysLoad": True}
    data = json.loads(settings.read_text("utf-8"))
    assert SERVER in data["enabledMcpjsonServers"]
    assert _install(settings, "--no-knowledge") == 0
    assert SERVER not in json.loads(mcp_file.read_text("utf-8"))["mcpServers"]
    assert SERVER not in json.loads(settings.read_text("utf-8")).get("enabledMcpjsonServers", [])


def test_a_user_install_prints_the_server_line(tmp_path: Path, capsys) -> None:
    path = _settings(tmp_path)
    assert _install(path, "--knowledge", "--no-find") == 0
    out = capsys.readouterr().out
    line = f"claude mcp add-json --scope user {SERVER} '"
    assert line in out
    entry = json.loads(out.split(line, 1)[1].split("'", 1)[0])
    assert entry == {"command": "sanchopanza", "args": ["knowledge-mcp"], "alwaysLoad": True}
    assert SERVER not in json.loads(path.read_text("utf-8")).get("enabledMcpjsonServers", [])


def test_the_default_install_follows_the_constant(tmp_path: Path, monkeypatch) -> None:
    settings, mcp_file = _project(tmp_path)
    assert install_knowledge.KNOWLEDGE_DEFAULT is False
    assert _install(settings) == 0
    assert KNOWLEDGE_COMMAND not in settings.read_text("utf-8")
    monkeypatch.setattr(install_knowledge, "KNOWLEDGE_DEFAULT", True)
    assert _install(settings) == 0
    assert KNOWLEDGE_COMMAND in settings.read_text("utf-8")
    assert SERVER in json.loads(mcp_file.read_text("utf-8"))["mcpServers"]


def test_scan_content_with_knowledge_scans_what_the_tools_return(tmp_path: Path) -> None:
    settings, _ = _project(tmp_path)
    assert _install(settings, "--knowledge", "--scan-content") == 0
    data = json.loads(settings.read_text("utf-8"))
    tools = set(data["env"]["SANCHOPANZA_CONTENT_TOOLS"].split(","))
    assert {SEARCH_TOOL, READ_TOOL, PICK_TOOL, "WebFetch", "WebSearch"} <= tools
    post = [e["matcher"] for e in data["hooks"]["PostToolUse"]
            if e["hooks"][0]["command"] == "sanchopanza hook"]  # fmt: skip
    assert post and re.compile(post[0]).fullmatch(READ_TOOL)


@pytest.mark.parametrize("words", [["sanchopanza", "hook"], ["py", "-m", "sanchopanza", "hook"]])
def test_the_server_entry_follows_the_hook_command(words: list[str]) -> None:
    entry = install_knowledge.server_entry(" ".join(words))
    assert entry["args"][-1] == "knowledge-mcp" and entry["alwaysLoad"] is True
    assert [entry["command"], *entry["args"][:-1]] == words[:-1]
