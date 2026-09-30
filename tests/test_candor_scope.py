"""Candor's lock holds the session that earned it, not the machine (the Indagis scene, 2026-09-30:
one machine-wide file held two sessions in other worktrees from their first call)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sanchopanza.candor import __main__ as candor_cli
from sanchopanza.candor import lock as lock_mod
from sanchopanza.candor.ledger import classify
from sanchopanza.candor.rules import Finding
from sanchopanza.harness import candor_hook


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("SANCHOPANZA_CANDOR_LOCK", raising=False)
    monkeypatch.delenv("SANCHOPANZA_CANDOR_LOCK_SCOPE", raising=False)
    monkeypatch.setattr(lock_mod, "home_dir", lambda: tmp_path / "home")
    monkeypatch.setenv("SANCHOPANZA_CANDOR_DIR", str(tmp_path / "state"))
    return tmp_path


def _tamper(session: str, cwd: Path) -> dict:
    return {"hook_event_name": "PreToolUse", "session_id": session, "cwd": str(cwd),
            "tool_name": "Edit", "tool_input": {"file_path": ".claude/settings.json"}}  # fmt: skip


def _read(session: str, cwd: Path) -> dict:
    return {"hook_event_name": "PreToolUse", "session_id": session, "cwd": str(cwd),
            "tool_name": "Read", "tool_input": {"file_path": "README.md"}}  # fmt: skip


def _denied(output: dict) -> bool:
    return (output.get("hookSpecificOutput") or {}).get("permissionDecision") == "deny"


def test_a_lock_holds_its_session_and_not_another(home: Path) -> None:
    repo = home / "repo"
    repo.mkdir()
    assert _denied(candor_hook.handle(_tamper("aaa", repo)))
    assert _denied(candor_hook.handle(_read("aaa", repo)))  # the flagged session stays held
    assert candor_hook.handle(_read("bbb", repo)) == {}  # another session, same repository


def test_project_scope_holds_every_session_of_the_repository(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SANCHOPANZA_CANDOR_LOCK_SCOPE", "project")
    repo, other = home / "repo", home / "other"
    (repo / ".git").mkdir(parents=True)
    (repo / "sub").mkdir()
    other.mkdir()
    assert _denied(candor_hook.handle(_tamper("aaa", repo)))
    assert _denied(candor_hook.handle(_read("bbb", repo / "sub")))  # same git root
    assert candor_hook.handle(_read("ccc", other)) == {}


def test_machine_scope_keeps_the_old_behaviour(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_CANDOR_LOCK_SCOPE", "machine")
    a, b = home / "a", home / "b"
    a.mkdir()
    b.mkdir()
    assert _denied(candor_hook.handle(_tamper("aaa", a)))
    assert _denied(candor_hook.handle(_read("bbb", b)))


def test_an_unknown_scope_reads_as_session(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_CANDOR_LOCK_SCOPE", "Galaxy")
    assert lock_mod.scope() == "session"


def test_a_session_without_an_id_falls_back_to_its_project(home: Path) -> None:
    path = lock_mod.default_path("", home)
    assert path.name.startswith("project-")


def test_the_explicit_file_wins_over_the_scope(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_CANDOR_LOCK", str(home / "mine.json"))
    assert lock_mod.default_path("aaa", home) == home / "mine.json"


def test_release_asks_which_when_several_are_held(
    home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for session in ("aaa", "bbb"):
        lock_mod.engage([Finding("critical", "tamper", "x")], session=session,
                        path=lock_mod.default_path(session, home))  # fmt: skip
    assert candor_cli.main(["release", "--by", "p", "--why", "r"]) == 2
    assert len(lock_mod.engaged_paths()) == 2
    assert candor_cli.main(["release", "--by", "p", "--why", "r", "--session", "aaa"]) == 0
    held = lock_mod.engaged_paths()
    assert [lock_mod.read(p).session for p in held] == ["bbb"]
    assert candor_cli.main(["release", "--by", "p", "--why", "r"]) == 0
    assert lock_mod.engaged_paths() == []
    assert "released" in capsys.readouterr().out


def test_status_lists_every_held_session(home: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert candor_cli.main(["status"]) == 0
    lock_mod.engage([Finding("critical", "tamper", "x")], session="aaa",
                    path=lock_mod.default_path("aaa", home))  # fmt: skip
    assert candor_cli.main(["status"]) == 1
    assert "session aaa" in capsys.readouterr().out


@pytest.mark.parametrize(
    "target",
    [
        r"C:\Users\r\.sancho\candor-lock.json",  # the legacy home, live on machines that had it
        "/home/u/.sanchopanza/candor-locks/session-x.json",
        "rm ~/.sancho/candor/abc.jsonl",
        "~/.sanchopanza/journal.jsonl",
    ],
)
def test_the_monitor_home_is_tamper_new_or_legacy(target: str) -> None:
    tool = "Bash" if target.startswith("rm ") else "Edit"
    assert classify(tool, target) == "tamper"


@pytest.mark.parametrize("target", ["src/sanchopanza/candor/lock.py", "src/sanchopanza/journal.py"])
def test_the_package_source_is_code_not_the_monitor(target: str) -> None:
    assert classify("Edit", target) == "write"
