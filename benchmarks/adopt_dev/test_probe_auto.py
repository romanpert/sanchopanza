"""Free tests of the find-auto probe (no Docker, no API, no Jev). In its own process, since the
probe pins `common.py` to the `auto` profile on import:

Run: .venv/Scripts/python.exe -m pytest benchmarks/adopt_dev/test_probe_auto.py -q
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("ADOPT_DEV_PROFILE", "auto")
try:
    from . import common
    from . import probe_auto as auto
except RuntimeError as exc:  # common.py pinned to another profile by an earlier test module
    pytest.skip(f"run this file in its own process: {exc}", allow_module_level=True)

from sanchopanza.harness.find_auto import EVENTS, HEADER  # noqa: E402

from . import probe_alwaysload as base  # noqa: E402
from .auto_facts import describe, expected_fire, tool_use_ids  # noqa: E402

ROOT = Path.home() / ".cache" / "sanchopanza" / "adopt"
WORK = "C:/w/django__django-1-S"
PATCH = ("diff --git a/pkg/compiler.py b/pkg/compiler.py\n--- a/pkg/compiler.py\n"
         "+++ b/pkg/compiler.py\n@@ -3,1 +3,1 @@\n-old\n+new\n")  # fmt: skip


def test_paths_caps_and_plan() -> None:
    assert common.PROFILE == "auto"
    assert common.OUT == ROOT / "dev-auto" and common.WORK == ROOT / "work-dau"
    assert (common.TOTAL_CAP_USD, common.CALL_CAP_USD) == (12.00, 1.50)
    assert [n for n, _ in common.PLAN] == list(common.NEED)
    assert all(arms == ("S",) for _, arms in common.PLAN)
    assert not {n for n, _ in common.PLAN} & common.phase_d_ids()


def test_it_refuses_to_run_before_the_freeze() -> None:
    if len(common.AUTO_COMMIT) == 40 and common.FROZEN_EXE.exists():
        pytest.skip("frozen already")
    assert "AUTO_COMMIT" in (common.plan_refusal() or "") or "no frozen copy" in (
        common.plan_refusal() or "")  # fmt: skip


def test_the_install_adds_find_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(auto, "_install_sancho", lambda w, e, k, extra=(): seen.append(extra))
    assert common.run.install_sancho is auto.install_with_auto
    common.run.install_sancho(Path("w"), Path("e"), Path("k"))
    assert seen == [("--find-auto",)]


# ---- facts of one session ------------------------------------------------------------------------


def _assistant(block: dict[str, Any], mid: str) -> dict[str, Any]:
    return {"type": "assistant", "message": {"id": mid, "content": [block]}}


def _evidence(tmp_path: Path, journal: list[dict[str, Any]], injected: bool = True) -> Path:
    evidence = tmp_path / "ev"
    evidence.mkdir()
    calls = [("Grep", {"pattern": "a"}), ("Grep", {"pattern": "b"}),
             ("Bash", {"command": "grep -rn c ."}), ("Glob", {"pattern": "**/d*.py"}),
             ("Read", {"file_path": f"{WORK}/pkg/compiler.py"}),
             ("Edit", {"file_path": f"{WORK}/pkg/compiler.py"})]  # fmt: skip
    lines = []
    for n, (name, given) in enumerate(calls, 1):
        block = {"type": "tool_use", "id": f"tu{n}", "name": name, "input": given}
        lines.append(_assistant(block, f"m{n}"))
        lines.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": f"tu{n}", "content": "x"}]}})  # fmt: skip
    (evidence / "stream-1.jsonl").write_text("\n".join(json.dumps(x) for x in lines), "utf-8")
    note = f"{HEADER}\n- pkg/compiler.py:1-9  x" if injected else ""
    (evidence / "transcript.jsonl").write_text(json.dumps({"content": note}) + "\n", "utf-8")
    rows = [{"kind": "find_auto", "data": d} for d in journal]
    (evidence / "journal.jsonl").write_text("\n".join(json.dumps(r) for r in rows), "utf-8")
    return evidence


def test_a_fire_is_placed_and_judged(tmp_path: Path) -> None:
    row = {"outcome": "fired", "search": 4, "tool_use_id": "tu4", "jev_usd": 0.002,
           "keys": ["pkg/compiler.py:1-9", "pkg/other.py:1-3"]}  # fmt: skip
    evidence = _evidence(tmp_path, [row])
    facts = describe(evidence, ["pkg/compiler.py"], PATCH, {}, WORK)["auto"]
    assert facts["fired"] and facts["fire_call"] == 4 and facts["expected_fire_call"] == 4
    assert facts["shown_gold_file"] and facts["shown_gold_hunk"] and facts["shown_gold_first"]
    assert facts["next_call"] == {"name": "Read", "path": "pkg/compiler.py"}
    assert facts["next_read_is_shown"] and facts["calls_to_shown_read"] == 1
    assert facts["injected_in_transcript"] and facts["jev_usd"] == 0.002


def test_no_fire_is_seen_as_such(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path, [{"outcome": "not_ready", "search": 4, "tool_use_id": "tu4"}],
                         injected=False)  # fmt: skip
    facts = describe(evidence, ["pkg/compiler.py"], PATCH, {}, WORK)["auto"]
    assert not facts["fired"] and facts["fire_call"] is None and facts["outcome"] == "not_ready"
    assert facts["expected_fire_call"] == 4 and "next_call" not in facts


def test_tool_use_ids_follow_the_calls(tmp_path: Path) -> None:
    from benchmarks.find_need.replay import stream_calls

    evidence = _evidence(tmp_path, [])
    _meta, calls = stream_calls(evidence / "stream-1.jsonl")
    assert len(tool_use_ids(evidence / "stream-1.jsonl")) == len(calls) == 6


def test_expected_fire_agrees_with_the_offline_replay_on_the_need_probe() -> None:
    """The need probe's ten sessions (no hook): the live rule over each stream fires where the
    benchmark's replay of R4 does."""
    from benchmarks.find_auto.evaluate import replay_untouched
    from benchmarks.find_need.replay import stream_calls

    streams = sorted((ROOT / "dev-need").glob("*/S/stream-1.jsonl"))
    if not streams:
        pytest.skip("no need-probe evidence on this machine")
    for stream in streams:
        name = stream.parent.parent.name
        _meta, calls = stream_calls(stream)
        fire = replay_untouched(calls, 4)
        work = str(ROOT / "work-dnd" / f"{name}-S")
        assert expected_fire(calls, work) == (fire.call if fire else None), name


# ---- stops ---------------------------------------------------------------------------------------


def _wired(tmp_path: Path, args: list[str], events: tuple[str, ...] = EVENTS) -> Path:
    evidence = tmp_path / "wired"
    evidence.mkdir(exist_ok=True)
    hook = {"type": "mcp_tool", "server": "sanchopanza", "tool": "find_auto"}
    settings = {"hooks": {e: [{"matcher": "Grep", "hooks": [hook]}] for e in events}}
    (evidence / "settings.json").write_text(json.dumps(settings), "utf-8")
    mcp = {"mcpServers": {"sanchopanza": {"command": "py", "args": ["h.py", *args]}}}
    (evidence / "mcp.json").write_text(json.dumps(mcp), "utf-8")
    return evidence


def test_wiring_problems(tmp_path: Path) -> None:
    assert auto.wiring_problem(_wired(tmp_path, ["find-mcp", "--auto"])) == ""
    assert "--auto" in auto.wiring_problem(_wired(tmp_path, ["find-mcp"]))
    assert "PostToolUseFailure" in auto.wiring_problem(
        _wired(tmp_path, ["find-mcp", "--auto"], ("PostToolUse",)))  # fmt: skip


def test_a_rule_that_should_have_fired_without_a_journal_stops(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(auto, "OUT", tmp_path)
    folder = tmp_path / "x" / "S"
    folder.mkdir(parents=True)
    (folder / "row.json").write_text("{}", "utf-8")
    for name in ("settings.json", "mcp.json"):
        (folder / name).write_text((_wired(tmp_path, ["find-mcp", "--auto"]) / name).read_text())
    facts = {"auto": {"expected_fire_call": 4, "journal": []}}
    monkeypatch.setattr(auto, "session_facts", lambda _n: facts)
    record = {"instance": "x", "calls": [{}]}
    with pytest.raises(base.Stop, match="journalled nothing"):
        auto.after_session(record)
    facts["auto"]["journal"] = [{"outcome": "not_ready"}]
    auto.after_session(record)  # it ran, it just found the index not ready
