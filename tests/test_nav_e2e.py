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

EVERY = nav.TASKS + nav.TRAP_TASKS + nav.HARD_TASKS + nav.STRATEGY_TASKS


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


def _req(tid: str) -> list:
    return next(t for t in nav.HARD_TASKS if t[0] == tid)[3]


@pytest.mark.parametrize(
    ("answer", "right"),
    [
        ("Walked all 10 pages.\nANSWER: 10", True),
        ("Walked all 10 pages.\n**ANSWER:10**", True),
        # Sonnet's real reply, H1, 2026-10-02: right, and failed by the first grader.
        (
            "I crawled all 10 pages.\n\nANSWER: There are 10 quotes by Albert Einstein across all "
            "pages of quotes.toscrape.com.",
            True,
        ),  # fmt: skip
        ("Walked all 10 pages and found 9.\nANSWER: 9", False),
        ("ANSWER: 100", False),
        ("ANSWER: 10.5", False),
        ("There are 10 of them.", False),  # no ANSWER line at all
        ("ANSWER: 10\n...then on reflection...\nANSWER: 9", False),  # the last line counts
    ],
)
def test_an_aggregation_answer_is_read_from_its_answer_line_only(answer, right):
    """ "page 10" elsewhere in the reply is not "10 quotes", and 100 is not 10."""
    assert nav.grade(answer, _req("H1"), "H1") is right


def test_a_sum_and_a_name_are_read_from_the_answer_line():
    assert nav.grade("ANSWER: The total is £437.74.", _req("H4"), "H4")
    assert not nav.grade("ANSWER: £437.745", _req("H4"), "H4")
    assert nav.grade("ANSWER: 13 quotes; Marilyn Monroe has the most (2).", _req("H3"), "H3")
    assert not nav.grade("ANSWER: 13 quotes.\nMonroe has most.", _req("H3"), "H3")


def test_tasks_that_are_not_aggregations_keep_the_substring_grader():
    a1 = next(t for t in nav.TASKS if t[0] == "A1")
    assert nav.grade("Item total $55.97, tax $4.48, total $60.45", a1[3], "A1")


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


def _strategy(tid: str) -> tuple:
    return next(t for t in nav.STRATEGY_TASKS if t[0] == tid)


def test_a_strategy_task_is_read_from_its_answer_line_like_an_aggregation():
    s1 = _strategy("S1")
    assert nav.grade("Fetched all 50 pages.\nANSWER: 42", s1[3], "S1")
    assert not nav.grade("ANSWER: 420", s1[3], "S1")
    assert not nav.grade("Found 42 of them.", s1[3], "S1")  # no ANSWER line


def _argv_of(monkeypatch, arm: str) -> tuple[list[str], dict]:
    seen: dict = {}

    class Done:
        stdout = json.dumps({"is_error": False, "result": "ANSWER: 42", "num_turns": 3}).encode()
        stderr = b""

    def fake_run(argv, cwd, env, capture_output, timeout):
        seen["argv"], seen["env"] = argv, env
        return Done()

    monkeypatch.setattr(nav.subprocess, "run", fake_run)
    monkeypatch.setattr(nav.mcp, "tool_calls", lambda work: {})
    monkeypatch.setattr(nav.mcp, "mcp_config", lambda work: work / "mcp.json")
    row = nav.one_session(_strategy("S1"), 1, arm)
    assert row["success"] is True
    return seen["argv"], seen["env"]


def _appended(argv: list[str]) -> str:
    return argv[argv.index("--append-system-prompt") + 1]


def test_the_hint_arm_carries_the_strategy_line_and_nothing_else_of_ours(monkeypatch):
    argv, env = _argv_of(monkeypatch, "HAIKU-HINT")
    assert nav.STRATEGY_HINT in _appended(argv)
    assert _appended(argv).startswith(nav.APPEND)
    assert argv[argv.index("--model") + 1] == "claude-haiku-4-5"
    assert "TYPESAFE_API_KEY" not in env, "a static line decides nothing and needs no key"
    settings = json.loads(pathlib.Path(argv[argv.index("--settings") + 1]).read_text())
    assert "hooks" not in settings


@pytest.mark.parametrize("arm", ["HAIKU", "SONNET", "HAIKU-LOOP"])
def test_no_other_arm_sees_the_strategy_line(monkeypatch, arm):
    monkeypatch.setattr(nav, "KEY", "test-key")
    argv, _ = _argv_of(monkeypatch, arm)
    assert nav.STRATEGY_HINT not in _appended(argv)


def test_the_strategy_line_is_ascii_because_it_travels_on_argv():
    assert nav.STRATEGY_HINT.isascii()


@pytest.mark.parametrize(("built", "refused"), [("JevDecider", False), ("NullDecider", True),
                                                ("", True)])  # fmt: skip
def test_preflight_refuses_a_key_that_builds_no_decider(monkeypatch, built, refused):
    """A key with no `httpx` beside it builds the null decider in silence (adopt, 2026-10-02)."""
    monkeypatch.setattr(nav, "KEY", "test-key")
    monkeypatch.setattr(nav, "decider_class", lambda: built)
    problems = [p for p in nav.preflight() if "decider" in p]
    assert bool(problems) is refused


def test_the_decider_probe_builds_jev_from_a_key_in_this_environment(monkeypatch):
    """Builds, does not call: constructing the client spends nothing."""
    monkeypatch.setattr(nav, "KEY", "test-key")
    assert nav.decider_class().startswith("Jev")


@pytest.mark.parametrize("arm", ["HAIKU", "HAIKU-HINT", "SONNET"])
def test_a_bench_session_cannot_reach_the_real_sessions_on_this_machine(monkeypatch, arm):
    argv, _ = _argv_of(monkeypatch, arm)
    denied = argv[argv.index("--disallowedTools") + 1].split()
    assert {"SendMessage", "ListAgents", "Bash"} <= set(denied)


def test_the_second_hint_arm_carries_the_second_line_only(monkeypatch):
    argv, env = _argv_of(monkeypatch, "HAIKU-HINT2")
    assert nav.STRATEGY_HINT_V2 in _appended(argv)
    assert nav.STRATEGY_HINT not in _appended(argv)
    assert argv[argv.index("--model") + 1] == "claude-haiku-4-5"
    assert "TYPESAFE_API_KEY" not in env


def test_the_second_line_asks_the_extraction_to_account_for_what_it_read():
    """S5, 2026-10-02: with the first line Haiku took one partial scroll as final, 0/3, where
    unaided it kept going when the result looked short, 3/3. The line is ASCII (argv)."""
    line = nav.STRATEGY_HINT_V2.lower()
    assert nav.STRATEGY_HINT_V2.isascii()
    assert "how many" in line and "before you answer" in line


def test_the_second_line_caps_every_loop():
    """H1, 2026-10-02: one evaluate looped on page 2 for 30 minutes; nothing stops an evaluate."""
    assert "cap on every loop" in nav.STRATEGY_HINT_V2
