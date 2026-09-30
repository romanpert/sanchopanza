"""`sanchopanza compact` and `sanchopanza install --compact`, with no paid provider."""

from __future__ import annotations

import io
import json
import sys
from importlib import resources

import pytest

from sanchopanza import cli
from sanchopanza.harness import install

from .context_helpers import write_transcript


@pytest.fixture(autouse=True)
def _journal(tmp_path, monkeypatch):
    monkeypatch.setenv("SANCHOPANZA_JOURNAL", str(tmp_path / "journal.jsonl"))
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)


def _stdin(monkeypatch, payload) -> None:
    raw = json.dumps(payload).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"))


def test_transcript_rules_arm_prints_messages_and_report(tmp_path, capsys):
    path = write_transcript(tmp_path / "abc.jsonl")
    code = cli.main(
        [
            "compact",
            "--transcript",
            str(path),
            "--arm",
            "rules",
            "--provider",
            "null",
            "--keep-recent",
            "0",
            "--archive",
            str(tmp_path / "arc"),
            "--min-reduction",
            "0.1",
        ]
    )
    out = json.loads(capsys.readouterr().out)
    assert code == 0
    assert out["report"]["reasons"]["stub:read_superseded"] == 1
    assert out["report"]["reduction"] > 0.1
    assert (tmp_path / "arc" / "abc" / "t1.txt").exists()
    assert len(out["messages"]) == 12


def test_below_the_minimum_exits_3_and_says_why(tmp_path, capsys):
    path = write_transcript(tmp_path / "abc.jsonl")
    code = cli.main(
        [
            "compact",
            "--transcript",
            str(path),
            "--provider",
            "null",
            "--archive",
            str(tmp_path / "arc"),
            "--min-reduction",
            "0.9",
        ]
    )
    captured = capsys.readouterr()
    assert code == cli.COMPACT_BELOW_MINIMUM
    assert "below the 90% minimum" in captured.err and "normal summary" in captured.err
    assert json.loads(captured.out)["report"]["arm"] == "sanchopanza"


def test_below_the_minimum_leaves_no_copy_of_the_conversation(tmp_path, capsys, monkeypatch):
    """Found end to end: a failed compaction left the whole conversation and the pruned
    results inside the project, where `grep -r` and `git add .` reach them."""
    monkeypatch.chdir(tmp_path)
    path = write_transcript(tmp_path / "abc.jsonl")
    out = tmp_path / ".sanchopanza" / "compact-s.json"
    code = cli.main(
        [
            "compact",
            "--transcript",
            str(path),
            "--provider",
            "null",
            "--session",
            "s",
            "--out",
            str(out),
            "--min-reduction",
            "0.99",
        ]
    )
    capsys.readouterr()
    assert code == cli.COMPACT_BELOW_MINIMUM
    assert not out.exists()
    archive = tmp_path / ".sanchopanza" / "archive"
    assert not any(p.is_file() for p in archive.rglob("*")) if archive.exists() else True
    assert (tmp_path / ".sanchopanza" / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_a_used_compaction_keeps_its_archive_and_points_stubs_at_it(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = write_transcript(tmp_path / "abc.jsonl")
    code = cli.main(
        [
            "compact",
            "--transcript",
            str(path),
            "--provider",
            "null",
            "--arm",
            "rules",
            "--session",
            "s",
            "--min-reduction",
            "0",
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert code == 0
    text = json.dumps(result["messages"])
    assert ".staging" not in text
    archive = tmp_path / ".sanchopanza" / "archive" / "s"
    if "sanchopanza pruned" in text:
        assert any(archive.iterdir())
    assert not (tmp_path / ".sanchopanza" / "archive" / "s.staging").exists()


def test_stdin_keeps_extra_keys_and_writes_out(tmp_path, capsys, monkeypatch):
    messages = [
        {"role": "user", "content": "go", "sanchopanza_index": 0},
        {
            "role": "assistant",
            "sanchopanza_index": 1,
            "content": [
                {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "ls"}}
            ],
        },
        {
            "role": "user",
            "sanchopanza_index": 2,
            "content": [{"type": "tool_result", "tool_use_id": "a", "content": "f\n" * 400}],
        },
        {
            "role": "assistant",
            "sanchopanza_index": 3,
            "content": [
                {"type": "tool_use", "id": "b", "name": "Bash", "input": {"command": "ls"}}
            ],
        },
        {
            "role": "user",
            "sanchopanza_index": 4,
            "content": [{"type": "tool_result", "tool_use_id": "b", "content": "f\n" * 400}],
        },
    ]
    _stdin(monkeypatch, {"session": "s/1", "messages": messages})
    out = tmp_path / "o" / "out.json"
    code = cli.main(
        [
            "compact",
            "--stdin",
            "--arm",
            "rules",
            "--keep-recent",
            "0",
            "--provider",
            "null",
            "--archive",
            str(tmp_path / "arc"),
            "--out",
            str(out),
        ]
    )
    report = json.loads(capsys.readouterr().out)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0 and report["reasons"]["stub:command_repeated"] == 1
    assert [m["sanchopanza_index"] for m in written["messages"]] == [0, 1, 2, 3, 4]
    assert (tmp_path / "arc" / "s_1" / "a.txt").exists()


def test_bad_stdin_fails_loudly(capsys, monkeypatch):
    _stdin(monkeypatch, {"messages": "nope"})
    assert cli.main(["compact", "--stdin", "--provider", "null"]) == 2
    assert "sanchopanza compact failed" in capsys.readouterr().err


def test_the_hook_module_ships_as_package_data():
    module = (resources.files("sanchopanza.harness") / "compact_hook.ts").read_text("utf-8")
    assert "on('session.compact'" in module and "SANCHOPANZA_COMPACT_COMMAND" in module
    assert "return next(event)" in module


def test_install_compact_writes_the_plugin_and_is_idempotent(tmp_path, capsys):
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"env": {"KEEP": "1"}, "enabledPlugins": {"x@y": True}}))
    plugin = tmp_path / "plugin"
    args = ["install", "--path", str(settings), "--compact", "--plugin-dir", str(plugin),
            "--context-budget", "0", "--guard-profile", "sandbox"]  # the plugin's env  # fmt: skip
    assert cli.main([*args, "--write"]) == 0
    written = json.loads(settings.read_text())
    assert written["env"] == {"KEEP": "1", install.FUNCTION_HOOKS: "1"}
    assert written["enabledPlugins"] == {"x@y": True, install.PLUGIN_KEY: True}
    source = written["extraKnownMarketplaces"][install.MARKETPLACE]["source"]
    assert source == {"source": "directory", "path": str(plugin.resolve())}
    assert json.loads((plugin / "hooks" / "hooks.json").read_text()) == {
        "modules": ["./compact_hook.ts"]
    }
    assert (plugin / "hooks" / "compact_hook.ts").exists()
    assert json.loads((plugin / ".claude-plugin" / "plugin.json").read_text())["name"] == (
        install.PLUGIN
    )
    capsys.readouterr()
    assert cli.main([*args, "--write"]) == 0
    again = capsys.readouterr().out
    assert "already wired" in again and "plugin file" not in again


def test_install_without_compact_unwires_the_plugin_but_keeps_the_variable(tmp_path):
    settings = tmp_path / "settings.json"
    plugin = tmp_path / "plugin"
    cli.main(
        ["install", "--path", str(settings), "--compact", "--plugin-dir", str(plugin), "--write"]
    )
    cli.main(["install", "--path", str(settings), "--write"])
    written = json.loads(settings.read_text())
    assert install.PLUGIN_KEY not in written["enabledPlugins"]
    assert install.MARKETPLACE not in written["extraKnownMarketplaces"]
    assert written["env"][install.FUNCTION_HOOKS] == "1"


def test_install_without_compact_leaves_a_plain_file_as_before(tmp_path):
    settings = tmp_path / "settings.json"
    cli.main(["install", "--path", str(settings), "--write"])
    written = json.loads(settings.read_text())
    assert "enabledPlugins" not in written and "extraKnownMarketplaces" not in written


def test_install_compact_dry_run_writes_nothing(tmp_path, capsys):
    plugin = tmp_path / "plugin"
    code = cli.main(
        ["install", "--path", str(tmp_path / "s.json"), "--compact", "--plugin-dir", str(plugin)]
    )
    assert code == 0 and not plugin.exists() and "plugin file to write" in capsys.readouterr().out


def test_a_settings_block_that_is_not_an_object_is_left_alone():
    merged, added, removed = install._merge_compact({"enabledPlugins": []}, None)
    assert merged == {"enabledPlugins": []} and added == removed == []
