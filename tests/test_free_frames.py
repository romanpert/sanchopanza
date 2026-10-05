"""The FRAMES sources pilot runner: sampling, arms, deny rules, provisional grading, the answer
before and after the hook's block, leaks and the usage limit. No model, no network, no money."""

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


frames = _load("browse_free_frames", "benchmarks/browse/free_frames.py")
free = frames.free


def _row(i: int, types: str, answer: str = "Paris", links: int = 3) -> dict[str, str]:
    row = {"": str(i), "Prompt": f"q{i}", "Answer": answer, "reasoning_types": types}
    for k in range(1, 12):
        row[f"wikipedia_link_{k}"] = f"https://en.wikipedia.org/wiki/P{k}" if k <= links else ""
    return row


def _bank() -> list[dict[str, str]]:
    alone = [_row(i, "Multiple constraints") for i in range(30)]
    num = [_row(100 + i, "Numerical reasoning | Multiple constraints") for i in range(15)]
    tem = [_row(200 + i, "Multiple constraints | Temporal reasoning") for i in range(15)]
    tab = [_row(300 + i, "Tabular reasoning | Multiple constraints") for i in range(10)]
    off = [_row(400, "Multiple constraints", answer="one two three four five")]
    off += [_row(401, "Multiple constraints", links=1), _row(402, "Multiple constraints", links=5)]
    off += [_row(403, "Numerical reasoning")]
    return alone + num + tem + tab + off


# --- sampling -----------------------------------------------------------------------------------


def test_filters_answer_length_links_and_type():
    assert frames.eligible(_row(1, "Multiple constraints", answer="one two three four"))
    assert not frames.eligible(_row(1, "Multiple constraints", answer="one two three four five"))
    assert not frames.eligible(_row(1, "Multiple constraints", links=1))
    assert not frames.eligible(_row(1, "Multiple constraints", links=5))
    assert frames.eligible(_row(1, "Multiple constraints", links=2))
    assert not frames.eligible(_row(1, "Numerical reasoning | Temporal reasoning"))


def test_strata():
    assert frames.stratum(_row(1, "Multiple constraints")) == "alone"
    assert frames.stratum(_row(1, "Numerical reasoning | Multiple constraints")) == "with"
    assert frames.stratum(_row(1, "Multiple constraints | Temporal reasoning")) == "with"
    assert frames.stratum(_row(1, "Tabular reasoning | Multiple constraints")) is None


def test_sample_is_seeded_balanced_and_filtered():
    bank = _bank()
    first = [frames.tid_of(r) for r in frames.sample(bank, 20, seed=7)]
    assert first == [frames.tid_of(r) for r in frames.sample(bank, 20, seed=7)]
    assert first != [frames.tid_of(r) for r in frames.sample(bank, 20, seed=8)]
    assert len(set(first)) == 20
    by_id = {frames.tid_of(r): r for r in bank}
    kinds = [frames.stratum(by_id[t]) for t in first]
    assert kinds.count("alone") == kinds.count("with") == 10
    assert kinds[:4] == ["alone", "with", "alone", "with"]  # the halves are interleaved
    assert all(frames.eligible(by_id[t]) for t in first)


def test_the_ids_in_the_repo_are_twenty_balanced_eligible_tasks_if_the_set_is_cached():
    ids = frames.IDS.read_text(encoding="utf-8").split()
    assert len(ids) == len(set(ids)) == frames.N_TASKS
    assert all(t.startswith("FR") and t[2:].isdigit() for t in ids)
    if not frames.FRAMES.exists():
        pytest.skip("FRAMES is not cached here")
    rows = frames.read_frames()
    assert ids == [frames.tid_of(r) for r in frames.sample(rows)]


def test_plan_runs_every_task_in_every_arm_interleaved_by_task():
    items = [(f"FR{i}", "", f"q{i}", "g") for i in range(3)]
    steps = frames.plan(items)
    assert len(steps) == 12
    assert [s[3] for s in steps[:4]] == list(frames.ARMS)
    assert [s[1][0] for s in steps[:4]] == ["FR0"] * 4
    assert [s[0] for s in steps] == list(range(12))


def test_caps_ceiling_and_reserve():
    assert frames.CAPS == {"SONNET": 1.50, "SONNET-SRC": 1.05, "HAIKU": 0.60, "HAIKU-SRC": 0.42}
    assert frames.RESERVE_USD == 1.50 and frames.CEILING_USD == 32.0
    limits = frames.phase.Limits(session_max_usd=frames.RESERVE_USD, ceiling_usd=32.0)
    assert frames.phase.stop_reason([{"list_usd": 30.4}], limits, 3) is None
    assert frames.phase.stop_reason([{"list_usd": 30.6}], limits, 3).startswith("ceiling")


# --- arms: deny rules and the hook --------------------------------------------------------------


def test_every_arm_denies_the_hosts_that_serve_the_set():
    settings = free.session_settings(frames.DENY, frames.hooks_for("SONNET"))
    deny = settings["permissions"]["deny"]
    for host in ("huggingface.co", "hf.co", "github.com", "raw.githubusercontent.com"):
        assert f"WebFetch(domain:{host})" in deny
    assert settings["permissions"]["allow"] == free.TOOLS.split()
    assert "hooks" not in settings


def test_only_src_arms_get_the_stop_hook():
    for arm in ("SONNET", "HAIKU"):
        assert frames.hooks_for(arm) is None
    for arm in ("SONNET-SRC", "HAIKU-SRC"):
        hooks = frames.hooks_for(arm)
        assert list(hooks) == ["Stop"]
        command = hooks["Stop"][0]["hooks"][0]["command"]
        assert command.endswith("-m sanchopanza.harness.sources_hook")


def test_calibration_settings_unchanged_without_extras():
    assert free.session_settings() == {"permissions": {"allow": free.TOOLS.split()}}


def test_the_hook_as_a_session_runs_it_blocks_once_then_stays_silent():
    outs = frames.hook_twice()
    assert json.loads(outs[0])["decision"] == "block"
    assert outs[1] == ""


# --- grading, leaks, limits ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "gold", "ok"),
    [
        ("$1,200", "1200", True),
        ("about 1200 people", "1,200", True),
        ("12.5%", "12.5", True),
        ("1201", "1200", False),
        ("The Eiffel Tower.", "Eiffel tower", True),
        ("St. John's Wood", "St Johns Wood", True),
        ("Parisian", "Paris", False),
        ("", "Paris", False),
        ("1990s", "1990", False),
    ],
)
def test_provisional_grade(answer: str, gold: str, ok: bool):
    assert frames.graded(answer, gold) is ok


def test_leak_markers():
    assert frames.leaked("from google/frames-benchmark on the hub")
    assert frames.leaked("the FRAMES dataset")
    assert not frames.leaked("film frames per second")
    assert frames.leaked(r"C:\Users\x\.cache\sanchopanza\free\frames-test.tsv")


def test_limit_markers():
    assert frames.limit_hit("API Error: 429 rate_limit_error")
    assert frames.limit_hit("You've hit your weekly limit")
    assert not frames.limit_hit("ANSWER: 4290")
    assert not frames.limit_hit("")


# --- the transcript: answers before and after the block -----------------------------------------


def _entry(kind: str, text: str, ts: str, side: bool = False) -> tuple[str, dict]:
    role = "assistant" if kind == "assistant" else "user"
    entry = {"type": kind, "timestamp": ts, "isSidechain": side,
             "message": {"role": role, "content": [{"type": "text", "text": text}]}}  # fmt: skip
    return json.dumps(entry), entry


def test_answers_before_and_after_the_block():
    entries = [
        _entry("user", "question", "t1"),
        _entry("assistant", "Done.\nANSWER: Lyon", "t2"),
        _entry("user", "Stop hook feedback: " + frames.REQUEST, "t3"),
        _entry("assistant", "Sources...\nANSWER: Paris", "t4"),
    ]
    seen = frames.answers(entries)
    assert seen == {"hook_fired": True, "block_ts": "t3", "answer_before": "Lyon",
                    "answer_after": "Paris"}  # fmt: skip


def test_one_block_as_claude_code_2_1_287_writes_it():
    """The smoke's transcripts carry the reason three times, adjacent: the user message, a
    `hook_blocking_error` attachment and the `stop_hook_summary`. One block, not three."""
    reason = {"reason": frames.REQUEST}
    entries = [
        _entry("assistant", "ANSWER: Lyon", "t2"),
        _entry("user", "Stop hook feedback:\n" + frames.REQUEST, "t3"),
        (json.dumps({"type": "attachment", "timestamp": "t3",
                     "attachment": {"type": "hook_blocking_error", **reason}}), {}),
        (json.dumps({"type": "system", "subtype": "stop_hook_summary", "timestamp": "t3",
                     **reason}), {}),
        _entry("assistant", "ANSWER: Paris", "t5"),
    ]  # fmt: skip
    seen = frames.answers(entries)
    assert seen["block_ts"] == "t3"
    assert (seen["answer_before"], seen["answer_after"]) == ("Lyon", "Paris")


def test_the_cap_in_the_extra_turn_keeps_the_answer_given_before():
    entries = [
        _entry("assistant", "ANSWER: Lyon", "t2"),
        _entry("user", frames.REQUEST, "t3"),
        _entry("assistant", "Looking for one more source", "t4"),
    ]
    seen = frames.answers(entries)
    assert (seen["answer_before"], seen["answer_after"]) == ("Lyon", "Lyon")


def test_no_block_means_before_equals_after():
    seen = frames.answers([_entry("assistant", "ANSWER: 1", "t1"), _entry("assistant", "x", "t2")])
    assert seen == {"hook_fired": False, "block_ts": None, "answer_before": "1",
                    "answer_after": "1"}  # fmt: skip


def test_main_entries_skip_subagents(tmp_path: pathlib.Path):
    lines = [_entry("assistant", "ANSWER: main", "t1")[0],
             _entry("assistant", "ANSWER: sub", "t2", side=True)[0]]  # fmt: skip
    (tmp_path / "s.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    seen = frames.answers(frames.main_entries(tmp_path))
    assert seen["answer_after"] == "main"


def test_usd_after_block_is_the_total_less_the_calls_before_it():
    calls = [{"ts": "t1"}, {"ts": "t2"}, {"ts": "t4"}, {"ts": "t5"}]
    assert frames.usd_after(calls, [0.1, 0.3, 0.5, 0.6], "t3") == 0.3
    assert frames.usd_after(calls, [0.1, 0.3, 0.5, 0.6], "t0") == 0.6


# --- the session wrapper ------------------------------------------------------------------------


def _fake_row(work: pathlib.Path) -> dict:
    return {"task": "FR1", "run": 1, "arm": "HAIKU-SRC", "success": False, "answer": "",
            "list_usd": 0.2, "usd_by_model": {}, "subtype": "success", "workdir": str(work),
            "tools": {}}  # fmt: skip


def test_a_429_in_the_session_stops_the_phase_and_says_stop_limit(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    (work / "stderr.txt").write_text("API Error: 429 weekly limit", encoding="utf-8")
    monkeypatch.setattr(free, "one_session", lambda *a, **k: _fake_row(work))
    monkeypatch.setattr(frames.trace, "folder_of", lambda _w: tmp_path / "none")
    sessions = tmp_path / "s.jsonl"
    step = (0, ("FR1", "", "q", "Paris"), 1, "HAIKU-SRC")
    later = (1, ("FR2", "", "q", "Lyon"), 1, "HAIKU-SRC")
    limits = frames.phase.Limits(session_max_usd=1.5, ceiling_usd=32.0)
    code, rows = frames.phase.run_phase(
        [step, later], [], limits, frames.session_for(sessions), sessions
    )
    assert code == 2 and len(rows) == 1 and rows[0]["not_run"]
    assert "STOP-LIMIT" in sessions.with_suffix(".log").read_text(encoding="utf-8")


def test_the_wrapper_passes_the_arm_cap_deny_and_hook(tmp_path, monkeypatch):
    seen = {}

    def fake(task, run, arm, **kw):
        seen.update(kw)
        return _fake_row(tmp_path)

    monkeypatch.setattr(free, "one_session", fake)
    monkeypatch.setattr(frames.trace, "folder_of", lambda _w: tmp_path / "none")
    row = frames.session_for(tmp_path / "s.jsonl")(("FR1", "", "q", "Paris"), 1, "HAIKU-SRC")
    assert seen["session_max_usd"] == 0.42 and seen["deny"] == frames.DENY
    assert seen["hooks"] == frames.hooks_for("HAIKU-SRC")
    assert "SANCHOPANZA_SOURCES_DIR" in seen["env_extra"]
    assert row["provisional"] and not row["hook_fired"] and not row["leak"]
    assert row["success"] is False and row["answer"] == ""


def test_report_counts_the_matrix_on_fired_sessions():
    rows = [
        {"arm": "SONNET-SRC", "list_usd": 0.5, "ok_auto": True, "ok_before": False,
         "hook_fired": True, "usd_after_block": 0.1},
        {"arm": "SONNET-SRC", "list_usd": 0.7, "ok_auto": True, "ok_before": True,
         "hook_fired": True, "usd_after_block": 0.3},
        {"arm": "SONNET", "list_usd": 0.4, "ok_auto": False},
    ]  # fmt: skip
    out = frames.report(rows)
    cell = out["by_arm"]["SONNET-SRC"]
    assert cell["before_after"]["wrong->right"] == 1 and cell["before_after"]["right->right"] == 1
    assert cell["mean_usd_after_block"] == 0.2
    assert out["by_arm"]["SONNET"]["ok_auto"] == 0 and out["provisional_grades"]


# --- grading: golds with an addition, golds made of symbols (fixed after the first pilot) -------


@pytest.mark.parametrize(
    ("answer", "gold", "ok"),
    [
        ("Lyon Circuit", "Lyon Circuit 1999", True),  # the gold appends a year
        ("Lyon Circuit 1999", "Lyon Circuit 1999", True),
        ("Lyon", "Lyon Circuit 1999", False),
        ("1999", "Lyon Circuit 1999", False),
        ("Paris", "Paris (France)", True),  # the gold appends a parenthesis
        ("-.--", "-.--", True),  # a gold of symbols alone
        ("-.--.", "-.--", True),  # the sentence's full stop
        ("**-.--**", "-.--", True),
        ("-..-", "-.--", False),
        ("--.--", "-.--", False),
        ("", "-.--", False),
    ],
)
def test_grade_golds_with_an_addition_or_of_symbols(answer: str, gold: str, ok: bool):
    assert frames.graded(answer, gold) is ok


def test_the_block_of_either_version_is_found():
    from sanchopanza.harness.sources_v2 import REQUEST_V2

    for request in (frames.REQUEST, REQUEST_V2 + " (Why: your reply has words of doubt.)"):
        entries = [_entry("assistant", "ANSWER: Lyon", "t2"),
                   _entry("user", "Stop hook feedback:\n" + request, "t3"),
                   _entry("assistant", "ANSWER: Paris", "t4")]  # fmt: skip
        seen = frames.answers(entries)
        assert seen["hook_fired"] and seen["answer_before"] == "Lyon"


def test_src_arms_of_either_version():
    assert frames.is_src("SONNET-SRC") and frames.is_src("HAIKU-SRC2")
    assert not frames.is_src("SONNET") and not frames.is_src("HAIKU")
