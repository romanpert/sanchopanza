"""The alternative find_auto windows on fixed fakes. No repository, no Docker, no API.

Run: .venv/Scripts/python.exe -m pytest benchmarks/find_auto -q
"""

from __future__ import annotations

from benchmarks.find_need.replay import Call

from .windows import (
    gates,
    nth_before_edit,
    nth_before_edited_read,
    nth_since_any_read,
    nth_since_kept_read,
    r4,
    r4_or_mth,
)

GREP = {"numFiles": 2, "filenames": ["pkg/a.py", "pkg/b.py"]}


def _searches(n: int) -> list[Call]:
    return [Call("Grep", {"pattern": f"s{i}"}, GREP) for i in range(n)]


def _read(path: str) -> Call:
    return Call("Read", {"file_path": f"/testbed/{path}"}, "1\tx")


def _edit(path: str) -> Call:
    return Call("Edit", {"file_path": f"/testbed/{path}", "old_string": "a", "new_string": "b"})


WRONG, GOLD = _read("pkg/wrong.py"), _read("pkg/gold.py")


def test_a_wrong_source_read_closes_r4_but_not_w1() -> None:
    calls = [*_searches(2), WRONG, *_searches(3)]
    assert r4(calls) is None
    assert nth_before_edit(calls, 4).call == 5


def test_an_edit_closes_w1_and_a_created_file_does_not() -> None:
    created = Call("Write", {"file_path": "/testbed/repro.py", "content": "x"})
    assert nth_before_edit([*_searches(2), _edit("pkg/gold.py"), *_searches(3)], 4) is None
    assert nth_before_edit([*_searches(2), created, *_searches(2)], 4).call == 5


def test_w2_resets_only_on_a_read_followed_by_its_edit() -> None:
    kept = [*_searches(3), GOLD, *_searches(1), _edit("pkg/gold.py")]
    assert nth_since_kept_read(kept, 4) is None  # the reset, then the edit closes
    wrong = [*_searches(3), WRONG, *_searches(2)]
    assert nth_since_kept_read(wrong, 4).call == 5


def test_w3_closes_only_on_the_file_later_edited() -> None:
    calls = [*_searches(2), WRONG, *_searches(2), GOLD, _edit("pkg/gold.py")]
    assert nth_before_edited_read(calls, 4).call == 5
    assert nth_before_edited_read([*_searches(2), GOLD, *_searches(2), _edit("pkg/gold.py")],
                                  4) is None  # fmt: skip


def test_w4_is_r4_then_the_mth_search_after_a_read_closed_it() -> None:
    assert r4_or_mth(_searches(5), 8).call == 4
    calls = [*_searches(2), WRONG, *_searches(6)]
    assert r4_or_mth(calls, 8).call == 9
    assert r4_or_mth([*calls[:5], _edit("pkg/wrong.py"), *calls[5:]], 8) is None


def test_w5_counts_searches_in_a_row_without_a_source_read() -> None:
    calls = [*_searches(3), WRONG, *_searches(3), WRONG, *_searches(4)]
    assert nth_since_any_read(calls, 4).call == 12
    assert nth_since_any_read(_searches(4), 4).call == 4


def test_gates_read_what_the_top_five_shows_against_the_reads() -> None:
    keys = ["pkg/a.py:1-9", "pkg/a.py:10-20", "pkg/b.py:1-5", "pkg/c.py:1-5"]
    assert gates(keys, {"pkg/a.py"}) == {"top1_unread": False, "two_unread": True,
                                         "any_unread": True}  # fmt: skip
    assert gates(keys, {"pkg/a.py", "pkg/b.py"})["two_unread"] is False
    assert gates(keys, set())["top1_unread"] is True
