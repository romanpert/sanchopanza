"""check_done's record keeps the part of a long tool result the agent's answer rests on.

On 950 unseen AgentDojo stops (docs/results/2026-10-16-checkdone114/) 115 of Jev 1.14's 150
false blocks had a tool result cut at its first 1,500 characters: the agent answered from the
whole result and the judge saw an answer it could not check. `done_evidence` keeps the head as
before and, past it, short windows around the values the agent wrote afterwards (numbers, ids,
names, files, addresses), inside a fixed extra budget. One function, used by the Stop hook and
by the bench.
"""

from __future__ import annotations

import json
from pathlib import Path

from sanchopanza.points import done_evidence as ev


def _listing(n: int, special: dict[int, str]) -> str:
    rows = []
    for i in range(n):
        name = special.get(i, f"note-{i:03d}.txt")
        rows.append(f"- filename: {name}\n  id_: '{i}'\n  size: {1000 + i}\n  owner: emma\n")
    return "".join(rows)


# --- anchors: what the agent wrote that a tool result can back -------------------------------


def test_anchors_are_the_values_an_answer_rests_on():
    text = (
        'The largest file is "recipe-collection.docx" (ID 11), 3599 bytes, owned by '
        "emma.johnson@bluesparrowtech.com. You meet Sarah Connor at Central Park Cafe on "
        "2024-05-15 at 12:30. See https://example.com/a?b=1. There are 3 of them."
    )
    found = ev.anchors(text)
    for want in ("recipe-collection.docx", "11", "3599", "emma.johnson@bluesparrowtech.com",
                 "Sarah Connor", "Central Park Cafe", "2024-05-15", "12:30",
                 "https://example.com/a?b=1"):  # fmt: skip
        assert want in found, want
    assert "3" not in found  # one digit backs nothing on its own
    assert "The" not in found and "You" not in found and "There" not in found


def test_anchors_keep_their_first_order_and_no_repeats():
    assert ev.anchors("pay 98.70 to Bob Smith, then 98.70 again to Bob Smith") == [
        "98.70",
        "Bob Smith",
    ]


def test_an_anchor_matches_whole_values_only():
    assert ev.find("2011-01-02 and 110", "11") is None
    assert ev.find("id_: '11'\n", "11") == 6
    assert ev.find("Owner: SARAH CONNOR", "Sarah Connor") == 7  # case does not matter
    assert ev.find("Date: 2023-11-15", "11") is None  # not the middle of a date
    assert ev.find("total 98.70", "98") is None  # nor the head of a longer number
    assert ev.find("at 2024-05-15 12:30:00", "12:30") == 14  # a time read off a timestamp


# --- the kept result -------------------------------------------------------------------------


def test_a_result_that_fits_is_kept_whole():
    assert ev.kept("short result", "anything 12345") == "short result"


def test_a_long_result_with_nothing_the_answer_rests_on_past_the_head_is_cut_as_before():
    result = _listing(80, {})
    assert len(result) > ev.HEAD
    assert ev.kept(result, "Done. I listed the files.") == result[: ev.HEAD]
    assert ev.kept(result, "") == result[: ev.HEAD]


def test_the_value_the_answer_names_past_the_head_is_kept_with_its_neighbourhood():
    result = _listing(80, {60: "recipe-collection.docx"})
    assert result.find("recipe-collection.docx") > ev.HEAD
    later = 'The largest file is "recipe-collection.docx".'
    out = ev.kept(result, later)
    assert out.startswith(result[: ev.HEAD] + ev.MARK)
    window = out[ev.HEAD + len(ev.MARK) :]
    assert "recipe-collection.docx" in window
    assert "size: 1060" in window  # the line after it: what makes it checkable


def test_values_already_in_the_head_add_nothing():
    result = _listing(80, {2: "recipe-collection.docx"})
    assert ev.kept(result, "It is recipe-collection.docx, size 1002.") == result[: ev.HEAD]


def test_the_extra_room_is_bounded_however_many_values_the_answer_names():
    result = _listing(400, {})
    later = " ".join(f"note-{i:03d}.txt" for i in range(100, 400, 3))
    out = ev.kept(result, later)
    assert len(out) <= ev.HEAD + ev.EXTRA
    assert out.startswith(result[: ev.HEAD])
    assert ev.kept(result, later) == out  # deterministic


def test_the_rarest_values_are_kept_first():
    filler = "x" * 2000
    result = filler + " id 77 " + "y" * 600 + " total 4321 " + ("z 77 " * 50)
    out = ev.kept(result, "Total 4321 for item 77", head=1500, extra=400)
    assert "4321" in out  # once past the head, against 77 fifty-one times


def test_windows_follow_the_order_of_the_result_and_merge_when_they_touch():
    result = "h" * 1600 + " alpha 5551 beta 5552 " + "q" * 900 + " gamma 5553 "
    out = ev.kept(result, "5553 then 5551 and 5552")
    tail = out[1500:]
    assert tail.index("5551") < tail.index("5552") < tail.index("5553")
    assert tail.count(ev.MARK.strip()) == 2  # one before the merged window, one before the last


def test_the_final_answer_is_looked_for_even_after_an_action_full_of_values():
    long = _listing(80, {60: "recipe-collection.docx"})
    noisy = "write(" + " ".join(f"v{i:04d}x{i}" for i in range(300)) + ")"
    steps = [("tool", long), ("action", noisy), ("agent", "It is recipe-collection.docx.")]
    assert "size: 1060" in ev.kept_results(steps)[0]


def test_a_value_cut_by_the_head_is_neither_seen_nor_found_by_halves():
    result = "x" * 1497 + " 123456 " + "y" * 600 + " 3456 " + "z" * 600 + " 12 "
    assert result[:1500].endswith(" 12") and result[1500:].startswith("3456 ")
    out = ev.kept(result, "the totals were 3456 and 12")
    assert "y 3456" in out  # the whole value past the head, not the tail of 123456
    assert "z 12 " in out  # "12" at the end of the head is half a number, not a visible 12


def test_long_sessions_stay_fast():
    import time

    long = _listing(80, {60: "recipe-collection.docx"})
    noisy = "write(" + " ".join(f"v{i:04d}x{i}" for i in range(300)) + ")"
    steps = [("tool", long), ("action", noisy)] * 300 + [("agent", "recipe-collection.docx")]
    start = time.perf_counter()
    ev.record(steps, evidence=True)
    assert time.perf_counter() - start < 5.0


def test_long_inputs_cost_linear_time():
    import time

    words = ["a" * 20_000, "1" * 20_000, "A" * 20_000, "a." * 10_000]
    big = "".join(f"line {i}: value {i * 7919 % 10**6} file f{i}.txt Owner Name{i % 50}\n"
                  for i in range(4000))  # fmt: skip
    later = " ".join(f"{i * 104729 % 10**6} f{i * 13 % 4000}.txt Name{i}" for i in range(200))
    start = time.perf_counter()
    for word in words:
        ev.anchors(word)
    ev.record([("tool", big)] * 20 + [("agent", later)], evidence=True)
    assert time.perf_counter() - start < 3.0  # was minutes: a hook has to answer in time


# --- the record: the same builder for the hook and the bench ---------------------------------


def test_the_record_without_evidence_is_the_old_record_byte_for_byte():
    steps = [("agent", "Reading it"), ("action", 'read({"p": "a"})'), ("tool", "r" * 2000),
             ("agent", "It says 12345")]  # fmt: skip
    assert ev.record(steps, evidence=False) == "\n".join(
        [
            "AGENT: Reading it",
            'AGENT ACTION: read({"p": "a"})',
            "TOOL RESULT: " + "r" * 1500,
            "AGENT: It says 12345",
        ]  # fmt: skip
    )


def test_the_record_looks_for_evidence_only_in_what_the_agent_wrote_after_the_result():
    long = _listing(80, {60: "recipe-collection.docx"})
    before = [("agent", "Looking for recipe-collection.docx"), ("tool", long)]
    assert "recipe-collection.docx" not in ev.record(before, evidence=True).split("TOOL RESULT:")[1]
    after = [("tool", long), ("action", 'share({"file": "recipe-collection.docx"})')]
    assert "size: 1060" in ev.record(after, evidence=True)


def test_evidence_never_pushes_a_record_that_fit_past_the_record_limit():
    long = _listing(80, {60: "recipe-collection.docx"})
    steps = [("tool", long), ("agent", "recipe-collection.docx")]
    old = ev.record(steps, evidence=False)
    new = ev.record(steps, evidence=True)
    assert len(new) > len(old)
    assert ev.record(steps, evidence=True, limit=len(new)) == new
    assert ev.record(steps, evidence=True, limit=len(new) - 1) == old  # it would be cut: old one
    assert ev.record(steps, evidence=True, limit=len(old) - 1) == new  # the old was cut anyway


def _transcript(tmp_path: Path, result: str, answer: str) -> Path:
    lines = [
        {"type": "user", "message": {"role": "user", "content": "Which file is the largest?"}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "list_files", "input": {}}]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": result}]}},
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "text", "text": answer}]}},
    ]  # fmt: skip
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    return path


def test_the_stop_hook_and_the_bench_build_the_same_record(tmp_path):
    from sanchopanza.harness.claude_code import transcript_task_and_record

    long = _listing(80, {60: "recipe-collection.docx"})
    answer = "The largest is recipe-collection.docx."
    path = _transcript(tmp_path, long, answer)
    steps = [("action", "list_files({})"), ("tool", long), ("agent", answer)]
    for evidence in (False, True):
        task, record = transcript_task_and_record(path, evidence=evidence)
        assert task == "Which file is the largest?"
        assert record == ev.record(steps, evidence=evidence)
    assert "size: 1060" in transcript_task_and_record(path, evidence=True)[1]
    assert "size: 1060" not in transcript_task_and_record(path)[1]  # off unless asked


def test_the_agentdojo_bench_renders_through_the_same_builder():
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "completion_run_ev", root / "benchmarks" / "completion" / "run.py"
    )
    bench = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bench)
    long = _listing(80, {60: "recipe-collection.docx"})
    messages = [
        {"role": "user", "content": [{"type": "text", "content": "Which file is the largest?"}]},
        {"role": "assistant", "content": [],
         "tool_calls": [{"function": "list_files", "args": {}}]},
        {"role": "tool", "content": [{"type": "text", "content": long}]},
        {"role": "assistant", "content": [{"type": "text", "content": "recipe-collection.docx"}]},
    ]  # fmt: skip
    steps = [("action", "list_files({})"), ("tool", long), ("agent", "recipe-collection.docx")]
    for evidence in (False, True):
        task, record = bench.render(messages, evidence=evidence)
        assert record == ev.record(steps, evidence=evidence)
    assert bench.render(messages)[1] == ev.record(steps, evidence=False)


def test_the_hook_reads_the_switch_from_the_environment():
    from sanchopanza.harness.claude_code import config_from_env

    assert config_from_env({}).done_evidence is False
    assert config_from_env({"SANCHOPANZA_DONE_EVIDENCE": "1"}).done_evidence is True
