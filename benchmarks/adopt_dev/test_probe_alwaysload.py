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
