"""The deterministic rules: what code decides about a tool result before any decider."""

from __future__ import annotations

import pytest

from sanchopanza.context import Call, calls, messages_from_claude_code, triage_rules
from sanchopanza.context.rules import failed

from .context_helpers import write_transcript

BIG = "x" * 1_000


def _verdicts(tmp_path, **options):
    messages = messages_from_claude_code(write_transcript(tmp_path / "s.jsonl"))
    return {
        k: (v.action, v.reason)
        for k, v in triage_rules(messages, calls(messages), **options).items()
    }


def test_the_rules_on_the_hand_written_session(tmp_path):
    verdicts = _verdicts(tmp_path, keep_recent=0)
    assert verdicts["t1"] == ("stub", "read_superseded")  # edited and read again later
    assert verdicts["t2"] == ("stub", "error_retried")  # the same command passed later
    assert verdicts["t3"] == ("keep", "small")
    assert verdicts["t4"] == ("ask", "undecided")
    assert verdicts["t5"] == ("ask", "undecided")


def test_the_last_messages_are_always_kept(tmp_path):
    verdicts = _verdicts(tmp_path, keep_recent=6)
    assert verdicts["t4"] == ("keep", "recent") and verdicts["t5"] == ("keep", "recent")
    assert verdicts["t1"] == ("stub", "read_superseded")


def _call(i: int, tool: str, result: str = BIG, error: bool = False, **arguments) -> Call:
    return Call(f"c{i}", tool, arguments, result, error, use_msg=2 * i + 1, result_msg=2 * i + 2)


def _run(*found: Call, keep_recent: int = 0):
    messages = [{"role": "user", "content": "x"}] * (2 * len(found) + 1)
    return triage_rules(messages, list(found), keep_recent=keep_recent)


def test_an_error_never_retried_is_kept():
    verdicts = _run(_call(0, "Bash", error=True, command="make"), _call(1, "Bash", command="ls"))
    assert (verdicts["c0"].action, verdicts["c0"].reason) == ("keep", "error")


def test_an_error_retried_and_failing_again_is_kept():
    verdicts = _run(
        _call(0, "Bash", error=True, command="make"), _call(1, "Bash", error=True, command="make")
    )
    assert verdicts["c0"].reason == "error"


def test_a_failure_is_read_from_the_text_too():
    assert failed(Call("a", "Bash", {}, "Traceback (most recent call last):\n..."))
    assert failed(Call("a", "Bash", {}, "<tool_use_error>File does not exist</tool_use_error>"))
    assert not failed(Call("a", "Read", {}, "this file mentions an error in passing"))


def test_a_read_of_another_range_does_not_supersede():
    verdicts = _run(
        _call(0, "Read", file_path="/a.py", offset=1, limit=50),
        _call(1, "Read", file_path="/a.py", offset=200, limit=50),
    )
    assert verdicts["c0"].action == "ask"
    whole = _run(
        _call(0, "Read", file_path="C:\\p\\a.py", offset=1, limit=50),
        _call(1, "Read", file_path="C:/p/a.py"),
    )
    assert whole["c0"].reason == "read_superseded"  # the whole file, same path either slash


def test_a_failed_edit_does_not_supersede_a_read():
    verdicts = _run(
        _call(0, "Read", file_path="/a.py"), _call(1, "Edit", error=True, file_path="/a.py")
    )
    assert verdicts["c0"].action == "ask"


def test_a_repeated_command_stubs_the_earlier_one_only():
    verdicts = _run(_call(0, "Bash", command="git status"), _call(1, "Bash", command="git status"))
    assert verdicts["c0"].reason == "command_repeated" and verdicts["c1"].action == "ask"


def test_an_earlier_stub_is_left_alone():
    stub = "[sanchopanza pruned this Read result: 900 chars. Full text saved at /x; Read it.]" * 6
    assert _run(_call(0, "Read", result=stub, file_path="/a"))["c0"].reason == "already_pruned"


def test_negative_options_are_refused():
    with pytest.raises(ValueError):
        triage_rules([], [], keep_recent=-1)
