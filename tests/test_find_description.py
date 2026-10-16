"""What the model reads about find_in_repo before it calls it: the tool description, the
parameters' own descriptions and the server's instructions (all fixed at session start).

The alwaysLoad probe (2026-10-03) put find in turn 1 with its schema and Haiku 4.5 called it in 0
of 10 sessions. Its description said what it finds, never when to use it; the rule lived in a skill
body that was never loaded, and Claude Code's own Grep description says to always use Grep.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sanchopanza.context.sources import kinds
from sanchopanza.harness import mcp


def _schema(tool: Any) -> dict[str, Any]:
    return getattr(tool, "input_schema", None) or tool.inputSchema


def _find_tool(tmp_path: Path) -> Any:
    server = mcp.build_archive_server(tmp_path / "archive", find=True, repo=tmp_path)
    return {t.name: t for t in asyncio.run(server.list_tools())}["find_in_repo"], server


def test_the_description_says_when_to_use_find_and_when_to_grep() -> None:
    text = mcp.FIND_DESCRIPTION.lower()
    assert "behaviour" in text  # the request describes behaviour ...
    assert "many files" in text and "nothing useful" in text  # ... or a search came back wide
    assert "grep" in text and "names" in text  # a named identifier: Grep instead
    assert "read" in text  # what to do with the keys


def test_the_description_stays_short_enough_to_pay_for_every_turn() -> None:
    assert len(mcp.FIND_DESCRIPTION) < 450
    assert len(mcp.FIND_INSTRUCTIONS) < 450


def test_every_parameter_has_a_description_and_kind_is_an_enum(tmp_path: Path) -> None:
    tool, _ = _find_tool(tmp_path)
    props = _schema(tool)["properties"]
    assert set(props) == {"query", "k", "kind"}
    assert all(props[name].get("description") for name in props)
    assert "words" in props["query"]["description"]  # the symptom, as the request puts it
    assert props["kind"]["enum"] == kinds()  # every registered kind stays callable
    assert props["kind"]["default"] == "code" and props["k"]["default"] == 8
    assert _schema(tool)["required"] == ["query"]


def test_the_kind_help_leads_with_code_and_keeps_the_other_kinds() -> None:
    help_ = mcp.KIND_HELP
    assert help_.startswith("code")
    for name in ("all", "symbol", "file", "memory", "archive"):
        assert name in help_
    assert "docs" in help_  # code leaves docs and config out; the help says where they are


def test_the_server_carries_the_same_rule_as_instructions(tmp_path: Path) -> None:
    _, server = _find_tool(tmp_path)
    assert server.instructions == mcp.find_instructions("sanchopanza-archive")
    text = mcp.FIND_INSTRUCTIONS.lower()
    assert "find_in_repo" in text and "behaviour" in text and "grep" in text


def test_a_server_without_find_carries_no_instructions(tmp_path: Path) -> None:
    lean = mcp.build_archive_server(tmp_path / "archive", find=False)
    assert not lean.instructions


def test_the_find_mcp_command_sets_the_instructions(monkeypatch) -> None:  # noqa: ANN001
    seen: dict[str, Any] = {}

    class Fake:
        def tool(self, description: str | None = None):  # noqa: ANN201
            return lambda fn: fn

        def run(self) -> None:
            seen["ran"] = True

    def fake_server(name: str, instructions: str = "") -> Fake:
        seen["instructions"] = instructions
        return Fake()

    monkeypatch.setattr(mcp, "_server", fake_server)
    mcp.main(["--tools", "find"])
    assert seen == {"instructions": mcp.FIND_INSTRUCTIONS, "ran": True}
    mcp.main(["--tools", "archive"])
    assert seen["instructions"] == ""


def test_the_tool_still_answers_with_the_described_parameters(tmp_path: Path) -> None:
    (tmp_path / "pager.py").write_text("def paginate(items, page):\n    return items\n", "utf-8")
    _, server = _find_tool(tmp_path)
    args = {"query": "paginate page", "k": 2, "kind": "code"}
    assert "pager.py:1-2" in str(asyncio.run(server.call_tool("find_in_repo", args)))
