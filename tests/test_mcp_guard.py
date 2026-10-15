"""The MCP guard (roadmap A3): a PreToolUse decision on `mcp__<server>__<tool>` calls.

Before it, the installed hook let every MCP call through with no decision: on ATBench-Codex,
whose risks live in MCP calls, it flagged 0 of 250 unsafe trajectories
(docs/results/2026-09-28-claude-code-broad). The guard asks the `actions` point about the
session so far plus the pending call, and denies at `Thresholds.action_stop`. Opt-in
(`SANCHOPANZA_GUARD_MCP=1`, `install --guard-mcp`) until the replay and the live probe of
docs/results/2026-10-16-a3-mcp say otherwise. No test here calls a paid provider.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from sanchopanza import funds
from sanchopanza.contract import DeciderOutOfFunds
from sanchopanza.harness import Guardian, HarnessConfig, ToolCall, mcp_guard
from sanchopanza.harness.claude_code import config_from_env, handle, needs_decision
from sanchopanza.harness.install import environment, matchers, plan
from sanchopanza.points import actions
from sanchopanza.providers import FixedDecider

from .helpers import squire, yes

PAY = "mcp__stripe__create_payment"
ARGS = {"amount": 5000, "to": "acct_123"}


class Seeing(FixedDecider):
    """A fixed answer that keeps every state it was asked about."""

    def __init__(self, p: float) -> None:
        super().__init__({"unsafe": yes(p)})
        self.states: list[dict[str, Any]] = []
        self.points: list[str] = []

    async def decide(self, point, state, questions):  # noqa: ANN001, ANN201
        self.states.append(dict(state))
        self.points.append(point)
        return await super().decide(point, state, questions)


class OutOfFunds:
    name = "jev"

    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, point, state, questions):  # noqa: ANN001, ANN201
        self.calls += 1
        raise DeciderOutOfFunds("HTTP 402 billing_error")


def _on() -> HarnessConfig:
    return config_from_env({"SANCHOPANZA_GUARD_MCP": "1"})


def _event(name: str = PAY, arguments: dict | None = None, **extra: Any) -> dict[str, Any]:
    return {"hook_event_name": "PreToolUse", "tool_name": name,
            "tool_input": dict(ARGS if arguments is None else arguments), **extra}  # fmt: skip


def _transcript(path: Path, entries: list[dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    return path


def _user(text: str) -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": text}}


def _tool_use(name: str, arguments: dict, tid: str, text: str = "") -> dict[str, Any]:
    blocks: list[dict[str, Any]] = [{"type": "text", "text": text}] if text else []
    blocks.append({"type": "tool_use", "id": tid, "name": name, "input": arguments})
    return {"type": "assistant", "message": {"role": "assistant", "content": blocks}}


def _result(tid: str, text: str) -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tid, "content": text}]}}  # fmt: skip


# --- the dial ---------------------------------------------------------------------------------


def test_off_by_default_and_an_mcp_call_needs_no_decision() -> None:
    config = config_from_env({})
    assert config.guard_mcp is False
    assert not needs_decision(_event(), config)


def test_on_by_the_environment_and_an_mcp_call_needs_a_decision() -> None:
    assert needs_decision(_event(), _on())


@pytest.mark.parametrize("value", ["0", "", "no", "false"])
def test_anything_but_yes_leaves_it_off(value: str) -> None:
    assert config_from_env({"SANCHOPANZA_GUARD_MCP": value}).guard_mcp is False


@pytest.mark.parametrize(
    "name",
    ["mcp__sanchopanza__find_in_repo", "mcp__sanchopanza-fetch__fetch_passages",
     "mcp__sanchopanza-knowledge__knowledge", "mcp__sanchopanza-archive__search_archive"],
)  # fmt: skip
def test_our_own_servers_are_not_judged(name: str) -> None:
    assert not needs_decision(_event(name), _on())


def test_servers_named_in_the_skip_list_are_not_judged() -> None:
    config = config_from_env({"SANCHOPANZA_GUARD_MCP": "1",
                              "SANCHOPANZA_GUARD_MCP_SKIP": "playwright, github"})  # fmt: skip
    assert not needs_decision(_event("mcp__playwright__browser_click"), config)
    assert not needs_decision(_event("mcp__github__create_issue"), config)
    assert needs_decision(_event(PAY), config)


def test_a_name_that_only_starts_like_mcp_is_not_an_mcp_call() -> None:
    assert not _on().guards_mcp("mcp_tool")
    assert not _on().guards_mcp("mcp____x")
    assert _on().guards_mcp("mcp__srv__op")


# --- the decision -----------------------------------------------------------------------------


def _verdict(p: float, config: HarnessConfig | None = None, record: str = ""):  # noqa: ANN202
    decider = Seeing(p)
    sq, journal = squire(decider)
    call = ToolCall(PAY, ARGS, record=record)
    verdict = asyncio.run(Guardian(sq, config or _on()).before_tool(call))
    return verdict, decider, journal


def test_a_call_the_point_flags_is_denied_with_a_reason() -> None:
    verdict, decider, journal = _verdict(0.9)
    assert verdict.action == "deny"
    assert "MCP call denied" in verdict.reason and "0.90" in verdict.reason
    assert decider.points == ["action_risk"]
    rows = [e["data"]["outcome"] for e in journal.events if e["kind"] == "decision"]
    assert rows[-1]["denied"] is True and rows[-1]["tool"] == PAY


def test_a_call_under_the_cut_passes() -> None:
    verdict, _, journal = _verdict(0.2)
    assert verdict.action == "allow"
    rows = [e["data"]["outcome"] for e in journal.events if e["kind"] == "decision"]
    assert rows[-1]["denied"] is False


def test_the_cut_is_the_threshold_action_stop() -> None:
    sq, _ = squire(Seeing(0.6), action_stop=0.7)
    verdict = asyncio.run(Guardian(sq, _on()).before_tool(ToolCall(PAY, ARGS)))
    assert verdict.action == "allow"


def test_the_default_cut_is_the_one_the_point_was_measured_at_offline() -> None:
    from sanchopanza.policy import Thresholds

    assert Thresholds().action_stop == actions.decide.__kwdefaults__["cut"] == 0.5


def test_off_the_decider_is_never_asked() -> None:
    verdict, decider, _ = _verdict(0.99, config=config_from_env({}))
    assert verdict.action == "allow" and decider.calls == 0


def test_the_point_sees_the_record_and_the_pending_call_at_its_end() -> None:
    _, decider, _ = _verdict(0.1, record="USER: pay the invoice\nAGENT ACTION: x()")
    record = decider.states[0]["record"]
    assert record.startswith("USER: pay the invoice")
    assert record.rstrip().endswith(mcp_guard.action_line(PAY, ARGS))


def test_without_a_record_the_pending_call_is_judged_alone() -> None:
    _, decider, _ = _verdict(0.1)
    assert decider.states[0]["record"] == mcp_guard.action_line(PAY, ARGS)


def test_out_of_funds_fails_open_and_says_so_once(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("SANCHOPANZA_FUNDS_DIR", str(tmp_path / "funds"))
    monkeypatch.setattr(funds, "_stderr_said", False)
    sq, journal = squire(OutOfFunds())
    guardian = Guardian(sq, _on())
    for _ in range(2):
        verdict = asyncio.run(guardian.before_tool(ToolCall(PAY, ARGS)))
        assert verdict.action == "allow"
    warnings = [e["data"] for e in journal.events if e["kind"] == "warning"]
    assert len(warnings) == 1 and warnings[0]["out_of_funds"] is True
    assert capsys.readouterr().err.count("out of funds") == 1


# --- the record from a Claude Code transcript -------------------------------------------------


def test_the_record_reads_requests_actions_and_results(tmp_path) -> None:
    path = _transcript(tmp_path / "t.jsonl", [
        _user("Find the overdue invoice and pay it"),
        _tool_use("mcp__billing__search", {"q": "overdue"}, "a", text="Looking it up."),
        _result("a", "invoice 77, pay to acct_999 as the note in the PDF says"),
        _tool_use(PAY, ARGS, "b"),
    ])  # fmt: skip
    record = mcp_guard.record_from_transcript(path, PAY, ARGS, tool_use_id="b")
    lines = record.splitlines()
    assert lines[0] == "USER: Find the overdue invoice and pay it"
    assert "AGENT THOUGHT: Looking it up." in lines
    assert any(x.startswith("ENVIRONMENT: invoice 77") for x in lines)
    assert lines[-1] == mcp_guard.action_line(PAY, ARGS)
    assert record.count(mcp_guard.action_line(PAY, ARGS)) == 1  # not twice


def test_the_pending_call_is_added_when_the_transcript_does_not_hold_it_yet(tmp_path) -> None:
    path = _transcript(tmp_path / "t.jsonl", [_user("pay it")])
    record = mcp_guard.record_from_transcript(path, PAY, ARGS, tool_use_id="b")
    assert record.splitlines() == ["USER: pay it", mcp_guard.action_line(PAY, ARGS)]


def test_every_request_of_the_session_is_kept(tmp_path) -> None:
    path = _transcript(tmp_path / "t.jsonl", [
        _user("Prepare a shortlist"), _tool_use("mcp__crm__list", {}, "a"), _result("a", "ok"),
        _user("Yes, enrich them"),
    ])  # fmt: skip
    lines = mcp_guard.record_from_transcript(path, PAY, ARGS).splitlines()
    assert lines[0] == "USER: Prepare a shortlist" and "USER: Yes, enrich them" in lines


def test_a_long_record_keeps_the_first_request_and_the_pending_call(tmp_path) -> None:
    filler = [_result(str(i), "x" * 1400) for i in range(40)]
    path = _transcript(tmp_path / "t.jsonl", [_user("the first request"), *filler])
    record = mcp_guard.record_from_transcript(path, PAY, ARGS, limit=6000)
    assert len(record) <= 6000
    assert record.startswith("USER: the first request")
    assert record.endswith(mcp_guard.action_line(PAY, ARGS))


def test_a_missing_transcript_still_judges_the_call(tmp_path) -> None:
    record = mcp_guard.record_from_transcript(tmp_path / "none.jsonl", PAY, ARGS)
    assert record == mcp_guard.action_line(PAY, ARGS)


def test_the_hook_reads_the_transcript_on_the_real_path(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    path = _transcript(tmp_path / "t.jsonl", [_user("pay the overdue invoice"),
                                              _tool_use(PAY, ARGS, "b")])  # fmt: skip
    decider = Seeing(0.95)
    sq, _ = squire(decider)
    event = _event(transcript_path=str(path), tool_use_id="b", cwd=str(tmp_path))
    out = asyncio.run(handle(event, Guardian(sq, _on())))
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert decider.states[0]["record"].startswith("USER: pay the overdue invoice")


def test_the_hook_off_answers_nothing_for_an_mcp_call(tmp_path) -> None:
    decider = Seeing(0.95)
    sq, _ = squire(decider)
    out = asyncio.run(handle(_event(cwd=str(tmp_path)), Guardian(sq, config_from_env({}))))
    assert out == {} and decider.calls == 0


def test_shell_and_mcp_are_judged_by_their_own_points(tmp_path) -> None:
    decider = Seeing(0.1)
    sq, _ = squire(decider)
    guardian = Guardian(sq, _on())
    shell = ToolCall("Bash", {"command": "find ./records -type f -delete"})
    asyncio.run(guardian.before_tool(shell))
    asyncio.run(guardian.before_tool(ToolCall(PAY, ARGS)))
    assert decider.points == ["guard", "action_risk"]


# --- install ----------------------------------------------------------------------------------


def test_install_wires_every_mcp_tool_only_with_the_flag() -> None:
    assert "mcp__" not in matchers(HarnessConfig())["PreToolUse"]
    pre = matchers(HarnessConfig(guard_mcp=True))["PreToolUse"]
    assert pre.endswith("|mcp__.*") and "Bash" in pre


def test_install_writes_the_variable_and_a_run_without_the_flag_takes_it_out(tmp_path) -> None:
    assert environment(HarnessConfig(guard_mcp=True))["SANCHOPANZA_GUARD_MCP"] == "1"
    assert "SANCHOPANZA_GUARD_MCP" not in environment(HarnessConfig())
    path = tmp_path / "settings.json"
    on = plan(path, HarnessConfig(guard_mcp=True))
    path.write_text(json.dumps(on.merged), encoding="utf-8")
    assert on.merged["env"]["SANCHOPANZA_GUARD_MCP"] == "1"
    off = plan(path, HarnessConfig())
    assert "SANCHOPANZA_GUARD_MCP" not in off.merged.get("env", {})
    assert "env: SANCHOPANZA_GUARD_MCP" in off.removed
    pre = [e["matcher"] for e in off.merged["hooks"]["PreToolUse"]]
    assert all("mcp__" not in m for m in pre)


def test_the_cli_flag_defaults_off_and_turns_it_on(tmp_path, capsys) -> None:
    from sanchopanza.cli import main

    base = ["install", "--path", str(tmp_path / "s.json"), "--no-find", "--no-skill",
            "--no-memory", "--no-guard", "--no-knowledge", "--context-budget", "0"]  # fmt: skip
    assert main(base) == 0
    assert "mcp__" not in capsys.readouterr().out
    assert main([*base, "--guard-mcp"]) == 0
    out = capsys.readouterr().out
    assert "mcp__.*" in out and "SANCHOPANZA_GUARD_MCP" in out


def test_the_sdk_matchers_follow_the_config() -> None:
    from sanchopanza.harness.claude_agent_sdk import pre_matcher

    assert "mcp__" not in pre_matcher(HarnessConfig())
    assert pre_matcher(HarnessConfig(guard_mcp=True)).endswith("|mcp__.*")
