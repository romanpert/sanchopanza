"""The W17 memory lots on F2's runner (docs/results/2026-10-16-memory-w17/prereg.md), with no
paid call: the two-arm plans and their bare-line stratum, the user-scope install in the arm's
own configuration folder, the caps, the quiet hours, the night of two lots, the seal, the
analysis and its verdicts, the capped decider, and what the agent sees."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from .helpers import bench_module
from .test_memory_carry_handoff import TELLS
from .test_memory_carry_handoff_work import FAKE, STEP1, STEP2, neutral

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "memory_carry"
night = bench_module(BENCH, "handoff_night")
handoff, hseal, carry = night.handoff, night.handoff_seal, night.carry
carry_s = handoff.carry_s
pairs = bench_module(BENCH, "handoff_pairs")
capped_sub = bench_module(BENCH, "capped_sub")
preflight = bench_module(BENCH, "handoff_preflight")
carry_hook = bench_module(BENCH, "carry_hook")

RUNS = ("w17-sonnet", "w17-opus")
NOON = dt.datetime(2026, 10, 16, 12, 0)


# ---- the plans, the stratum and the folders ----------------------------------------------------


def test_the_two_lots_are_pairs_of_n0_and_s_with_a_bare_line_stratum() -> None:
    sonnet, opus = (handoff.build_plan(r) for r in RUNS)
    assert len(sonnet) == 96 and len(opus) == 72
    for plan in (sonnet, opus):
        assert {a for _, _, a, _ in plan} == {"N0", "S"}
        for i in range(0, len(plan), 2):
            assert sorted(a for _, _, a, _ in plan[i : i + 2]) == ["N0", "S"]
            assert len({(s, r) for s, _, _, r in plan[i : i + 2]}) == 1
        firsts = [plan[i][2] for i in range(0, len(plan), 2)]
        assert firsts.count("N0") == firsts.count("S")
    assert {m for _, m, _, _ in sonnet} == {"sonnet"} and {m for _, m, _, _ in opus} == {"opus"}
    lines = {r: handoff.line_of("w17-sonnet", r) for r in (1, 2, 3, 4)}
    assert lines == {1: "named", 2: "named", 3: "bare", 4: "bare"}
    assert [handoff.line_of("w17-opus", r) for r in (1, 2, 3)] == ["named", "named", "bare"]
    assert {handoff.line_of("f2-sonnet", r) for r in (1, 2, 3, 4)} == {"named"}
    bare = [p for p in sonnet if handoff.line_of("w17-sonnet", p[3]) == "bare"]
    assert len(bare) == 48 and len({p[0] for p in bare}) == 12


def test_the_bare_line_names_nothing_and_is_a_continuation() -> None:
    from sanchopanza.harness.memory_recall import continuation

    assert handoff.BARE_LINE == "Let's continue."
    assert continuation(handoff.BARE_LINE)
    for name in handoff.HANDOFF:
        assert not [w for w in TELLS[name] if w in handoff.BARE_LINE.lower()]


def test_f2_s_runs_keep_their_three_arms_and_caps() -> None:
    assert handoff.arms_of("f2-sonnet") == ("N0", "H", "S")
    assert handoff.call_cap("f2-opus", "opus") == 1.50
    assert handoff.scope_of("f2-sonnet") == "project"
    assert handoff.lot_of("f2-pilot") == "f2" and handoff.lot_of("w17-opus") == "w17"


def test_two_arm_folders_are_opaque() -> None:
    names = {(t, a): handoff.folder_name("w17-sonnet", t, a) for t in range(48)
             for a in ("N0", "S")}  # fmt: skip
    assert all(re.fullmatch(r"t\d\d-[abc]", n) for n in names.values())
    assert all(names[(t, "N0")] != names[(t, "S")] for t in range(48))
    for arm in ("N0", "S"):
        assert {names[(t, arm)][-1] for t in range(48)} == {"a", "b", "c"}
    # F2's own names are unchanged by the two-arm form
    assert handoff.folder_name("f2-sonnet", 7, "H") == "t07-" + dict(
        zip(handoff.ARMS, _shuffled("f2-sonnet/7"), strict=True))["H"]  # fmt: skip


def _shuffled(seed: str) -> list[str]:
    import random

    letters = list(handoff.LETTERS)
    random.Random(seed).shuffle(letters)
    return letters


def test_the_lot_s_roots_are_neutral_and_its_own() -> None:
    lot = handoff.LOTS["w17"]
    work = str(lot["work"]).lower()
    assert not [w for w in ("memory", "f2", "handoff", "sonnet", "opus", "w17", "lot") if w in work]
    assert lot["work"] != handoff.WORK and lot["out"] != handoff.OUT
    assert {handoff.RUNS[r]["dir"] for r in RUNS} == {"r1", "r2"}
    assert lot["sequence"] == RUNS and lot["gate"] is None and lot["quiet"]


# ---- caps ----------------------------------------------------------------------------------------


def test_the_lot_s_call_caps_and_reserves() -> None:
    assert handoff.call_cap("w17-sonnet", "sonnet") == 0.50
    assert handoff.call_cap("w17-opus", "opus") == 0.80
    cmd = handoff.command("x", "opus", cap=handoff.call_cap("w17-opus", "opus"))
    assert cmd[cmd.index("--max-budget-usd") + 1] == "0.80"
    assert handoff.reserve_of("sonnet", "S", "w17-sonnet") == pytest.approx(2 * (0.50 + 0.44) + 0.1)
    assert handoff.reserve_of("opus", "N0", "w17-opus") == pytest.approx(2 * (0.80 + 0.84))
    assert handoff.reserve_of("opus", "N0") == pytest.approx(2 * (1.50 + 0.84))  # F2 unchanged


def test_the_night_cap_binds_both_runs_and_each_holds_a_pair() -> None:
    lot = handoff.LOTS["w17"]
    assert lot["night_cap"] == 45.0
    assert [handoff.RUNS[r]["cap"] for r in RUNS] == [17.0, 33.0]
    for run in RUNS:
        spec = handoff.RUNS[run]
        pair = sum(handoff.reserve_of(spec["model"], a, run) for a in handoff.arms_of(run))
        assert pair < spec["cap"] <= lot["night_cap"]
    ok, detail = preflight.caps_check("w17")
    assert ok and "binds both" in detail


def test_a_session_that_reported_no_cost_is_charged_its_cap_and_a_worst_turn(
    tmp_path: Path,
) -> None:
    got = handoff.charged({"cost": 0.0, "cost_reported": False}, "opus", 0.80)
    assert got["cost"] == pytest.approx(0.80 + 0.84) and got["cost_charged"]
    kept = {"cost": 0.2, "cost_reported": True}
    assert handoff.charged(kept, "opus", 0.80) == kept
    assert handoff.charged({}, "sonnet", None)["cost"] == pytest.approx(0.80 + 0.44)  # F2's cap
    rec = tmp_path / "rec"
    rec.mkdir()
    (rec / "session-1.jsonl").write_text(json.dumps({"type": "result", "total_cost_usd": 0.3}))
    (rec / "session-2.jsonl").write_text(json.dumps({"type": "system", "subtype": "init"}))
    assert handoff.lost_cost(tmp_path / "none", rec, 1.64) == pytest.approx(0.3 + 1.64)
    assert handoff.lost_cost(tmp_path / "none", rec) == pytest.approx(0.3)


def test_a_pair_starts_only_when_both_its_arms_fit(tmp_path: Path) -> None:
    arm, calls = fake_arm([{"cost": 1.0}] * 96)
    pair = sum(handoff.reserve_of("sonnet", a, "w17-sonnet") for a in ("N0", "S"))
    got = handoff.run_plan(tmp_path / "lot", "w17-sonnet", tmp_path / "k", False, pair + 1.5,
                           None, lambda: NOON, lambda s: None, arm,
                           work_root=tmp_path / "w")  # fmt: skip
    assert got == "cap" and len(calls) == 2  # the second pair would not fit whole: no orphan


# ---- the user-scope install ----------------------------------------------------------------------


def test_s_installs_at_user_scope_in_its_own_configuration(tmp_path: Path) -> None:
    work = tmp_path / "r1" / handoff.folder_name("w17-sonnet", 0, "S")
    got = handoff.arm_run(tmp_path / "lot", work, "h_batch", "sonnet", "S", 3,
                          tmp_path / "r1" / "typesafe.key", True, run="w17-sonnet")  # fmt: skip
    assert got["line"] == "bare" and got["scope"] == "user"
    assert got["planned"][-1] == "session 2: bare"
    repo, config = work / "repo", work / "claude-config"
    assert not (repo / ".claude").exists() and not (repo / ".mcp.json").exists()
    assert not list(work.rglob(".mcp.json"))
    settings = (config / "settings.json").read_text(encoding="utf-8")
    assert '"sanchopanza ' not in settings and "carry_hook.py" in settings
    assert "memory-hook" in settings and "guard-hook" in settings
    assert (config / "skills" / "sanchopanza-code" / "SKILL.md").is_file()
    rec = tmp_path / "lot" / "arms" / work.name
    assert (rec / "install.txt").exists() and (rec / "install" / "rewired").is_dir()
    assert not (work / "install.txt").exists() and not (work / "install").exists()
    n0 = tmp_path / "r1" / handoff.folder_name("w17-sonnet", 0, "N0")
    handoff.arm_run(tmp_path / "lot", n0, "h_batch", "sonnet", "N0", 3, tmp_path / "k", True,
                    run="w17-sonnet")  # fmt: skip
    assert not list((n0 / "claude-config").iterdir())


def test_the_runner_s_user_install_is_the_bare_default(tmp_path: Path) -> None:
    ok, detail = preflight.user_check(tmp_path)
    assert ok, detail


def test_user_scope_needs_the_memory_hook_at_start_not_a_server(tmp_path: Path) -> None:
    rows = [{"sub": "memory-hook", "event": "SessionStart", "exit": 0},
            {"sub": "memory-hook", "event": "UserPromptSubmit", "exit": 0}]  # fmt: skip
    (tmp_path / "hooks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    result = {"init": {"mcp": {}, "skill_names": ["init", "sanchopanza-code"]}}
    assert carry_s.session_breaks(tmp_path, result, 0, server=None) == []
    assert carry_s.session_breaks(tmp_path, result, 0)[0].startswith("MCP server")
    no_skill = {"init": {"mcp": {}, "skill_names": ["init"]}}
    assert carry_s.session_breaks(tmp_path, no_skill, 0, server=None) == [
        "the sanchopanza-code skill is not in the session's init"
    ]
    (tmp_path / "hooks.jsonl").write_text(json.dumps(rows[1]) + "\n")
    assert "SessionStart" in carry_s.session_breaks(tmp_path, result, 0, server=None)[0]


def test_init_keeps_the_skill_names() -> None:
    event = {"type": "system", "subtype": "init", "skills": ["a", {"name": "sanchopanza-code"}, 3]}
    assert carry.init_facts(event)["skill_names"] == ["a", "sanchopanza-code"]
    assert carry.init_facts(event)["skills"] == 3


# ---- a whole pair against a stand-in claude ----------------------------------------------------


def stand_in(tmp_path: Path, monkeypatch: Any) -> None:
    fake = tmp_path / "fake_claude.py"
    fake.write_text(FAKE)
    (tmp_path / "step1.txt").write_text(STEP1)
    (tmp_path / "step2.txt").write_text(STEP2)
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.json"))
    monkeypatch.setenv(carry.TOKEN, "tok-test-123")
    monkeypatch.setattr(handoff, "command", lambda prompt, model, resume=None, cap=None:
                        [sys.executable, str(fake), prompt, resume or "", str(cap)])  # fmt: skip


def test_a_bare_n0_arm_gets_the_bare_line(tmp_path: Path, monkeypatch: Any) -> None:
    stand_in(tmp_path, monkeypatch)
    got = handoff.arm_run(tmp_path / "lot", tmp_path / "w" / "t00-a", "h_batch", "sonnet", "N0",
                          3, tmp_path / "k", False, run="w17-sonnet")  # fmt: skip
    calls = json.loads((tmp_path / "calls.json").read_text())
    assert [c["prompt"] for c in calls][1] == handoff.BARE_LINE
    assert got["line"] == "bare" and not got.get("cut") and got["kept_all"]
    named = handoff.arm_run(tmp_path / "lot", tmp_path / "w" / "t01-a", "h_batch", "sonnet",
                            "N0", 1, tmp_path / "k", False, run="w17-sonnet")  # fmt: skip
    calls = json.loads((tmp_path / "calls.json").read_text())
    assert calls[-1]["prompt"] == handoff.HANDOFF["h_batch"]["continue"]
    assert named["line"] == "named"


# ---- quiet hours and the night -------------------------------------------------------------------


def fake_arm(results: list[Any]):
    calls: list[tuple[str, str, int, str]] = []

    def arm(out: Path, work: Path, name: str, model: str, arm: str, rep: int, keyfile: Path,
            dry: bool, **_: Any) -> dict[str, Any]:  # fmt: skip
        work.mkdir(parents=True, exist_ok=True)
        calls.append((name, arm, rep, work.name))
        extra = results.pop(0) if results else {}
        return {**pair_row(name, arm, rep), "folder": str(work), **extra}

    return arm, calls


def go(out: Path, arm_fn: Any, run: str = "w17-sonnet", clock: Any = lambda: NOON,
       lifted: Any = lambda: "") -> str:  # fmt: skip
    """`lifted` stands in for the registry (no Windows Update pause unless a test says so)."""
    return handoff.run_plan(out / "lot", run, out / "k", False, 100.0, None, clock,
                            lambda s: None, arm_fn, work_root=out / "w",
                            lifted=lifted)  # fmt: skip


def test_the_lot_runs_whole_and_resumes(tmp_path: Path) -> None:
    arm, calls = fake_arm([])
    assert go(tmp_path, arm) == "" and len(calls) == 96
    assert handoff.complete(tmp_path / "lot", "w17-sonnet")
    again, more = fake_arm([])
    assert go(tmp_path, again) == "" and more == []


def test_no_arm_starts_that_would_run_into_the_quiet_hours(tmp_path: Path) -> None:
    arm, calls = fake_arm([])
    late = dt.datetime(2026, 10, 17, 1, 55)
    assert go(tmp_path, arm, clock=lambda: late) == "quiet" and calls == []
    assert handoff.EXIT["quiet"] == 8
    early = dt.datetime(2026, 10, 17, 7, 59)
    assert go(tmp_path, arm, clock=lambda: early) == "quiet"
    assert go(tmp_path, arm, clock=lambda: dt.datetime(2026, 10, 17, 8, 0)) == ""
    f2, f2_calls = fake_arm([])
    got = handoff.run_plan(tmp_path / "f2", "f2-pilot", tmp_path / "k", False, 100.0, None,
                           lambda: late, lambda s: None, f2, work_root=tmp_path / "w2")  # fmt: skip
    assert got == "" and len(f2_calls) == 12  # F2's night ran through its quiet hours


def test_a_windows_update_pause_lifts_the_quiet_hours_and_the_log_says_so(
    tmp_path: Path, capsys: Any
) -> None:
    """Amendment 1: asked before every arm that would reach 02:00-08:00; each lift is logged."""
    late = dt.datetime(2026, 10, 17, 1, 55)
    asked: list[int] = []

    def paused() -> str:
        asked.append(1)
        return "Windows Update paused until 2026-10-24 01:10 UTC"

    arm, calls = fake_arm([])
    assert go(tmp_path / "a", arm, clock=lambda: late, lifted=paused) == "" and len(calls) == 96
    assert len(asked) == 96
    log = capsys.readouterr().out
    assert log.count("quiet hours lifted for t") == 96 and "2026-10-24 01:10" in log
    noon, noon_calls = fake_arm([])
    assert go(tmp_path / "b", noon, lifted=paused) == "" and len(asked) == 96  # not asked at noon
    ended = iter(["Windows Update paused until 2026-10-24 01:10 UTC", ""])
    more, more_calls = fake_arm([])
    assert go(tmp_path / "c", more, clock=lambda: late, lifted=lambda: next(ended)) == "quiet"
    assert len(more_calls) == 1  # the pause ended: the rule is back before the next arm


def test_the_real_pause_reader_is_the_default() -> None:
    import inspect

    default = inspect.signature(handoff.run_plan).parameters["lifted"].default
    assert default is handoff.winupdate.quiet_lifted


def test_the_redo_s_roots_are_new_and_the_interrupted_ones_refused(
    tmp_path: Path, monkeypatch: Any
) -> None:
    lot = handoff.LOTS["w17"]
    old_out, old_work = handoff.W17_INTERRUPTED
    assert lot["out"] == Path(r"C:\sp-runs\memory-w17-redo") and lot["out"] != old_out
    assert lot["work"] == Path(r"C:\sp-runs\w19") and lot["work"] != old_work
    for path in (lot["out"], lot["work"]):  # neither is inside the other run's folders
        assert old_out not in path.parents and old_work not in path.parents
    # the night refuses them (dry too) before it writes anything there: stand-ins, not the real
    monkeypatch.setattr(handoff, "W17_INTERRUPTED", (tmp_path / "old", tmp_path / "oldwork"))
    monkeypatch.setattr(hseal, "require_sealed_checkout", lambda lot="f2": None)
    ran: list[Any] = []
    monkeypatch.setattr(handoff, "execute", fake_execute(ran))
    for dry in (False, True):
        got = night.night(tmp_path / "old", dry=dry, lot="w17", only="w17-opus")
        assert got == hseal.SEALED_CHECKOUT_REFUSED and not (tmp_path / "old").exists()
    monkeypatch.setitem(handoff.LOTS["w17"], "work", tmp_path / "oldwork")
    assert night.night(tmp_path / "new", lot="w17", only="w17-opus") == 11 and ran == []
    assert night.interrupted_refusal(tmp_path / "old", "f2") == ""


def test_the_redo_alone_in_its_new_root_has_the_sealed_run_cap(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """No w17-sonnet ledger in the new root: min(33, 45 - 0) = 33 USD, the sealed run cap."""
    ran: list[Any] = []
    monkeypatch.setattr(hseal, "require_sealed_checkout", lambda lot="f2": None)
    monkeypatch.setattr(handoff, "execute", fake_execute(ran))
    assert night.spent_before(tmp_path, "w17-opus", "w17") == 0.0
    assert night.night(tmp_path, lot="w17", only="w17-opus") == 0
    assert ran == [("w17-opus", 33.0)]


def test_the_redo_s_launcher_runs_only_opus_from_its_new_root() -> None:
    text = (ROOT / "memlot-night-run.cmd").read_text(encoding="utf-8")
    body = [x for x in text.splitlines() if not x.lstrip().lower().startswith("rem")]
    sets = {x.split("=", 1)[0][4:]: x.split("=", 1)[1] for x in body if x.startswith("set ")}
    assert sets["ROOT"] == r"C:\sp-runs\memory-w17-redo"
    assert sets["ONLY"] == "--only w17-opus"
    assert not [x for x in body if "w17-sonnet" in x or "memory-w17\\" in x]
    runs = [x for x in body if "handoff_night.py" in x]
    assert len(runs) == 2 and all("%ONLY%" in x for x in runs)
    assert r'call "%ROOT%\keys-env.cmd"' in text and r'call "%ROOT%\python-env.cmd"' in text
    assert 'if /i not "%~1"=="opus"' in text  # anything but opus or dry: exit 2


def fake_execute(ran: list[Any]):
    def execute(run: str, out: Path, cap: float, dry: bool = False, night: Path | None = None,
                work_root: Path | None = None) -> str:  # fmt: skip
        ran.append((run, cap))
        return ""

    return execute


def test_the_lot_s_night_runs_both_lots_under_one_cap(tmp_path: Path, monkeypatch: Any) -> None:
    ran: list[Any] = []
    monkeypatch.setattr(hseal, "require_sealed_checkout", lambda lot="f2": None)
    monkeypatch.setattr(handoff, "execute", fake_execute(ran))
    handoff.book(tmp_path / "w17-sonnet", "arm", 17.5, "x")
    assert night.night(tmp_path, lot="w17") == 0
    assert ran == [("w17-sonnet", handoff.RUNS["w17-sonnet"]["cap"]), ("w17-opus", 27.5)]
    assert not (tmp_path / "gate.json").exists()
    only: list[Any] = []
    monkeypatch.setattr(handoff, "execute", fake_execute(only))
    assert night.night(tmp_path, lot="w17", only="w17-opus") == 0
    assert [r for r, _ in only] == ["w17-opus"]


def test_the_lot_s_night_refuses_without_its_seal(tmp_path: Path, monkeypatch: Any) -> None:
    seen: list[str] = []

    def refuse(lot: str = "f2") -> None:
        seen.append(lot)
        raise SystemExit(hseal.SEALED_CHECKOUT_REFUSED)

    monkeypatch.setattr(hseal, "require_sealed_checkout", refuse)
    with pytest.raises(SystemExit):
        night.night(tmp_path, lot="w17")
    assert seen == ["w17"]


# ---- the seal ------------------------------------------------------------------------------------


def test_the_lot_s_seal_names_its_own_prereg_launcher_and_modules() -> None:
    results, fixed = hseal.LOTS["w17"]
    assert results.name == "2026-10-16-memory-w17"
    for rel in (
        "memlot-night-run.cmd",
        "benchmarks/memory_carry/handoff_pairs.py",
        "benchmarks/memory_carry/capped_sub.py",
        "tests/test_memory_carry_w17.py",
        "benchmarks/memory_carry/carry_hook.py",
        "benchmarks/memory_carry/carry_s.py",
    ):
        assert rel in fixed
    assert hseal.LOTS["f2"] == (hseal.RESULTS, hseal.SEALED_FIXED)


# ---- the analysis --------------------------------------------------------------------------------


def pair_row(scene: str, arm: str, rep: int, model: str = "sonnet", **over: Any) -> dict[str, Any]:
    base = {"scene": scene, "model": model, "arm": arm, "repeat": rep, "tests_pass": True,
            "task_pass": True, "fact_pass": True, "decision_pass": True, "intact_pass": True,
            "kept_all": arm == "S", "cost": 0.10, "jev_usd": 0.0002 if arm == "S" else 0.0,
            "sessions": [{"tag": "session-1", "cost": 0.05}, {"tag": "session-2", "cost": 0.05}],
            "line": handoff.line_of("w17-sonnet" if model == "sonnet" else "w17-opus", rep),
            "tokens": {"input": 1, "output": 2, "cache_read": 3, "cache_write": 4}}  # fmt: skip
    return {**base, **over}


def lot_rows(run: str, s: dict[str, Any] | None = None,
             n0: dict[str, Any] | None = None) -> list[dict[str, Any]]:  # fmt: skip
    model = handoff.RUNS[run]["model"]
    return [pair_row(sc, a, r, model, **((s or {}) if a == "S" else (n0 or {})))
            for sc, _, a, r in handoff.build_plan(run)]  # fmt: skip


def test_sonnet_gana_needs_success_and_the_cost_bound() -> None:
    cheap = pairs.analyse(lot_rows("w17-sonnet", s={"cost": 0.103}), "sonnet")
    assert cheap["pairs"] == 48 and cheap["criteria"]["s1_better"]
    assert cheap["criteria"]["s2_cost"] and cheap["verdict"] == "gana"
    assert cheap["cost_ratio"]["median"] == pytest.approx(1.032)
    dear = pairs.analyse(lot_rows("w17-sonnet", s={"cost": 0.125}), "sonnet")
    assert dear["criteria"]["s1_better"] and not dear["criteria"]["s2_cost"]
    assert dear["verdict"] == "S' better than N0; no gana (cost)"
    same = pairs.analyse(lot_rows("w17-sonnet", n0={"kept_all": True}), "sonnet")
    assert same["verdict"] == "not shown"
    harmed = pairs.analyse(lot_rows("w17-sonnet", s={"tests_pass": False, "cost": 0.1}), "sonnet")
    assert harmed["verdict"] == "not shown" and not harmed["criteria"]["s3_tests"]
    assert pairs.analyse(lot_rows("w17-sonnet")[:70], "sonnet")["verdict"] == "sin veredicto"
    strata = cheap["strata"]
    assert strata["bare"]["pairs"] == 24 and strata["named"]["pairs"] == 24
    assert strata["bare"]["better"] and strata["bare"]["S_vs_N0"]["a_only"] == 24


def test_opus_reads_the_cost_three_ways() -> None:
    kept = {"kept_all": True}
    free = pairs.analyse(lot_rows("w17-opus", s={**kept, "cost": 0.099}, n0=kept), "opus")
    assert free["criteria"]["o1_cost"] and free["criteria"]["o2_not_worse"]
    assert free["verdict"] == "no extra cost"
    dear = pairs.analyse(lot_rows("w17-opus", s={**kept, "cost": 0.11}, n0=kept), "opus")
    assert dear["verdict"] == "costs extra" and dear["cost_ratio"]["ci95"][0] > 1
    worse = pairs.analyse(lot_rows("w17-opus", s={"kept_all": False, "cost": 0.099}, n0=kept),
                          "opus")  # fmt: skip
    assert not worse["criteria"]["o2_not_worse"] and worse["verdict"] == "not determined"
    assert free["scoreboard"] == "sin margen"  # N0 kept all everywhere: no room to win


def test_a_small_but_certain_extra_cost_is_extra_cost() -> None:
    kept = {"kept_all": True}
    rows = lot_rows("w17-opus", s={**kept, "cost": 0.1028}, n0=kept)  # 1.03x with Jev
    got = pairs.analyse(rows, "opus")
    assert got["criteria"]["o1_cost"] and got["cost_ratio"]["ci95_raw"][0] > 1
    assert got["verdict"] == "costs extra"


def test_the_row_s_send_backs_decide_no_harm() -> None:
    rows = lot_rows("w17-sonnet", s={"cost": 0.103, "sendbacks_other_rule": 1})
    got = pairs.analyse(rows, "sonnet")
    assert got["false_sendbacks"] == 48 and not got["criteria"]["s3_sendbacks"]


def test_the_ratios_are_resampled_in_pair_order() -> None:
    rows = lot_rows("w17-sonnet", s={"cost": 0.11})
    rows = [{**r, "cost": r["cost"] + 0.001 * r["repeat"]} if r["arm"] == "S" else r for r in rows]
    a, b = pairs.analyse(rows, "sonnet"), pairs.analyse(rows[::-1], "sonnet")
    assert a["cost_ratio"] == b["cost_ratio"]


def test_the_analysis_refuses_a_folder_that_is_not_a_w17_run(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        pairs.main([str(tmp_path / "f2-sonnet")])


def test_the_sealed_checkout_refuses_a_path_that_names_the_lot() -> None:
    assert "names the lot" in hseal.path_refusal("w17", Path("C:/x/sanchopanza-w17-memlot"))
    assert hseal.path_refusal("w17", Path("C:/x/sp-w18")) == ""
    assert hseal.path_refusal("f2", Path("C:/x/sanchopanza-w17-memlot")) == ""
    with pytest.raises(SystemExit):
        hseal.require_sealed_checkout("w17", Path("C:/x/sanchopanza-w17-memlot"))


@pytest.mark.parametrize(("text", "want"), [
    (r"ls ..\..", {"../.."}),
    ("cat ../../t03-b/repo/app.py", {"../..", "sibling"}),
    (r"cd C:\sp-runs\w18\r1\t05-a\repo", set()),
    (r"type C:\sp-runs\w18\r1\typesafe.key", {"typesafe.key"}),
    ("cat ../../jev-ledger.jsonl ../hooks.jsonl ../journal.jsonl",
     {"../..", "jev-", "hooks.jsonl", "journal.jsonl"}),
])  # fmt: skip
def test_touches_names_what_lies_beside_the_arm(text: str, want: set[str]) -> None:
    assert handoff.hc.touches([json.dumps({"command": text})], own="t05-a") == want


def test_opus_scoreboard_reads_room_and_cost() -> None:
    rows = lot_rows("w17-opus", s={"kept_all": True, "cost": 0.08})
    got = pairs.analyse(rows, "opus")
    assert got["scoreboard"] == "gana (coste)"  # N0 never kept all, S' always, cheaper


def test_the_session_one_ratio_and_cost_are_reported() -> None:
    rows = lot_rows("w17-sonnet", s={"sessions": [{"tag": "session-1", "cost": 0.06},
                                                  {"tag": "session-2", "cost": 0.05}]})  # fmt: skip
    got = pairs.analyse(rows, "sonnet")
    assert got["session_1_ratio"]["median"] == pytest.approx(1.2)
    assert got["cost_median_usd"]["N0"] == pytest.approx(0.10)


def test_the_bootstrap_is_the_sealed_one() -> None:
    got = pairs.ratio_interval([1.0, 1.1, 1.2, 0.9])
    assert got["draws"] == 10_000 and got["seed"] == pairs.SEED == 20261017
    assert got["ci95"][0] <= got["median"] <= got["ci95"][1]


# ---- the capped decider --------------------------------------------------------------------------


def test_the_hook_s_decider_is_capped_on_the_lot_s_ledger(tmp_path: Path) -> None:
    from sanchopanza.providers.capped import CappedDecider

    ledger = tmp_path / "jev-ledger.jsonl"
    got = capped_sub.capped_factory(ledger, 0.5)({"TYPESAFE_API_KEY": "dummy"})
    assert isinstance(got, CappedDecider) and got.name == "jev"
    plain = capped_sub.capped_factory(ledger, 0.5)({})
    assert not isinstance(plain, CappedDecider)


def test_the_hook_launcher_routes_through_the_cap_when_the_lot_asks(tmp_path: Path) -> None:
    keyfile = tmp_path / "typesafe.key"
    assert carry_hook.command_of(keyfile, "memory-hook", [])[1:3] == ["-m", "sanchopanza"]
    (tmp_path / carry_hook.CAP_FILE).write_text(json.dumps({"cap_usd": 0.5}))
    cmd = carry_hook.command_of(keyfile, "memory-hook", ["x"])
    assert cmd[1].endswith("capped_sub.py") and cmd[-2:] == ["memory-hook", "x"]
    assert str(tmp_path / "jev-ledger.jsonl") in cmd and "0.5" in cmd


# ---- what the agent sees -------------------------------------------------------------------------

LOT_WORDS = ("handoff", "f2", "w17", "memlot", "sonnet", "opus", "memory-w17", "bare")
ARM_TOKEN = re.compile(r"(?<![A-Za-z0-9])(N0|S|S')(?![A-Za-z0-9])")


@pytest.mark.parametrize("name", sorted(handoff.HANDOFF))
def test_nothing_the_agent_sees_names_the_scene_the_arm_the_stratum_or_the_lot(
    name: str, tmp_path: Path
) -> None:
    work_root = tmp_path / "r1"
    for t, (arm, rep) in enumerate((("N0", 1), ("S", 1), ("N0", 3), ("S", 3))):
        work = work_root / handoff.folder_name("w17-sonnet", t, arm)
        handoff.arm_run(tmp_path / "lot", work, name, "sonnet", arm, rep,
                        work_root / "typesafe.key", True, run="w17-sonnet")  # fmt: skip
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


def test_the_skill_names_no_lot_model_or_ritual() -> None:
    from sanchopanza.harness.install_defaults import skill_text

    text = skill_text().lower()
    for word in ("sonnet", "opus", "haiku", "handoff", "ritual", "f2", "w17", "lot ", "benchmark"):
        assert word not in text, word
