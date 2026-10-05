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
