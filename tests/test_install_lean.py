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


# ---- the guard: pointers by default, the whole-results block one flag away ----------------------

CHOOSER = "SANCHOPANZA_GUARD_CHOOSER"


def _guard_commands(settings: Path) -> dict[str, list[str]]:
    hooks = json.loads(settings.read_text("utf-8")).get("hooks", {})
    return {
        event: [h["command"] for e in hooks.get(event, []) for h in e.get("hooks", [])
                if "guard-hook" in h.get("command", "")]
        for event in ("PreCompact", "SessionStart", "PostToolUse")
    }  # fmt: skip


def _env(settings: Path) -> dict[str, str]:
    return json.loads(settings.read_text("utf-8")).get("env", {})


def test_the_default_guard_is_one_command_per_event_and_names_no_chooser(tmp_path: Path) -> None:
    """The pointer block fits one hook's inline limit: no split, and the hook's own default
    chooser (pointers) is the one used."""
    settings, _ = _paths(tmp_path)
    assert _install(settings) == 0
    one = ["sanchopanza guard-hook"]
    assert _guard_commands(settings) == {"PreCompact": one, "SessionStart": one, "PostToolUse": one}
    assert CHOOSER not in _env(settings)


def test_the_guard_full_dial_works_both_ways(tmp_path: Path) -> None:
    settings, _ = _paths(tmp_path)
    assert _install(settings, "--guard-full") == 0
    commands = _guard_commands(settings)
    assert commands["PreCompact"] == ["sanchopanza guard-hook --parts 6"]
    assert commands["SessionStart"] == [f"sanchopanza guard-hook --part {i} --parts 6"
                                        for i in range(1, 7)]  # fmt: skip
    assert _env(settings)[CHOOSER] == "struct"
    assert _install(settings) == 0  # a run without the flag: back to the pointer block
    assert _guard_commands(settings)["SessionStart"] == ["sanchopanza guard-hook"]
    assert CHOOSER not in _env(settings)


def test_a_chooser_the_owner_set_is_theirs_to_keep(tmp_path: Path) -> None:
    settings, _ = _paths(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"env": {CHOOSER: "keep"}}), "utf-8")
    assert _install(settings) == 0
    assert _env(settings)[CHOOSER] == "keep"


def test_no_guard_takes_our_chooser_and_hooks_out(tmp_path: Path) -> None:
    settings, _ = _paths(tmp_path)
    assert _install(settings, "--guard-full") == 0
    assert _install(settings, "--no-guard") == 0
    assert CHOOSER not in _env(settings)
    assert _guard_commands(settings) == {"PreCompact": [], "SessionStart": [], "PostToolUse": []}


# ---- the whole default plan, and every earlier behaviour one flag away ---------------------------


def test_the_default_plan_is_the_lean_one_and_each_old_behaviour_is_one_flag_away(
    tmp_path: Path,
) -> None:
    settings, mcp_file = _paths(tmp_path)
    assert _install(settings) == 0
    lean = (_find_entry(mcp_file), _guard_commands(settings), _env(settings).get(CHOOSER))
    assert lean == ({"command": "sanchopanza", "args": ["find-mcp"]},
                    {e: ["sanchopanza guard-hook"] for e in ("PreCompact", "SessionStart",
                                                             "PostToolUse")},
                    None)  # fmt: skip
    skill = settings.parent / "skills" / "sanchopanza-code" / "SKILL.md"
    assert len(_front(skill.read_text("utf-8"))["description"]) < 200

    assert _install(settings, "--find-always-load", "--guard-full") == 0
    assert _find_entry(mcp_file)["alwaysLoad"] is True
    assert len(_guard_commands(settings)["SessionStart"]) == 6
    assert _env(settings)[CHOOSER] == "struct"

    assert _install(settings) == 0  # and back
    assert (_find_entry(mcp_file), _guard_commands(settings), _env(settings).get(CHOOSER)) == lean


def test_the_python_api_benchmarks_call_has_the_same_dial(tmp_path: Path) -> None:
    """`plan` and `mcp_json_changes` (what sealed runners call): lean by default, each earlier
    behaviour one keyword away."""
    from sanchopanza.harness.generic import HarnessConfig
    from sanchopanza.harness.install import mcp_json_changes, plan

    path = tmp_path / "settings.json"
    lean = plan(path, HarnessConfig(), guard=True).merged
    full = plan(path, HarnessConfig(), guard=True, guard_full=True).merged
    assert len(lean["hooks"]["SessionStart"][0]["hooks"]) == 1
    assert CHOOSER not in lean.get("env", {})
    assert len(full["hooks"]["SessionStart"][0]["hooks"]) == 6
    assert full["env"][CHOOSER] == "struct"
    target = tmp_path / ".mcp.json"
    deferred = mcp_json_changes(target, False, find=True)["mcpServers"]["sanchopanza"]
    loaded = mcp_json_changes(target, False, find=True, find_always_load=True)
    assert "alwaysLoad" not in deferred
    assert loaded["mcpServers"]["sanchopanza"]["alwaysLoad"] is True


# ---- review fix: a chooser the owner set is never overwritten nor removed -----------------------

CHOOSER_BY = "SANCHOPANZA_GUARD_CHOOSER_BY"


def test_guard_full_marks_its_chooser_and_a_plain_install_removes_only_ours(tmp_path: Path) -> None:
    settings, _ = _paths(tmp_path)
    assert _install(settings, "--guard-full") == 0
    assert _env(settings)[CHOOSER] == "struct" and _env(settings)[CHOOSER_BY] == "sanchopanza"
    assert _install(settings) == 0
    assert CHOOSER not in _env(settings) and CHOOSER_BY not in _env(settings)


def test_an_owner_struct_is_kept_by_a_plain_install(tmp_path: Path) -> None:
    settings, _ = _paths(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"env": {CHOOSER: "struct"}}), "utf-8")
    assert _install(settings) == 0
    assert _env(settings)[CHOOSER] == "struct" and CHOOSER_BY not in _env(settings)
    assert _install(settings, "--guard-full") == 0  # theirs already: left unmarked
    assert _install(settings) == 0
    assert _env(settings)[CHOOSER] == "struct"


def test_guard_full_refuses_to_overwrite_an_owner_chooser_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    settings, _ = _paths(tmp_path)
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"env": {CHOOSER: "keep"}}), "utf-8")
    assert _install(settings, "--guard-full") == 0
    assert _env(settings)[CHOOSER] == "keep" and CHOOSER_BY not in _env(settings)
    err = capsys.readouterr().err
    assert "--guard-full" in err and CHOOSER in err and "keep" in err
