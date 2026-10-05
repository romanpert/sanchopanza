"""The fetch v2 pilot's runner: twenty FRAMES tasks none of the earlier pilots ran, two Haiku
arms, the -FETCH2 arm with the server at version 2 and the hook with the page budget, a 10 USD
ceiling. No model, no network, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


p2 = _load("browse_free_fetch2_pilot", "benchmarks/browse/free_fetch2_pilot.py")
TOOL = p2.TOOL_NAME


def test_arms_caps_ceiling_and_a_private_folder():
    assert p2.ARMS == ("HAIKU", "HAIKU-FETCH2")
    assert p2.CAPS == {"HAIKU": 0.60, "HAIKU-FETCH2": 0.60}
    assert p2.CEILING_USD == 10.0
    assert p2.PRIVATE not in (p2.pilot.PRIVATE, p2.free.CACHE)
    assert p2.SEED != p2.pilot.SEED


def test_the_tasks_are_none_of_any_earlier_pilot():
    assert set(p2.PRIOR_IDS) >= {"frames-ids.txt", "frames2-ids.txt", "fetch-pilot-ids.txt"}
    if not p2.IDS.exists():
        pytest.skip("the ids are drawn on the first --plan")
    ids = p2.IDS.read_text(encoding="utf-8").split()
    assert len(ids) == len(set(ids)) == 20 and not set(ids) & p2.taken_ids()
    if p2.frames.FRAMES.exists():
        assert ids == p2.pilot.sample(p2.frames.read_frames(), p2.taken_ids(), seed=p2.SEED)


def test_the_fetch2_arm_gets_version_two_the_budget_and_both_hook_events(tmp_path):
    assert p2.arm_options("HAIKU", tmp_path) == {"hooks": None, "env_extra": None,
                                                 "mcp_servers": None}  # fmt: skip
    options = p2.arm_options("HAIKU-FETCH2", tmp_path)
    env = options["env_extra"]
    assert env["SANCHOPANZA_FETCH_VERSION"] == "2"
    assert env["SANCHOPANZA_FETCH_MAX_PAGES"] == str(p2.MAX_PAGES)
    assert env["SANCHOPANZA_FETCH_DIR"] == str(tmp_path)
    server = options["mcp_servers"][p2.pilot.SERVER]
    assert server["alwaysLoad"] is True and server["env"]["SANCHOPANZA_FETCH_VERSION"] == "2"
    pre, post = options["hooks"]["PreToolUse"][0], options["hooks"]["PostToolUse"][0]
    assert pre["matcher"] == "WebFetch|WebSearch"
    assert post["matcher"] == f"{TOOL}|WebFetch"
    assert "fetch_hook" in pre["hooks"][0]["command"]
    assert pre["hooks"][0]["command"] == post["hooks"][0]["command"]


def _e(name: str, result: str = "page") -> dict:
    return {"name": name, "input": {}, "result": result, "is_error": False}


def test_page_runs_count_pages_since_the_last_search_and_skip_denied_webfetch():
    denied = _e("WebFetch", p2.pilot.DENIED_MARK + " ...")
    events = [_e(TOOL), _e(TOOL), denied, _e("WebSearch")] + [_e(TOOL)] * 5
    assert p2.page_runs(events, max_pages=3) == {"longest_page_run": 5, "page_notes": 2}


def test_the_replayed_hook_notes_what_the_count_says(tmp_path, monkeypatch):
    events = [_e(TOOL)] * 4 + [_e("WebSearch")] + [_e(TOOL)] * 2
    rows = [{"task": "FR1", "arm": "HAIKU-FETCH", "workdir": str(tmp_path)},
            {"task": "FR1", "arm": "HAIKU", "workdir": str(tmp_path)}]  # fmt: skip
    monkeypatch.setattr(p2.pilot, "_tool_events", lambda folder: events)

    class Hand:
        @staticmethod
        def graded(row):
            return {**row, "ok_hand": True}

    monkeypatch.setattr(p2, "_load", lambda name, path: Hand)
    found = p2.replay_budget(rows, ns=(1, 3))
    assert found["sessions"] == 1
    assert found["by_n"]["1"]["pages_noted"] == 3 + 1
    assert found["by_n"]["3"]["pages_noted"] == 1
    assert found["by_n"]["3"]["right_noted"] == 1


def test_the_scripted_endpoint_calls_the_tool_once_then_answers():
    body = {"model": "m", "tools": [{"name": TOOL}], "messages": [{"role": "user", "content": "q"}]}
    first = p2.scripted_reply(body, "https://example.com/")
    assert first[1]["content_block"]["name"] == TOOL
    assert json.loads(first[2]["delta"]["partial_json"])["url"] == "https://example.com/"
    assert first[-2]["delta"]["stop_reason"] == "tool_use"
    result = {
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "t", "content": "x"}],
    }
    second = p2.scripted_reply({**body, "messages": [*body["messages"], result]}, "u")
    assert second[1]["content_block"]["type"] == "text"
    assert b"event: message_stop" in p2._sse(second)


def test_the_note_mark_is_in_the_hook_note():
    from sanchopanza.harness.fetch_hook import page_note

    assert p2.NOTE_MARK in page_note(9) and len(p2.NOTE_MARK) >= 20


def test_report_counts_by_arm():
    row = {"list_usd": 0.1, "ok_auto": True, "reader_usd": 0.01, "haiku_usd": 0.1,
           "calls": {"web_search": 1, "fetch_passages": 2, "fetch_passages_unread": 0,
                     "passage_tokens": 100, "page_notes": 0}}  # fmt: skip
    out = p2.report([{**row, "arm": "HAIKU"}, {**row, "arm": "HAIKU-FETCH2"}])
    assert set(out["by_arm"]) == {"HAIKU", "HAIKU-FETCH2"} and out["max_pages"] == p2.MAX_PAGES


hand2 = _load("browse_free_fetch2_pilot_hand", "benchmarks/browse/free_fetch2_pilot_hand.py")


def _graded(task: str, arm: str, right: bool, web: int, usd: float = 0.1) -> dict:
    return {"task": task, "arm": arm, "ok_auto": right, "list_usd": usd,
            "calls": {"web_search": web}}  # fmt: skip


def test_the_hand_report_pairs_the_two_haiku_arms(monkeypatch):
    rows = [_graded("A", "HAIKU", True, 2), _graded("A", "HAIKU-FETCH2", False, 1),
            _graded("B", "HAIKU", False, 1), _graded("B", "HAIKU-FETCH2", True, 0)]  # fmt: skip
    monkeypatch.setitem(hand2.HAND, ("B", "HAIKU"), (True, "why"))
    out = hand2.report(rows, None)
    assert out["by_arm"]["HAIKU"]["right"] == 2 and out["by_arm"]["HAIKU-FETCH2"]["right"] == 1
    pair = out["HAIKU-FETCH2_vs_HAIKU"]
    assert pair["all"]["paired"]["a_only_tasks"] == ["A"]
    assert pair["both_used_the_web"]["tasks"] == ["A"]
