"""The long-chain runner's pure parts (long-session pre-mortem, free verification item 1): the
meter against B2's stored transcripts, the grade against B2's stored grades, the stop rules,
the gate and the statistics, and candor in observe mode. No Docker, no network, no `claude`."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import sys
from typing import Any

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADOPT = ROOT / "benchmarks" / "adopt"
B2 = pathlib.Path.home() / ".cache" / "sanchopanza" / "adopt" / "runs" / "pydantic__pydantic-long40-1"
OURS = ("run", "long", "docker_env", "perbug", "long_run", "long_call", "long_guard",
        "long_report", "arm_files", "hook_env", "meter", "carry", "chains", "related", "masking")


@pytest.fixture(scope="module")
def mods():  # type: ignore[no-untyped-def]
    for name in OURS:
        sys.modules.pop(name, None)
    sys.path.insert(0, str(ADOPT))
    import long_guard  # puts memory_carry and benchmarks on the path
    import long_report

    import carry
    import meter

    yield {"carry": carry, "guard": long_guard, "report": long_report, "meter": meter}
    sys.path.remove(str(ADOPT))
    for name in OURS:
        sys.modules.pop(name, None)


# ---- meter ---------------------------------------------------------------------------------------


def _assistant(mid: str, out: int, w5: int = 0, w1: int = 100, side: bool = False) -> str:
    usage = {"input_tokens": 2, "output_tokens": out, "cache_read_input_tokens": 1000,
             "cache_creation_input_tokens": w5 + w1,
             "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1}}
    return json.dumps({"type": "assistant", "isSidechain": side, "message": {
        "id": mid, "model": "claude-sonnet-5-5", "usage": usage, "content": []}})  # fmt: skip


def test_requests_are_deduplicated_by_message_id_and_the_last_line_wins(mods) -> None:  # type: ignore[no-untyped-def]
    found = mods["meter"].requests_in([_assistant("m1", 10), _assistant("m1", 30),
                                       _assistant("m2", 5)])  # fmt: skip
    assert [(r.id, r.output) for r in found] == [("m1", 30), ("m2", 5)]


def test_five_minute_and_one_hour_writes_are_priced_apart(mods) -> None:  # type: ignore[no-untyped-def]
    meter = mods["meter"]
    (five,) = meter.requests_in([_assistant("a", 0, w5=1_000_000, w1=0)])
    (hour,) = meter.requests_in([_assistant("b", 0, w5=0, w1=1_000_000)])
    read = 1000 * 0.3 / 1e6
    assert five.cost(meter.OWNER_RATES) == pytest.approx(3.75 + read + 6e-6)
    assert hour.cost(meter.OWNER_RATES) == pytest.approx(6.0 + read + 6e-6)


def test_model_usage_the_transcript_lacks_is_unlogged_and_counted(mods) -> None:  # type: ignore[no-untyped-def]
    meter = mods["meter"]
    found = meter.requests_in([_assistant("a", 100)])
    usage = {"claude-sonnet-5-5": {"inputTokens": 2, "outputTokens": 9100,
                                   "cacheReadInputTokens": 161_000,
                                   "cacheCreationInputTokens": 100}}  # fmt: skip
    out = meter.reconcile(found, usage, meter.OWNER_RATES)
    assert out["unlogged"]["claude-sonnet-5-5"]["outputTokens"] == 9000
    assert out["unlogged_usd"] == pytest.approx((9000 * 15 + 160_000 * 0.3) / 1e6)


def test_a_first_request_writing_over_50k_is_flagged(mods) -> None:  # type: ignore[no-untyped-def]
    meter = mods["meter"]
    assert meter.first_write_flags(meter.requests_in([_assistant("a", 1, w1=60_000)]))["flagged"]
    assert not meter.first_write_flags(meter.requests_in([_assistant("a", 1, w1=900)]))["flagged"]


B2_COST = {"N": 8.74, "S": 7.32, "Sm": 6.37}  # dev-log, "Phase B2", at Claude Code's 2/10


@pytest.mark.skipif(not B2.exists(), reason="B2's run folders are not on this machine")
@pytest.mark.parametrize("arm", ["N", "S", "Sm"])
def test_the_meter_reproduces_b2_from_its_transcripts_call_by_call(mods, arm: str) -> None:  # type: ignore[no-untyped-def]
    meter = mods["meter"]
    final = {r.id: r for r in meter.transcript_requests(B2 / arm / "transcript.jsonl")}
    before: dict[str, Any] = {}
    total, unlogged = 0.0, 0.0
    for k in range(1, 41):
        lines = (B2 / arm / f"stream-{k}.jsonl").read_text(encoding="utf-8").splitlines()
        mine = tuple(final[r.id] for r in meter.requests_in(lines) if r.id in final)
        usage = next(json.loads(x) for x in reversed(lines) if '"type":"result"' in x)["modelUsage"]
        out = meter.reconcile(mine, meter.usage_delta(usage, before), meter.CLAUDE_CODE_RATES)
        total, unlogged, before = total + out["total_usd"], unlogged + out["unlogged_usd"], usage
    assert total == pytest.approx(B2_COST[arm], rel=0.02)
    # the compaction calls are what the transcripts leave out: none in N, two in S, four in Sm
    assert (unlogged == 0) == (arm == "N")


@pytest.mark.skipif(not B2.exists(), reason="B2's run folders are not on this machine")
def test_b2_at_the_owners_prices_is_one_and_a_half_times_its_cost_usd(mods) -> None:  # type: ignore[no-untyped-def]
    meter = mods["meter"]
    found = meter.transcript_requests(B2 / "N" / "transcript.jsonl")
    owner = sum(r.cost(meter.OWNER_RATES) for r in found)
    assert owner == pytest.approx(1.5 * B2_COST["N"], rel=0.02)


# ---- grade ---------------------------------------------------------------------------------------


@pytest.mark.skipif(not B2.exists(), reason="B2's run folders are not on this machine")
def test_b2s_stored_grades_give_the_documented_strict_and_per_bug_counts(mods) -> None:  # type: ignore[no-untyped-def]
    counts = {arm: mods["report"].stored_counts(json.loads(
        (B2 / arm / "grade.json").read_text(encoding="utf-8"))) for arm in ("N", "S", "Sm")}
    assert {a: c["strict"] for a, c in counts.items()} == {"N": 27, "S": 30, "Sm": 0}
    assert {a: c["f2p"] for a, c in counts.items()} == {"N": 27, "S": 30, "Sm": 26}


@pytest.mark.skipif(not B2.exists(), reason="B2's run folders are not on this machine")
def test_b2s_n_would_not_pass_the_gate_on_the_share_above_200k(mods) -> None:  # type: ignore[no-untyped-def]
    grade = {"resolved": 27, "bugs_total": 40}
    row = mods["report"].gate_row(B2 / "N", grade)
    assert row["peak"] > 250_000 and row["requests"] == 225 and row["compactions"] == 0
    assert row["checks"]["share_over_200k"] is False  # the prereg's 38 %
    assert row["window"]["bound"] == "at least" and row["pass"] is not True


# ---- stop rules ----------------------------------------------------------------------------------


def test_limit_events_rejected_and_warning_are_read_and_allowed_is_not(mods) -> None:  # type: ignore[no-untyped-def]
    guard = mods["guard"]
    event = {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}
    assert guard.limit_event(event) == "limit"
    assert guard.limit_event({**event, "rate_limit_info": {"status": "allowed_warning"}}) == \
        "warning"  # fmt: skip
    assert guard.limit_event({**event, "rate_limit_info": {"status": "allowed"}}) == ""
    assert guard.limit_event({"type": "result", "api_error_status": 429}) == "limit"


def test_limit_flag_and_stop_file_stop_the_next_call(mods, tmp_path: pathlib.Path) -> None:  # type: ignore[no-untyped-def]
    guard, flag = mods["guard"], tmp_path / "LIMIT.flag"
    assert guard.stop_reason(tmp_path, flag) == ""
    guard.raise_limit(flag, "429 in chain c")
    assert "LIMIT" in guard.stop_reason(tmp_path, flag)
    flag.unlink()
    (tmp_path / "STOP").write_text("x", encoding="utf-8")
    assert "STOP" in guard.stop_reason(tmp_path, flag)


INIT = {"version": "2.1.287", "model": "claude-sonnet-5-5", "permission_mode": "default",
        "api_key_source": "none", "mcp": {"sanchopanza": "connected"}}  # fmt: skip


def test_init_invariants(mods) -> None:  # type: ignore[no-untyped-def]
    guard = mods["guard"]
    s = guard.Expect("2.1.287", "claude-sonnet-5-5", "default", ("sanchopanza",))
    assert guard.init_breaks(INIT, s) == ()
    assert guard.init_breaks({**INIT, "permission_mode": "auto"}, s)  # seen 2026-10-05
    assert guard.init_breaks({**INIT, "version": "2.1.288"}, s)
    assert guard.init_breaks({**INIT, "mcp": {"sanchopanza": "failed"}}, s)  # B2's S, unseen
    n = guard.Expect("2.1.287", "claude-sonnet-5-5", "default")
    assert guard.init_breaks(INIT, n)  # a server in N that nobody installed
    assert guard.init_breaks({}, n) == ("no init event",)


def test_permission_modes_must_be_one_and_never_bypass(mods) -> None:  # type: ignore[no-untyped-def]
    guard = mods["guard"]
    assert guard.permission_breaks({"N/1": "default", "S/1": "default"}) == ()
    assert guard.permission_breaks({"N/1": "default", "S/1": "auto"})
    assert guard.permission_breaks({"N/1": "bypassPermissions"})


def test_first_request_prefixes(mods) -> None:  # type: ignore[no-untyped-def]
    guard = mods["guard"]
    assert guard.prefix_breaks({"N": 30_000, "Ne": 30_020, "S": 31_000}) == ()
    assert guard.prefix_breaks({"N": 30_000, "Ne": 30_200})
    assert guard.prefix_breaks({"N": 30_000, "S": 30_000})  # S installed nothing?


def test_resume_policy_and_a_vanished_diff(mods) -> None:  # type: ignore[no-untyped-def]
    guard = mods["guard"]
    assert guard.resume_decision(0, "d", "d", "dev") == "retry"
    assert guard.resume_decision(2, "d", "d", "dev") == "continue"
    assert guard.resume_decision(0, "d", "d2", "held") == "set-aside"
    assert guard.diff_vanished("diff --git a", "") and not guard.diff_vanished("", "")


def test_midnight_and_jev_outage(mods) -> None:  # type: ignore[no-untyped-def]
    guard = mods["guard"]
    assert guard.crosses_midnight(dt.datetime(2026, 10, 6, 22, 0), 3.0)
    assert not guard.crosses_midnight(dt.datetime(2026, 10, 6, 9, 0), 3.0)
    null = {"provider": "null", "error": None}
    assert guard.jev_outage([null] * 10) and not guard.jev_outage([null] * 9)
    assert not guard.jev_outage([*[null] * 9, {"provider": "jev", "error": None}])


def test_a_pid_is_killed_only_when_command_line_and_creation_date_match(mods) -> None:  # type: ignore[no-untyped-def]
    guard, killed = mods["guard"], []
    status = {"pid": 42, "command_line": "python long_run.py run", "created": "t0"}
    other = {"command_line": "python something-else.py", "created": "t0"}
    assert "another process" in guard.verified_kill(status, lambda _p: other, killed.append)
    assert killed == []
    same = {"command_line": "python long_run.py run", "created": "t0"}
    guard.verified_kill(status, lambda _p: same, lambda pid: killed.append(pid) or 0)
    assert killed == [42]


# ---- carry's init reader, now public ------------------------------------------------------------


def test_carry_init_facts_names_each_mcp_server_with_its_status(mods) -> None:  # type: ignore[no-untyped-def]
    event = {"type": "system", "subtype": "init", "model": "m", "claude_code_version": "2.1.287",
             "permissionMode": "default", "apiKeySource": "none",
             "mcp_servers": [{"name": "sanchopanza", "status": "failed"}], "plugins": []}
    facts = mods["carry"].init_facts(event)
    assert facts["mcp"] == {"sanchopanza": "failed"} and facts["mcp_servers"] == 1
    assert facts["permission_mode"] == "default" and facts["version"] == "2.1.287"


# ---- statistics ----------------------------------------------------------------------------------


def test_holm_steps_down(mods) -> None:  # type: ignore[no-untyped-def]
    holm = mods["report"].holm
    assert holm({"S-N": 0.01, "S-Ne": 0.04}) == {"S-N": True, "S-Ne": True}
    assert holm({"S-N": 0.03, "S-Ne": 0.04}) == {"S-N": False, "S-Ne": False}


def test_noninferiority_at_minus_five_points(mods) -> None:  # type: ignore[no-untyped-def]
    report = mods["report"]
    same = [[(True, True)] * 40 + [(False, False)] * 20 for _ in range(12)]
    assert report.noninferior(same)
    worse = [[(False, True)] * 10 + [(True, True)] * 50 for _ in range(12)]
    assert not report.noninferior(worse)
    diff, low, high = report.cluster_bootstrap(worse, reps=500)
    assert diff == pytest.approx(-10 / 60) and low <= diff <= high


def test_cost_ratio_is_the_paired_geometric_mean(mods) -> None:  # type: ignore[no-untyped-def]
    out = mods["report"].cost_ratio([(8.0, 10.0), (16.0, 20.0), (4.0, 5.0)])
    assert out["ratio"] == pytest.approx(0.8) and out["n"] == 3


# ---- loss ----------------------------------------------------------------------------------------


def _line(**entry: Any) -> str:
    return json.dumps(entry)


def test_rereads_after_a_compaction_and_send_backs_are_counted(mods, tmp_path) -> None:  # type: ignore[no-untyped-def]
    def tool(mid: str, name: str, **arg: str) -> str:
        return _line(type="assistant", message={"id": mid, "model": "claude-sonnet-5-5",
                     "usage": {"input_tokens": 1, "output_tokens": 1000},
                     "content": [{"type": "tool_use", "name": name, "input": arg}]})  # fmt: skip

    path = tmp_path / "t.jsonl"
    path.write_text("\n".join([
        tool("a", "Read", file_path="pkg/a.py"),
        _line(type="system", subtype="compact_boundary"),
        tool("b", "Bash", command="sed -n 1,40p pkg/a.py"),
        tool("c", "Read", file_path="pkg/new.py"),
        _line(type="user", message={"content": "Stop hook feedback:\nnot done"}),
        tool("d", "Bash", command="ls"),
        _line(type="user", message={"content": "Bug 4 of this session."}),
        tool("e", "Bash", command="ls")]), encoding="utf-8")  # fmt: skip
    report = mods["report"]
    assert report.rereads(path)["rereads"] == 1
    back = report.send_backs(path)
    assert back["blocks"] == 1 and back["requests"] == 1
    assert back["owner_usd"] == pytest.approx((3 + 15_000) / 1e6)


# ---- candor in observe mode (pre-mortem 16) ------------------------------------------------------


def test_candor_observe_a_forced_critical_finding_writes_no_lock_and_no_block(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sanchopanza.candor import lock as lock_mod
    from sanchopanza.harness import candor_hook

    monkeypatch.setenv("SANCHOPANZA_CANDOR_LOCK", str(tmp_path / "lock.json"))
    monkeypatch.setenv("SANCHOPANZA_CANDOR_DIR", str(tmp_path / "candor"))
    monkeypatch.setenv("SANCHOPANZA_CANDOR_MODE", "observe")
    monkeypatch.delenv("SANCHOPANZA_CANDOR_JUDGE", raising=False)
    tamper = {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "Edit",
              "tool_input": {"file_path": ".claude/settings.json"}}  # critical: tamper
    assert candor_hook.handle(tamper) == {}
    assert not lock_mod.read().engaged and not (tmp_path / "lock.json").exists()
    later = {**tamper, "tool_name": "Read", "tool_input": {"file_path": "src/p.py"}}
    assert "permissionDecision" not in json.dumps(candor_hook.handle(later))
