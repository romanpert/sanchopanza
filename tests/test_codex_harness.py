"""The Codex hook bodies: schema-shaped events in, archive written, `additionalContext` out,
fail-open on anything wrong. No Codex, no model, no network.

Event shapes follow openai/codex `codex-rs/hooks/schema/generated/*.command.input.schema.json`
(33a0f766): Bash's `tool_response` is a string, an MCP tool's is a serialized CallToolResult.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from sanchopanza.context import archive as archive_mod
from sanchopanza.harness import codex

NEEDLE = "RELEASE_TOKEN=RT-8KX2-4821"
LOG = "\n".join(
    [f"2026-09-28T10:{i // 60:02d}:{i % 60:02d} INFO step {i} ok" for i in range(150)]
    + [NEEDLE]
    + [f"2026-09-28T11:{i // 60:02d}:{i % 60:02d} INFO step {i} ok" for i in range(150)]
)


def _post(tmp_path: Path, response, tool: str = "Bash", **extra) -> dict:
    return {
        "cwd": str(tmp_path),
        "hook_event_name": "PostToolUse",
        "model": "gpt-6-luna",
        "permission_mode": "default",
        "session_id": "019a-session",
        "tool_input": {"command": "python make_log.py"},
        "tool_name": tool,
        "tool_response": response,
        "tool_use_id": "call_abc123",
        "transcript_path": None,
        "turn_id": "turn-1",
        **extra,
    }


def _start(tmp_path: Path, source: str = "startup") -> dict:
    return {
        "cwd": str(tmp_path),
        "hook_event_name": "SessionStart",
        "model": "gpt-6-luna",
        "permission_mode": "default",
        "session_id": "019a-session-2",
        "source": source,
        "transcript_path": None,
    }


@pytest.fixture(autouse=True)
def _no_archive_override(monkeypatch):
    monkeypatch.delenv("SANCHOPANZA_ARCHIVE", raising=False)
    monkeypatch.delenv("SANCHO_ARCHIVE", raising=False)


def _session_dir(tmp_path: Path, session: str = "019a-session") -> Path:
    return archive_mod.session_dir(archive_mod.root_for(tmp_path), session)


def test_large_bash_output_is_archived_whole_and_pointed_at(tmp_path):
    out = codex.post_tool_use(_post(tmp_path, LOG))

    saved = _session_dir(tmp_path) / "codex-call_abc123.txt"
    assert saved.read_text(encoding="utf-8") == LOG
    meta = json.loads(saved.with_name("codex-call_abc123.meta.json").read_text("utf-8"))
    assert meta["tool"] == "Bash" and meta["about"] == "python make_log.py"
    assert meta["by"] == "codex" and meta["chars"] == len(LOG)

    specific = out["hookSpecificOutput"]
    assert set(out) == {"hookSpecificOutput"}
    assert specific["hookEventName"] == "PostToolUse"
    line = specific["additionalContext"]
    assert "\n" not in line and line.startswith(codex.MARK)
    assert str(saved.resolve()) in line and codex.SEARCH_TOOL in line


def test_output_matches_codex_output_schema(tmp_path):
    """Only keys the generated output schema allows (additionalProperties: false)."""
    out = codex.post_tool_use(_post(tmp_path, LOG))
    assert set(out) <= {
        "continue",
        "decision",
        "hookSpecificOutput",
        "reason",
        "stopReason",
        "suppressOutput",
        "systemMessage",
    }
    assert set(out["hookSpecificOutput"]) <= {
        "additionalContext",
        "hookEventName",
        "updatedMCPToolOutput",
    }
    assert "updatedMCPToolOutput" not in out["hookSpecificOutput"]  # Codex rejects it


def test_index_names_the_needle_when_available(tmp_path, monkeypatch):
    calls = []

    def fake_index(text, limit=240):
        calls.append(limit)
        return "RT-8KX2-4821; RELEASE_TOKEN=RT-8KX2-4821"

    import sanchopanza.context.index as index_mod

    monkeypatch.setattr(index_mod, "index_of", fake_index, raising=False)
    line = codex.post_tool_use(_post(tmp_path, LOG))["hookSpecificOutput"]["additionalContext"]
    assert "Holds: RT-8KX2-4821" in line and calls == [codex.INDEX_LIMIT]


def test_missing_index_falls_back_to_no_index(tmp_path, monkeypatch):
    real_import = __import__

    def no_index(name, *args, **kwargs):
        if name in ("sanchopanza.context.index", "sanchopanza.context.compact"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", no_index)
    line = codex.post_tool_use(_post(tmp_path, LOG))["hookSpecificOutput"]["additionalContext"]
    assert "Holds:" not in line and line.startswith(codex.MARK)


def test_medium_output_is_archived_without_context(tmp_path):
    text = "x" * 2_000
    assert codex.post_tool_use(_post(tmp_path, text)) == {}
    assert (_session_dir(tmp_path) / "codex-call_abc123.txt").read_text("utf-8") == text


def test_small_output_is_neither_archived_nor_mentioned(tmp_path):
    assert codex.post_tool_use(_post(tmp_path, "ok\n")) == {}
    assert not archive_mod.root_for(tmp_path).exists()


def test_mcp_call_tool_result_is_read_as_text(tmp_path):
    response = {"content": [{"type": "text", "text": LOG}], "isError": False}
    out = codex.post_tool_use(_post(tmp_path, response, tool="mcp__docs__fetch"))
    saved = _session_dir(tmp_path) / "codex-call_abc123.txt"
    assert saved.read_text("utf-8") == LOG
    assert "mcp__docs__fetch" in out["hookSpecificOutput"]["additionalContext"]


def test_unknown_response_shape_is_archived_as_json(tmp_path):
    response = {"rows": [{"n": i, "value": "v" * 20} for i in range(400)]}
    codex.post_tool_use(_post(tmp_path, response, tool="mcp__db__query"))
    saved = _session_dir(tmp_path) / "codex-call_abc123.txt"
    assert json.loads(saved.read_text("utf-8")) == response


def test_own_search_tool_is_not_archived(tmp_path):
    tool = f"mcp__{codex.SERVER}__{codex.SEARCH_TOOL}"
    assert codex.post_tool_use(_post(tmp_path, LOG, tool=tool)) == {}
    assert not archive_mod.root_for(tmp_path).exists()


def test_archive_ignores_itself_in_git_and_journal_records_the_run(tmp_path):
    codex.post_tool_use(_post(tmp_path, LOG, transcript_path="/x/rollout.jsonl"))
    home = tmp_path / ".sanchopanza"
    assert (home / ".gitignore").read_text("utf-8") == "*\n"
    record = json.loads((home / codex.JOURNAL).read_text("utf-8").splitlines()[0])
    assert record["event"] == "PostToolUse" and record["chars"] == len(LOG)
    assert record["transcript"] == "/x/rollout.jsonl" and record["context"].startswith(codex.MARK)


def test_archive_override_from_environment(tmp_path, monkeypatch):
    elsewhere = tmp_path / "elsewhere"
    monkeypatch.setenv("SANCHOPANZA_ARCHIVE", str(elsewhere))
    codex.post_tool_use(_post(tmp_path / "project", LOG))
    assert (elsewhere / "019a-session" / "codex-call_abc123.txt").exists()


def test_session_start_is_silent_on_an_empty_archive(tmp_path):
    assert codex.session_start(_start(tmp_path)) == {}
    archive_mod.root_for(tmp_path).mkdir(parents=True)
    assert codex.session_start(_start(tmp_path)) == {}


def test_session_start_names_the_archive_and_search_tool(tmp_path):
    codex.post_tool_use(_post(tmp_path, LOG))
    out = codex.session_start(_start(tmp_path, "resume"))
    specific = out["hookSpecificOutput"]
    assert specific["hookEventName"] == "SessionStart"
    note = specific["additionalContext"]
    assert "1 earlier tool output" in note and codex.SEARCH_TOOL in note
    assert len(note) < 600


@pytest.mark.parametrize(
    "raw",
    ["", "not json", "[1, 2]", '{"hook_event_name": "PostToolUse", "tool_response": null}'],
)
def test_run_hook_fails_open_on_bad_input(raw):
    assert codex.run_hook("post-tool-use", raw) in ("{}",)


def test_run_hook_fails_open_when_archive_cannot_be_written(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(archive_mod, "write_entry", boom)
    assert codex.run_hook("post-tool-use", json.dumps(_post(tmp_path, LOG))) == "{}"


def test_a_failure_is_one_stderr_line_without_the_tool_output(tmp_path, monkeypatch, capsys):
    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(archive_mod, "write_entry", boom)
    raw = json.dumps(_post(tmp_path, LOG)).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"))
    assert codex.main(["post-tool-use"]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "{}"
    assert captured.err == "sanchopanza codex hook: OSError: disk full\n"
    assert NEEDLE not in captured.err


def test_a_type_error_inside_the_index_is_reported_not_retried(tmp_path, monkeypatch, capsys):
    calls = []

    def broken_index(text, limit=240):
        calls.append(limit)
        raise TypeError("bad operand inside the index")

    import sanchopanza.context.index as index_mod

    monkeypatch.setattr(index_mod, "index_of", broken_index, raising=False)
    assert codex.run_hook("post-tool-use", json.dumps(_post(tmp_path, LOG))) == "{}"
    assert calls == [codex.INDEX_LIMIT]  # not called again without `limit`
    err = capsys.readouterr().err
    assert err == "sanchopanza codex hook: TypeError: bad operand inside the index\n"


def test_an_index_without_limit_is_called_without_it(tmp_path, monkeypatch):
    def old_index(text):
        return "RT-8KX2-4821; " + "x" * 400

    import sanchopanza.context.index as index_mod

    monkeypatch.setattr(index_mod, "index_of", old_index, raising=False)
    line = codex.post_tool_use(_post(tmp_path, LOG))["hookSpecificOutput"]["additionalContext"]
    assert "Holds: RT-8KX2-4821; " in line
    assert "x" * (codex.INDEX_LIMIT + 1) not in line


def test_run_hook_output_is_ascii_json(tmp_path):
    event = _post(tmp_path, LOG + "\nr\u00e9sum\u00e9 \u2713")
    out = codex.run_hook("post-tool-use", json.dumps(event))
    assert out.isascii()
    assert json.loads(out)["hookSpecificOutput"]["hookEventName"] == "PostToolUse"


def test_main_reads_stdin_and_always_exits_zero(tmp_path, monkeypatch, capsys):
    raw = json.dumps(_post(tmp_path, LOG)).encode("utf-8")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"))
    assert codex.main(["post-tool-use"]) == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]

    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"\xff\xfe"), encoding="utf-8"))
    assert codex.main(["session-start"]) == 0
    assert capsys.readouterr().out.strip() == "{}"


def test_module_runs_as_a_hook_process(tmp_path):
    """The exact command line the hooks.json names, as Codex would spawn it."""
    done = subprocess.run(
        [sys.executable, "-m", "sanchopanza.harness.codex", "post-tool-use"],
        input=json.dumps(_post(tmp_path, LOG)).encode("utf-8"),
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0
    assert json.loads(done.stdout)["hookSpecificOutput"]["additionalContext"]


def test_hooks_json_matches_codex_hooks_file_shape():
    document = json.loads(codex.hooks_json(python="C:/py/python.exe"))
    assert set(document) == {"description", "hooks"}
    assert set(document["hooks"]) == {"PostToolUse", "SessionStart"}
    for groups in document["hooks"].values():
        (group,) = groups
        assert "matcher" not in group  # every tool
        (handler,) = group["hooks"]
        assert handler["type"] == "command" and handler["timeout"] == codex.HOOK_TIMEOUT_SEC
        assert handler["command"].startswith('"C:/py/python.exe" -m sanchopanza.harness.codex ')
        assert handler["commandWindows"] == handler["command"]


def test_config_toml_parses_and_registers_the_archive_server():
    text = codex.config_toml(
        python="C:\\py\\python.exe", archive="D:\\a b\\archive", tool_output_token_limit=4000
    )
    parsed = tomllib.loads(text)
    assert parsed["tool_output_token_limit"] == 4000
    server = parsed["mcp_servers"][codex.SERVER]
    assert server["command"] == "C:\\py\\python.exe"
    assert server["args"] == ["-m", "sanchopanza", "archive-mcp", "--archive", "D:\\a b\\archive"]
    tool = server["tools"][codex.SEARCH_TOOL]
    assert tool == {"approval_mode": "approve", "output_token_limit": codex.SEARCH_OUTPUT_TOKENS}


def test_config_toml_without_limit_leaves_codex_default():
    parsed = tomllib.loads(codex.config_toml(python="py", extra={"model": '"gpt-6-luna"'}))
    assert "tool_output_token_limit" not in parsed and parsed["model"] == "gpt-6-luna"


def test_project_files_are_returned_not_written(tmp_path):
    files = codex.project_files(tmp_path, python="py")
    assert set(files) == {".codex/hooks.json", ".codex/config.toml"}
    assert not (tmp_path / ".codex").exists()


def test_config_command_prints_both_files(capsys):
    assert codex.main(["config"]) == 0
    out = capsys.readouterr().out
    assert "# --- .codex/hooks.json" in out and "[mcp_servers.sanchopanza_archive]" in out
    assert codex.main(["nonsense"]) == 2
