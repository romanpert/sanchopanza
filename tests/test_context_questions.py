"""The questions of the `context` point, ours and the fast-jev-compaction replica."""

from __future__ import annotations

import json

from sanchopanza import Decision, Truth, truth
from sanchopanza.context import calls, messages_from_claude_code
from sanchopanza.points import context as q

from .context_helpers import APP, write_transcript

SECRET = "sk-ant-api03-" + "A" * 40


def _session(tmp_path):
    messages = messages_from_claude_code(write_transcript(tmp_path / "s.jsonl"))
    return messages, calls(messages)


def test_one_truth_per_candidate_with_ids_in_order(tmp_path):
    messages, found = _session(tmp_path)
    state, qs = q.prune_questions("Fix it", messages, found, candidates=["t4", "t5"])
    assert list(qs) == ["C01", "C02"] and all(isinstance(x, Truth) for x in qs.values())
    assert "C01" in qs["C01"].instructions and set(qs["C01"].criteria) == {"true", "false"}
    assert set(state) == {"context", "task", "history"}
    history = state["history"]
    assert "CALL C01 Read" in history and "RESULT C01 (ok," in history
    assert "CALL C02 Bash" in history and "CALL Bash" in history  # t2 is shown, unlabelled


def test_candidate_results_are_cut_head_and_tail_and_others_shorter(tmp_path):
    messages, found = _session(tmp_path)
    state, _ = q.prune_questions("Fix it", messages, found, candidates=["t4"])
    line = next(x for x in state["history"].splitlines() if "RESULT C01" in x)
    whole = next(x for x in state["history"].split("\n  RESULT") if " C01 (" in x)
    assert "chars omitted" in whole and len(whole) < q.RESULT_LIMIT + 120
    assert line.startswith(f"  RESULT C01 (ok, {len(APP)} chars)")


def test_at_most_call_max_candidates_are_asked(tmp_path):
    messages, found = _session(tmp_path)
    ids = [c.id for c in found] * 10
    _, qs = q.prune_questions("t", messages, found, candidates=ids)
    assert len(qs) == q.CALL_MAX


def test_stubbed_by_rules_are_shown_as_removed(tmp_path):
    messages, found = _session(tmp_path)
    state, _ = q.prune_questions(
        "t", messages, found, candidates=["t4"], hidden={"t1": "read_superseded"}
    )
    assert "[removed: read_superseded]" in state["history"]


def test_secrets_are_redacted_before_the_state_leaves(tmp_path):
    messages = [
        {"role": "user", "content": f"use {SECRET}"},
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "a", "name": "Bash", "input": {"command": "env"}}
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "a", "content": f"KEY={SECRET}\n" * 3}
            ],
        },
    ]
    state, _ = q.prune_questions("t", messages, calls(messages), candidates=["a"])
    assert SECRET not in json.dumps(state) and "[secret]" in state["history"]
    fast, _ = q.fastjev_questions(messages, calls(messages), [0])
    assert SECRET not in json.dumps(fast)


def test_a_long_history_is_fitted_under_the_limit():
    blocks = []
    for i in range(80):
        blocks.append(
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "t" * 1_400},
                    {
                        "type": "tool_use",
                        "id": f"a{i}",
                        "name": "Bash",
                        "input": {"command": f"c{i}"},
                    },
                ],
            }
        )
        blocks.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": f"a{i}", "content": "r" * 2_000}
                ],
            }
        )
    state, _ = q.prune_questions("t", blocks, calls(blocks), candidates=["a0", "a79"])
    assert len(state["history"]) <= q.HISTORY_LIMIT + 60
    assert "CALL C01" in state["history"] and "CALL C02" in state["history"]


def test_fastjev_questions_are_theirs_verbatim(tmp_path):
    messages, found = _session(tmp_path)
    state, qs = q.fastjev_questions(messages, found, [0, 1])
    assert list(qs) == ["call_t1", "result_t1", "call_t2", "result_t2"]
    assert qs["call_t1"].instructions == (
        "Tool call t1 (Read) should stay in the history: knowing this call was made, with its "
        "input, still matters for what the assistant does next"
    )
    assert qs["result_t2"].instructions == (
        f"The full output of tool call t2 (Bash, {found[1].chars} chars) should stay in the "
        "history verbatim: the assistant still needs its contents and re-running the tool "
        "would not do"
    )
    assert state["context"].endswith(
        "Whatever is not kept is deleted permanently, but the assistant can always re-run a "
        "tool or re-read a file."
    )
    entry = next(e for e in state["history"] if e.get("tool_calls"))
    assert entry["tool_calls"][0]["result"] == f"ok, {found[0].chars} chars (omitted)"
    errored = next(c for e in state["history"] for c in e.get("tool_calls", []) if c["id"] == "t2")
    assert errored["result"].startswith("error, ")
    assert state["goal"] == "Fix the failing test in app.py"


def _answers(**ps: float) -> Decision:
    return Decision("context_fastjev", {k: truth(v) for k, v in ps.items()}, "t", "t")


def test_fastjev_decision_table():
    both = q.fastjev_decide(_answers(call_t1=0.9, result_t1=0.6), 0)
    only_call = q.fastjev_decide(_answers(call_t1=0.5, result_t1=0.49), 0)
    neither = q.fastjev_decide(_answers(call_t1=0.1, result_t1=0.2), 0)
    unanswered = q.fastjev_decide(_answers(), 0)
    assert (both.action, only_call.action, neither.action) == ("keep", "truncate", "drop")
    assert (only_call.reason, neither.reason) == ("result_dropped", "call_dropped")
    assert unanswered.action == "keep" and unanswered.keep_result == 1.0


def test_fastjev_pins_the_first_and_last_six_messages(tmp_path):
    messages, found = _session(tmp_path)
    pinned = [q.fastjev_pinned(c, len(messages)) for c in found]
    assert pinned == [False, False, True, True, True]


def test_fastjev_truncation_note():
    assert q.fastjev_truncated("short", False) == "short"
    cut = q.fastjev_truncated("a" * 1_000, True)
    assert cut.startswith("a" * 300 + "\n") and "truncated 700 chars" in cut and "(error)" in cut
