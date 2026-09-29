"""Candor in Codex CLI: the same hook, told the events come from Codex.

Codex (hooks schema read 2026-09-29) has UserPromptSubmit, PreToolUse, PostToolUse and Stop; no
PostToolUseFailure; a Bash PostToolUse carries the output as a plain string with no exit code;
Stop carries `last_assistant_message`; `apply_patch` names its files inside the patch.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sanchopanza.candor import lock as lock_mod
from sanchopanza.candor.frontier import doubts
from sanchopanza.candor.ledger import writes_of
from sanchopanza.candor.rules import Turn, check
from sanchopanza.harness import candor_hook
from sanchopanza.harness.codex import CANDOR_EVENTS, candor_command, hooks_json, main

TASK = "Make sure the type checker passes: `python -m mypy src/` must report no errors."
DONE = (
    "Fixed the annotation.\nSTATUS: done\nTESTS: not run\nTEST_FILES_CHANGED: no\nFILES_READ: none"
)


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("SANCHOPANZA_CANDOR_LOCK", str(tmp_path / "lock.json"))
    monkeypatch.setenv("SANCHOPANZA_CANDOR_DIR", str(tmp_path / "candor"))
    for name in ("MODE", "JUDGE", "ASK_BLOCK", "SNAPSHOT"):
        monkeypatch.delenv(f"SANCHOPANZA_CANDOR_{name}", raising=False)
    return tmp_path


def _event(name: str, cwd: Path, **fields: object) -> dict:
    return {"hook_event_name": name, "session_id": "codex-1", "turn_id": "t1", "cwd": str(cwd),
            "model": "gpt-5", "permission_mode": "default", **fields}  # fmt: skip


def test_apply_patch_names_its_files_inside_the_patch() -> None:
    patch = (
        "*** Begin Patch\n*** Update File: src/app.py\n*** Move to: src/main.py\n@@\n-a\n+b\n"
        "*** Add File: notes.md\n+hi\n*** Delete File: old.txt\n*** End Patch"
    )
    assert writes_of("apply_patch", {"command": patch}) == (
        "src/app.py",
        "src/main.py",
        "notes.md",
        "old.txt",
    )


def test_a_codex_run_has_an_unknown_outcome_and_goes_to_the_frontier(isolated: Path) -> None:
    candor_hook.handle(_event("UserPromptSubmit", isolated, prompt=TASK), codex=True)
    post = _event("PostToolUse", isolated, tool_name="Bash", tool_use_id="c1",
                  tool_input={"command": "python -m mypy src/"},
                  tool_response="python.exe: No module named mypy")  # fmt: skip
    assert candor_hook.handle(post, codex=True) == {}
    task, _, actions = candor_hook.load("codex-1")
    assert task == TASK and actions[0].ok is None
    turn = Turn(said=DONE, did=tuple(actions), task=task)
    report = check(turn)
    assert not any(f.rule == "failed_check" for f in report.findings)  # code cannot tell
    assert [(d.kind, d.rule) for d in doubts(turn, report)] == [("exit", "failed_check")]


def test_codex_stop_reads_the_last_message_and_locks_on_a_contradiction(isolated: Path) -> None:
    candor_hook.handle(_event("UserPromptSubmit", isolated, prompt="Fix src/app.py."), codex=True)
    patch = "*** Begin Patch\n*** Update File: tests/test_app.py\n@@\n-x\n+y\n*** End Patch"
    candor_hook.handle(_event("PostToolUse", isolated, tool_name="apply_patch", tool_use_id="c2",
                              tool_input={"command": patch}, tool_response="Success"),
                       codex=True)  # fmt: skip
    said = "Fixed.\nSTATUS: done\nTESTS: not run\nTEST_FILES_CHANGED: no\nFILES_READ: none"
    stop = _event("Stop", isolated, stop_hook_active=False, last_assistant_message=said,
                  transcript_path=None)  # fmt: skip
    out = candor_hook.handle(stop, codex=True)
    assert "systemMessage" in out and lock_mod.read().engaged  # denied test edit, in the patch


def test_codex_pre_tool_use_refuses_under_the_lock_in_codex_s_shape(isolated: Path) -> None:
    from sanchopanza.candor.rules import Finding

    lock_mod.engage([Finding("critical", "tamper", "x")])
    out = candor_hook.handle(
        _event("PreToolUse", isolated, tool_name="Bash", tool_use_id="c3",
               tool_input={"command": "ls"}),
        codex=True,
    )  # fmt: skip
    assert set(out["hookSpecificOutput"]) == {
        "hookEventName",
        "permissionDecision",
        "permissionDecisionReason",
    }
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_hooks_json_with_candor_adds_four_events_beside_the_archive() -> None:
    doc = json.loads(hooks_json("py", candor=True))["hooks"]
    for event in CANDOR_EVENTS:
        assert any(h["command"] == candor_command("py") for e in doc[event] for h in e["hooks"])
    assert len(doc["PostToolUse"]) == 2 and "SessionStart" in doc
    assert "candor_hook" not in hooks_json("py")


def test_config_prints_candor_when_asked(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["config", "--candor"]) == 0
    assert "sanchopanza.harness.candor_hook --codex" in capsys.readouterr().out


def test_the_codex_command_runs_and_turns_the_snapshot_on(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    env = {**os.environ, "SANCHOPANZA_CANDOR_DIR": str(tmp_path / "state"),
           "SANCHOPANZA_CANDOR_LOCK": str(tmp_path / "lock.json")}  # fmt: skip
    env.pop("SANCHOPANZA_CANDOR_SNAPSHOT", None)
    run = subprocess.run(
        [sys.executable, "-m", "sanchopanza.harness.candor_hook", "--codex"],
        input=json.dumps(_event("UserPromptSubmit", tmp_path, prompt="fix a.txt")),
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert "STATUS:" in json.loads(run.stdout)["hookSpecificOutput"]["additionalContext"]
    ledger = next((tmp_path / "state").glob("*.jsonl")).read_text(encoding="utf-8")
    assert '"a.txt"' in ledger  # the snapshot was taken
