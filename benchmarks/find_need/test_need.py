"""The need measure and the trigger replays on fixed fake streams. No Docker, no API.

Run: .venv/Scripts/python.exe -m pytest benchmarks/find_need -q
"""

from __future__ import annotations

import json
from pathlib import Path

from .need import dev_set, gold_files, per_instance
from .real import names_code, turn_need
from .replay import (
    Call,
    is_empty,
    is_listing,
    reach,
    replay_empty,
    replay_live,
    replay_wide,
    source_edits,
    stream_calls,
    transcript_turns,
)

LISTING = "find . -type f -name '*.py' | grep -E '(auth|form)' | head -20"
TWENTY = "\n".join(f"./pkg/m{i}.py" for i in range(20))


def _use(uid: str, name: str, given: dict, parent: str | None = None) -> dict:
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"id": f"m-{uid}", "content": [
                {"type": "tool_use", "id": uid, "name": name, "input": given}]}}  # fmt: skip


def _result(uid: str, text: str, structured: object = None, error: bool = False) -> dict:
    return {"type": "user", "parent_tool_use_id": None, "tool_use_result": structured,
            "message": {"content": [{"type": "tool_result", "tool_use_id": uid,
                                     "content": text, "is_error": error}]}}  # fmt: skip


def _stream(tmp_path: Path, events: list[dict]) -> Path:
    path = tmp_path / "stream-1.jsonl"
    init = {"type": "system", "subtype": "init", "model": "claude-haiku-4-5-20251001"}
    path.write_text("\n".join(json.dumps(e) for e in [init, *events]) + "\n", encoding="utf-8")
    return path


def _calls(tmp_path: Path) -> list[Call]:
    """listing (wide) -> empty grep -> Read gold -> empty Grep -> Write new script -> Edit gold."""
    events = [
        _use("a", "Bash", {"command": LISTING}),
        _result("a", TWENTY, {"stdout": TWENTY}),
        _use("b", "Bash", {"command": "grep -rn 'nothing' pkg"}),
        _result("b", "Error: Exit code 1", "Error: Exit code 1", error=True),
        _use("x", "Grep", {"pattern": "y"}, parent="sub"),  # a subagent's call: not counted
        _use("c", "Read", {"file_path": "C:\\w\\pkg\\core.py"}),
        _result("c", "1\tcode"),
        _use("d", "Grep", {"pattern": "zzz"}),
        _result(
            "d", "No files found", {"mode": "files_with_matches", "numFiles": 0, "filenames": []}
        ),  # fmt: skip
        _use("e", "Write", {"file_path": "C:\\w\\repro.py", "content": "x"}),
        _result("e", "ok"),
        _use("f", "Edit", {"file_path": "C:\\w\\pkg\\core.py"}),
        _result("f", "ok"),
    ]
    meta, calls = stream_calls(_stream(tmp_path, events))
    assert meta["model"] == "claude-haiku-4-5-20251001"
    return calls


def test_stream_keeps_main_thread_calls_with_results(tmp_path: Path) -> None:
    calls = _calls(tmp_path)
    assert [c.name for c in calls] == ["Bash", "Bash", "Read", "Grep", "Write", "Edit"]
    assert calls[0].result == {"stdout": TWENTY}
    assert calls[1].error and is_empty(calls[1]) and is_empty(calls[3])
    assert not is_empty(calls[0])


def test_listing_versus_content_search() -> None:
    assert is_listing(Call("Bash", {"command": LISTING}))
    assert is_listing(Call("Glob", {"pattern": "**/*.py"}))
    assert not is_listing(Call("Bash", {"command": "grep -rn foo . | head -20"}))
    assert not is_listing(Call("Bash", {"command": "find . -name '*.py' | xargs grep -l foo"}))


def test_source_edits_skip_new_files_and_tests() -> None:
    calls = [Call("Write", {"file_path": "repro.py"}), Call("Edit", {"file_path": "repro.py"}),
             Call("Edit", {"file_path": "tests/test_core.py"}),
             Call("Read", {"file_path": "pkg/old.py"}), Call("Write", {"file_path": "pkg/old.py"}),
             Call("Edit", {"file_path": "pkg/core.py"}, error=True),
             Call("Edit", {"file_path": "pkg/core.py"})]  # fmt: skip
    assert source_edits(calls) == [4, 6]


def test_reach_counts_searches_before_the_gold_read(tmp_path: Path) -> None:
    calls = _calls(tmp_path)
    facts = reach(calls, ["pkg/core.py"])
    assert (facts["read_at"], facts["read_searches"], facts["searches_total"]) == (3, 2, 3)
    view = reach([Call("Bash", {"command": "sed -n 1,40p pkg/core.py"})], ["pkg/core.py"])
    assert (view["read_at"], view["view_at"], view["view_searches"]) == (None, 1, 0)


def test_replays(tmp_path: Path) -> None:
    calls = _calls(tmp_path)
    live = replay_live(calls)
    assert live is not None and (live.call, live.search, live.kind) == (1, 1, "listing")
    assert replay_wide(calls, 3, "source", listings=False) is None
    new = replay_empty(calls, 2, "source")  # the 2nd empty search, before the Edit of core.py
    assert new is not None and (new.call, new.search, new.kind) == (4, 3, "empty")
    assert replay_empty(calls, 2, "source", within=2) is None
    assert replay_empty(calls[:2] + calls[5:], 2, "source") is None  # edited before a 2nd empty


def test_transcript_turns_split_on_typed_requests(tmp_path: Path) -> None:
    rows = [
        {"type": "user", "message": {"content": "the totals are wrong after a refund"}},
        {"type": "assistant", "message": {"model": "m", "content": [
            {"type": "tool_use", "id": "1", "name": "Grep", "input": {"pattern": "refund"}}]}},
        {"type": "user", "toolUseResult": {"numFiles": 0, "filenames": []},
         "message": {"content": [{"type": "tool_result", "tool_use_id": "1", "content": ""}]}},
        {"type": "user", "isMeta": True,
         "message": {"content": "<system-reminder>x</system-reminder>"}},
        {"type": "user", "message": {"content": "now fix `calc_total` in billing.py"}},
    ]  # fmt: skip
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    turns = transcript_turns(path)
    assert [len(t["calls"]) for t in turns] == [1, 0] and turns[0]["model"] == "m"
    assert is_empty(turns[0]["calls"][0])
    assert not names_code(turns[0]["prompt"]) and names_code(turns[1]["prompt"])


def test_turn_need_targets_the_first_source_edit() -> None:
    calls = [Call("Grep", {"pattern": "a"}), Call("Read", {"file_path": "x/b.py"}),
             Call("Edit", {"file_path": "x/b.py"})]  # fmt: skip
    assert turn_need(calls) == {"edits": True, "read_at": 2, "searches": 1}
    assert turn_need(calls[:2]) == {"edits": False}


def _row(instance: str, arm: str, searches: int | None, source: str = "A-singles") -> dict:
    return {"source": source, "instance": instance, "arm": arm, "variant": "", "repo": "r",
            "difficulty": "d", "reach_searches": searches, "resolved": None,
            "hard": searches is None or searches >= 5}  # fmt: skip


def test_dev_set_ranks_by_hard_share_and_skips_phase_d() -> None:
    rows = [_row("a__a-1", "N", None), _row("a__a-1", "S", 9),  # 2/2 hard
            _row("b__b-2", "N", 6), _row("b__b-2", "S", 1),  # 1/2 hard
            _row("c__c-3", "N", 12), _row("c__c-3", "S", 12),  # 2/2 but in phase D
            _row("d__d-4", "N", 1), _row("d__d-4", "S", 30),  # control easy: not eligible
            _row("e__e-5", "F", 20, "find-e2e")]  # no control arm  # fmt: skip
    table = per_instance(rows, excluded={"c__c-3"})
    assert [r["instance"] for r in table][:3] == ["a__a-1", "e__e-5", "c__c-3"]
    assert dev_set(table) == ["a__a-1", "b__b-2"]


def test_gold_files_from_a_patch() -> None:
    patch = "diff --git a/x/b.py b/x/b.py\n--- a/x/b.py\ndiff --git a/a.py b/a.py\n"
    assert gold_files(patch) == ["a.py", "x/b.py"]
