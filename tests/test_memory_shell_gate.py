"""The shell touch closes once a session edits through a file tool (v6.1).

On SWE-chat, whose agents edit with Edit and Write, the shell touch added no recall and most of
what it gave was unrelated; Sonnet 5.5 in B2 never edited with a file tool, and there the shell
touch is the only way memory reaches it.
"""

# ruff: noqa: F811  (tests take the imported `store` fixture as a parameter)
from __future__ import annotations

from pathlib import Path

import pytest

from sanchopanza.harness import memory_hook as mh

from .test_memory_hook import (
    CWD,
    HEX_LINE,
    _bash_setup,
    bash_event,
    context_of,
    event,
    store,  # noqa: F401  (the fixture)
    touch_event,
)

CARBON = "pygments/lexers/carbon.py"


def test_after_a_file_tool_edit_the_shell_touch_gives_nothing(store: Path) -> None:
    new = _bash_setup(store)
    assert mh.handle(touch_event(new, "s2", "Edit", f"{CWD}/README.md", "nothing of s1")) == {}
    assert mh.handle(bash_event(new, "s2", f"cat {CARBON}", HEX_LINE)) == {}
    # the file tools' own touch is unchanged
    assert "session s1" in context_of(mh.handle(touch_event(new, "s2", "Read", f"{CWD}/{CARBON}")))


def test_a_read_through_a_file_tool_keeps_the_shell_touch(store: Path) -> None:
    new = _bash_setup(store)
    assert mh.handle(touch_event(new, "s2", "Read", f"{CWD}/README.md", "other text here")) == {}
    assert "session s1" in context_of(mh.handle(bash_event(new, "s2", f"cat {CARBON}", HEX_LINE)))


def test_the_closed_shell_touch_stays_closed_after_the_next_prompt(
    store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SANCHOPANZA_MEMORY_PROMPT", "off")  # the prompt itself gives nothing
    new = _bash_setup(store)
    mh.handle(touch_event(new, "s2", "Edit", f"{CWD}/notes.txt", "nothing of s1"))
    mh.handle(event(new, "UserPromptSubmit", "s2", "and now the lexer"))
    assert mh.handle(bash_event(new, "s2", f"cat {CARBON}", HEX_LINE)) == {}


def test_a_write_does_not_close_the_shell_touch(store: Path) -> None:
    # review of the gate: a shell editor may create one file with Write and edit on with sed
    new = _bash_setup(store)
    mh.handle(touch_event(new, "s2", "Write", f"{CWD}/notes.txt", ""))
    assert "session s1" in context_of(mh.handle(bash_event(new, "s2", f"cat {CARBON}", HEX_LINE)))


def test_the_flag_survives_a_record_given_and_a_compaction(store: Path) -> None:
    new = _bash_setup(store)
    mh.handle(touch_event(new, "s2", "Edit", f"{CWD}/README.md", "nothing of s1"))
    assert "session s1" in context_of(mh.handle(touch_event(new, "s2", "Read", f"{CWD}/{CARBON}")))
    mh.handle({**event(new, "SessionStart", "s2"), "source": "compact"})
    assert mh.handle(bash_event(new, "s2", f"cat {CARBON}", HEX_LINE)) == {}
    assert mh._state(mh.store_for({"transcript_path": str(new)}), "s2").get("file_edit")


def test_a_subagent_s_edit_does_not_close_the_shell_touch(store: Path) -> None:
    new = _bash_setup(store)
    edit = touch_event(new, "s2", "Edit", f"{CWD}/README.md", "nothing of s1")
    mh.handle({**edit, "agent_id": "sub-1"})
    assert "session s1" in context_of(mh.handle(bash_event(new, "s2", f"cat {CARBON}", HEX_LINE)))


def test_another_session_s_edit_does_not_close_this_one(store: Path) -> None:
    new = _bash_setup(store)
    mh.handle(touch_event(new, "other", "Edit", f"{CWD}/README.md", "nothing of s1"))
    assert "session s1" in context_of(mh.handle(bash_event(new, "s2", f"cat {CARBON}", HEX_LINE)))
