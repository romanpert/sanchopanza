"""Lot longdoc-free's Claude Code driver (benchmarks/h2h/h2h_lfree.py): the answer, the arms'
files and prompts, the interleaving, the money and the refusals. No session, no network."""

from __future__ import annotations

import datetime as dt
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, rel: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


h2h = _load("lf_h2h", "benchmarks/h2h/h2h_lfree.py")


def _benchmarks_off_the_path() -> None:
    """The driver puts benchmarks/ on sys.path, where `agentdojo/` imports as a namespace
    package and breaks the agentdojo skip of later tests (memory: trampas-tests-sys-path)."""
    for entry in (str(ROOT / "benchmarks"), str(ROOT / "benchmarks" / "b6_es")):
        while entry in sys.path:
            sys.path.remove(entry)


_benchmarks_off_the_path()
CACHED = h2h.pool.RAW.exists() and h2h.pool.IDS_FILE.exists()


@pytest.fixture(autouse=True)
def _benchmarks_on_the_path_while_testing(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "benchmarks"))


# ---- the answer --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reply", "answer"),
    [
        ("I looked through the book.\nANSWER: Peyton", "Peyton"),
        ("**ANSWER:** Mrs. Deandra", "Mrs. Deandra"),
        ("Answer: first\nmore\nanswer: the Hebrides", "the Hebrides"),
        ("The summer home is the Hebrides.", "The summer home is the Hebrides."),
        ("Reasoning...\n\nPeyton\n", "Peyton"),
        ("Final answer: Peyton", "Peyton"),
        ("", None),
        ("   \n", None),
        (None, None),
    ],
)
def test_the_answer_is_the_last_answer_line_else_the_last_line(reply, answer):
    assert h2h.extract(reply) == answer


def test_grading_is_infbench_token_f1_and_no_answer_scores_zero():
    assert h2h.grade("Peyton", ['"Peyton"']) == 1.0
    assert h2h.grade(None, ["Peyton"]) == 0.0
    assert 0 < h2h.grade("Peyton Bronwyn", ["Peyton"]) < 1


# ---- arms --------------------------------------------------------------------------------------


def _task(variant: str, stage: str = "dev") -> object:
    return h2h.FreeTask(f"7:{variant}", 7, variant, "abc", "Who is it?", ("Peyton",), stage)


def test_each_arm_reads_its_own_file_and_the_same_prompt():
    assert h2h.document_of(_task("N")) == h2h.pool.novel_path("abc")
    assert h2h.document_of(_task("H0")) == h2h.pool.novel_path("abc")
    assert h2h.document_of(_task("H")) == h2h.jev_phase.passages_path("dev", 7)
    assert h2h.document_of(_task("H", "confirm")) == h2h.jev_phase.passages_path("confirm", 7)
    assert h2h.document_of(_task("HC")) is None
    assert h2h.prompt(_task("N")) == h2h.prompt(_task("H")) == h2h.prompt(_task("H0"))
    assert "document.txt" in h2h.prompt(_task("N")) and "Be very concise" in h2h.prompt(_task("N"))
    assert "no file" in h2h.prompt(_task("HC")) and "document.txt" not in h2h.prompt(_task("HC"))
    assert all("ANSWER:" in h2h.prompt(_task(v)) for v in ("N", "H", "H0", "HC"))


def test_haiku_arms_rotate_with_the_question_and_sonnet_has_one():
    assert h2h.variants_at("HAIKU", 0) == ["H", "H0", "HC"]
    assert h2h.variants_at("HAIKU", 1) == ["H0", "HC", "H"]
    assert h2h.variants_at("HAIKU", 2) == ["HC", "H", "H0"]
    assert h2h.variants_at("SONNET", 5) == ["N"]


def test_the_phase_keys_name_the_variant_so_resumed_rows_never_collide():
    tasks = [_task(v) for v in ("H", "H0", "HC")]
    steps = h2h.steps(h2h.DEV_HAIKU, tasks)
    assert [s[1][0] for s in steps] == ["7:H", "7:H0", "7:HC"]
    assert {s[3] for s in steps} == {"HAIKU-CC"}


@pytest.mark.skipif(not CACHED, reason="∞Bench En.QA or its frozen ids not cached")
def test_the_dev_phases_cover_every_dev_question_once_per_arm():
    dev = set(h2h.pool.phase_ids(h2h.pool.read_frozen(), "dev"))
    n = h2h.tasks_of(h2h.DEV_N)
    haiku = h2h.tasks_of(h2h.DEV_HAIKU)
    assert {t.item for t in n} == dev and len(n) == h2h.DEV_N.n == len(dev)
    assert len(haiku) == h2h.DEV_HAIKU.n == 3 * len(dev)
    assert {(t.item, t.variant) for t in haiku} == {(i, v) for i in dev for v in ("H", "H0", "HC")}
    assert [t.item for t in n] == [t.item for t in haiku[::3]]  # the same seeded order
    smoke = h2h.tasks_of(h2h.SMOKE)
    assert len(smoke) == 1 and smoke[0].variant == "N"


# ---- money -------------------------------------------------------------------------------------


def test_each_dev_phase_has_room_for_its_sessions_at_one_and_a_half_times_the_estimate():
    """cap_for stops a phase once ceiling - spent - worst turn is under the floor: the room
    before that must hold n sessions at 1.5x the design's estimate (N 0.10; Haiku 0.03 H,
    0.05 H0, 0.005 HC)."""
    for phase, mean in ((h2h.DEV_N, 0.10), (h2h.DEV_HAIKU, (0.03 + 0.05 + 0.005) / 3)):
        room = phase.ceiling - phase.worst_turn - phase.floor
        assert room >= 1.5 * mean * phase.n, phase.key


def test_the_dev_stage_most_is_its_ceilings_plus_the_smokes_worst_turn():
    got = h2h.money("dev")
    assert got["most_usd"] == pytest.approx(0.80 + 4.32 + 12.00 + 9.00)
    assert got["most_usd"] <= 105.0  # the owner's Claude cap for the whole lot


# ---- rows without text -------------------------------------------------------------------------


def test_public_rows_carry_scores_and_money_not_the_answer():
    row = {"arm": "HAIKU-CC", "task_id": "7:H", "item": 7, "variant": "H", "f1": 1.0,
           "answer_words": 1, "has_answer_line": True, "final_answer": "Peyton",
           "list_usd": 0.02, "ok": True, "run": 1, "usd_by_model": {}}  # fmt: skip
    out = h2h.public_rows([row], h2h.DEV_HAIKU)
    assert out and "Peyton" not in str(out) and out[0]["f1"] == 1.0 and out[0]["id"] == 7


# ---- refusals ----------------------------------------------------------------------------------


def _git(branch: bool = False, status: str = "", tracked: bool = True, sealed_at: str = "abc"):
    def git(*args: str) -> subprocess.CompletedProcess:
        if args[0] == "symbolic-ref":
            return subprocess.CompletedProcess(args, 0 if branch else 1, "", "")
        if args[0] == "ls-files":
            return subprocess.CompletedProcess(args, 0 if tracked else 1, "", "")
        if args[0] == "rev-parse":
            return subprocess.CompletedProcess(args, 0, "abc\n", "")
        if args[0] == "log":
            return subprocess.CompletedProcess(args, 0, f"{sealed_at}\n", "")
        return subprocess.CompletedProcess(args, 0, status, "")

    return git


def test_a_run_starts_only_from_the_seal_commit_detached_and_clean():
    lot = h2h.claude_lot("dev")
    seal = h2h.jev_phase.sealed_head_problems
    assert seal(lot, _git()) == []
    assert any("branch" in p for p in seal(lot, _git(branch=True)))
    assert any("changes" in p for p in seal(lot, _git(status=" M x.py\n")))
    assert any("not committed" in p for p in seal(lot, _git(tracked=False)))
    assert any("not the commit that sealed" in p for p in seal(lot, _git(sealed_at="def")))


def test_the_launcher_takes_this_runner():
    assert h2h.launcher_problems() == []


def test_an_unsealed_stage_is_refused_before_any_session(tmp_path: Path):
    kind, why = h2h.refusal("dev", dt.datetime(2026, 10, 18, 9, 0), run_dir=tmp_path, git=_git())
    assert kind == "preflight" and "sealed" in why


def test_the_claude_lot_binds_the_jev_phases_prereg_with_the_whole_instrument():
    lot = h2h.claude_lot("dev")
    assert lot.prereg == h2h.jev_phase.lot("dev").prereg
    assert lot.instrument == ("src", "benchmarks", "docs/results/2026-10-16-longdoc-free/ids.json")


# ---- one session end to end, with a fake claude ------------------------------------------------


def _session(tmp_path, monkeypatch, variant: str, reply: str) -> tuple[dict, dict]:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    gaia = h2h.gaia
    monkeypatch.setattr(gaia, "RUNS", tmp_path / "runs")
    tmp_path.mkdir(parents=True, exist_ok=True)
    novel = tmp_path / "abc.txt"
    novel.write_text("The Bronwyns spent the summer in the Hebrides. " * 100, "utf-8")
    kept = tmp_path / "7.txt"
    kept.write_text("They spent the summer in the Hebrides.", "utf-8")
    monkeypatch.setattr(h2h.pool, "novel_path", lambda key: novel)
    monkeypatch.setattr(h2h.jev_phase, "passages_path", lambda phase, item: kept)
    seen: dict = {}

    def fake(argv, work, side, env):
        doc = work / "document.txt"
        seen["doc"] = doc.read_text("utf-8") if doc.exists() else None
        seen["prompt"] = argv[-1]
        seen["model"] = argv[argv.index("--model") + 1]
        seen["cap"] = argv[argv.index("--max-budget-usd") + 1]
        return {"result": reply, "total_cost_usd": 0.04, "is_error": False,
                "subtype": "success", "num_turns": 3}, ""  # fmt: skip

    monkeypatch.setattr(gaia, "run_claude", fake)
    task = h2h.FreeTask(f"7:{variant}", 7, variant, "abc", "What is the name of the Bronwyns' "
                        "summer home?", ("the Hebrides",), "dev")  # fmt: skip
    arm = "SONNET-CC" if variant == "N" else "HAIKU-CC"
    model = arm.split("-")[0]
    row = h2h.one_session(task, 1, arm, {"phase": "t"}, "t", {model: 0.75})
    return row, seen


def test_n_reads_the_novel_and_is_graded_by_infbench(tmp_path, monkeypatch):
    row, seen = _session(tmp_path, monkeypatch, "N", "Searched the file.\nANSWER: The Hebrides")
    assert seen["doc"].startswith("The Bronwyns") and len(seen["doc"]) > 1000
    assert seen["model"] == "claude-sonnet-5-5" and seen["cap"] == "0.75"
    assert "document.txt" in seen["prompt"] and "Bronwyns' summer home" in seen["prompt"]
    assert row["final_answer"] == "The Hebrides" and row["f1"] == 1.0
    assert row["item"] == 7 and row["variant"] == "N" and row["has_answer_line"]
    assert row["task_id"] == "7:N" and row["list_usd"] == pytest.approx(0.04)


def test_h_reads_the_kept_passages_and_hc_reads_nothing(tmp_path, monkeypatch):
    row, seen = _session(tmp_path, monkeypatch, "H", "ANSWER: Hebrides")
    assert seen["doc"] == "They spent the summer in the Hebrides."
    assert seen["model"] == "claude-haiku-4-5-20251001" and row["f1"] == 1.0
    row, seen = _session(tmp_path / "hc", monkeypatch, "HC", "I am not sure.\nANSWER: Skye")
    assert seen["doc"] is None and "no file" in seen["prompt"]
    assert row["f1"] == 0.0 and row["final_answer"] == "Skye"


def test_a_long_answer_loses_precision_and_no_text_is_no_answer(tmp_path, monkeypatch):
    row, _ = _session(tmp_path, monkeypatch, "H0", "ANSWER: their summer home was the Hebrides")
    assert 0 < row["f1"] < 0.5 and row["answer_words"] == 6
    row, _ = _session(tmp_path / "e", monkeypatch, "H0", "")
    assert row["final_answer"] is None and row["f1"] == 0.0


# ---- review of 2026-10-17 ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "API Error: 500 Internal server error",
        "Invalid API key · Please run /login",
        "Let me search the file for the summer home.",
    ],
)
def test_a_failed_or_capped_session_without_an_answer_line_has_no_answer(reply):
    assert h2h.extract(reply, ok=False) is None
    assert h2h.extract(reply + "\nANSWER: Peyton", ok=False) == "Peyton"


def test_a_failed_session_reaches_the_guard_as_no_answer(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    gaia = h2h.gaia
    monkeypatch.setattr(gaia, "RUNS", tmp_path / "runs")
    novel = tmp_path / "abc.txt"
    novel.write_text("text " * 10, "utf-8")
    monkeypatch.setattr(h2h.pool, "novel_path", lambda key: novel)
    monkeypatch.setattr(gaia, "run_claude", lambda argv, work, side, env: (
        {"result": "Invalid API key · Please run /login", "total_cost_usd": 0.0,
         "is_error": True, "subtype": "error_during_execution"}, ""))  # fmt: skip
    task = h2h.FreeTask("7:N", 7, "N", "abc", "Who?", ("Peyton",), "dev")
    row = h2h.one_session(task, 1, "SONNET-CC", {"phase": "t"}, "t", {"SONNET": 0.75})
    assert row["final_answer"] is None and row["f1"] == 0.0
    assert h2h.guard_mod.trouble(row, h2h.meter.SONNET_55) is not None


def test_the_short_f1_cuts_the_answer_to_twelve_tokens():
    long = "Peyton " + "and so on " * 10
    assert h2h.grade_short("Peyton", ["Peyton"]) == 1.0
    assert h2h.grade_short(long, ["Peyton"]) > h2h.grade(long, ["Peyton"])


def test_the_data_check_refuses_a_changed_novel_and_a_changed_passage(tmp_path, monkeypatch):
    table = {"items": [{"id": 1, "novel": "k1", "chars": 3, "phase": "dev"}]}
    monkeypatch.setattr(h2h.pool, "require_pinned", lambda: None)
    monkeypatch.setattr(h2h.pool, "read_frozen", lambda: table)
    novel = tmp_path / "k1.txt"
    novel.write_text("abc", "utf-8")
    monkeypatch.setattr(h2h.pool, "novel_path", lambda key: novel)
    monkeypatch.setattr(h2h.pool, "novel_key", lambda text: "k1" if text == "abc" else "other")
    kept = tmp_path / "1.txt"
    kept.write_text("kept", "utf-8")
    monkeypatch.setattr(h2h.jev_phase, "passages_path", lambda phase, item: kept)
    monkeypatch.setattr(h2h, "OUT", tmp_path)
    (tmp_path / "jev-dev.jsonl").write_text('{"id": 1, "kept_chars": 4}\n', "utf-8")
    assert h2h.data_problems("dev") == []
    (tmp_path / "jev-dev.jsonl").write_text('{"id": 1, "kept_chars": 5}\n', "utf-8")
    assert any("differ" in p for p in h2h.data_problems("dev"))
    novel.write_text("abd", "utf-8")
    assert any("differ from their key" in p for p in h2h.data_problems("dev"))


def test_the_launcher_filled_in_place_is_the_one_change_allowed():
    lot = h2h.claude_lot("dev")
    seal = h2h.jev_phase.sealed_head_problems
    assert seal(lot, _git(status=" M longdoc-free-jev-run.cmd\n")) == []
    assert seal(lot, _git(status=" M longdoc-free-jev-run.cmd\n M src/x.py\n"))


def test_the_stage_spend_is_zero_before_any_session(tmp_path, monkeypatch):
    monkeypatch.setattr(h2h, "PRIVATE", tmp_path)
    assert h2h.stage_spent("dev") == 0.0
