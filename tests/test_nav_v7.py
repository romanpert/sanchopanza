"""v7's development runner: line v6 plus the crawl notes against Haiku alone. No model, no
browser, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("browse_nav_v7", ROOT / "benchmarks/browse/nav_v7.py")
v7 = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_v7"] = v7
spec.loader.exec_module(v7)
v7.install()
nav = v7.nav


def test_the_round_is_the_five_tasks_and_three_arms_under_its_ceiling():
    assert [t[0] for t in v7.TASKS] == ["F1", "F2", "F3", "F5", "F8"]
    assert v7.ARMS[0] == "HAIKU-V7" and v7.ARMS[-1] == "HAIKU-V6", "V6 only if it fits"
    assert v7.CEILING_USD <= 6.00 and nav.SESSION_MAX_USD == 1.00
    for tool in ("SendMessage", "ListAgents", "ScheduleWakeup", "CronCreate", "RemoteTrigger"):
        assert tool in nav.DISALLOWED.split()


def test_only_v7_gets_the_notes(tmp_path):
    def env(arm):
        return json.loads(v7.settings_for(arm, tmp_path).read_text("utf-8")).get("env")

    assert env("HAIKU-V7") == {
        "SANCHOPANZA_CRAWL_LINE_VERSION": "6",
        "SANCHOPANZA_CRAWL_NOTES": "1",
    }
    assert env("HAIKU-V6") == {"SANCHOPANZA_CRAWL_LINE_VERSION": "6"}
    assert env("HAIKU") is None


def _row(arm, evaluates=2):
    return {"task": "F5", "run": 1, "arm": arm, "ok": True, "workdir": "x", "success": True,
            "list_usd": 0.1, "tools": {"mcp__playwright__browser_evaluate": evaluates}}  # fmt: skip


@pytest.mark.parametrize(
    ("arm", "notes", "evaluates", "not_run"),
    [
        ("HAIKU-V7", True, 2, False),
        ("HAIKU-V7", False, 2, True),
        ("HAIKU-V7", False, 0, False),  # no evaluate, nothing to carry the notes
        ("HAIKU-V6", True, 2, True),
        ("HAIKU-V6", False, 2, False),
    ],
)
def test_a_session_counts_only_with_the_notes_its_arm_should_have(
    monkeypatch, arm, notes, evaluates, not_run
):
    text = v7.v6.MARKS["6"] + (" /* sanchopanza notes */" if notes else "")
    monkeypatch.setattr(nav, "one_session", lambda task, run, a: _row(a, evaluates))
    monkeypatch.setattr(v7.v6.confirm3, "_transcript", lambda workdir: text)
    assert bool(v7.one_session(v7.TASKS[3], 1, arm).get("not_run")) is not_run


def test_a_guard_stop_is_counted_as_a_tool_result_not_as_the_sentence_in_the_code(monkeypatch):
    code = '"function": "... evaluate stopped after 120 s ..."'
    stop = '"content":"### Error\\nError: evaluate stopped after 120 s"'
    text = v7.v6.MARKS["6"] + " /* sanchopanza notes */ " + code * 5 + stop
    monkeypatch.setattr(nav, "one_session", lambda task, run, a: _row(a))
    monkeypatch.setattr(v7.v6.confirm3, "_transcript", lambda workdir: text)
    assert v7.one_session(v7.TASKS[0], 1, "HAIKU-V7")["guard_stops"] == 1
