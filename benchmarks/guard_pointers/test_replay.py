"""The guard replay on a synthetic session with two compactions, and the real run's discovery
when it is on this machine. No model, no API.

Run: .venv/Scripts/python.exe -m pytest benchmarks/guard_pointers -q
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

from . import replay

# one Read that fits a part of the whole-results block (each part holds at most 9,500 chars)
BODY = "\n".join(f"{n:6d}\t    total = compute(item_{n})" for n in range(1, 150))


def _assistant(mid: str, tool: str, cid: str, **given: Any) -> dict[str, Any]:
    usage = {"input_tokens": 5, "output_tokens": 40, "cache_read_input_tokens": 20_000,
             "cache_creation_input_tokens": 300}  # fmt: skip
    content = [{"type": "tool_use", "id": cid, "name": tool, "input": given}]
    return {"type": "assistant", "message": {"id": mid, "role": "assistant", "usage": usage,
                                             "content": content}}  # fmt: skip


def _result(cid: str, text: str) -> dict[str, Any]:
    block = {"type": "tool_result", "tool_use_id": cid, "content": text}
    return {"type": "user", "message": {"role": "user", "content": [block]}}


def _session(path: Path) -> Path:
    entries = [
        {"type": "user", "message": {"role": "user", "content": "Fix the pricing bug."}},
        _assistant("m1", "Bash", "t1", command="./probe --once"),
        _result("t1", "code PRB-7788\nlimit 12"),
        _assistant("m2", "Read", "t2", file_path="/w/pkg/pricing.py"),
        _result("t2", BODY),
        {"type": "system", "subtype": "compact_boundary"},
        {"type": "user", "isCompactSummary": True,
         "message": {"role": "user", "content": "Summary."}},
        _assistant("m3", "Bash", "t3", command="./probe --once"),
        _result("t3", "already used"),
        _assistant("m4", "Read", "t4", file_path="/w/pkg/pricing.py"),
        _result("t4", BODY),
        _assistant("m5", "Read", "t5", file_path="/w/pkg/other.py"),
        _result("t5", "x = 1"),
        {"type": "system", "subtype": "compact_boundary"},
        _assistant("m6", "Bash", "t6", command="ls"),
        _result("t6", "a b"),
    ]  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def test_a_session_is_replayed_compaction_by_compaction(tmp_path: Path) -> None:
    arm = tmp_path / "cfg" / "x__y-long60-1-sonnet-Ne"
    path = _session(arm / "claude-config" / "projects" / "p" / "s.jsonl")
    rows = replay.replay_session(path)
    assert [r["compaction"] for r in rows] == [1, 2]
    first = rows[0]
    assert first["session"] == "x__y-long60-1-sonnet-Ne" and first["arm"] == "Ne"
    assert first["segment_requests"] == 3
    assert first["struct_held"] == 2  # the probe's output and the file read
    assert first["refetches"] == 2  # the probe run again and the file read again
    assert first["reads"] == 2 and first["reads_seen_before"] == 1 and first["reads_held"] == 1
    assert first["shell"] == 1 and first["shell_held"] == 1
    assert first["archived"] == 1  # the one-shot probe output
    assert first["pointer_chars"] < first["struct_chars"]
    assert first["struct_usd"] > first["pointer_usd"] > 0


def test_carry_cost_is_one_write_and_a_read_per_later_request() -> None:
    usd = replay.carry_usd(1_000, 3)
    assert usd == pytest.approx(300 * 4e-6 + 300 * 2 * 0.2e-6)


def test_discovery_takes_the_sonnet_ne_and_nl_arms_only(tmp_path: Path) -> None:
    for name in ("a-long60-1-sonnet-Ne", "a-long60-1-sonnet-Nl", "a-long60-1-haiku-Ne",
                 "a-long60-1-sonnet-S"):  # fmt: skip
        _session(tmp_path / "cfg" / name / "claude-config" / "projects" / "p" / "s.jsonl")
    found = [replay.arm_of(p) for p in replay.discover(tmp_path)]
    assert found == ["a-long60-1-sonnet-Ne", "a-long60-1-sonnet-Nl"]


def test_the_output_names_sessions_by_arm_folder_only(tmp_path: Path) -> None:
    _session(tmp_path / "runs" / "cfg" / "c-long60-2-sonnet-Nl" / "claude-config" / "projects"
             / "p" / "s.jsonl")  # fmt: skip
    out = tmp_path / "out"
    assert replay.main(["--runs", str(tmp_path / "runs"), "--out", str(out)]) == 0
    text = (out / "compactions.json").read_text("utf-8")
    assert str(tmp_path) not in text and "c-long60-2-sonnet-Nl" in text
    summary = json.loads((out / "summary.json").read_text("utf-8"))
    assert summary["sessions"] == 1 and summary["compactions"] == 2


def test_the_recorded_run_has_ten_sonnet_sessions() -> None:
    runs = os.environ.get("SANCHOPANZA_GUARD_REPLAY_RUNS", "")
    if not runs or not (Path(runs) / "cfg").is_dir():
        pytest.skip("the long-compaction run is not on this machine "
                    "(set SANCHOPANZA_GUARD_REPLAY_RUNS to its root)")  # fmt: skip
    found = replay.discover(Path(runs))
    assert len(found) == 10
    assert sorted({replay.arm_of(p).rsplit("-", 1)[-1] for p in found}) == ["Ne", "Nl"]
