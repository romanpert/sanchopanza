"""The nudge probe's facts from an evidence folder, without Docker or the API.

Run: .venv/Scripts/python.exe -m pytest benchmarks/adopt_dev -q
"""

from __future__ import annotations

import json
from pathlib import Path

from .nudge_facts import FIND_TOOL, before_gold, describe, firings, tool_calls


def _assistant(mid: str, *calls: tuple[str, dict]) -> dict:
    blocks = [{"type": "tool_use", "id": f"{mid}-{i}", "name": n, "input": a}
              for i, (n, a) in enumerate(calls)]  # fmt: skip
    return {"type": "assistant", "message": {"id": mid, "content": blocks}}


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _evidence(tmp_path: Path) -> Path:
    rows = [
        _assistant("m1", ("Grep", {"pattern": "x"})),
        _assistant("m1", ("Bash", {"command": "find . -name '*.py' | head -20"})),
        _assistant("m2", (FIND_TOOL, {"query": "drops the last row"})),
        _assistant("m3", ("Read", {"file_path": "C:\\w\\django\\db\\query.py"})),
        _assistant("m4", ("Edit", {"file_path": "django/db/query.py"})),
        {"type": "assistant", "isSidechain": True, "message": {"id": "s1", "content": []}},
    ]
    _write(tmp_path / "transcript.jsonl", rows)
    _write(tmp_path / "journal.jsonl", [
        {"kind": "decision", "data": {}},
        {"kind": "find_nudge", "data": {"tool": "Bash", "search": 2, "listed": 20}}])  # fmt: skip
    _write(tmp_path / "hooks.jsonl", [
        {"sub": "find-hook", "event": "PostToolUse", "seconds": 0.1, "out_chars": 0},
        {"sub": "find-hook", "event": "PostToolUse", "seconds": 0.2, "out_chars": 300},
        {"sub": "hook", "event": "PreToolUse", "seconds": 0.3}])  # fmt: skip
    return tmp_path


def test_tool_calls_carry_their_api_call(tmp_path: Path) -> None:
    calls = tool_calls(_evidence(tmp_path) / "transcript.jsonl")
    assert [c["api_call"] for c in calls] == [1, 1, 2, 3, 4]


def test_searches_before_the_first_gold_read(tmp_path: Path) -> None:
    calls = tool_calls(_evidence(tmp_path) / "transcript.jsonl")
    seen = before_gold(calls, ["django/db/query.py"])
    assert seen == {"searches": 2, "finds": 1, "read_at_call": 4}
    assert before_gold(calls, ["other.py"])["searches"] is None


def test_firings_from_journal_and_hooks(tmp_path: Path) -> None:
    seen = firings(_evidence(tmp_path))
    assert seen["journal"] == [{"tool": "Bash", "search": 2, "listed": 20}]
    assert (seen["hook_events"], seen["hook_outputs"], seen["hook_seconds"]) == (2, 1, 0.3)


def test_describe_one_session(tmp_path: Path) -> None:
    seen = describe(_evidence(tmp_path), ["django/db/query.py"])
    assert seen["find_calls"] == [{"api_call": 2, "call": 3, "query": "drops the last row",
                                   "kind": "code"}]  # fmt: skip
    assert seen["first_edit_call"] == 5 and seen["searches_before_edit"] == 2
