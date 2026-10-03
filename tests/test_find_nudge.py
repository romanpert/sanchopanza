"""The find nudge (`sanchopanza find-hook`): one line of PostToolUse context, at most once per
session, when an early search before any edit came back wide (>= 15 files, or a full `head -K`
listing) and find_in_repo is installed. Through messages only: tools and system never change."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest

from sanchopanza.harness import find_nudge

FILES = [f"django/db/models/m{i}.py" for i in range(20)]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"sanchopanza": {"command": "sanchopanza"}}}), "utf-8"
    )
    approve(repo, {"enabledMcpjsonServers": ["sanchopanza"]})
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    monkeypatch.setenv("SANCHOPANZA_GUARD_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("SANCHOPANZA_JOURNAL", str(tmp_path / "journal.jsonl"))
    monkeypatch.delenv("SANCHOPANZA_FIND_NUDGE", raising=False)
    monkeypatch.delenv("SANCHO_FIND_NUDGE", raising=False)
    monkeypatch.setattr(find_nudge, "user_config", lambda: tmp_path / "no-claude.json")
    monkeypatch.setattr(find_nudge, "user_settings", lambda: tmp_path / "no-settings.json")
    (tmp_path / "transcript.jsonl").write_text("", "utf-8")
    return repo


def approve(repo: Path, settings: dict[str, Any], name: str = "settings.json") -> None:
    (repo / ".claude").mkdir(exist_ok=True)
    (repo / ".claude" / name).write_text(json.dumps(settings), "utf-8")


def event(tool: str, tool_input: dict[str, Any], response: Any, project: Path) -> dict[str, Any]:
    return {"hook_event_name": "PostToolUse", "session_id": "s-1", "cwd": str(project),
            "transcript_path": str(project.parent / "transcript.jsonl"), "tool_name": tool,
            "tool_input": tool_input, "tool_response": response}  # fmt: skip


def grep(project: Path, files: list[str]) -> dict[str, Any]:
    response = {"mode": "files_with_matches", "filenames": files, "numFiles": len(files)}
    return event("Grep", {"pattern": "select"}, response, project)


def bash(project: Path, command: str, lines: list[str]) -> dict[str, Any]:
    response = {"stdout": "\n".join(lines), "stderr": "", "interrupted": False}
    return event("Bash", {"command": command}, response, project)


def context(out: dict[str, Any] | None) -> str:
    return ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext", "")


def journal(project: Path) -> list[dict[str, Any]]:
    path = project.parent / "journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]


def test_a_twenty_file_grep_before_any_edit_suggests_find(project: Path) -> None:
    out = find_nudge.handle(grep(project, FILES))
    note = context(out)
    assert 'mcp__sanchopanza__find_in_repo(query="' in note and "20 files" in note
    assert note.count("\n") == 0  # one line
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert set(out) == {"hookSpecificOutput"}  # messages only: nothing else changes
    rows = journal(project)
    assert [r["kind"] for r in rows] == ["find_nudge"]
    assert rows[0]["data"]["tool"] == "Grep" and rows[0]["data"]["listed"] == 20
    assert rows[0]["data"]["search"] == 1


def test_it_fires_once_per_session(project: Path) -> None:
    assert context(find_nudge.handle(grep(project, FILES)))
    assert find_nudge.handle(grep(project, FILES)) is None
    other = {**grep(project, FILES), "session_id": "s-2"}
    assert context(find_nudge.handle(other))


def test_not_after_an_edit_seen_by_the_hook(project: Path) -> None:
    edit = event("Edit", {"file_path": "a.py"}, {"filePath": "a.py"}, project)
    assert find_nudge.handle(edit) is None
    assert find_nudge.handle(grep(project, FILES)) is None
    assert journal(project) == []


def test_not_after_an_edit_found_in_the_transcript(project: Path) -> None:
    line = {"type": "assistant", "message": {"id": "m1", "content": [
        {"type": "tool_use", "id": "t1", "name": "MultiEdit", "input": {}}]}}  # fmt: skip
    (project.parent / "transcript.jsonl").write_text(json.dumps(line) + "\n", "utf-8")
    assert find_nudge.handle(grep(project, FILES)) is None


def test_not_on_five_files(project: Path) -> None:
    assert find_nudge.handle(grep(project, FILES[:5])) is None


def test_not_past_the_third_search(project: Path) -> None:
    for _ in range(3):
        assert find_nudge.handle(grep(project, FILES[:2])) is None
    assert find_nudge.handle(grep(project, FILES)) is None


def test_commands_that_are_not_searches_do_not_count(project: Path) -> None:
    for _ in range(4):
        assert find_nudge.handle(bash(project, "python -m pytest tests -q", FILES)) is None
    assert context(find_nudge.handle(grep(project, FILES)))


def test_not_without_find_installed(project: Path) -> None:
    (project / ".mcp.json").unlink()
    assert find_nudge.handle(grep(project, FILES)) is None
    assert journal(project) == []


def test_a_user_scope_find_counts_as_installed(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (project / ".mcp.json").unlink()
    user = tmp_path / "claude.json"
    user.write_text(json.dumps({"mcpServers": {"sanchopanza": {"command": "x"}}}), "utf-8")
    monkeypatch.setattr(find_nudge, "user_config", lambda: user)
    assert context(find_nudge.handle(grep(project, FILES)))


def test_a_project_server_nobody_approved_is_not_loaded(project: Path) -> None:
    """Claude Code loads a `.mcp.json` server only once it is approved: unapproved, find is not
    there and the nudge would point at a tool the agent does not have."""
    (project / ".claude" / "settings.json").unlink()
    assert find_nudge.handle(grep(project, FILES)) is None


@pytest.mark.parametrize(
    ("name", "settings"),
    [
        ("settings.local.json", {"enabledMcpjsonServers": ["sanchopanza"]}),
        ("settings.json", {"enableAllProjectMcpServers": True}),
    ],
)
def test_other_approvals_of_the_project_server(
    project: Path, name: str, settings: dict[str, Any]
) -> None:
    (project / ".claude" / "settings.json").unlink()
    approve(project, settings, name)
    assert context(find_nudge.handle(grep(project, FILES)))


def test_a_disabled_project_server_is_not_loaded(project: Path) -> None:
    approve(project, {"enableAllProjectMcpServers": True}, "settings.json")
    approve(project, {"disabledMcpjsonServers": ["sanchopanza"]}, "settings.local.json")
    assert find_nudge.handle(grep(project, FILES)) is None


def test_an_approval_kept_in_the_user_config_counts(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approved at Claude Code's prompt: the answer lives in ~/.claude.json, by project."""
    (project / ".claude" / "settings.json").unlink()
    user = tmp_path / "claude.json"
    entry = {"enabledMcpjsonServers": ["sanchopanza"]}
    user.write_text(json.dumps({"projects": {project.as_posix(): entry}}), "utf-8")
    monkeypatch.setattr(find_nudge, "user_config", lambda: user)
    assert context(find_nudge.handle(grep(project, FILES)))


def test_an_approval_without_the_server_is_not_enough(project: Path) -> None:
    (project / ".mcp.json").unlink()
    assert find_nudge.handle(grep(project, FILES)) is None


def test_two_concurrent_calls_nudge_once(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Claude Code runs hooks of parallel tool calls at once: both read the state before either
    writes it. The `fired` marker is created exclusively, and only its creator nudges."""
    import threading

    both = threading.Barrier(2, timeout=10)
    real = find_nudge.find_installed

    def installed_together(event: dict[str, Any]) -> bool:
        both.wait()  # each has loaded an open state and found a wide search
        return real(event)

    monkeypatch.setattr(find_nudge, "find_installed", installed_together)
    outs: list[dict[str, Any] | None] = [None, None]

    def call(i: int) -> None:
        outs[i] = find_nudge.handle(grep(project, FILES))

    threads = [threading.Thread(target=call, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert sum(bool(context(out)) for out in outs) == 1
    assert [r["kind"] for r in journal(project)] == ["find_nudge"]
    assert find_nudge.handle(grep(project, FILES)) is None


def test_the_off_switch(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_FIND_NUDGE", "0")
    assert find_nudge.handle(grep(project, FILES)) is None


def test_a_full_head_listing_in_bash(project: Path) -> None:
    command = "find . -name '*.py' | grep admin | head -20"
    lines = [f"./django/contrib/admin/f{i}.py" for i in range(12)] + ["./docs/x.txt"] * 8
    out = find_nudge.handle(bash(project, command, lines))
    assert "head -20" in context(out)
    assert journal(project)[0]["data"]["head"] == 20


def test_a_head_listing_that_came_back_short_is_not_wide(project: Path) -> None:
    command = "grep -rl select_related django | head -20"
    assert find_nudge.handle(bash(project, command, FILES[:7])) is None


def test_a_wide_shell_search_without_head(project: Path) -> None:
    lines = [f"./django/x{i}.py:12:    def select(self):" for i in range(16)]
    assert context(find_nudge.handle(bash(project, "grep -rn 'def select' .", lines)))


def test_powershell_listing_with_select_first(project: Path) -> None:
    command = "Get-ChildItem -Recurse -Filter *.py | Select-Object -First 10"
    lines = [f"C:\\w\\django\\f{i}.py" for i in range(10)]
    response = {"stdout": "\r\n".join(lines), "stderr": ""}
    assert context(find_nudge.handle(event("PowerShell", {"command": command}, response, project)))


def test_grep_content_mode_counts_distinct_files() -> None:
    content = "\n".join(f"a/f{i % 4}.py:{i}:x" for i in range(40))
    response = {"mode": "content", "numFiles": 0, "filenames": [], "content": content}
    assert find_nudge.listed("Grep", response) == 4


def test_glob_counts_its_files() -> None:
    assert find_nudge.listed("Glob", {"filenames": FILES, "numFiles": 20}) == 20


def test_shell_paths_are_counted_once_each() -> None:
    text = "./a/b.py:1:x\n./a/b.py:2:y\n./a/c.py:3:z\nsome prose line\nREADME.md\n"
    assert find_nudge.listed("Bash", {"stdout": text}) == 3


def test_head_limits_are_read_from_the_last_stage() -> None:
    assert find_nudge.head_limit("grep -rl x . | head -20") == 20
    assert find_nudge.head_limit("ls | head -n 15") == 15
    assert find_nudge.head_limit("ls | head -n15") == 15
    assert find_nudge.head_limit("gci -r | Select-Object -First 12") == 12
    assert find_nudge.head_limit("grep -rl x .") is None


def test_main_reads_stdin_and_writes_json(
    project: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(
        json.dumps(grep(project, FILES)).encode())))  # fmt: skip
    assert find_nudge.main() == 0
    assert (
        "find_in_repo"
        in json.loads(capsys.readouterr().out)["hookSpecificOutput"]["additionalContext"]
    )


def test_main_fails_open_on_bad_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.TextIOWrapper(io.BytesIO(b"not json")))
    assert find_nudge.main() == 0
    assert capsys.readouterr().out == ""
