"""The multi-step browse runner: its task set, and how it tells a treated session from one that
only carried the label. No model, no browser, no money."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "browse_nav_e2e", ROOT / "benchmarks/browse/nav_e2e.py"
)
nav = importlib.util.module_from_spec(spec)
sys.modules["browse_nav_e2e"] = nav
spec.loader.exec_module(nav)

EVERY = nav.TASKS + nav.TRAP_TASKS + nav.HARD_TASKS


def test_task_ids_are_unique_and_every_task_has_an_answer_to_grade_on():
    ids = [t[0] for t in EVERY]
    assert len(ids) == len(set(ids))
    for tid, url, question, required in EVERY:
        assert url.startswith("https://"), tid
        assert question.strip(), tid
        assert required, f"{tid} has nothing to grade on"


def test_every_request_is_ascii():
    """A request goes to `claude -p` on the command line; on Windows a character outside ASCII
    there is one more thing that can go wrong, and none of them needs one."""
    for tid, _, question, _ in EVERY:
        assert question.isascii(), f"{tid}: {question!r}"


def test_an_aggregation_answer_is_read_from_its_answer_line_only():
    """The count must come from the ANSWER line: "page 10" elsewhere is not "10 quotes"."""
    h1 = next(t for t in nav.HARD_TASKS if t[0] == "H1")
    required = h1[3]
    assert nav.base.graded("Walked all 10 pages.\nANSWER: 10", required)
    assert nav.base.graded("Walked all 10 pages.\n**ANSWER:10**", required)
    assert not nav.base.graded("Walked all 10 pages and found 9.\nANSWER: 9", required)


def _journal(path: pathlib.Path, events: list[dict]) -> pathlib.Path:
    path.write_text("".join(json.dumps(e) + "\n" for e in events), encoding="utf-8")
    return path


def _decision(spoke: bool, page_chars: int) -> dict:
    return {"kind": "decision", "data": {"point": "loop",
            "outcome": {"spoke": spoke, "page_chars": page_chars}}}  # fmt: skip


def test_the_hook_record_counts_what_the_guard_did(tmp_path):
    path = _journal(tmp_path / "j.jsonl", [
        _decision(False, 0), _decision(True, 420), _decision(False, 300),
        {"kind": "loop_note", "data": {"kind": "errors", "streak": 2}},
        {"kind": "decision", "data": {"point": "browse", "outcome": {}}},  # not the guard's
        {"kind": "loop_error", "data": {"error": "TimeoutError"}},
    ])  # fmt: skip
    assert nav.hook_record(path) == {
        "hook_decisions": 3, "hook_spoke": 1, "hook_blind": 1, "hook_error_notes": 1,
        "hook_errors": 1,
    }  # fmt: skip


def test_no_journal_is_zero_of_everything(tmp_path):
    assert set(nav.hook_record(tmp_path / "missing.jsonl").values()) == {0}


@pytest.mark.parametrize(
    ("events", "treated", "why"),
    [
        ([_decision(False, 10)], True, ""),
        ([], False, "hook absent"),
        ([{"kind": "loop_error", "data": {"error": "x"}}], False, "decider failed"),
        ([{"kind": "loop_note", "data": {}}], False, "hook absent"),
    ],
)
def test_a_loop_session_counts_as_treated_only_if_the_guard_asked(tmp_path, monkeypatch, events,
                                                                   treated, why):  # fmt: skip
    """The 2026-10-02 fault: a session with no journal was counted as treated."""

    class Done:
        stdout = json.dumps({"is_error": False, "result": "ANSWER: 10", "num_turns": 5,
                             "total_cost_usd": 0.1}).encode()  # fmt: skip
        stderr = b""

    def fake_run(argv, cwd, env, capture_output, timeout):
        if events:
            _journal(pathlib.Path(env["SANCHOPANZA_JOURNAL"]), events)
        return Done()

    monkeypatch.setattr(nav, "KEY", "test-key")
    monkeypatch.setattr(nav.subprocess, "run", fake_run)
    monkeypatch.setattr(nav.mcp, "tool_calls", lambda work: {})
    monkeypatch.setattr(nav.mcp, "mcp_config", lambda work: work / "mcp.json")
    task = next(t for t in nav.HARD_TASKS if t[0] == "H1")
    row = nav.one_session(task, 1, "HAIKU-LOOP")
    assert (not row.get("not_run")) is treated
    if why:
        assert why in row["subtype"]
    assert (pathlib.Path(row["workdir"]) / "stderr.txt").exists(), "stderr is kept"


def test_a_plain_session_is_never_judged_by_the_hook(tmp_path, monkeypatch):
    class Done:
        stdout = json.dumps({"is_error": False, "result": "ANSWER: 10", "num_turns": 5}).encode()
        stderr = b""

    monkeypatch.setattr(nav.subprocess, "run", lambda *a, **k: Done())
    monkeypatch.setattr(nav.mcp, "tool_calls", lambda work: {})
    monkeypatch.setattr(nav.mcp, "mcp_config", lambda work: work / "mcp.json")
    task = next(t for t in nav.HARD_TASKS if t[0] == "H1")
    row = nav.one_session(task, 1, "HAIKU")
    assert not row.get("not_run") and "hook_decisions" not in row
    assert row["success"] is True
