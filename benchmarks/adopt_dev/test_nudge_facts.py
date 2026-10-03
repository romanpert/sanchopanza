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


def test_find_hook_ran_reads_invocations_not_firings(tmp_path: Path) -> None:
    from .nudge_facts import find_hook_ran

    assert find_hook_ran(tmp_path) is False  # no hooks.jsonl at all
    _write(tmp_path / "hooks.jsonl", [{"sub": "hook", "event": "PreToolUse"},
                                      {"sub": "find-mcp", "event": "server start"}])  # fmt: skip
    assert find_hook_ran(tmp_path) is False
    _write(tmp_path / "hooks.jsonl", [{"sub": "find-hook", "event": "PostToolUse",
                                       "out_chars": 0}])  # fmt: skip
    assert find_hook_ran(tmp_path) is True  # ran, did not fire: enough


GUARD = """
import json, sys
from pathlib import Path
from benchmarks.adopt_dev import probe_nudge as p
p.OUT = Path(sys.argv[1])
row = {"instance": "x", "arm": "S", "calls": [{}]}
checked = []
p.guard_find_hook({**row, "arm": "N"}, checked)  # an N session is never checked
try:
    p.guard_find_hook(row, checked)
except p.base.Stop as why:
    print("STOP", why)
p.guard_find_hook(row, checked)  # only the first S session is checked
print("checked", checked)
"""


def test_the_probe_stops_when_find_hook_never_ran(tmp_path: Path) -> None:
    """In a process of its own: probe_nudge pins common.py to the nudge profile."""
    import os
    import subprocess
    import sys

    (tmp_path / "x" / "S").mkdir(parents=True)
    _write(tmp_path / "x" / "S" / "hooks.jsonl", [{"sub": "hook", "event": "PreToolUse"}])
    root = Path(__file__).resolve().parents[2]
    # common.py, imported here for another profile, set ADOPT_SANCHO to that profile's copy
    env = {k: v for k, v in os.environ.items() if k != "ADOPT_SANCHO"}
    env = {**env, "ADOPT_DEV_PROFILE": "nudge"}
    out = subprocess.run([sys.executable, "-c", GUARD, str(tmp_path)], cwd=root, env=env,
                         capture_output=True, text=True, timeout=120)  # fmt: skip
    assert out.returncode == 0, out.stderr[-2000:]
    assert "STOP find-hook never ran (x S" in out.stdout
    assert "checked ['x']" in out.stdout
