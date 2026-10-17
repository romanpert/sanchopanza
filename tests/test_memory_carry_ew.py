"""The equal-work memory lot on F2's runner (docs/results/2026-10-17-memory-equal-work/prereg.md),
with no paid call: the plan, the caps, the nudge (one resumed turn with a fixed text when the
`task` check fails after session 2, in both arms), its row, its cost, S's hooks on a resumed
session, the night, the seal, the launcher, the sealed reading and what the agent sees."""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from .helpers import bench_module
from .test_memory_carry_handoff import TELLS
from .test_memory_carry_handoff_work import STEP1, STEP2, neutral

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "memory_carry"
night = bench_module(BENCH, "handoff_night")
handoff, hseal, carry = night.handoff, night.handoff_seal, night.carry
carry_s, nudge = handoff.carry_s, handoff.handoff_nudge
ew = bench_module(BENCH, "handoff_ew")
pairs = bench_module(BENCH, "handoff_pairs")
preflight = bench_module(BENCH, "handoff_preflight")

RUN = "ew-sonnet"
NOON = dt.datetime(2026, 10, 17, 12, 0)


# ---- the plan, the roots and the caps ------------------------------------------------------------


def test_the_lot_is_w17_s_sonnet_plan_with_the_nudge() -> None:
    plan = handoff.build_plan(RUN)
    assert plan == [(s, m, a, r) for s, m, a, r in handoff.build_plan("w17-sonnet")]
    assert len(plan) == 96 and {m for _, m, _, _ in plan} == {"sonnet"}
    assert handoff.arms_of(RUN) == ("N0", "S") and handoff.scope_of(RUN) == "user"
    assert [handoff.line_of(RUN, r) for r in (1, 2, 3, 4)] == ["named", "named", "bare", "bare"]
    assert handoff.nudges(RUN) and not handoff.nudges("w17-sonnet") and not handoff.nudges(None)
    assert handoff.LOTS["ew"]["sequence"] == (RUN,) and handoff.lot_of(RUN) == "ew"
    assert nudge.NUDGE == "Yes, go ahead."


def test_the_lot_s_roots_are_new_and_neutral() -> None:
    lot = handoff.LOTS["ew"]
    assert lot["out"] == Path(r"C:\sp-runs\mem-ew") and lot["work"] == Path(r"C:\sp-runs\w20")
    assert lot["gate"] is None and lot["quiet"]
    work = str(lot["work"]).lower()
    words = ("memory", "f2", "handoff", "sonnet", "opus", "w17", "lot", "bare", "ew", "nudge")
    assert not [w for w in words if w in work.replace("sp-runs", "")]
    others = [Path(handoff.LOTS[k][d]) for k in ("f2", "w17") for d in ("out", "work")]
    for path in (lot["out"], lot["work"]):
        assert path not in others and not [o for o in others if o in path.parents]
        assert not [o for o in handoff.W17_INTERRUPTED if o in (path, *path.parents)]


def test_the_run_cap_is_18_usd_and_each_call_reserves_its_cap_and_a_worst_turn() -> None:
    assert handoff.RUNS[RUN]["cap"] == 18.0 == handoff.LOTS["ew"]["night_cap"]
    assert handoff.call_cap(RUN, "sonnet") == 0.25
    assert handoff.WORST_TURN["sonnet"] == pytest.approx(0.44)
    assert handoff.calls_of("N0", RUN) == handoff.calls_of("S", RUN) == 3
    assert handoff.calls_of("N0", "w17-sonnet") == 2 and handoff.calls_of("H") == 3
    assert handoff.reserve_of("sonnet", "N0", RUN) == pytest.approx(3 * (0.25 + 0.44))
    assert handoff.reserve_of("sonnet", "S", RUN) == pytest.approx(3 * (0.25 + 0.44) + 0.15)
    pair = sum(handoff.reserve_of("sonnet", a, RUN) for a in ("N0", "S"))
    assert pair == pytest.approx(4.29)
    assert 18.0 - pair == pytest.approx(13.71)  # no pair starts past this spend
    # W17's and F2's reserves are unchanged
    assert handoff.reserve_of("sonnet", "S", "w17-sonnet") == pytest.approx(2 * 0.94 + 0.1)
    assert handoff.reserve_of("opus", "N0") == pytest.approx(2 * (1.50 + 0.84))
    ok, detail = preflight.caps_check("ew")
    assert ok and "18.0" in detail and "4.29" in detail


def test_no_pair_starts_that_could_pass_the_run_cap(tmp_path: Path) -> None:
    arm, calls = fake_arm([{"cost": 1.0}] * 96)
    got = handoff.run_plan(tmp_path / "lot", RUN, tmp_path / "k", False, 18.0, None,
                           lambda: NOON, lambda s: None, arm, work_root=tmp_path / "w",
                           lifted=lambda: "", restart=lambda: "")  # fmt: skip
    # 1 USD an arm: seven pairs start (12 + 4.29 <= 18), the eighth would not fit (14 + 4.29)
    spent = handoff.ledger(tmp_path / "lot")
    assert got == "cap" and spent + 4.29 > 18.0 and len(calls) % 2 == 0
    assert spent - 2.0 + 4.29 <= 18.0  # the last pair that started did fit


def test_a_nudge_that_reported_no_cost_is_charged_its_cap_and_a_worst_turn() -> None:
    assert handoff.charge_of("sonnet", handoff.call_cap(RUN, "sonnet")) == pytest.approx(0.69)


def test_an_interrupted_arm_s_nudge_is_counted(tmp_path: Path) -> None:
    rec = tmp_path / "rec"
    rec.mkdir()
    for tag in ("session-1", "session-2"):
        (rec / f"{tag}.jsonl").write_text(json.dumps({"type": "result", "total_cost_usd": 0.1}))
    (rec / "nudge.jsonl").write_text(json.dumps({"type": "system", "subtype": "init"}))
    assert handoff.lost_cost(tmp_path / "none", rec, 0.69) == pytest.approx(0.2 + 0.69)


# ---- the nudge against a stand-in claude ---------------------------------------------------------

FAKE_EW = r"""
import json, os, pathlib, sys
prompt, resume, cap = sys.argv[1], sys.argv[2], sys.argv[3]
here = pathlib.Path(__file__).parent
log = pathlib.Path(os.environ["FAKE_LOG"])
calls = json.loads(log.read_text()) if log.exists() else []
log.write_text(json.dumps(calls + [{"prompt": prompt, "resume": resume, "cap": cap}]))
mode = os.environ.get("FAKE_MODE", "asks")
sid = (resume if mode != "other" else "sid-x") if resume else f"sid-{len(calls)}"
size = 40000 if resume else 20000
step1, step2 = (here / "step1.txt").read_text(), (here / "step2.txt").read_text()
code = None
if not resume:
    first = "Step 1" in prompt
    code = step1 if first else (step1 + step2 if mode == "works" else None)
elif mode != "stubborn":
    code = step1 + step2
if code is not None:
    pathlib.Path("app/labels.py").write_text(code)
init = {"type": "system", "subtype": "init", "session_id": sid,
        "model": "claude-sonnet-5-5", "claude_code_version": "2.1.287"}
usage = {"input_tokens": 10, "cache_read_input_tokens": size}
said = {"type": "assistant", "message": {"content": [], "usage": usage}}
# a resumed turn reports the session's running total (session 2's cost plus its own)
own = (10 * 2.0 + 20 * 10.0 + size * 0.2 + 5 * 4.0) / 1e6
total = own + (10 * 2.0 + 20 * 10.0 + 20000 * 0.2 + 5 * 4.0) / 1e6 if resume else own
result = {"type": "result", "subtype": "success", "total_cost_usd": total, "num_turns": 2,
          "result": "Shall I go on with step 2?" if code is None else "done",
          "usage": {**usage, "output_tokens": 20, "cache_creation_input_tokens": 5}}
events = (init, said) if resume and mode == "nocost" else (init, said, result)
for e in events:
    print(json.dumps(e))
"""
OWN_2 = (10 * 2.0 + 20 * 10.0 + 20000 * 0.2 + 5 * 4.0) / 1e6  # 0.00424, a fresh session
OWN_NUDGE = (10 * 2.0 + 20 * 10.0 + 40000 * 0.2 + 5 * 4.0) / 1e6  # 0.00824


def stand_in(tmp_path: Path, monkeypatch: Any, mode: str) -> Path:
    fake = tmp_path / "fake_claude.py"
    fake.write_text(FAKE_EW)
    (tmp_path / "step1.txt").write_text(STEP1)
    (tmp_path / "step2.txt").write_text(STEP2)
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.json"))
    monkeypatch.setenv("FAKE_MODE", mode)
    monkeypatch.setenv(carry.TOKEN, "tok-test-123")
    monkeypatch.setattr(handoff, "command", lambda prompt, model, resume=None, cap=None:
                        [sys.executable, str(fake), prompt, resume or "", str(cap)])  # fmt: skip
    return tmp_path / "calls.json"


def n0_arm(tmp_path: Path, rep: int = 1) -> dict[str, Any]:
    return handoff.arm_run(tmp_path / "lot", tmp_path / "w" / "t00-a", "h_batch", "sonnet",
                           "N0", rep, tmp_path / "k", False, run=RUN)  # fmt: skip


def test_an_arm_that_did_not_do_step_2_gets_one_nudge_and_its_own_cost(
    tmp_path: Path, monkeypatch: Any
) -> None:
    log = stand_in(tmp_path, monkeypatch, "asks")
    got = n0_arm(tmp_path)
    calls = json.loads(log.read_text())
    assert [c["resume"] for c in calls] == ["", "", "sid-1"]
    assert calls[2]["prompt"] == "Yes, go ahead." and {c["cap"] for c in calls} == {"0.25"}
    assert not got.get("cut") and got["nudged"] is True
    assert got["kept_all_s2"] is False and got["checks_s2"]["task_pass"] is False
    assert got["kept_all"] is True and got["task_pass"] is True
    push = got["nudge"]
    assert push["cost_reported_total"] == pytest.approx(OWN_2 + OWN_NUDGE)
    assert push["cost"] == pytest.approx(OWN_NUDGE)
    assert push["cost_source"] == handoff.handoff_cost.RUNNING
    assert push["same_session"] and push["context_carried"] and push["resumed"] == "sid-1"
    assert got["cost"] == pytest.approx(OWN_2 + OWN_2 + OWN_NUDGE)  # never the running total
    assert got["tokens"]["output"] == 60 and len(got["sessions"]) == 2
    assert got["planned"][-1] == "nudge: claude -p --resume <session 2 id> 'Yes, go ahead.'"
    rec = tmp_path / "lot" / "arms" / "t00-a"
    assert (rec / "nudge.jsonl").exists() and not (rec / "handoff.txt").exists()
    assert "handoff" not in got or got["handoff"] == {}


def test_an_arm_that_did_step_2_gets_no_nudge(tmp_path: Path, monkeypatch: Any) -> None:
    log = stand_in(tmp_path, monkeypatch, "works")
    got = n0_arm(tmp_path)
    assert len(json.loads(log.read_text())) == 2
    assert got["nudged"] is False and got["nudge"] == {}
    assert got["kept_all_s2"] is True and got["kept_all"] is True
    assert got["cost"] == pytest.approx(2 * OWN_2)


def test_a_nudge_that_does_not_help_leaves_the_arm_failed(tmp_path: Path, monkeypatch: Any) -> None:
    stand_in(tmp_path, monkeypatch, "stubborn")
    got = n0_arm(tmp_path, rep=3)
    assert got["line"] == "bare" and got["nudged"] and not got.get("cut")
    assert got["kept_all_s2"] is False and got["kept_all"] is False


def test_the_nudge_names_nothing_and_is_not_memory_s_continuation_cue() -> None:
    from sanchopanza.harness.memory_recall import continuation

    assert not continuation(nudge.NUDGE)  # S' gets no record by code for it, as N0 gets none
    for name in handoff.HANDOFF:
        assert not [w for w in TELLS[name] if w in nudge.NUDGE.lower()]


def test_only_a_failed_task_check_calls_for_the_nudge() -> None:
    assert nudge.wanted({"task_pass": False, "kept_all": False})
    assert not nudge.wanted({"task_pass": True, "fact_pass": False, "kept_all": False})
    assert not nudge.wanted({"task_pass": True, "kept_all": True})


def test_a_nudge_into_another_session_cuts_the_arm(tmp_path: Path, monkeypatch: Any) -> None:
    stand_in(tmp_path, monkeypatch, "other")
    got = n0_arm(tmp_path)
    assert got["cut"] == "nudge: the resumed turn is not session 2's session"
    assert "kept_all" not in got


def test_a_nudge_that_reported_no_cost_is_cut_and_charged(tmp_path: Path, monkeypatch: Any) -> None:
    stand_in(tmp_path, monkeypatch, "nocost")
    got = n0_arm(tmp_path)
    assert got["cut"].startswith("nudge: ") and "without a result" in got["cut"]
    assert got["nudge"]["cost_charged"] and got["nudge"]["cost"] == pytest.approx(0.69)
    assert got["cost"] == pytest.approx(2 * OWN_2 + 0.69)


def test_a_session_2_without_an_id_gets_a_cut_nudge_not_an_exception(
    tmp_path: Path, monkeypatch: Any
) -> None:
    stand_in(tmp_path, monkeypatch, "asks")
    real = handoff.one

    def no_id(*args: Any, **kw: Any) -> dict[str, Any]:
        got = real(*args, **kw)
        return {**got, "init": {**got["init"], "session_id": None}} if args[6] == "session-2" \
            else got  # fmt: skip

    monkeypatch.setattr(handoff, "one", no_id)
    got = n0_arm(tmp_path)
    assert got["cut"] == "nudge: the turn ended without a result (the resumed session reported " \
        "no session id)"  # fmt: skip
    assert got["nudge"]["cost_charged"] and got["crossed_midnight"] is False


@pytest.mark.parametrize(("change", "why"), [
    ({"timeout": True}, "nudge: timeout"),
    ({"subtype": ""}, "without a result"),
    ({"init": {"version": "2.1.300", "model": "claude-sonnet-5-5"}}, "ran claude-sonnet-5-5 on"),
    ({"same_session": False}, "not session 2's session"),
    ({"context_carried": False}, "did not carry session 2's context"),
    ({}, ""),
])  # fmt: skip
def test_nudge_cut(change: dict[str, Any], why: str) -> None:
    good = {"returncode": 0, "subtype": "success", "same_session": True, "context_carried": True,
            "init": {"version": carry.PIN, "model": carry.MODELS["sonnet"]}}  # fmt: skip
    turn = {**good, **change}
    got = nudge.cut_of(turn, handoff.pinned(turn, "sonnet"))
    assert (why in got) if why else got == ""


def test_a_nudge_stopped_by_its_own_budget_counts_as_run() -> None:
    turn = {"returncode": 1, "subtype": carry.BUDGET_STOP, "same_session": True,
            "context_carried": True, "init": {"version": carry.PIN,
                                              "model": carry.MODELS["sonnet"]}}  # fmt: skip
    assert nudge.cut_of(turn, True) == ""


def test_s_s_nudge_needs_its_prompt_hook_and_records_the_resume_start(
    tmp_path: Path, monkeypatch: Any
) -> None:
    stand_in(tmp_path, monkeypatch, "asks")
    seen: list[dict[str, Any]] = []

    def breaks(run: Path, result: Any, since: int = 0, server: Any = "x",
               start: bool = True) -> list[str]:  # fmt: skip
        seen.append({"tag": result.get("tag"), "server": server, "start": start})
        if result.get("tag") == "nudge":  # the hooks of a resumed session, as Claude Code logs them
            with (run / "hooks.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"sub": "memory-hook", "event": "SessionStart",
                                    "source": "resume", "exit": 0}) + "\n")  # fmt: skip
        return []

    monkeypatch.setattr(carry_s, "session_breaks", breaks)
    monkeypatch.setattr(carry_s, "pair_breaks", lambda facts: [])
    got = handoff.arm_run(tmp_path / "lot", tmp_path / "w" / "t00-b", "h_batch", "sonnet", "S", 1,
                          tmp_path / "w" / "typesafe.key", False, run=RUN)  # fmt: skip
    assert not got.get("cut") and got["nudged"] and got["kept_all"]
    assert seen == [{"tag": "session-1", "server": None, "start": True},
                    {"tag": "session-2", "server": None, "start": True},
                    {"tag": "nudge", "server": None, "start": False}]  # fmt: skip
    assert got["nudge"]["session_starts"] == ["resume"]


def test_a_nudge_whose_prompt_hook_did_not_answer_is_a_harness_cut(
    tmp_path: Path, monkeypatch: Any
) -> None:
    stand_in(tmp_path, monkeypatch, "asks")
    monkeypatch.setattr(carry_s, "session_breaks", lambda run, result, since=0, server=None,
                        start=True: ["the memory hook answered no prompt"]
                        if result.get("tag") == "nudge" else [])  # fmt: skip
    monkeypatch.setattr(carry_s, "pair_breaks", lambda facts: [])
    got = handoff.arm_run(tmp_path / "lot", tmp_path / "w" / "t00-c", "h_batch", "sonnet", "S", 1,
                          tmp_path / "w" / "typesafe.key", False, run=RUN)  # fmt: skip
    assert got["cut"] == "harness: nudge: the memory hook answered no prompt"


def test_a_resumed_session_s_breaks_skip_only_the_session_start(tmp_path: Path) -> None:
    rows = [{"sub": "memory-hook", "event": "UserPromptSubmit", "exit": 0}]
    (tmp_path / "hooks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    result = {"init": {"mcp": {}, "skill_names": ["sanchopanza-code"]}}
    assert carry_s.session_breaks(tmp_path, result, 0, server=None, start=False) == []
    assert "SessionStart" in carry_s.session_breaks(tmp_path, result, 0, server=None)[0]
    (tmp_path / "hooks.jsonl").write_text("")
    assert carry_s.session_breaks(tmp_path, result, 0, server=None, start=False) == [
        "the memory hook answered no prompt of this session without an error"
    ]
    no_skill = {"init": {"mcp": {}, "skill_names": []}}
    assert "skill" in carry_s.session_breaks(tmp_path, no_skill, 0, server=None, start=False)[-1]


def test_the_installed_memory_hook_answers_a_resumed_session_start(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """S' at user scope: the SessionStart entry matches every source ("" matcher), and the hook
    answers source `resume` as any start (the standing rules), without an error."""
    from sanchopanza.harness import install, memory_hook

    assert install.MEMORY_HOOKS["SessionStart"] == ""
    work = tmp_path / "arm"
    config = work / "claude-config"
    config.mkdir(parents=True)
    carry_s.install_user(work, config, tmp_path / "k", carry.environment())
    settings = json.loads((config / "settings.json").read_text(encoding="utf-8"))
    starts = [e for e in settings["hooks"]["SessionStart"]
              if any("memory-hook" in h.get("command", "") for h in e["hooks"])]  # fmt: skip
    assert [e.get("matcher", "") for e in starts] == [""]
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("SANCHOPANZA_MEMORY_STORE_LOG", str(tmp_path / "hook-log.jsonl"))
    event = {"hook_event_name": "SessionStart", "source": "resume", "session_id": "s2",
             "cwd": str(tmp_path), "transcript_path": str(tmp_path / "t.jsonl")}  # fmt: skip
    got = memory_hook.handle(event)
    assert isinstance(got, dict)
    logged = [json.loads(x) for x in (tmp_path / "hook-log.jsonl").read_text().splitlines()]
    assert {"event": "SessionStart", "source": "resume"}.items() <= logged[-1].items()


# ---- the night, the seal and the launcher --------------------------------------------------------


def fake_arm(results: list[Any]):
    calls: list[tuple[str, str, int, str]] = []

    def arm(out: Path, work: Path, name: str, model: str, arm: str, rep: int, keyfile: Path,
            dry: bool, **_: Any) -> dict[str, Any]:  # fmt: skip
        work.mkdir(parents=True, exist_ok=True)
        calls.append((name, arm, rep, work.name))
        extra = results.pop(0) if results else {}
        return {**pair_row(name, arm, rep), "folder": str(work), **extra}

    return arm, calls


def test_the_lot_runs_whole_resumes_and_keeps_the_quiet_hours(tmp_path: Path) -> None:
    arm, calls = fake_arm([])
    go = lambda clock: handoff.run_plan(tmp_path / "lot", RUN, tmp_path / "k", False, 18.0,  # noqa: E731
                                        None, clock, lambda s: None, arm,
                                        work_root=tmp_path / "w", lifted=lambda: "",
                                        restart=lambda: "")  # fmt: skip
    assert go(lambda: dt.datetime(2026, 10, 18, 1, 55)) == "quiet" and calls == []
    with_cheap = [{"cost": 0.01}] * 96
    arm, calls = fake_arm(with_cheap)
    assert go(lambda: NOON) == "" and len(calls) == 96
    assert handoff.complete(tmp_path / "lot", RUN)


def fake_execute(ran: list[Any]):
    def execute(run: str, out: Path, cap: float, dry: bool = False, night: Path | None = None,
                work_root: Path | None = None) -> str:  # fmt: skip
        ran.append((run, cap, dry))
        return ""

    return execute


def test_the_night_runs_only_this_lot_under_its_18_usd(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setitem(handoff.LOTS["ew"], "work", tmp_path / "work")
    seen: list[str] = []
    monkeypatch.setattr(hseal, "require_sealed_checkout", lambda lot="f2": seen.append(lot))
    ran: list[Any] = []
    monkeypatch.setattr(handoff, "execute", fake_execute(ran))
    monkeypatch.setattr(night, "table", lambda root, run: None)
    assert night.night(tmp_path, lot="ew") == 0
    assert ran == [(RUN, 18.0, False)] and seen == ["ew"]
    assert night.spent_before(tmp_path, RUN, "ew") == 0.0


def test_the_night_s_table_is_the_sealed_reading(tmp_path: Path) -> None:
    out = tmp_path / RUN
    out.mkdir()
    handoff.write_rows(out, lot_rows())
    night.table(tmp_path, RUN)
    got = json.loads((tmp_path / f"{RUN}-table.json").read_text(encoding="utf-8"))
    assert got["reading"] == "equal work (R3)" and got["pairs"] == 48


def test_the_dry_night_builds_every_arm_and_calls_nothing(tmp_path: Path, capsys: Any) -> None:
    assert night.night(tmp_path / "root", dry=True, lot="ew") == 0
    lines = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith("{")]
    assert len(lines) == 96 and lines[-1]["planned"][-1].startswith("nudge: ")
    assert not (tmp_path / "root" / "dry" / RUN / "f2.json").exists()


def test_the_seal_names_this_lot_s_prereg_launcher_modules_and_tests() -> None:
    results, fixed = hseal.LOTS["ew"]
    assert results.name == "2026-10-17-memory-equal-work"
    for rel in ("ew-night-run.cmd", "benchmarks/memory_carry/handoff_nudge.py",
                "benchmarks/memory_carry/handoff_ew.py", "benchmarks/memory_carry/handoff.py",
                "benchmarks/memory_carry/winupdate.py", "tests/test_memory_carry_ew.py",
                "tests/test_memory_carry_w17.py", "tests/test_launchers.py"):  # fmt: skip
        assert rel in fixed, rel
    assert hseal.LOTS["w17"] == (hseal.RESULTS_W17, hseal.SEALED_FIXED_W17)
    assert "handoff_nudge.py" not in " ".join(hseal.SEALED_FIXED_W17)


@pytest.mark.parametrize(("path", "named"), [
    ("C:/x/sanchopanza-e1-ew", True), ("C:/x/sanchopanza-w17-memlot", True),
    ("C:/x/sp-nudge", True), ("C:/x/sp-w20", False),
])  # fmt: skip
def test_the_sealed_checkout_refuses_a_path_that_names_the_lot(path: str, named: bool) -> None:
    assert bool(hseal.path_refusal("ew", Path(path))) is named


def launcher() -> tuple[str, list[str]]:
    text = (ROOT / "ew-night-run.cmd").read_text(encoding="ascii")
    return text, [x for x in text.splitlines() if not x.lstrip().lower().startswith("rem")]


def test_the_launcher_runs_only_this_lot_from_its_own_root() -> None:
    text, body = launcher()
    sets = {x.split("=", 1)[0][4:]: x.split("=", 1)[1] for x in body if x.startswith("set ")}
    assert sets["ROOT"] == r"C:\sp-runs\mem-ew" and sets["LOT"] == "--lot ew"
    runs = [x for x in body if "handoff_night.py" in x]
    assert len(runs) == 2 and all("%LOT%" in x and "--only" not in x for x in runs)
    assert [x for x in runs if "--dry" in x] and 'if /i not "%~1"=="run"' in text
    assert r'call "%ROOT%\keys-env.cmd"' in text and r'call "%ROOT%\python-env.cmd"' in text
    assert r"claude-pin\2.1.287" in text and "set DISABLE_AUTOUPDATER=1" in body
    words = re.search(r'findstr /i "([^"]+)"', text)
    assert words and set(words.group(1).split()) == set(hseal.PATH_WORDS["ew"])


# ---- the sealed reading --------------------------------------------------------------------------


def pair_row(scene: str, arm: str, rep: int, **over: Any) -> dict[str, Any]:
    """An arm that ran: S' kept all after session 2; N0 did not and its nudge did it."""
    s = arm == "S"
    base = {"scene": scene, "model": "sonnet", "arm": arm, "repeat": rep, "tests_pass": True,
            "task_pass": True, "fact_pass": True, "decision_pass": True, "intact_pass": True,
            "kept_all": True, "kept_all_s2": s, "nudged": not s,
            "checks_s2": {"tests_pass": True, "task_pass": s, "fact_pass": s,
                          "decision_pass": s, "intact_pass": True, "kept_all": s},
            "nudge": {} if s else {"cost": 0.04}, "cost": 0.10 if s else 0.12,
            "jev_usd": 0.0002 if s else 0.0, "line": handoff.line_of(RUN, rep),
            "sessions": [{"tag": "session-1", "cost": 0.05},
                         {"tag": "session-2", "cost": 0.05 if s else 0.03}],
            "tokens": {"input": 1, "output": 2, "cache_read": 3, "cache_write": 4}}  # fmt: skip
    return {**base, **over}


def lot_rows(s: dict[str, Any] | None = None, n0: dict[str, Any] | None = None,
             each: Any = None) -> list[dict[str, Any]]:  # fmt: skip
    out = []
    for i, (sc, _, a, r) in enumerate(handoff.build_plan(RUN)):
        row = pair_row(sc, a, r, **((s or {}) if a == "S" else (n0 or {})))
        out.append(each(i // 2, row) if each else row)
    return out


def test_equal_work_wins_on_cost_when_the_nudged_n0_costs_more() -> None:
    got = ew.analyse(lot_rows())
    assert got["pairs"] == 48 and got["verdict"] == "gana (coste)"
    assert got["cost_ratio"]["median"] == pytest.approx((0.1002) / 0.12)
    assert got["cost_ratio"]["seed"] == ew.SEED == 20261021 and got["cost_ratio"]["draws"] == 10_000
    assert got["headroom"] == {"n0_fails_s2": 48, "pairs": 48, "room": True}
    assert got["nudges"]["N0"] == {"nudged": 48, "kept_after": 48, "rate": 1.0}
    assert got["nudges"]["S"] == {"nudged": 0, "kept_after": 0, "rate": 0.0}
    assert got["strata"]["bare"]["pairs"] == 24 and got["strata"]["named"]["pairs"] == 24


def test_the_w17_reading_without_the_nudge_is_a_sealed_secondary() -> None:
    got = ew.analyse(lot_rows())["w17_reading"]
    assert got["S_vs_N0"]["a_only"] == 48 and got["criteria"]["s1_better"]
    assert got["cost_ratio"]["median"] == pytest.approx(0.1002 / 0.08)  # sessions 1-2 only
    assert got["verdict"] == "S' better than N0; no gana (cost)"


def test_no_room_is_measured_before_the_nudge() -> None:
    kept = {"kept_all_s2": True, "nudged": False, "nudge": {}, "cost": 0.08,
            "checks_s2": {"tests_pass": True, "task_pass": True, "kept_all": True}}  # fmt: skip
    rows = lot_rows(n0=kept)
    assert ew.analyse(rows)["verdict"] == "sin margen"
    # two pairs of 48 where N0 failed before its nudge: 2 < 0.05 x 48 = 2.4, still no room
    two = lot_rows(each=lambda k, r: {**r, **kept} if r["arm"] == "N0" and k >= 2 else r)
    assert ew.analyse(two)["headroom"]["n0_fails_s2"] == 2 and ew.analyse(two)["verdict"] == (
        "sin margen"
    )
    three = lot_rows(each=lambda k, r: {**r, **kept} if r["arm"] == "N0" and k >= 3 else r)
    assert ew.analyse(three)["verdict"] != "sin margen"


def test_success_wins_when_the_nudge_does_not_recover_n0() -> None:
    stuck = {"kept_all": False, "task_pass": False, "cost": 0.10}
    got = ew.analyse(lot_rows(s={"cost": 0.104}, n0=stuck))
    assert got["criteria"]["better"] and got["criteria"]["cost_within_bound"]
    assert not got["criteria"]["cost_below_1"] and got["verdict"] == "gana (éxito)"
    dear = ew.analyse(lot_rows(s={"cost": 0.13}, n0=stuck))
    assert dear["verdict"] == "no gana"


def test_harm_or_a_worse_success_blocks_the_cost_win() -> None:
    harmed = ew.analyse(lot_rows(s={"tests_pass": False}))
    assert not harmed["criteria"]["no_harm"] and harmed["verdict"] == "no gana"
    worse = ew.analyse(lot_rows(s={"kept_all": False}))
    assert not worse["criteria"]["tango_not_worse"] and worse["verdict"] == "no gana"


def test_too_few_pairs_is_no_verdict_and_cut_pairs_are_left_out() -> None:
    rows = lot_rows()
    cut = [{**r, "cut": "nudge: timeout"} if r["arm"] == "N0" and i < 18 else r
           for i, r in enumerate(rows)]  # fmt: skip
    got = ew.analyse(cut)
    assert got["pairs"] == 39 and got["verdict"] == "sin veredicto"
    assert got["not_run_reasons"] == {"nudge": 9}


def test_the_ratio_is_the_arm_s_whole_cost_resampled_in_pair_order() -> None:
    rows = lot_rows(
        each=lambda k, r: {**r, "cost": r["cost"] + 0.001 * k} if r["arm"] == "S" else r
    )
    a, b = ew.analyse(rows), ew.analyse(rows[::-1])
    assert a["cost_ratio"] == b["cost_ratio"]
    assert not math.isinf(a["cost_ratio"]["ci95_raw"][1])


def test_the_nudge_s_tool_calls_are_reported_with_the_sessions() -> None:
    push = {"tag": "nudge", "cost": 0.04, "touched": ["store"], "cost_source": "x",
            "session_starts": []}  # fmt: skip
    got = ew.analyse(lot_rows(n0={"nudge": push}))
    assert got["touched"] == {"N0 nudge": {"store": 48}}
    assert got["nudge_report"]["N0"]["cost_median_usd"] == pytest.approx(0.04)
    assert got["nudge_report"]["N0"]["cost_sources"] == {"x": 48}


def test_the_analysis_refuses_a_folder_that_is_not_this_lot_s(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        ew.main([str(tmp_path / "w17-sonnet")])


# ---- what the agent sees -------------------------------------------------------------------------

LOT_WORDS = ("handoff", "f2", "w17", "memlot", "sonnet", "opus", "bare", "ew-", "mem-ew", "nudge",
             "equal", "go ahead")  # fmt: skip
ARM_TOKEN = re.compile(r"(?<![A-Za-z0-9])(N0|S|S')(?![A-Za-z0-9])")


@pytest.mark.parametrize("name", sorted(handoff.HANDOFF))
def test_nothing_the_agent_sees_names_the_scene_the_arm_the_stratum_or_the_lot(
    name: str, tmp_path: Path
) -> None:
    work_root = tmp_path / "r1"
    for t, (arm, rep) in enumerate((("N0", 1), ("S", 1), ("N0", 3), ("S", 3))):
        work = work_root / handoff.folder_name(RUN, t, arm)
        handoff.arm_run(tmp_path / "lot", work, name, "sonnet", arm, rep,
                        work_root / "typesafe.key", True, run=RUN)  # fmt: skip
    words = [*handoff.HANDOFF, *LOT_WORDS]
    installed = ("/claude-config/settings.json", "/claude-config/skills/sanchopanza-code/")
    for path in work_root.rglob("*"):
        if ".git" in path.relative_to(work_root).parts:
            continue
        rel = neutral(path.relative_to(work_root).as_posix(), tmp_path)
        assert not [w for w in words if w in rel.lower()], rel
        assert not [w for w in TELLS[name] if w in rel.lower()], rel
        assert not ARM_TOKEN.search(rel.replace("/", " ")), rel
        if path.is_file():
            text = neutral(path.read_text(encoding="utf-8", errors="replace"), tmp_path).lower()
            assert not [w for w in words if w in text], rel
            if not any(part in f"/{rel}" for part in installed):
                assert not [w for w in TELLS[name] if w in text], rel
