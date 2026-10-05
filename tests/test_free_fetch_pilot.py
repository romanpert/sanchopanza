"""The fetch pilot's runner: twenty new FRAMES tasks by metadata, the -FETCH arms get the server
(loaded up front) and the hook, the web calls are counted from the transcripts. No model, no
network, no money."""

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


pilot = _load("browse_free_fetch_pilot", "benchmarks/browse/free_fetch_pilot.py")
frames = pilot.frames
free = pilot.free


def _row(i: int, answer: str = "Paris", links: int = 3) -> dict[str, str]:
    row = {"": str(i), "Prompt": f"q{i}", "Answer": answer, "reasoning_types": "Tabular reasoning"}
    for k in range(1, 12):
        row[f"wikipedia_link_{k}"] = f"https://en.wikipedia.org/wiki/P{k}" if k <= links else ""
    return row


def test_eligible_by_metadata_only():
    assert pilot.eligible(_row(1, links=3))
    assert not pilot.eligible(_row(1, links=2))
    assert not pilot.eligible(_row(1, answer="one two three four five"))
    assert not pilot.eligible(_row(1, answer=""))


def test_sample_is_seeded_and_disjoint():
    bank = [_row(i) for i in range(60)] + [_row(100 + i, links=1) for i in range(10)]
    taken = {f"FR{i}" for i in range(0, 60, 2)}
    first = pilot.sample(bank, taken, 20, seed=3)
    assert first == pilot.sample(bank, taken, 20, seed=3)
    assert first != pilot.sample(bank, taken, 20, seed=4)
    assert len(set(first)) == 20 and not set(first) & taken


def test_the_ids_in_the_repo_are_twenty_new_tasks():
    ids = pilot.IDS.read_text(encoding="utf-8").split()
    assert len(ids) == len(set(ids)) == 20 and not set(ids) & pilot.taken_ids()
    if not frames.FRAMES.exists():
        pytest.skip("FRAMES is not cached here")
    assert ids == pilot.sample(frames.read_frames(), pilot.taken_ids())


def test_arms_caps_and_ceilings():
    assert pilot.CAPS == {"SONNET": 1.50, "SONNET-FETCH": 1.50, "HAIKU": 0.60,
                          "HAIKU-FETCH": 0.60}  # fmt: skip
    assert pilot.SONNET_CEILING_USD == 15.0 and pilot.CEILING_USD == 20.0
    assert pilot.PRIVATE not in (frames.PRIVATE, pilot.free.CACHE)


def test_only_fetch_arms_get_the_server_loaded_up_front_and_the_hook(tmp_path: pathlib.Path):
    assert pilot.arm_options("SONNET", tmp_path) == {"hooks": None, "env_extra": None,
                                                     "mcp_servers": None}  # fmt: skip
    options = pilot.arm_options("HAIKU-FETCH", tmp_path)
    server = options["mcp_servers"][pilot.SERVER]
    assert server["alwaysLoad"] is True and server["args"][-1] == "fetch-mcp"
    assert options["env_extra"]["SANCHOPANZA_FETCH_DIR"] == str(tmp_path)
    hook = options["hooks"]["PreToolUse"][0]
    assert hook["matcher"] == "WebFetch" and "fetch_hook" in hook["hooks"][0]["command"]


def test_extra_servers_reach_the_mcp_config_and_the_allow_list(tmp_path: pathlib.Path):
    path = free.session_mcp_config(tmp_path, {"x": {"command": "c", "alwaysLoad": True}})
    servers = json.loads(path.read_text(encoding="utf-8"))["mcpServers"]
    assert servers["x"]["alwaysLoad"] is True and "playwright" in servers
    settings = free.session_settings((), None, f"{free.TOOLS} mcp__x")
    assert "mcp__x" in settings["permissions"]["allow"]
    assert free.session_settings() == {"permissions": {"allow": free.TOOLS.split()}}


def _use(i: int, name: str, **inp) -> dict:
    return {"type": "tool_use", "id": f"t{i}", "name": name, "input": inp}


def _result(i: int, text: str, error: bool = False) -> dict:
    return {"type": "tool_result", "tool_use_id": f"t{i}", "content": text, "is_error": error}


def _transcript(folder: pathlib.Path, blocks: list[tuple[str, dict]]) -> None:
    folder.mkdir(parents=True)
    lines = [json.dumps({"type": who, "message": {"role": who, "content": [b]}})
             for who, b in blocks]  # fmt: skip
    (folder / "s.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_web_calls_count_denials_returns_and_passages(tmp_path: pathlib.Path):
    tool = pilot.TOOL_NAME
    _transcript(tmp_path / "f", [
        ("assistant", _use(1, "WebSearch", query="q")), ("user", _result(1, "links")),
        ("assistant", _use(2, "WebFetch", url="https://a.org/x")),
        ("user", _result(2, f"Hook denied: {pilot.REASON}", True)),
        ("assistant", _use(3, tool, url="https://a.org/x", purpose="p")),
        ("user", _result(3, "T\nhttps://a.org/x\n" + "w" * 400)),
        ("assistant", _use(4, tool, url="https://a.org/y.pdf", purpose="p")),
        ("user", _result(4, json.dumps({"result": "y.pdf is application/pdf: not read here."}))),
        ("assistant", _use(5, "WebFetch", url="https://a.org/x")), ("user", _result(5, "summary")),
        ("assistant", _use(6, "ToolSearch", query="select:WebFetch")), ("user", _result(6, "ok")),
    ])  # fmt: skip
    calls = pilot.web_calls(tmp_path / "f")
    assert calls["web_search"] == 1 and calls["web_fetch"] == 2
    assert calls["web_fetch_denied_by_hook"] == 1 and calls["web_fetch_back"] == 1
    assert calls["fetch_passages"] == 2 and calls["fetch_passages_unread"] == 1
    assert calls["passage_tokens"] == len("T\nhttps://a.org/x\n" + "w" * 400) // 4
    assert calls["tool_search"] == 1 and calls["subagents"] == 0


def test_reader_usd_is_what_the_transcript_does_not_show(tmp_path: pathlib.Path):
    usage = {"input_tokens": 1_000_000, "output_tokens": 0}
    message = {"id": "m1", "model": "claude-sonnet-5", "usage": usage, "content": []}
    entry = {"type": "assistant", "timestamp": "1", "message": message}
    (tmp_path / "f").mkdir()
    (tmp_path / "f" / "s.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")
    by_model = {"claude-sonnet-5": 2.5, "claude-haiku-4-5": 0.3}
    assert pilot.reader_usd(tmp_path / "f", by_model) == pytest.approx(0.8)
    assert pilot.haiku_usd(by_model) == pytest.approx(0.3)


def test_report_counts_by_arm():
    calls = {"fetch_passages": 2, "fetch_passages_unread": 0, "passage_tokens": 3000}
    rows = [{"arm": "SONNET-FETCH", "list_usd": 0.2, "ok_auto": True, "calls": calls},
            {"arm": "SONNET-FETCH", "list_usd": 0.4, "ok_auto": False, "calls": calls}]  # fmt: skip
    cell = pilot.report(rows)["by_arm"]["SONNET-FETCH"]
    assert cell["right"] == 1 and cell["median_usd"] == pytest.approx(0.3)
    assert cell["calls"]["fetch_passages"] == 4 and cell["passage_tokens_per_read"] == 1500


def test_smoke_check_wants_the_tool_without_tool_search():
    assert pilot.smoke_check({"calls": {"fetch_passages": 1, "tool_search": 0}})["always_loaded"]
    assert not pilot.smoke_check({"calls": {"fetch_passages": 1, "tool_search": 1}})[
        "always_loaded"
    ]


handp = _load("browse_free_fetch_pilot_hand", "benchmarks/browse/free_fetch_pilot_hand.py")


def _graded(task: str, arm: str, right: bool, web: int, usd: float = 0.1) -> dict:
    return {"task": task, "arm": arm, "ok_auto": right, "list_usd": usd,
            "calls": {"web_search": web}}  # fmt: skip


def test_hand_pairs_on_all_tasks_and_on_those_both_arms_used_the_web():
    rows = [_graded("A", "SONNET", True, 2), _graded("A", "SONNET-FETCH", False, 1),
            _graded("B", "SONNET", True, 0), _graded("B", "SONNET-FETCH", True, 0),
            _graded("C", "SONNET", False, 3), _graded("C", "SONNET-FETCH", False, 0)]  # fmt: skip
    out = handp.report(rows, None)["SONNET-FETCH_vs_SONNET"]
    assert out["all"]["paired"]["a_only_tasks"] == ["A"] and out["all"]["tasks"] == 3
    assert out["both_used_the_web"]["tasks"] == ["A"]
    assert out["both_used_the_web"]["base"]["right"] == 1
    assert out["both_used_the_web"]["fetch"]["right"] == 0


def test_hand_overrides_only_the_listed_session(monkeypatch):
    monkeypatch.setitem(handp.HAND, ("A", "SONNET"), (False, "why"))
    assert handp.graded(_graded("A", "SONNET", True, 1))["ok_hand"] is False
    assert handp.graded(_graded("A", "SONNET-FETCH", True, 1))["ok_hand"] is True
