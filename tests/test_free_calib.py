"""The free-task calibration runner and the transcript reader under it: order, caps, ceiling,
refusals, grading and the cost trajectory. No model, no browser, no money."""

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


calib = _load("browse_free_calib", "benchmarks/browse/free_calib.py")
free = calib.free
trace = free.trace


# --- order, caps and ceiling ------------------------------------------------------------------


def test_interleave_spreads_a_short_stream_through_a_long_one():
    out = calib.interleave([list("abcdef"), ["X", "Y"]])
    assert sorted(out) == sorted("abcdefXY")
    assert out.index("X") < out.index("d") and out.index("Y") > out.index("d")
    assert [x for x in out if x.islower()] == list("abcdef")


def test_interleave_keeps_paired_streams_side_by_side():
    out = calib.interleave([["s1", "s2"], ["h1", "h2"]])
    assert out == ["s1", "h1", "s2", "h2"]


def test_interleave_of_nothing():
    assert calib.interleave([[], []]) == []


def test_caps_per_arm_and_set():
    assert calib.cap_for("SONNET", "AB2aa5dd83") == 1.50
    assert calib.cap_for("HAIKU", "AB2aa5dd83") == 0.60
    assert calib.cap_for("HAIKU", "BC1019") == 0.40
    with pytest.raises(KeyError):
        calib.cap_for("SONNET", "BC1019")  # not part of this phase
    assert calib.RESERVE_USD == 1.50


def test_the_ceiling_stops_before_a_session_that_could_cross_it():
    limits = calib.phase.Limits(session_max_usd=calib.RESERVE_USD, ceiling_usd=calib.CEILING_USD)
    rows = [{"task": "AB1", "run": 1, "arm": "HAIKU", "list_usd": 38.4}]
    assert calib.phase.stop_reason(rows, limits, 5) is None
    rows = [{"task": "AB1", "run": 1, "arm": "HAIKU", "list_usd": 38.6}]
    assert calib.phase.stop_reason(rows, limits, 5).startswith("ceiling")


def test_a_ceiling_stop_cuts_every_set_alike(monkeypatch):
    ab = [{"tid": f"AB{i}", "question": "q", "gold": "1"} for i in range(25)]
    bc = [{"tid": f"BC{i}", "question": "q", "gold": "1"} for i in range(10)]
    monkeypatch.setattr(free, "assistantbench", lambda n: ab)
    monkeypatch.setattr(calib, "fresh_browsecomp", lambda n, exclude: bc)
    steps = calib.plan()
    assert len(steps) == 60
    half = steps[:30]
    assert sum(s[1][0].startswith("BC") for s in half) == 5
    sonnet = sum(s[3] == "SONNET" for s in half)
    assert abs(sonnet - sum(s[3] == "HAIKU" and s[1][0].startswith("AB") for s in half)) <= 1
    assert [s[0] for s in steps] == list(range(60))


def test_fresh_browsecomp_leaves_out_the_pilot(monkeypatch):
    def sample(k):
        return [{"tid": f"BC{i}", "question": "q", "gold": "g"} for i in range(k)]

    monkeypatch.setattr(free, "browsecomp", sample)
    picked = calib.fresh_browsecomp(3, frozenset({"BC0", "BC2"}))
    assert [t["tid"] for t in picked] == ["BC1", "BC3", "BC4"]


# --- refusals and grading ---------------------------------------------------------------------


def test_refusal_is_seen_and_marked_for_the_phase():
    assert free.refused("You've hit your weekly limit", "", False)
    assert free.refused("API Error: 429 rate limited", "", True)
    assert free.refused("", "429 Too Many Requests", True)
    assert not free.refused("ANSWER: 429", "", False)  # a right answer may be that number
    assert calib.phase.usage_limited({"answer": free.LIMIT_MARKER})


def test_grading_on_the_answer_line():
    assert free.graded("blah\nANSWER: 14.2 dollars", "14.2")
    assert free.graded("ANSWER: about 14.25", "14.2")  # within 1 %
    assert not free.graded("14.2 is in the text\nANSWER: 20", "14.2")
    assert free.graded(
        "ANSWER: Glass Onion: A Knives Out Mystery (2022)", "Glass Onion: A Knives Out Mystery"
    )
    assert not free.graded("no answer line", "x")


# --- the transcript reader --------------------------------------------------------------------


def _assistant(mid, ts, blocks, model="claude-sonnet-5", out=10, side=False, **usage):
    return {"type": "assistant", "timestamp": ts, "isSidechain": side,
            "message": {"id": mid, "model": model, "content": blocks,
                        "usage": {"input_tokens": 0, "output_tokens": out, **usage}}}  # fmt: skip


def _result(tool_id, text):
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tool_id, "content": [{"type": "text", "text": text}]}
    ]}}  # fmt: skip


ENTRIES = [
    _assistant("m1", "t1", [{"type": "thinking", "thinking": ""}], out=5),
    _assistant(
        "m1", "t1", [{"type": "tool_use", "id": "u1", "name": "WebSearch", "input": {}}], out=1_000
    ),  # fmt: skip
    _result("u1", "page says 42"),
    _assistant(
        "m2",
        "t2",
        [
            {"type": "tool_use", "id": "u2", "name": "WebFetch", "input": {}},
            {"type": "tool_use", "id": "u3", "name": "WebSearch", "input": {}},
        ],
        out=1_000,
    ),  # fmt: skip
    _result("u2", "fetched"),
    _result("u3", "searched"),
    _assistant("m3", "t3", [{"type": "text", "text": "ANSWER: 42"}], out=2_000),
]


def test_entries_merge_by_message_id_and_keep_the_largest_usage():
    calls = trace.parse_entries(ENTRIES)
    assert [c["tools"] for c in calls] == [["WebSearch"], ["WebFetch", "WebSearch"], []]
    assert calls[0]["usage"]["output_tokens"] == 1_000
    assert "42" in calls[0]["results"] and "fetched" in calls[1]["results"]
    assert calls[2]["text"].strip() == "ANSWER: 42"
    assert trace.first_index(calls, lambda t: "42" in t, "results") == 0
    assert trace.first_index(calls, lambda t: "42" in t, "text") == 2
    assert trace.tool_counts(calls) == {"WebSearch": 2, "WebFetch": 1}
    assert not trace.browser_opened(calls)


def test_call_usd_prices_each_kind_of_token():
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
             "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 2_000_000,
             "cache_creation": {"ephemeral_1h_input_tokens": 1_000_000}}  # fmt: skip
    assert trace.call_usd("claude-sonnet-5", usage) == pytest.approx(2 + 10 + 0.2 + 2.5 + 4)
    assert trace.call_usd("claude-haiku-4-5", usage) == pytest.approx(1 + 5 + 0.1 + 1.25 + 2)


def test_trajectory_spreads_the_unseen_reader_over_web_calls_and_ends_on_the_total():
    calls = trace.parse_entries(ENTRIES)
    own = [trace.call_usd(c["model"], c["usage"]) for c in calls]  # 0.01, 0.01, 0.02
    reader = 0.03
    out = trace.trajectory(calls, sum(own) + reader, {"claude-sonnet-5": sum(own), "haiku": reader})
    assert out[-1] == pytest.approx(sum(own) + reader)
    assert out[0] == pytest.approx(0.01 + 0.01)  # one of three web calls
    assert out[1] - out[0] == pytest.approx(0.01 + 0.02)  # two of three
    assert out == sorted(out)


def test_trajectory_scales_to_a_total_it_cannot_explain():
    calls = trace.parse_entries(ENTRIES)
    out = trace.trajectory(calls, 1.0, {})
    assert out[-1] == pytest.approx(1.0)
    assert trace.trajectory([], 1.0, {}) == []


def test_summary_reads_main_and_subagent_transcripts(tmp_path, monkeypatch):
    monkeypatch.setattr(trace, "PROJECTS", tmp_path)
    work = "C:\\Temp\\sp-free-ab1r1-x"
    folder = trace.folder_of(work)
    (folder / "s" / "subagents").mkdir(parents=True)
    main = [ENTRIES[0], ENTRIES[1], ENTRIES[2], ENTRIES[6]]
    sub = [_assistant("s1", "t2", [{"type": "tool_use", "id": "b1",
                                     "name": "mcp__playwright__browser_navigate", "input": {}}],
                      side=True)]  # fmt: skip
    (folder / "s.jsonl").write_text("\n".join(json.dumps(e) for e in main), encoding="utf-8")
    (folder / "s" / "subagents" / "agent-a.jsonl").write_text(json.dumps(sub[0]), encoding="utf-8")
    got = trace.summary(work, 0.5, {})
    assert got["api_calls"] == 3
    assert got["web_search"] == 1 and got["web_fetch"] == 0
    assert got["browser_opened"] is True
    assert got["trajectory"][-1] == pytest.approx(0.5)
