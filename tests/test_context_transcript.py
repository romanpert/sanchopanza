"""Reading a Claude Code transcript into Messages-API messages, and pairing the tool calls."""

from __future__ import annotations

import json

from sanchopanza.context import calls, messages_from_claude_code
from sanchopanza.context.transcript import (
    blocks_of,
    chars,
    is_prompt,
    merge_consecutive,
    message_text,
    task_of,
    text_of,
)

from .context_helpers import APP, ENTRIES, write_transcript


def test_entries_become_alternating_messages_without_sidechains_meta_or_system(tmp_path):
    messages = messages_from_claude_code(write_transcript(tmp_path / "s.jsonl"))
    assert [m["role"] for m in messages] == ["user", "assistant"] * 6
    first_reply = messages[1]["content"]
    assert [b["type"] for b in first_reply] == ["text", "tool_use"]  # two entries, one message
    flat = json.dumps(messages)
    assert "s1" not in flat and "Caveat" not in flat and "older session" not in flat


def test_every_call_is_paired_with_its_result_in_order(tmp_path):
    messages = messages_from_claude_code(write_transcript(tmp_path / "s.jsonl"))
    found = calls(messages)
    assert [c.id for c in found] == ["t1", "t2", "t3", "t4", "t5"]
    t2 = found[1]
    assert t2.tool == "Bash" and t2.is_error and t2.input == {"command": "pytest -q"}
    assert (t2.use_msg, t2.result_msg) == (3, 4)
    assert found[3].result == APP.replace("-", "+")  # a list of text blocks, joined


def test_a_call_without_its_result_is_not_a_candidate():
    messages = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "a", "name": "Bash"}]},
    ]
    assert calls(messages) == []


def test_a_compact_boundary_starts_the_conversation_again(tmp_path):
    entries = [
        *ENTRIES[:5],
        {"type": "system", "subtype": "compact_boundary"},
        {"type": "user", "message": {"role": "user", "content": "Summary of before"}},
    ]
    messages = messages_from_claude_code(write_transcript(tmp_path / "s.jsonl", entries))
    assert messages == [
        {"role": "user", "content": [{"type": "text", "text": "Summary of before"}]}
    ]


def test_a_broken_line_is_skipped_not_fatal(tmp_path):
    path = write_transcript(tmp_path / "s.jsonl")
    path.write_text(path.read_text(encoding="utf-8") + '{"type": "user", "mess\n', encoding="utf-8")
    assert len(messages_from_claude_code(path)) == 12


def test_task_is_the_first_and_the_latest_prompt():
    messages = [
        {"role": "user", "content": "Build the parser"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x", "content": "r"}]},
        {"role": "user", "content": "Now add tests"},
    ]
    assert task_of(messages) == "First request: Build the parser\n\nLatest request: Now add tests"
    assert task_of(messages[:1]) == "Build the parser"
    assert task_of([]) == ""
    assert not is_prompt(messages[2]) and not is_prompt(messages[1])


def test_text_helpers():
    assert text_of([{"type": "text", "text": "a"}, {"type": "image"}, "junk"]) == "a\n[image]"
    assert text_of(None) == ""
    assert blocks_of({"content": ""}) == [] and blocks_of({"content": 5}) == []
    assert message_text({"content": [{"type": "thinking", "thinking": "x"}]}) == ""
    merged = merge_consecutive([{"role": "user", "content": "a"}, {"role": "user", "content": "b"}])
    assert len(merged) == 1 and len(merged[0]["content"]) == 2


def test_chars_counts_text_inputs_and_results():
    messages = [
        {"role": "user", "content": "abc"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "a", "input": {"k": 1}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "a", "content": "xy"}]},
    ]
    assert chars(messages) == 3 + len('{"k": 1}') + 2
