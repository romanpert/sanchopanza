"""Free tests of the probe's own parts (no Docker, no API):

Run: .venv/Scripts/python.exe -m pytest benchmarks/adopt_dev -q
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from .probe_alwaysload import find_refusal, stream_session
from .session_facts import FIND_TOOL, Clock, caching, deferral, hook_seconds

INIT = {"type": "system", "subtype": "init", "tools": ["Bash", FIND_TOOL],
        "mcp_servers": [{"name": "sanchopanza", "status": "connected"}]}  # fmt: skip


def fake_claude(lines: list[dict], sleep_after: float = 0.0) -> list[str]:
    body = "".join(f"print({json.dumps(json.dumps(x))}, flush=True)\n" for x in lines)
    return [sys.executable, "-c", f"import time\n{body}time.sleep({sleep_after})\n"]


def test_stream_session_times_milestones(tmp_path: Path) -> None:
    lines = [INIT, {"type": "assistant", "message": {"id": "m1", "content": []}},
             {"type": "result", "subtype": "success", "total_cost_usd": 0.01}]  # fmt: skip
    clock = Clock(time.time())
    code, reason = stream_session(fake_claude(lines), tmp_path, None, None, tmp_path, clock,
                                  find_refusal)  # fmt: skip
    assert (code, reason) == (0, "")
    latency = clock.latency()
    assert 0 <= latency["to_init_s"] <= latency["to_first_assistant_s"] <= latency["to_result_s"]
    assert len((tmp_path / "stream-1.jsonl").read_text().splitlines()) == 3


def test_stream_session_kills_when_find_is_not_connected(tmp_path: Path) -> None:
    bad = {**INIT, "mcp_servers": [{"name": "sanchopanza", "status": "failed"}]}
    began = time.time()
    code, reason = stream_session(fake_claude([bad], sleep_after=60), tmp_path, None, None,
                                  tmp_path, Clock(began), find_refusal)  # fmt: skip
    assert "failed" in reason
    assert time.time() - began < 30 and code != 0


def entry(kind: str, **extra: object) -> str:
    return json.dumps({"type": kind, **extra})


def test_deferral_and_caching(tmp_path: Path) -> None:
    transcript = tmp_path / "t.jsonl"
    usage = [(0, 100), (90, 10), (5, 200), (300, 4)]  # call 3 reads almost nothing: a break
    rows = [entry("attachment", attachment={"type": "deferred_tools_delta",
                                            "addedNames": ["Monitor"]})]  # fmt: skip
    rows += [entry("assistant", message={"id": f"m{i}", "usage": {
        "cache_read_input_tokens": r, "cache_creation_input_tokens": w}})
        for i, (r, w) in enumerate(usage)]  # fmt: skip
    transcript.write_text("\n".join(rows), encoding="utf-8")
    assert deferral(transcript)["find_deferred"] is False
    from .session_facts import api_calls

    seen = caching(api_calls(transcript))
    assert seen["api_calls"] == 4 and seen["breaks"] == [3] and seen["ok"] is False


def test_hook_seconds_by_event(tmp_path: Path) -> None:
    lines = [{"sub": "find-mcp", "event": "server start"},
             {"sub": "hook", "event": "UserPromptSubmit", "seconds": 0.5},
             {"sub": "hook", "event": "UserPromptSubmit", "seconds": 0.2},
             {"sub": "hook", "event": "PreToolUse", "seconds": 0.1}]  # fmt: skip
    (tmp_path / "hooks.jsonl").write_text("\n".join(json.dumps(x) for x in lines))
    seen = hook_seconds(tmp_path)
    assert seen["first_user_prompt_submit_s"] == 0.5
    assert seen["by_event"]["UserPromptSubmit"]["n"] == 2 and seen["server"] == ["server start"]


# ---- money and resume ----------------------------------------------------------------------------


def test_a_session_without_a_result_line_is_charged_its_cap() -> None:
    from .probe_alwaysload import CALL_CAP_USD, charge_for

    ended = {"subtype": "success", "cost_usd": 0.0}
    assert charge_for(0, "", ended) == 0.0
    assert charge_for(0, "", {"subtype": None, "cost_usd": 0.0}) == CALL_CAP_USD
    assert charge_for(1, "", {"subtype": None, "cost_usd": 0.0}) == CALL_CAP_USD
    assert charge_for(-9, "", ended) == CALL_CAP_USD
    assert charge_for(0, "server failed", ended) == CALL_CAP_USD


def _row(folder: Path, cost: float, jev: float = 0.0, status: str = "") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    call = {"cost_usd": cost, **({"status": status} if status else {})}
    (folder / "row.json").write_text(json.dumps({"calls": [call], "jev_usd": jev}), "utf-8")


def test_spent_counts_jev_and_every_set_aside_folder(tmp_path: Path, monkeypatch) -> None:
    from . import probe_alwaysload as probe

    monkeypatch.setattr(probe, "OUT", tmp_path)
    _row(tmp_path / "a" / "S", 0.40, jev=0.02)
    _row(tmp_path / "a" / "S-notrun1", 0.10, jev=0.01, status="NOT RUN (error result)")
    aside = tmp_path / "a" / "N-abandoned-1"
    aside.mkdir(parents=True)
    (aside / "abandoned.json").write_text(json.dumps({"charged_usd": 1.5, "jev_usd": 0.03}))
    assert probe.spent() == round(0.40 + 0.02 + 0.10 + 0.01 + 1.5 + 0.03, 6)


def test_a_usage_limited_arm_is_set_aside_and_run_again(tmp_path: Path, monkeypatch) -> None:
    from . import probe_alwaysload as probe

    monkeypatch.setattr(probe, "OUT", tmp_path)
    _row(tmp_path / "a" / "S", 0.10, status="NOT RUN (error result)")
    _row(tmp_path / "a" / "N", 0.30)
    assert probe.todo_arms("a", ("S", "N")) == ["S"]
    before = probe.spent()
    assert probe.set_notrun_aside(tmp_path / "a" / "S").name == "S-notrun1"
    assert not (tmp_path / "a" / "S").exists() and probe.spent() == before
    _row(tmp_path / "a" / "S", 0.20, status="NOT RUN (error result)")
    assert probe.set_notrun_aside(tmp_path / "a" / "S").name == "S-notrun2"
    assert probe.todo_arms("a", ("S", "N")) == ["S"]
    _row(tmp_path / "a" / "S", 0.50)
    assert probe.todo_arms("a", ("S", "N")) == []
