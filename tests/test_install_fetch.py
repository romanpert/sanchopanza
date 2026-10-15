"""`sanchopanza install --fetch`: the PreToolUse hook on WebFetch wired once, taken out cleanly,
beside other people's hooks; and the server's command line printed by the CLI."""

from __future__ import annotations

import json
import re
from pathlib import Path

from sanchopanza.cli import main
from sanchopanza.harness.generic import HarnessConfig
from sanchopanza.harness.install import FETCH_COMMAND, FETCH_HOOKS, apply, plan


def _settings(tmp_path: Path) -> Path:
    path = tmp_path / "settings.json"
    theirs = {"matcher": "Bash", "hooks": [{"type": "command", "command": "theirs"}]}
    path.write_text(json.dumps({"hooks": {"PreToolUse": [theirs]}}), "utf-8")
    return path


def _commands(doc: dict, event: str) -> list[str]:
    return [h["command"] for e in doc["hooks"].get(event, []) for h in e["hooks"]]


def test_install_fetch_wires_one_hook_on_webfetch_and_keeps_theirs(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), fetch=True))
    doc = json.loads(path.read_text("utf-8"))
    ours = [e for e in doc["hooks"]["PreToolUse"] if e["hooks"][0]["command"] == FETCH_COMMAND]
    assert len(ours) == 1 and ours[0]["matcher"] == FETCH_HOOKS["PreToolUse"]
    assert "theirs" in _commands(doc, "PreToolUse")
    again = plan(path, HarnessConfig(), fetch=True)
    assert not again.added and not again.removed


def test_the_matcher_is_webfetch_only() -> None:
    matcher = re.compile(FETCH_HOOKS["PreToolUse"])
    assert matcher.fullmatch("WebFetch")
    assert not matcher.fullmatch("WebSearch")


def test_install_without_fetch_takes_ours_out(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), fetch=True))
    removal = plan(path, HarnessConfig(), fetch=False)
    assert any("(fetch)" in line for line in removal.removed)
    apply(removal)
    doc = json.loads(path.read_text("utf-8"))
    assert FETCH_COMMAND not in json.dumps(doc)
    assert "theirs" in _commands(doc, "PreToolUse")


def test_the_cli_prints_the_server_line(tmp_path: Path, capsys) -> None:
    path = _settings(tmp_path)
    code = main(["install", "--path", str(path), "--fetch", "--no-find", "--no-skill",
                 "--context-budget", "0", "--write"])  # fmt: skip
    assert code == 0
    out = capsys.readouterr().out
    assert "claude mcp add-json --scope user sanchopanza-fetch" in out
    entry = json.loads(out.split("sanchopanza-fetch '", 1)[1].split("'", 1)[0])
    assert entry == {"command": "sanchopanza", "args": ["fetch-mcp"], "alwaysLoad": True}


# --- S seal (2026-10-05): the server the hook sends WebFetch to is registered with it --------


def _project(tmp_path: Path) -> Path:
    path = tmp_path / "proj" / ".claude" / "settings.json"
    path.parent.mkdir(parents=True)
    return path


def _install(path: Path, *flags: str) -> int:
    return main(["install", "--path", str(path), *flags, "--no-find", "--no-skill",
                 "--context-budget", "0", "--write"])  # fmt: skip


def test_a_project_install_registers_and_approves_the_fetch_server(tmp_path: Path) -> None:
    """The hook denies a URL's first WebFetch and names `fetch_passages`; without the server in
    the project's .mcp.json the agent was sent to a tool that did not exist (S seal draft)."""
    from sanchopanza.harness.fetch_hook import TOOL_NAME
    from sanchopanza.harness.install import FETCH_SERVER

    path = _project(tmp_path)
    assert _install(path, "--fetch") == 0
    servers = json.loads((path.parent.parent / ".mcp.json").read_text("utf-8"))["mcpServers"]
    assert servers[FETCH_SERVER] == {"command": "sanchopanza", "args": ["fetch-mcp"],
                                     "alwaysLoad": True}  # fmt: skip
    assert f"mcp__{FETCH_SERVER}__fetch_passages" == TOOL_NAME
    doc = json.loads(path.read_text("utf-8"))
    assert FETCH_SERVER in doc["enabledMcpjsonServers"]
    assert _install(path) == 0
    servers = json.loads((path.parent.parent / ".mcp.json").read_text("utf-8"))["mcpServers"]
    assert FETCH_SERVER not in servers
    assert FETCH_SERVER not in json.loads(path.read_text("utf-8")).get("enabledMcpjsonServers", [])


def test_a_project_install_keeps_find_and_fetch_side_by_side(tmp_path: Path) -> None:
    from sanchopanza.harness.install import FETCH_SERVER, FIND_SERVER

    path = _project(tmp_path)
    assert main(["install", "--path", str(path), "--fetch", "--find", "--no-skill",
                 "--context-budget", "0", "--write"]) == 0  # fmt: skip
    servers = json.loads((path.parent.parent / ".mcp.json").read_text("utf-8"))["mcpServers"]
    assert {FIND_SERVER, FETCH_SERVER} <= set(servers)
    approved = json.loads(path.read_text("utf-8"))["enabledMcpjsonServers"]
    assert approved == [FIND_SERVER, FETCH_SERVER]
