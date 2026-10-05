"""Memory v6.3 candidate: the record before the first shell write, not after it.

With v6.2 a record reaches an agent that edits through the shell at its first write of the file,
after the change is made (125 of 152 on the maintainer's sessions). A PreToolUse hook can only
show the agent text before a command runs by denying it (Claude Code feeds the reason back; it
applies in every permission mode). Off by default (`SANCHOPANZA_MEMORY_SHELL_FIRST=deny` turns it
on): a command that writes a file with a record not yet given is denied once, the record as the
reason; the same command is never denied twice, and the record is not given again after it.
"""

# ruff: noqa: F811  (tests take the imported `store` fixture as a parameter)
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sanchopanza.harness import memory_hook as mh

from .test_memory_hook import (
    HEX_LINE,
    _bash_setup,
    bash_event,
    context_of,
    store,  # noqa: F401  (the fixture)
)

CARBON = "pygments/lexers/carbon.py"
WRITE = f"sed -i 's/Hex/Hexadecimal/' {CARBON}"


def pre(event: dict[str, Any]) -> dict[str, Any]:
    out = {**event, "hook_event_name": "PreToolUse"}
    out.pop("tool_response", None)
    return out


def reason_of(out: dict[str, Any]) -> str:
    spec = out.get("hookSpecificOutput") or {}
    assert spec.get("hookEventName") == "PreToolUse"
    assert spec.get("permissionDecision") == "deny"
    return str(spec.get("permissionDecisionReason"))


@pytest.fixture
def first_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_SHELL_FIRST", "deny")


def test_off_by_default(store: Path) -> None:
    new = _bash_setup(store)
    assert mh.handle(pre(bash_event(new, "s2", WRITE))) == {}


def test_first_write_is_denied_once_with_the_record(store: Path, first_on: None) -> None:
    new = _bash_setup(store)
    reason = reason_of(mh.handle(pre(bash_event(new, "s2", WRITE))))
    assert "request 1 of session s1" in reason and CARBON in reason
    assert "again" in reason  # it says how to go on


def test_the_same_command_runs_the_second_time(store: Path, first_on: None) -> None:
    new = _bash_setup(store)
    mh.handle(pre(bash_event(new, "s2", WRITE)))
    assert mh.handle(pre(bash_event(new, "s2", WRITE))) == {}
    assert mh.handle(bash_event(new, "s2", WRITE)) == {}  # PostToolUse: already given


def test_a_changed_command_for_the_same_file_is_not_denied_again(
    store: Path, first_on: None
) -> None:
    new = _bash_setup(store)
    mh.handle(pre(bash_event(new, "s2", WRITE)))
    other = f"sed -i 's/Hex/HexLiteral/' {CARBON}"
    assert mh.handle(pre(bash_event(new, "s2", other))) == {}


def test_a_read_is_never_denied(store: Path, first_on: None) -> None:
    new = _bash_setup(store)
    assert mh.handle(pre(bash_event(new, "s2", f"sed -n 1,40p {CARBON}"))) == {}


def test_a_file_with_no_record_is_not_denied(store: Path, first_on: None) -> None:
    new = _bash_setup(store)
    assert mh.handle(pre(bash_event(new, "s2", "echo x > other/new_file.py"))) == {}


def test_not_in_a_subagent(store: Path, first_on: None) -> None:
    new = _bash_setup(store)
    event = {**pre(bash_event(new, "s2", WRITE)), "agent_id": "a1"}
    assert mh.handle(event) == {}


def test_file_tools_are_untouched(store: Path, first_on: None) -> None:
    new = _bash_setup(store)
    event = {
        **pre(bash_event(new, "s2", WRITE)),
        "tool_name": "Edit",
        "tool_input": {"file_path": CARBON, "old_string": HEX_LINE, "new_string": "x"},
    }
    assert mh.handle(event) == {}


def test_touch_off_turns_it_off(store: Path, first_on: None, monkeypatch) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_TOUCH", "off")
    new = _bash_setup(store)
    assert mh.handle(pre(bash_event(new, "s2", WRITE))) == {}


def test_after_a_deny_the_post_touch_of_a_write_still_works_for_other_files(
    store: Path, first_on: None
) -> None:
    """Without SHELL_FIRST the PostToolUse write give is v6.2's; with it a file whose record
    was given at the deny gives nothing more, and the log says which phase gave it."""
    new = _bash_setup(store)
    mh.handle(pre(bash_event(new, "s2", WRITE)))
    log = (store / "log.jsonl").read_text(encoding="utf-8")
    assert '"phase": "pre"' in log
    assert context_of(mh.handle(bash_event(new, "s2", WRITE))) == ""
