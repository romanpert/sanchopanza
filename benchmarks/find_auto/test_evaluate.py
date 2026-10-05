"""The substitution evaluation's pure parts on fixed fakes. No repository, no Docker, no API.

Run: .venv/Scripts/python.exe -m pytest benchmarks/find_auto -q
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from benchmarks.find_need.replay import Call

from .evaluate import (
    CACHE_READ,
    CACHE_WRITE,
    HEADER,
    call_turns,
    context_cost,
    expected_value,
    fire_points,
    gold_lines,
    hits,
    is_source,
    queries,
    query_name,
    render,
    replay_untouched,
    repo_path,
    search_words,
    value,
)

PATCH = """diff --git a/pkg/core.py b/pkg/core.py
--- a/pkg/core.py
+++ b/pkg/core.py
@@ -10,4 +10,4 @@ def f():
     a = 1
-    b = 2
+    b = 3
     c = 4
     d = 5
@@ -40,2 +40,3 @@ def g():
     x = 1
+    y = 2
     z = 3
"""

EMPTY_GREP = {"numFiles": 0, "filenames": [], "content": ""}
FULL_GREP = {"numFiles": 2, "filenames": ["pkg/a.py", "pkg/b.py"]}


def _grep(pattern: str, result: dict) -> Call:
    return Call("Grep", {"pattern": pattern}, result)


def test_gold_lines_marks_removed_lines_and_both_sides_of_an_insertion() -> None:
    assert gold_lines(PATCH) == {"pkg/core.py": {11, 40, 41}}


def test_hits_count_files_and_changed_lines_within_the_first_k() -> None:
    lines = gold_lines(PATCH)
    keys = ["docs/x.rst:1-9", "pkg/core.py:20-30", "pkg/core.py:1-12"]
    got = hits(keys, lines)
    assert not got["any@1"] and got["any@3"] and got["short60"]
    assert not got["hunk@1"] and got["hunk@3"]
    assert hits(keys[:2], lines)["hunk@3"] is False  # the file, but not the changed lines


def test_search_words_keep_the_searched_names_and_drop_shell_words() -> None:
    bash = Call("Bash", {"command": "grep -rn 'def to_stacked_array' /testbed --include=*.py"})
    assert search_words(bash) == ["to_stacked_array"]
    assert search_words(_grep("class Foo\\(Bar", EMPTY_GREP)) == ["Foo", "Bar"]
    assert search_words(Call("Read", {"file_path": "a.py"})) == []


def test_queries_split_empty_searches_from_all_searches() -> None:
    calls = [_grep("found_name", FULL_GREP), _grep("missing_name", EMPTY_GREP)]
    got = queries("the issue", calls, fire=2)
    assert got["Q2"] == "the issue\nmissing_name"
    assert got["Q3"] == "the issue\nfound_name missing_name"
    assert got["Q4"] == "found_name missing_name"
    assert queries("the issue", calls, fire=1)["Q2"] == ""


def test_fire_points_second_empty_search_nth_search_and_the_prompt() -> None:
    calls = [_grep("a1", EMPTY_GREP), Call("Read", {"file_path": "x.py"}, "1\tx"),
             _grep("a2", EMPTY_GREP), _grep("a3", FULL_GREP), _grep("a4", FULL_GREP),
             _grep("a5", FULL_GREP)]  # fmt: skip
    got = fire_points(calls, "Saving a model drops the timezone")
    assert got["A"] == 3  # after the third call, the second empty search
    assert got["B4"] == 5 and got["B5"] == 6 and got["B6"] is None
    assert got["C"] == 0 and got["C0"] == 0
    assert fire_points(calls, "`Model.save()` drops tz")["C"] is None


def test_an_edit_of_a_source_file_closes_the_search_triggers() -> None:
    calls = [_grep("a1", EMPTY_GREP), Call("Read", {"file_path": "pkg/core.py"}, "1\tx"),
             Call("Edit", {"file_path": "pkg/core.py"}, "ok"), _grep("a2", EMPTY_GREP)]  # fmt: skip
    assert fire_points(calls, "x")["A"] is None


def _event(mid: str, uid: str, parent: str | None = None) -> dict:
    return {"type": "assistant", "parent_tool_use_id": parent,
            "message": {"id": mid, "content": [{"type": "tool_use", "id": uid, "name": "Grep",
                                                "input": {}}]}}  # fmt: skip


def test_call_turns_groups_calls_by_api_message_and_skips_subagents(tmp_path: Path) -> None:
    events = [_event("m1", "a"), _event("m1", "b"), _event("m1", "b"), _event("s", "x", "sub"),
              {"type": "assistant", "message": {"id": "m2", "content": [{"type": "text"}]}},
              _event("m3", "c"),
              {"type": "result", "total_cost_usd": 0.03, "num_turns": 3}]  # fmt: skip
    path = tmp_path / "stream-1.jsonl"
    path.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
    turns, result = call_turns(path)
    assert turns == [1, 1, 3]
    assert result == {"cost": 0.03, "turns": 3, "api_turns": 3}


def test_value_counts_saved_turns_only_for_an_early_hit() -> None:
    turns = [1, 2, 3, 4, 5, 6, 7, 8]
    assert value(None, 8, turns, True) == {"fired": False}
    hit = value(3, 8, turns, True)
    assert hit["before_reach"] and hit["saved_turns"] == 4 and hit["saved_calls"] == 4
    assert "saved_turns" not in value(3, 8, turns, False)
    late = value(8, 5, turns, True)
    assert not late["before_reach"] and "saved_turns" not in late
    assert "saved_turns" not in value(3, None, turns, True)  # never reached: no turn count
    assert value(0, 3, turns, True)["saved_turns"] == 2  # at the prompt


def test_expected_value_weighs_saved_turns_against_context_and_detours() -> None:
    base = {"turns": 10, "cost_per_turn": 0.01}
    rows = [
        {**base, "value": {"fired": True, "before_reach": True, "hit": True, "turn": 2,
                           "saved_turns": 4}},
        {**base, "value": {"fired": True, "before_reach": True, "hit": False, "turn": 2}},
        {**base, "value": {"fired": True, "before_reach": False, "hit": True, "turn": 2}},
        {**base, "value": {"fired": False}},
    ]  # fmt: skip
    got = expected_value(rows, follow=0.5, detour=1.0, tokens=100)
    context = 3 * context_cost(100, 8)
    assert context == pytest.approx(3 * 100 * (CACHE_WRITE + 8 * CACHE_READ))
    assert got["saved_usd"] == pytest.approx(0.02)
    assert got["cost_usd"] == pytest.approx(round(context + 0.01, 4))


def test_is_source_keeps_library_code_only() -> None:
    assert is_source("django/db/models/base.py:1-20")
    assert not is_source("tests/model_fields/test_x.py:1-20")
    assert not is_source("docs/ref/models.txt:1-20")
    assert not is_source(".github/ISSUE_TEMPLATE/bugreport.yml:39-47")
    assert not is_source("examples/plot.py:1-9")


def test_query_name_maps_variants_and_the_prompt_to_q1() -> None:
    fact = {"fires": {"A": 4, "C": 0}, "queries": {"A": {"Q3": "abc"}}}
    assert query_name(fact, "A", "Q3") == "abc"
    assert query_name(fact, "A", "Q3+code") == "abc+code"
    assert query_name(fact, "A", "Q1+code") == "Q1+code"
    assert query_name(fact, "C", "Q3") == "Q1"
    assert query_name(fact, "A", "Q2") is None


def test_render_shows_keys_and_the_line_with_most_query_words() -> None:
    note = render([("pkg/core.py:10-20", "def f():\n    tz = aware(value)\n    return 1")],
                  "aware tz value lost")  # fmt: skip
    assert note.splitlines() == [HEADER, "- pkg/core.py:10-20  tz = aware(value)"]


def test_untouched_trigger_counts_searches_until_a_source_file_is_read() -> None:
    assert repo_path(r"C:\c\work\django__django-1-N\django\db\core.py") == "django/db/core.py"
    assert repo_path("/testbed/.github/x.yml") == ".github/x.yml"
    searches = [_grep(f"s{i}", FULL_GREP) for i in range(4)]
    assert replay_untouched(searches, 4).call == 4
    test_read = Call("Read", {"file_path": "/testbed/tests/test_a.py"}, "1\tx")
    assert replay_untouched([*searches[:2], test_read, *searches[2:]], 4).call == 5
    source_read = Call("Read", {"file_path": "/testbed/pkg/core.py"}, "1\tx")
    assert replay_untouched([*searches[:2], source_read, *searches[2:]], 4) is None
