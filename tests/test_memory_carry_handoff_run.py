"""F2's runner, analysis, gate and night (`benchmarks/memory_carry/handoff*.py`), with no paid
call: Tango's interval against his published examples, the plan and its caps, the handoff's NOT
RUN rules, the gate, the verdicts, the stops (limit, STOP, interrupted, exception, broken,
midnight), the seal and the sealed checkout. The agent's view and a whole arm against a
stand-in claude are in `test_memory_carry_handoff_work.py`."""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "memory_carry"
night = bench_module(BENCH, "handoff_night")
handoff, an, hseal = night.handoff, night.handoff_analyze, night.handoff_seal
hc, carry = handoff.hc, handoff.carry

Z95 = 1.959963984540054


# ---- Tango and McNemar -------------------------------------------------------------------------


def test_tango_matches_the_marijuana_example_of_tango_1998() -> None:
    # Tango (1998), Statistics in Medicine 17:891-908, section 6.2: n = 32, b = 9, c = 3; "the
    # proposed score-based confidence interval is -0.027 to 0.390".
    assert round(an.tango_bound(9, 3, 32, Z95), 3) == -0.027
    assert round(an.tango_bound(9, 3, 32, Z95, lower=False), 3) == 0.390


def test_tango_matches_the_contact_lens_example_of_tango_1998() -> None:
    # Section 6.1: n = 44, b = 0, c = 1; Z = 1.709 at Delta = 0.1 and the 90 % lower limit -0.096.
    assert round(an.tango_score(0, 1, 44, -0.1), 3) == 1.709
    assert round(an.tango_bound(0, 1, 44, an.Z_ONE_SIDED_95), 3) == -0.096


def test_tango_with_no_discordant_triple_and_mcnemar() -> None:
    low = an.tango_bound(0, 0, 48, an.Z_ONE_SIDED_95)
    assert -0.07 < low < 0
    assert an.mcnemar(5, 0) == pytest.approx(1 / 32)
    assert an.mcnemar(0, 0) == 1.0


# ---- the plan, its folders and its caps --------------------------------------------------------


def test_plans_rotate_the_arms_and_hold_the_owner_s_runs() -> None:
    pilot, sonnet, opus = (handoff.build_plan(r) for r in ("f2-pilot", "f2-sonnet", "f2-opus"))
    assert len(pilot) == 12 and len(sonnet) == 144 and len(opus) == 72
    assert {r for _, _, _, r in pilot} == {0} and {r for _, _, _, r in sonnet} == {1, 2, 3, 4}
    firsts = [sonnet[i][2] for i in range(0, len(sonnet), 3)]
    assert {a: firsts.count(a) for a in handoff.ARMS} == {"N0": 16, "H": 16, "S": 16}
    for i in range(0, len(sonnet), 3):
        assert sorted(a for _, _, a, _ in sonnet[i : i + 3]) == ["H", "N0", "S"]
        assert len({(s, r) for s, _, _, r in sonnet[i : i + 3]}) == 1
    assert {m for _, m, _, _ in opus} == {"opus"}
    assert [handoff.RUNS[r]["cap"] for r in night.SEQUENCE] == [11.5, 109.0, 106.0]
    assert handoff.NIGHT_CAP == 230.0 and sum(handoff.RUNS[r]["cap"] for r in night.SEQUENCE) <= 230
    assert handoff.CALL_CAPS == {"sonnet": 0.80, "opus": 1.50}


def test_folder_names_are_opaque_and_the_letter_says_nothing_of_the_arm() -> None:
    names = {(t, a): handoff.folder_name("f2-sonnet", t, a) for t in range(48)
             for a in handoff.ARMS}  # fmt: skip
    assert all(re.fullmatch(r"t\d\d-[abc]", n) for n in names.values())
    for t in range(48):
        assert len({names[(t, a)] for a in handoff.ARMS}) == 3
    for arm in handoff.ARMS:
        assert {names[(t, arm)][-1] for t in range(48)} == {"a", "b", "c"}
    assert handoff.folder_name("f2-sonnet", 7, "H") == handoff.folder_name("f2-sonnet", 7, "H")
    work = str(handoff.WORK).lower()
    assert not [w for w in ("memory", "f2", "handoff", "sonnet", "opus") if w in work]
    assert {handoff.RUNS[r]["dir"] for r in night.SEQUENCE} == {"r1", "r2", "r3"}


def test_one_worst_turn_per_call_from_claude_code_s_rates() -> None:
    assert handoff.WORST_TURN["sonnet"] == pytest.approx(0.44)
    assert handoff.WORST_TURN["opus"] == pytest.approx(0.84)
    assert handoff.reserve_of("sonnet", "H") == pytest.approx(3 * (0.80 + 0.44))
    assert handoff.reserve_of("sonnet", "N0") == pytest.approx(2 * (0.80 + 0.44))
    assert handoff.reserve_of("opus", "S") == pytest.approx(2 * (1.50 + 0.84) + 0.10)
    for run in night.SEQUENCE:  # every run's cap holds at least one triple's reserve
        spec = handoff.RUNS[run]
        assert spec["cap"] > sum(handoff.reserve_of(spec["model"], a) for a in handoff.ARMS)


def test_command_resumes_with_the_owner_s_wording_under_the_same_cap() -> None:
    cmd = handoff.command(handoff.HANDOFF_REQUEST, "sonnet", resume="abc")
    assert handoff.HANDOFF_REQUEST == "Give me a prompt to continue this work in a clean session."
    assert cmd[:5] == ["claude", "-p", handoff.HANDOFF_REQUEST, "--resume", "abc"]
    assert cmd[cmd.index("--max-budget-usd") + 1] == "0.80" and "--settings" in cmd
    assert "--resume" not in handoff.command("x", "opus")
    dash = handoff.command("- step 2: ship_all", "sonnet")
    assert dash[-2:] == ["--", "- step 2: ship_all"] and dash[:2] == ["claude", "-p"]
    assert dash.count("- step 2: ship_all") == 1 and "x" not in dash


# ---- the handoff's NOT RUN rules ---------------------------------------------------------------

PIN_INIT = {"version": carry.PIN, "model": carry.MODELS["sonnet"]}
GOOD = {"returncode": 0, "subtype": "success", "text": "Continue with step 2...", "cost": 0.02,
        "cost_reported": True, "context_carried": True, "init": PIN_INIT}  # fmt: skip


@pytest.mark.parametrize(("change", "why"), [
    ({}, ""),
    ({"returncode": 1, "subtype": ""}, "handoff: exit 1"),
    ({"text": "  "}, "handoff: no text"),
    ({"cost_reported": False}, "handoff: no cost reported"),
    ({"cost": 0.0}, "handoff: no cost reported"),
    ({"context_carried": False}, "handoff: the resumed turn did not carry"),
    ({"context_carried": None}, ""),
    ({"text": "x" * 32_700}, "handoff: session 2's command line"),
    ({"timeout": True}, "handoff: timeout"),
    ({"init": {**PIN_INIT, "version": "2.1.300"}}, "handoff: ran"),
    ({"init": {**PIN_INIT, "model": "claude-opus-5-5"}}, "handoff: ran"),
])  # fmt: skip
def test_handoff_cut(change: dict[str, Any], why: str) -> None:
    got = handoff.handoff_cut({**GOOD, **change}, "sonnet")
    assert got.startswith(why) and bool(got) == bool(why)


def test_context_carried_needs_half_of_session_1_s_context() -> None:
    assert handoff.carried({"last_prompt": 30000}, {"first_prompt": 31000}) is True
    assert handoff.carried({"last_prompt": 30000}, {"first_prompt": 16000}) is True
    assert handoff.carried({"last_prompt": 30000}, {"first_prompt": 14000}) is False
    assert handoff.carried({"last_prompt": None}, {"first_prompt": 18000}) is None


def test_the_weekly_limit_is_read_from_a_short_or_error_result_too() -> None:
    assert hc.limit_text({"text": "You've hit your limit · resets 3am"}, "")
    assert hc.limit_text({"text": "x" * 900 + " weekly limit", "is_error": True}, "")
    assert not hc.limit_text({"text": "x" * 900 + " no usage limit here"}, "")
    assert hc.limit_text({"text": "done"}, "Claude AI usage limit reached")
    assert not hc.limit_text({"text": "Added fetch_all with limit=100."}, "")


def test_checks_run_without_the_keys_path_or_pythonpath(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("SANCHOPANZA_KEYS_ENV", "C:/somewhere/.env")
    monkeypatch.setenv("PYTHONPATH", "C:/somewhere/src")
    code = ("import os, sys; sys.exit(int(any(k in os.environ for k in "
            "('SANCHOPANZA_KEYS_ENV', 'PYTHONPATH', 'TYPESAFE_API_KEY'))))")  # fmt: skip
    assert handoff.passes(tmp_path, code)


def test_decoys_never_touch_the_scene() -> None:
    for name, scene in handoff.HANDOFF.items():
        got = handoff.decoys(name)
        assert len(got) == carry.DECOYS == len(set(got))
        assert not {carry.DECOY_POOL[k] for k in scene["near"]} & set(got)


# ---- the gate ----------------------------------------------------------------------------------


def row(scene: str, arm: str, rep: int = 0, **over: Any) -> dict[str, Any]:
    base = {"scene": scene, "model": "sonnet", "arm": arm, "repeat": rep, "tests_pass": True,
            "task_pass": True, "fact_pass": True, "decision_pass": True, "intact_pass": True,
            "kept_all": arm != "N0", "cost": 0.3, "jev_usd": 0.001 if arm == "S" else 0.0,
            "sessions": [{"cost": 0.1}], "tokens": {"input": 1, "output": 2, "cache_read": 3,
                                                    "cache_write": 4}}  # fmt: skip
    if arm == "H":
        base["handoff"] = {"chars": 900, "cost_reported": True, "cost": 0.03,
                           "context_carried": True, "names": {"C": True, "D": True},
                           "tokens": {"output": 300}}  # fmt: skip
        base["pasted_verbatim"] = True
    if arm == "S":
        base["hook_starts"] = 2
    return {**base, **over}


def pilot_rows(**per: dict[str, Any]) -> list[dict[str, Any]]:
    plan = handoff.build_plan("f2-pilot")
    return [row(s, a, r, **per.get(f"{s}:{a}", {})) for s, _, a, r in plan]


def test_gate_passes_when_all_five_hold() -> None:
    result = an.gate(pilot_rows(), handoff.build_plan("f2-pilot"))
    assert result["pass"] and result["reasons"] == []
    assert "PASS" in an.gate_text(result) and "(e) holds" in an.gate_text(result)


HAND = {"chars": 500, "cost_reported": True, "context_carried": True}


@pytest.mark.parametrize(("per", "letter"), [
    ({"h_batch:H": {"cut": "handoff: no text", "handoff": {"chars": 0}}}, "a"),
    ({"h_weeks:H": {"handoff": {**HAND, "cost_reported": False}}}, "a"),
    ({"h_weeks:H": {"handoff": {**HAND, "context_carried": None}}}, "a"),
    ({"h_spanish:H": {"pasted_verbatim": False}}, "a"),
    ({"h_spanish:H": {"pasted_verbatim": None}}, "a"),
    ({"h_spanish:S": {"fact_pass": None}}, "b"),
    ({"h_spanish:N0": {"cut": "timeout"}}, "b"),
    ({"h_weeks:N0": {"task_pass": False}, "h_weeks:H": {"task_pass": False},
      "h_weeks:S": {"task_pass": False}}, "c"),
    ({"h_nomutate:S": {"hook_starts": 1}}, "e"),
])  # fmt: skip
def test_gate_fails_on_each_condition(per: dict[str, Any], letter: str) -> None:
    result = an.gate(pilot_rows(**per), handoff.build_plan("f2-pilot"))
    assert not result["pass"] and not result[letter]


def test_gate_fails_when_n0_keeps_everything_or_an_arm_is_missing() -> None:
    plan = handoff.build_plan("f2-pilot")
    kept = an.gate(pilot_rows(**{f"{s}:N0": {"kept_all": True} for s in handoff.HANDOFF_PILOT}),
                   plan)  # fmt: skip
    assert not kept["pass"] and not kept["d"]
    short = an.gate(pilot_rows()[:-1], plan)
    assert not short["pass"] and "without a row" in short["reasons"][0]


# ---- analysis and verdicts ---------------------------------------------------------------------


def sonnet_rows(**change: Any) -> list[dict[str, Any]]:
    return [row(s, a, r, **(change if a == "S" else {}))
            for s, _, a, r in handoff.build_plan("f2-sonnet")]  # fmt: skip


def test_analyse_reads_the_criteria_in_sequence() -> None:
    rows = sonnet_rows()
    result = an.analyse(rows, "sonnet")
    assert result["triples"] == 48 and result["S_vs_H"]["a_only"] == 0
    assert result["criteria"]["1_s_not_worse_than_h"] and result["criteria"]["2_s_better_than_n0"]
    assert result["verdict"] == "S not worse than H; S better than N0"
    assert result["S_vs_H"]["tango_lower_95_raw"] > -an.MARGIN
    worse = [r if r["arm"] != "S" or r["repeat"] > 2 else {**r, "kept_all": False} for r in rows]
    got = an.analyse(worse, "sonnet")
    assert not got["criteria"]["1_s_not_worse_than_h"]
    assert got["criteria"]["2_s_better_than_n0"] is None and got["verdict"] == "not shown"
    assert an.analyse(rows[:30], "sonnet")["verdict"] == "sin veredicto"
    assert result["handoff_names"]["both"] == 48 and result["cost_ratio_median"]["S/H"] > 1


def test_no_harm_is_needed_for_either_claim() -> None:
    harmed = an.analyse(sonnet_rows(tests_pass=False), "sonnet")
    assert harmed["criteria"]["1_s_not_worse_than_h"] and not harmed["criteria"]["5a_tests"]
    assert harmed["verdict"] == "not shown"
    assert an.verdict_of("opus", True, True, True, True) == (
        "direction only: S not worse than H; S better than N0"
    )
    assert an.verdict_of("opus", True, True, True, False) == "direction only: not shown"
    assert an.verdict_of("sonnet", True, True, False, True) == "S not worse than H"
    assert an.verdict_of("sonnet", True, False, True, True) == "not shown"


# ---- the run's stops ---------------------------------------------------------------------------


def fake_arm(results: list[Any]):
    calls: list[tuple[str, str, int, str]] = []

    def arm(out: Path, work: Path, name: str, model: str, arm: str, rep: int, keyfile: Path,
            dry: bool) -> dict[str, Any]:  # fmt: skip
        work.mkdir(parents=True, exist_ok=True)
        calls.append((name, arm, rep, work.name))
        extra = results.pop(0) if results else {}
        if isinstance(extra, Exception):
            raise extra
        return {**row(name, arm, rep), "folder": str(work), **extra}

    return arm, calls


NOON = dt.datetime(2026, 10, 15, 12, 0)


def go(out: Path, arm_fn: Any, cap: float = 100.0, clock: Any = lambda: NOON,
       sleep: Any = lambda s: None) -> str:  # fmt: skip
    return handoff.run_plan(out / "lot", "f2-pilot", out / "k", False, cap, None, clock, sleep,
                            arm_fn, work_root=out / "w")  # fmt: skip


def test_the_run_ends_writes_rows_atomically_and_resumes_for_free(tmp_path: Path) -> None:
    arm, calls = fake_arm([])
    assert go(tmp_path, arm) == ""
    lot = tmp_path / "lot"
    assert len(handoff.rows_of(lot)) == 12 and handoff.complete(lot, "f2-pilot")
    assert not (lot / "f2.json.tmp").exists()
    assert handoff.ledger(lot) == pytest.approx(12 * 0.3 + 4 * 0.001)
    assert {c[3] for c in calls} == {p.name for p in (tmp_path / "w").iterdir()}
    again, more = fake_arm([])
    assert go(tmp_path, again) == "" and more == []


def test_the_cap_stops_before_an_arm(tmp_path: Path) -> None:
    arm, calls = fake_arm([{"cost": 3.0}] * 12)
    assert go(tmp_path, arm, cap=11.5) == "cap"
    assert len(calls) == 3 and handoff.ledger(tmp_path / "lot") == pytest.approx(9.001)


def test_a_usage_limit_pauses_without_a_row(tmp_path: Path) -> None:
    arm, calls = fake_arm([{}, {"limit_hit": True, "cut": "usage limit"}])
    assert go(tmp_path, arm) == "limit"
    assert (tmp_path / "lot" / "LIMIT.flag").exists() and len(
        handoff.rows_of(tmp_path / "lot")
    ) == 1
    assert list((tmp_path / "w").glob(f"{calls[1][3]}.limit-*"))


def test_an_exception_in_an_arm_is_not_run_and_the_night_goes_on(tmp_path: Path) -> None:
    arm, calls = fake_arm([RuntimeError("boom")])
    assert go(tmp_path, arm) == ""
    rows = handoff.rows_of(tmp_path / "lot")
    cut = [r for r in rows if r.get("cut")]
    assert len(rows) == 12 and len(cut) == 1
    assert cut[0]["cut"] == "harness exception: RuntimeError"


def test_stop_file_and_interrupted_arms_are_set_aside(tmp_path: Path) -> None:
    lot = tmp_path / "lot"
    lot.mkdir()
    (lot / "STOP").write_text("")
    arm, calls = fake_arm([])
    assert go(tmp_path, arm) == "manual" and calls == []
    (lot / "STOP").unlink()
    first = handoff.build_plan("f2-pilot")[0]
    name = handoff.folder_name("f2-pilot", 0, first[2])
    (tmp_path / "w" / name).mkdir(parents=True)
    (lot / "arms" / name).mkdir(parents=True)
    (lot / "arms" / name / "session-1.jsonl").write_text(
        json.dumps({"type": "result", "total_cost_usd": 0.25}) + "\n"
    )
    assert go(tmp_path, arm) == ""
    assert handoff.ledger(lot) == pytest.approx(0.25 + 12 * 0.3 + 4 * 0.001)
    assert json.loads((lot / "interrupts.json").read_text()) == {name: 1}
    assert list((tmp_path / "w").glob(f"{name}.interrupted-*"))
    assert list((lot / "arms").glob(f"{name}.interrupted-*"))


def test_an_arm_interrupted_too_often_is_not_run(tmp_path: Path) -> None:
    first = handoff.build_plan("f2-pilot")[0]
    name = handoff.folder_name("f2-pilot", 0, first[2])
    (tmp_path / "lot").mkdir()
    (tmp_path / "lot" / "interrupts.json").write_text(json.dumps({name: handoff.INTERRUPTS}))
    (tmp_path / "w" / name).mkdir(parents=True)
    arm, calls = fake_arm([])
    assert go(tmp_path, arm) == ""
    cut = [r for r in handoff.rows_of(tmp_path / "lot") if r.get("cut")]
    assert len(cut) == 1 and cut[0]["cut"].startswith("interrupted")


def test_arms_without_a_result_in_a_row_stop_the_run(tmp_path: Path) -> None:
    arm, calls = fake_arm([{"cut": "session-1 ended without a result (exit 1)"}] * 3)
    assert go(tmp_path, arm) == "broken" and len(calls) == 3


def test_s_not_running_as_s_stops_the_run(tmp_path: Path) -> None:
    arm, calls = fake_arm([{"cut": "harness: session-1: MCP server sanchopanza: failed"}])
    assert go(tmp_path, arm) == "harness" and len(calls) == 1


def test_the_midnight_rule_waits_for_the_next_day(tmp_path: Path) -> None:
    times = iter([dt.datetime(2026, 10, 15, 23, 50)] * 3 + [dt.datetime(2026, 10, 16, 0, 1)] * 99)
    slept: list[float] = []
    arm, calls = fake_arm([])
    assert go(tmp_path, arm, clock=lambda: next(times), sleep=slept.append) == ""
    assert slept and len(calls) == 12


# ---- the seal and the sealed checkout ----------------------------------------------------------


def fake_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo, results = tmp_path / "repo", tmp_path / "repo" / "docs" / "results" / "x"
    for rel in (*hseal.SEALED_FIXED, "src/sanchopanza/a.py", "src/sanchopanza/h/skill.md"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(f"# {rel}\n")
    results.mkdir(parents=True)
    (results / "prereg.md").write_text("prereg\r\n")
    return repo, results


def test_seal_covers_every_src_file_and_pyproject_and_is_written_once(tmp_path: Path) -> None:
    repo, results = fake_repo(tmp_path)
    assert not hseal.seal_ok(repo, results)
    value = hseal.seal(repo, results)
    assert hseal.seal_ok(repo, results) and hseal.seal(repo, results) == value
    sealed = json.loads((results / "prereg.manifest.json").read_text())
    assert {"src/sanchopanza/a.py", "src/sanchopanza/h/skill.md", "pyproject.toml",
            "benchmarks/meter.py"} <= set(sealed)  # fmt: skip
    (repo / "src/sanchopanza/h/skill.md").write_text("# changed\n")
    assert not hseal.seal_ok(repo, results)
    with pytest.raises(SystemExit):
        hseal.seal(repo, results)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.org",
                    *args], check=True, capture_output=True)  # fmt: skip


def test_the_checkout_must_be_the_sealing_commit_and_clean(tmp_path: Path) -> None:
    repo, results = fake_repo(tmp_path)
    git(repo, "init", "-q")
    hseal.seal(repo, results)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "seal")
    assert hseal.checkout_refusal(repo, results) == ""
    (repo / "notes.txt").write_text("x")
    assert "not clean" in hseal.checkout_refusal(repo, results)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "later")
    assert "not the sealing commit" in hseal.checkout_refusal(repo, results)


def test_the_live_night_refuses_without_the_seal(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(hseal, "seal_ok", lambda *a: False)
    with pytest.raises(SystemExit) as stop:
        night.night(tmp_path)
    assert stop.value.code == hseal.SEALED_CHECKOUT_REFUSED


def fake_execute(ran: list[Any]):
    def execute(run: str, out: Path, cap: float, dry: bool = False, night: Path | None = None,
                work_root: Path | None = None) -> str:  # fmt: skip
        ran.append((run, cap))
        return ""

    return execute


def test_the_night_stops_at_a_failed_gate(tmp_path: Path, monkeypatch: Any) -> None:
    ran: list[Any] = []
    monkeypatch.setattr(hseal, "require_sealed_checkout", lambda: None)
    monkeypatch.setattr(handoff, "execute", fake_execute(ran))
    (tmp_path / "f2-pilot").mkdir()
    (tmp_path / "f2-pilot" / "f2.json").write_text(
        json.dumps(pilot_rows(**{f"{s}:N0": {"kept_all": True} for s in handoff.HANDOFF_PILOT}))
    )
    assert night.night(tmp_path) == night.GATE_FAIL and [r for r, _ in ran] == ["f2-pilot"]
    assert "FAIL" in (tmp_path / "gate.md").read_text()
    assert not (tmp_path / "night.lock").exists()


def test_the_night_runs_the_sequence_after_a_passing_gate(tmp_path: Path,
                                                          monkeypatch: Any) -> None:  # fmt: skip
    ran: list[Any] = []
    monkeypatch.setattr(hseal, "require_sealed_checkout", lambda: None)
    monkeypatch.setattr(handoff, "execute", fake_execute(ran))
    (tmp_path / "f2-pilot").mkdir()
    (tmp_path / "f2-pilot" / "f2.json").write_text(json.dumps(pilot_rows()))
    handoff.book(tmp_path / "f2-pilot", "arm", 7.0, "x")
    handoff.book(tmp_path / "f2-sonnet", "arm", 120.0, "y")
    assert night.night(tmp_path) == 0
    assert ran == [("f2-pilot", 11.5), ("f2-sonnet", 109.0), ("f2-opus", 103.0)]


def test_the_night_refuses_at_a_limit_flag_in_the_root(tmp_path: Path, monkeypatch: Any) -> None:
    ran: list[Any] = []
    monkeypatch.setattr(hseal, "require_sealed_checkout", lambda: None)
    monkeypatch.setattr(handoff, "execute", fake_execute(ran))
    (tmp_path / "LIMIT.flag").write_text("x")
    assert night.night(tmp_path) == handoff.EXIT["limit"] and ran == []


# ---- harness files the agent touched (reported) ------------------------------------------------


@pytest.mark.parametrize(("text", "want"), [
    ("cat ../store/c--x/rules.json", {"store"}),
    (r"C:\sp-runs\w16\r2\t00-a\claude-config\projects", {"claude-config"}),
    (r"Get-Content ..\store\x\rules.json", {"store"}),
    ("Read .claude/settings.json", {".claude"}),
    (r"type ..\repo\.mcp.json", {".mcp.json"}),
    (r"Get-Content C:\w\t00-a\repo\.claude\settings.json", {".claude"}),
    ("python benchmarks/memory_carry/carry_hook.py", {"carry_hook"}),
    ("app/datastore.py restore.py my.claudette store_front.py", set()),
])  # fmt: skip
def test_touches_names_harness_files_only(text: str, want: set[str]) -> None:
    assert hc.touches([json.dumps({"command": text})]) == want


def test_stream_records_which_harness_files_a_session_touched(tmp_path: Path) -> None:
    use = {"type": "tool_use", "name": "Bash", "input": {"command": "ls ../store"}}
    event = {"type": "assistant", "message": {"content": [use], "usage": {}}}
    (tmp_path / "s.jsonl").write_text(json.dumps(event) + chr(10))
    assert hc.stream_extra(tmp_path / "s.jsonl")["touched"] == ["store"]


def test_touched_is_reported_and_criteria_again_without_those_triples() -> None:
    peek = {"sessions": [{"tag": "session-1"}, {"tag": "session-2", "touched": ["store"]}]}
    rows = [r if not (r["arm"] == "S" and r["repeat"] == 1) else {**r, **peek}
            for r in sonnet_rows()]  # fmt: skip
    rows += [
        {
            **row("h_batch", "H", 9),
            "model": "sonnet",
            "cut": "handoff: session 2's first prompt differs from handoff.txt",
        }
    ]
    result = an.analyse(rows, "sonnet")
    assert result["touched"] == {"S session-2": {"store": 12}}
    again = result["without_s2_touched"]
    assert again["triples"] == 36 and len(again["dropped"]) == 12
    assert again["1_s_not_worse_than_h"] and again["2_s_better_than_n0"]
    assert result["not_run_reasons"] == {
        "handoff: session 2's first prompt differs from handoff.txt": 1
    }
    assert "without_s2_touched" not in an.analyse(sonnet_rows(), "sonnet")
