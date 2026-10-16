"""The default install made cheaper in tokens without taking capability out (2026-10-16): what
was paid on every request or every compaction is loaded when wanted, and each earlier
behaviour stays one flag away.

- find_in_repo is deferred behind Claude Code's tool search (no `alwaysLoad`): read in the
  2.1.287 binary, a server without the key has its tools "deferred when tool search is enabled",
  the model sees the bare name and fetches the schema with ToolSearch. `--find-always-load`
  puts the schema back in every request.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import cli
from sanchopanza.harness import install_defaults as defaults
from sanchopanza.harness import mcp

FIND_TOOL = "mcp__sanchopanza__find_in_repo"


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    settings = tmp_path / "proj" / ".claude" / "settings.json"
    return settings, tmp_path / "proj" / ".mcp.json"


def _install(settings: Path, *flags: str) -> int:
    return cli.main(["install", "--path", str(settings), *flags, "--write"])


def _find_entry(mcp_file: Path) -> dict[str, Any]:
    return json.loads(mcp_file.read_text("utf-8"))["mcpServers"]["sanchopanza"]


# ---- find_in_repo: deferred by default, always loaded on request --------------------------------


def test_the_find_server_entry_is_deferred_unless_asked_to_load_always() -> None:
    assert defaults.find_server_entry("sanchopanza hook") == {
        "command": "sanchopanza", "args": ["find-mcp"]}  # fmt: skip
    loaded = defaults.find_server_entry("sanchopanza hook", always_load=True)
    assert loaded == {"command": "sanchopanza", "args": ["find-mcp"], "alwaysLoad": True}
    auto = defaults.find_server_entry("sanchopanza hook", auto=True, always_load=True)
    assert auto["args"] == ["find-mcp", "--auto"] and auto["alwaysLoad"] is True


def test_the_install_dial_for_always_load_works_both_ways(tmp_path: Path) -> None:
    settings, mcp_file = _paths(tmp_path)
    assert _install(settings) == 0
    assert "alwaysLoad" not in _find_entry(mcp_file)
    assert _install(settings, "--find-always-load") == 0
    assert _find_entry(mcp_file)["alwaysLoad"] is True
    assert _install(settings) == 0  # a run without the flag defers it again
    assert "alwaysLoad" not in _find_entry(mcp_file)
    data = json.loads(settings.read_text("utf-8"))
    assert data["enabledMcpjsonServers"] == ["sanchopanza"]  # approved either way


def test_a_user_install_prints_the_line_that_matches_the_dial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    settings = tmp_path / "user" / "settings.json"
    assert cli.main(["install", "--path", str(settings)]) == 0
    line = next(x for x in capsys.readouterr().out.splitlines() if "claude mcp add-json" in x)
    assert "alwaysLoad" not in line and '"find-mcp"' in line
    assert cli.main(["install", "--path", str(settings), "--find-always-load"]) == 0
    line = next(x for x in capsys.readouterr().out.splitlines() if "claude mcp add-json" in x)
    assert '"alwaysLoad":true' in line


def test_the_server_instructions_name_the_deferred_tool_in_one_short_line() -> None:
    """Deferred, the description is not in the prompt until the tool is loaded: the server's
    instructions (an attachment at session start) are what says when to load it, so they name
    the tool as ToolSearch selects it, and they stay one line."""
    text = mcp.FIND_INSTRUCTIONS
    assert FIND_TOOL in text and "\n" not in text
    assert "behaviour" in text and "grep" in text.lower()
    assert len(text) < 200


def test_the_find_tool_carries_a_search_hint_for_tool_search(tmp_path: Path) -> None:
    """Claude Code scores a deferred tool's `_meta["anthropic/searchHint"]` in ToolSearch's
    keyword match (read in the 2.1.287 binary): a query in other words still finds find."""
    server = mcp.build_archive_server(tmp_path / "archive", find=True, repo=tmp_path)
    tool = {t.name: t for t in asyncio.run(server.list_tools())}["find_in_repo"]
    meta = getattr(tool, "meta", None) or getattr(tool, "_meta", None) or {}
    hint = meta.get(mcp.SEARCH_HINT_KEY, "")
    assert "code" in hint and "behaviour" in hint


def test_the_kind_help_is_short() -> None:
    assert len(mcp.KIND_HELP) < 180


# ---- the skill: a one-line description in every session, the body only when invoked ------------


def _front(text: str) -> dict[str, str]:
    head = text.split("---")[1]
    return dict(line.split(": ", 1) for line in head.strip().splitlines())


def test_the_skill_description_is_one_short_line_that_still_names_its_triggers() -> None:
    """Claude Code lists every skill's description in each session's first message; the body
    is read only when the skill is invoked (never, in 275 head-to-head sessions)."""
    front = _front(defaults.skill_text())
    assert front["name"] == "sanchopanza-code"
    description = front["description"]
    assert len(description) < 200
    for word in ("sanchopanza", "guard", "memory", "find_in_repo"):
        assert word in description


def test_the_skill_body_keeps_its_sections() -> None:
    body = defaults.skill_text().split("---", 2)[2]
    for heading in ("## 1. Finding code", "## 2. After a compaction", "## 3. Memory",
                    "## 4. Keep the context small", "## 5. When a hook speaks"):  # fmt: skip
        assert heading in body
