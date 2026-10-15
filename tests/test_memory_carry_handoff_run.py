"""F2's runner, analysis, gate and night (`benchmarks/memory_carry/handoff*.py`), with no paid
call: Tango's interval against his published examples, the plan and its caps, the handoff's NOT
RUN rules, the gate, the stops (limit, STOP, interrupted, broken, midnight), the seal, and a
whole H arm against a stand-in claude."""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from .helpers import bench_module

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks" / "memory_carry"
night = bench_module(BENCH, "handoff_night")
handoff, an = night.handoff, night.handoff_analyze
carry = handoff.carry

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


# ---- the plan and its caps ---------------------------------------------------------------------


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
    assert handoff.NIGHT_CAP == 230.0
    assert handoff.CALL_CAPS == {"sonnet": 0.80, "opus": 1.50}


def test_reserve_counts_three_calls_for_h_and_one_worst_turn() -> None:
    assert handoff.reserve_of("sonnet", "H") == pytest.approx(3 * 0.80 + 0.40)
    assert handoff.reserve_of("sonnet", "N0") == pytest.approx(2 * 0.80 + 0.40)
    assert handoff.reserve_of("opus", "S") == pytest.approx(2 * 1.50 + 0.75 + 0.10)


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

GOOD = {"returncode": 0, "subtype": "success", "text": "Continue with step 2...", "cost": 0.02,
        "cost_reported": True, "context_carried": True}  # fmt: skip


@pytest.mark.parametrize(("change", "why"), [
    ({}, ""),
    ({"returncode": 1, "subtype": ""}, "handoff: exit 1"),
    ({"text": "  "}, "handoff: no text"),
    ({"cost_reported": False}, "handoff: no cost reported"),
    ({"cost": 0.0}, "handoff: no cost reported"),
    ({"context_carried": False}, "handoff: the resumed turn did not carry"),
    ({"context_carried": None}, ""),
    ({"text": "x" * 30_001}, "handoff: text over"),
    ({"timeout": True}, "handoff: timeout"),
])  # fmt: skip
def test_handoff_cut(change: dict[str, Any], why: str) -> None:
    got = handoff.handoff_cut({}, {**GOOD, **change})
    assert got.startswith(why) and bool(got) == bool(why)


def test_context_carried_compares_the_resumed_prompt_with_session_1() -> None:
    assert handoff.carried({"last_prompt": 30000}, {"first_prompt": 31000}) is True
    assert handoff.carried({"last_prompt": 30000}, {"first_prompt": 18000}) is False
    assert handoff.carried({"last_prompt": None}, {"first_prompt": 18000}) is None


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
        base["handoff"] = {
            "chars": 900,
            "cost_reported": True,
            "cost": 0.03,
            "names": {"C": True, "D": True},
            "tokens": {"output": 300},
        }
    return {**base, **over}


def pilot_rows(**per: dict[str, Any]) -> list[dict[str, Any]]:
    plan = handoff.build_plan("f2-pilot")
    return [row(s, a, r, **per.get(f"{s}:{a}", {})) for s, _, a, r in plan]


def test_gate_passes_when_all_four_hold() -> None:
    result = an.gate(pilot_rows(), handoff.build_plan("f2-pilot"))
    assert result["pass"] and result["reasons"] == []
    assert "PASS" in an.gate_text(result)


@pytest.mark.parametrize(("per", "letter"), [
    ({"h_batch:H": {"cut": "handoff: no text", "handoff": {"chars": 0}}}, "a"),
    ({"h_weeks:H": {"handoff": {"chars": 500, "cost_reported": False}}}, "a"),
    ({"h_spanish:S": {"fact_pass": None}}, "b"),
    ({"h_spanish:N0": {"cut": "timeout"}}, "b"),
    ({"h_weeks:N0": {"task_pass": False}, "h_weeks:H": {"task_pass": False},
      "h_weeks:S": {"task_pass": False}}, "c"),
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


# ---- analysis ----------------------------------------------------------------------------------


def test_analyse_reads_the_criteria_in_sequence() -> None:
    rows = [row(s, a, r) for s, _, a, r in handoff.build_plan("f2-sonnet")]
    result = an.analyse(rows, "sonnet")
    assert result["triples"] == 48 and result["S_vs_H"]["a_only"] == 0
    assert result["criteria"]["1_s_not_worse_than_h"] and result["criteria"]["2_s_better_than_n0"]
    assert result["verdict"] == "S not worse than H; S better than N0"
    worse = [r if r["arm"] != "S" or r["repeat"] > 2 else {**r, "kept_all": False} for r in rows]
    got = an.analyse(worse, "sonnet")
    assert not got["criteria"]["1_s_not_worse_than_h"]
    assert got["criteria"]["2_s_better_than_n0"] is None and got["verdict"] == "not shown"
    few = an.analyse(rows[:30], "sonnet")
    assert few["verdict"] == "sin veredicto"
    assert result["handoff_names"]["both"] == 48 and result["cost_ratio_median"]["S/H"] > 1


# ---- the run's stops ---------------------------------------------------------------------------


def fake_arm(results: list[dict[str, Any]]):
    calls: list[tuple[str, str, int]] = []

    def arm(out: Path, name: str, model: str, arm: str, rep: int, keyfile: Path,
            dry: bool) -> dict[str, Any]:  # fmt: skip
        (out / f"{name}-{model}-{arm}-{rep}").mkdir(parents=True, exist_ok=True)
        calls.append((name, arm, rep))
        extra = results.pop(0) if results else {}
        return {**row(name, arm, rep), **extra}

    return arm, calls


NOON = dt.datetime(2026, 10, 15, 12, 0)


def go(out: Path, arm_fn: Any, cap: float = 100.0, clock: Any = lambda: NOON,
       sleep: Any = lambda s: None) -> str:  # fmt: skip
    return handoff.run_plan(out, "f2-pilot", out / "k", False, cap, None, clock, sleep, arm_fn)


def test_the_run_ends_writes_rows_and_resumes_for_free(tmp_path: Path) -> None:
    arm, calls = fake_arm([])
    assert go(tmp_path, arm) == ""
    assert len(handoff.rows_of(tmp_path)) == 12 and handoff.complete(tmp_path, "f2-pilot")
    assert handoff.ledger(tmp_path) == pytest.approx(12 * 0.3 + 4 * 0.001)
    again, more = fake_arm([])
    assert go(tmp_path, again) == "" and more == []


def test_the_cap_stops_before_an_arm(tmp_path: Path) -> None:
    arm, calls = fake_arm([{"cost": 3.0}] * 12)
    assert go(tmp_path, arm, cap=11.5) == "cap"
    assert handoff.ledger(tmp_path) + 2.0 <= 11.5 + 2.8 and len(calls) < 12


def test_a_usage_limit_pauses_without_a_row(tmp_path: Path) -> None:
    arm, calls = fake_arm([{}, {"limit_hit": True, "cut": "usage limit"}])
    assert go(tmp_path, arm) == "limit"
    assert (tmp_path / "LIMIT.flag").exists() and len(handoff.rows_of(tmp_path)) == 1
    assert list(tmp_path.glob("*.limit-*"))


def test_stop_file_and_interrupted_arms(tmp_path: Path) -> None:
    (tmp_path / "STOP").write_text("")
    arm, calls = fake_arm([])
    assert go(tmp_path, arm) == "manual" and calls == []
    (tmp_path / "STOP").unlink()
    first = handoff.build_plan("f2-pilot")[0]
    folder = tmp_path / f"{first[0]}-{first[1]}-{first[2]}-{first[3]}"
    folder.mkdir()
    (folder / "session-1.jsonl").write_text(
        json.dumps({"type": "result", "total_cost_usd": 0.25}) + "\n"
    )
    assert go(tmp_path, arm) == ""
    assert handoff.ledger(tmp_path) == pytest.approx(0.25 + 12 * 0.3 + 4 * 0.001)
    assert json.loads((tmp_path / "interrupts.json").read_text()) == {folder.name: 1}


def test_an_arm_interrupted_too_often_is_not_run(tmp_path: Path) -> None:
    first = handoff.build_plan("f2-pilot")[0]
    name = f"{first[0]}-{first[1]}-{first[2]}-{first[3]}"
    (tmp_path / "interrupts.json").write_text(json.dumps({name: handoff.INTERRUPTS}))
    (tmp_path / name).mkdir()
    arm, calls = fake_arm([])
    assert go(tmp_path, arm) == ""
    cut = [r for r in handoff.rows_of(tmp_path) if r.get("cut")]
    assert len(cut) == 1 and cut[0]["cut"].startswith("interrupted")


def test_arms_without_a_result_in_a_row_stop_the_run(tmp_path: Path) -> None:
    arm, calls = fake_arm([{"cut": "session-1 ended without a result (exit 1)"}] * 3)
    assert go(tmp_path, arm) == "broken" and len(calls) == 3


def test_the_midnight_rule_waits_for_the_next_day(tmp_path: Path) -> None:
    times = iter([dt.datetime(2026, 10, 15, 23, 50)] * 3 + [dt.datetime(2026, 10, 16, 0, 1)] * 99)
    slept: list[float] = []
    arm, calls = fake_arm([])
    assert go(tmp_path, arm, clock=lambda: next(times), sleep=slept.append) == ""
    assert slept and len(calls) == 12


# ---- the seal ----------------------------------------------------------------------------------


def test_seal_is_written_once_and_breaks_on_any_change(tmp_path: Path) -> None:
    repo, results = tmp_path / "repo", tmp_path / "repo" / "docs" / "results" / "x"
    for rel in (*handoff.SEALED_FIXED, "src/sanchopanza/a.py"):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(f"# {rel}\n")
    results.mkdir(parents=True)
    (results / "prereg.md").write_text("prereg\r\n")
    assert not handoff.seal_ok(repo, results)
    value = handoff.seal(repo, results)
    assert handoff.seal_ok(repo, results) and handoff.seal(repo, results) == value
    assert "src/sanchopanza/a.py" in json.loads((results / "prereg.manifest.json").read_text())
    (repo / "src/sanchopanza/a.py").write_text("# changed\n")
    assert not handoff.seal_ok(repo, results)
    with pytest.raises(SystemExit):
        handoff.seal(repo, results)


def test_the_live_night_refuses_without_the_seal(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr(handoff, "seal_ok", lambda *a: False)
    with pytest.raises(SystemExit):
        night.night(tmp_path)


def test_the_night_stops_at_a_failed_gate(tmp_path: Path, monkeypatch: Any) -> None:
    ran: list[str] = []
    monkeypatch.setattr(handoff, "require_seal", lambda: None)
    monkeypatch.setattr(handoff, "execute", lambda run, out, cap, dry=False, night=None:
                        ran.append(run) or "")  # fmt: skip
    (tmp_path / "f2-pilot").mkdir()
    (tmp_path / "f2-pilot" / "f2.json").write_text(
        json.dumps(pilot_rows(**{f"{s}:N0": {"kept_all": True} for s in handoff.HANDOFF_PILOT}))
    )
    assert night.night(tmp_path) == night.GATE_FAIL and ran == ["f2-pilot"]
    assert "FAIL" in (tmp_path / "gate.md").read_text()
    assert not (tmp_path / "night.lock").exists()


def test_the_night_runs_the_sequence_after_a_passing_gate(tmp_path: Path,
                                                          monkeypatch: Any) -> None:  # fmt: skip
    caps: list[tuple[str, float]] = []
    monkeypatch.setattr(handoff, "require_seal", lambda: None)
    monkeypatch.setattr(handoff, "execute", lambda run, out, cap, dry=False, night=None:
                        caps.append((run, cap)) or "")  # fmt: skip
    (tmp_path / "f2-pilot").mkdir()
    (tmp_path / "f2-pilot" / "f2.json").write_text(json.dumps(pilot_rows()))
    handoff.book(tmp_path / "f2-pilot", "arm", 7.0, "x")
    handoff.book(tmp_path / "f2-sonnet", "arm", 120.0, "y")
    assert night.night(tmp_path) == 0
    assert caps == [("f2-pilot", 11.5), ("f2-sonnet", 109.0), ("f2-opus", 103.0)]


# ---- a whole H arm against a stand-in claude ---------------------------------------------------

STEP1 = """def label_for(order):
    return {'to': order['name'], 'address': order['address'],
            'weight_kg': round(order['weight_g'] / 1000, 2)}
"""
STEP2 = """

def ship_all(orders, carrier):
    paid = [label_for(o) for o in orders if o['paid']]
    out = []
    for i in range(0, len(paid), 50):
        out += carrier.create_labels(paid[i:i + 50])
    return out
"""
FAKE = r"""
import json, os, pathlib, sys
prompt, resume = sys.argv[1], sys.argv[2]
here = pathlib.Path(__file__).parent
log = pathlib.Path(os.environ["FAKE_LOG"])
calls = json.loads(log.read_text()) if log.exists() else []
log.write_text(json.dumps(calls + [{"prompt": prompt, "resume": resume}]))
sid = resume or f"sid-{len(calls)}"
size = 40000 if resume else 20000
step1, step2 = (here / "step1.txt").read_text(), (here / "step2.txt").read_text()
if not resume:
    code = step1 if "Step 1" in prompt else step1 + step2
    pathlib.Path("app/labels.py").write_text(code)
text = "HANDOFF: ship_all with create_labels, at most 50 per call." if resume else "done"
init = {"type": "system", "subtype": "init", "session_id": sid,
        "model": "claude-sonnet-5-5", "claude_code_version": "2.1.287"}
usage = {"input_tokens": 10, "cache_read_input_tokens": size}
said = {"type": "assistant", "message": {"content": [], "usage": usage}}
result = {"type": "result", "subtype": "success", "total_cost_usd": 0.05, "num_turns": 2,
          "result": text, "usage": {**usage, "output_tokens": 20,
                                    "cache_creation_input_tokens": 5}}
for e in (init, said, result):
    print(json.dumps(e))
"""


def test_a_whole_h_arm_resumes_pastes_the_handoff_and_checks(tmp_path: Path,
                                                             monkeypatch: Any) -> None:  # fmt: skip
    fake = tmp_path / "fake_claude.py"
    fake.write_text(FAKE)
    (tmp_path / "step1.txt").write_text(STEP1)
    (tmp_path / "step2.txt").write_text(STEP2)
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.json"))
    monkeypatch.setenv(carry.TOKEN, "tok-test-123")
    monkeypatch.setattr(handoff, "command", lambda prompt, model, resume=None:
                        [sys.executable, str(fake), prompt, resume or ""])  # fmt: skip
    got = handoff.arm_run(tmp_path / "out", "h_batch", "sonnet", "H", 0, tmp_path / "k", False)
    calls = json.loads((tmp_path / "calls.json").read_text())
    assert [c["resume"] for c in calls] == ["", "sid-0", ""]
    assert calls[1]["prompt"] == handoff.HANDOFF_REQUEST
    assert calls[2]["prompt"].startswith("HANDOFF:")
    assert (
        (tmp_path / "out" / "h_batch-sonnet-H-0" / "handoff.txt").read_text().startswith("HANDOFF:")
    )
    assert not got.get("cut") and got["kept_all"] and got["intact_pass"]
    assert got["handoff"]["context_carried"] and got["handoff"]["names"] == {"C": True, "D": True}
    assert got["cost"] == pytest.approx(0.15) and got["tokens"]["output"] == 60
    n0 = handoff.arm_run(tmp_path / "out", "h_batch", "sonnet", "N0", 0, tmp_path / "k", False)
    assert n0["kept_all"] and n0["cost"] == pytest.approx(0.10)
