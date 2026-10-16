"""The MCP guard after the call (W17): a PostToolUse decision on what an MCP tool returned.

A3's PreToolUse guard reads the session up to the pending call, never its result. On
ATBench-Codex the offline reference, whose record ends on the last tool result, flagged 33
unsafe trajectories the hook missed, 14 of them a tool that misbehaved in its answer
(docs/results/2026-10-16-a3-mcp; benchmarks/a3_mcp/w17_ceiling.py). This check asks the same
`actions` point with the result last, at its own cut (`Thresholds.action_result_stop`), and on a
flag answers Claude Code with `decision: block` (the reason reaches the model), a notice to the
operator, and, with `withhold`, the result replaced (`updatedMCPToolOutput`, MCP tools only).
Opt-in (`SANCHOPANZA_GUARD_MCP_POST`, `install --guard-mcp-post`). No test calls a paid provider.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import pytest

from sanchopanza.harness import Guardian, HarnessConfig, ToolCall, mcp_guard
from sanchopanza.harness.claude_code import config_from_env, handle, needs_decision
from sanchopanza.harness.install import environment, matchers, plan
from sanchopanza.policy import Thresholds
from sanchopanza.providers import FixedDecider

from .helpers import squire
from .test_mcp_guard import ARGS, OFF_MATCHER, PAY, Seeing, _result, _tool_use, _transcript, _user

RESULT = '{"status": "success", "requested_target": "staging", "actual_target": "production"}'


def _post_on(value: str = "1") -> HarnessConfig:
    return config_from_env({"SANCHOPANZA_GUARD_MCP_POST": value})


def _post_event(name: str = PAY, response: Any = RESULT, **extra: Any) -> dict[str, Any]:
    return {"hook_event_name": "PostToolUse", "tool_name": name, "tool_input": dict(ARGS),
            "tool_response": response, **extra}  # fmt: skip


def _note(p: float, config: HarnessConfig | None = None, record: str = "", **cuts: float):  # noqa: ANN202
    decider = Seeing(p)
    sq, journal = squire(decider, **cuts)
    call = ToolCall(PAY, ARGS, event="PostToolUse", record=record)
    note = asyncio.run(Guardian(sq, config or _post_on()).after_tool(call, RESULT))
    return note, decider, journal


# --- the dial ---------------------------------------------------------------------------------


def test_off_by_default_and_an_mcp_result_needs_no_decision() -> None:
    config = config_from_env({})
    assert config.guard_mcp_post is False and config.mcp_post_withhold is False
    assert not needs_decision(_post_event(), config)


def test_on_by_the_environment_and_an_mcp_result_needs_a_decision() -> None:
    config = _post_on()
    assert config.guard_mcp_post is True and config.mcp_post_withhold is False
    assert needs_decision(_post_event(), config)


def test_withhold_turns_it_on_and_replaces_the_result() -> None:
    config = _post_on("withhold")
    assert config.guard_mcp_post is True and config.mcp_post_withhold is True


@pytest.mark.parametrize("value", ["0", "", "no", "false", "maybe"])
def test_anything_else_leaves_it_off(value: str) -> None:
    assert _post_on(value).guard_mcp_post is False


def test_it_is_independent_of_the_check_before_the_call() -> None:
    pre_only = config_from_env({"SANCHOPANZA_GUARD_MCP": "1"})
    assert not needs_decision(_post_event(), pre_only)
    assert _post_on().guards_mcp_result(PAY) and not _post_on().guards_mcp(PAY)


def test_an_empty_result_and_our_own_servers_need_no_decision() -> None:
    assert not needs_decision(_post_event(response=""), _post_on())
    assert not needs_decision(_post_event("mcp__sanchopanza__find_in_repo"), _post_on())
    skip = config_from_env({"SANCHOPANZA_GUARD_MCP_POST": "1",
                            "SANCHOPANZA_GUARD_MCP_SKIP": "stripe"})  # fmt: skip
    assert not needs_decision(_post_event(), skip)


# --- the decision -----------------------------------------------------------------------------


def test_a_result_the_point_flags_blocks_with_a_reason_and_tells_the_operator() -> None:
    note, decider, journal = _note(0.9)
    assert note is not None and "0.90" in note.block and PAY in note.user
    assert note.withhold == ""
    assert decider.points == ["action_risk"]
    rows = [e["data"]["outcome"] for e in journal.events if e["kind"] == "decision"]
    assert rows[-1]["denied"] is True and rows[-1]["after"] is True


def test_a_result_under_the_cut_says_nothing() -> None:
    note, _, journal = _note(0.2)
    assert note is None
    rows = [e["data"]["outcome"] for e in journal.events if e["kind"] == "decision"]
    assert rows[-1]["denied"] is False


def test_the_cut_is_its_own_threshold() -> None:
    assert Thresholds().action_result_stop == 0.5
    flagged, _, _ = _note(0.6, action_stop=0.9, action_result_stop=0.5)
    passed, _, _ = _note(0.6, action_stop=0.5, action_result_stop=0.7)
    assert flagged is not None and passed is None


def test_the_point_reads_the_call_then_its_result_last() -> None:
    _, decider, _ = _note(0.1, record="USER: deploy the worker to staging")
    lines = decider.states[0]["record"].splitlines()
    assert lines[0] == "USER: deploy the worker to staging"
    assert lines[-2] == mcp_guard.action_line(PAY, ARGS)
    assert lines[-1] == mcp_guard.result_line(RESULT)


def test_withhold_replaces_the_result_with_the_reason() -> None:
    note, _, _ = _note(0.9, config=_post_on("withhold"))
    assert note is not None and note.withhold and "production" not in note.withhold
    assert note.block in note.withhold


def test_off_the_decider_is_never_asked() -> None:
    note, decider, _ = _note(0.99, config=config_from_env({}))
    assert note is None and decider.calls == 0


def test_no_answer_is_no_opinion() -> None:
    decider = FixedDecider({})
    sq, _ = squire(decider)
    call = ToolCall(PAY, ARGS, event="PostToolUse")
    assert asyncio.run(Guardian(sq, _post_on()).after_tool(call, RESULT)) is None


# --- the record after the call, from a Claude Code transcript ---------------------------------


def test_the_record_ends_on_the_result_and_holds_the_call_once(tmp_path) -> None:
    path = _transcript(tmp_path / "t.jsonl", [
        _user("deploy the rate limiter to staging"),
        _tool_use("mcp__cf__list", {}, "a"), _result("a", "two workers"),
        _tool_use(PAY, ARGS, "b"),
    ])  # fmt: skip
    record = mcp_guard.record_after_result(path, PAY, ARGS, RESULT, tool_use_id="b")
    lines = record.splitlines()
    assert lines[0] == "USER: deploy the rate limiter to staging"
    assert "ENVIRONMENT: two workers" in lines
    assert lines[-2:] == [mcp_guard.action_line(PAY, ARGS), mcp_guard.result_line(RESULT)]
    assert record.count(mcp_guard.action_line(PAY, ARGS)) == 1


def test_a_transcript_that_already_holds_the_result_does_not_repeat_it(tmp_path) -> None:
    path = _transcript(tmp_path / "t.jsonl", [
        _user("deploy"), _tool_use(PAY, ARGS, "b"), _result("b", RESULT)])  # fmt: skip
    record = mcp_guard.record_after_result(path, PAY, ARGS, RESULT, tool_use_id="b")
    assert record.count("actual_target") == 1 and record.endswith(mcp_guard.result_line(RESULT))


def test_the_result_is_masked_and_capped(tmp_path) -> None:
    token = "ghp_" + "c" * 40
    big = token + " " + "r" * 30_000 + " the tail of the answer"
    record = mcp_guard.record_after_result(None, PAY, ARGS, big)
    assert "ghp_cccc" not in record
    assert len(record.splitlines()[-1]) <= mcp_guard.PENDING_CHARS
    assert record.endswith("the tail of the answer")


def test_the_hook_reads_the_transcript_and_answers_block(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    path = _transcript(tmp_path / "t.jsonl", [_user("deploy to staging"),
                                              _tool_use(PAY, ARGS, "b")])  # fmt: skip
    decider = Seeing(0.95)
    sq, _ = squire(decider)
    event = _post_event(transcript_path=str(path), tool_use_id="b", cwd=str(tmp_path))
    out = asyncio.run(handle(event, Guardian(sq, _post_on())))
    assert out["decision"] == "block" and "0.95" in out["reason"]
    assert PAY in out["systemMessage"]
    assert "updatedMCPToolOutput" not in out.get("hookSpecificOutput", {})
    assert decider.states[0]["record"].startswith("USER: deploy to staging")


def test_the_hook_with_withhold_replaces_the_mcp_output(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    sq, _ = squire(Seeing(0.95))
    out = asyncio.run(handle(_post_event(cwd=str(tmp_path)), Guardian(sq, _post_on("withhold"))))
    replaced = out["hookSpecificOutput"]["updatedMCPToolOutput"]
    assert isinstance(replaced, str) and replaced and "production" not in replaced
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"


def test_the_hook_reads_an_mcp_content_list(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    decider = Seeing(0.1)
    sq, _ = squire(decider)
    content = [{"type": "text", "text": RESULT}]
    asyncio.run(handle(_post_event(response=content, cwd=str(tmp_path)),
                       Guardian(sq, _post_on())))  # fmt: skip
    assert decider.states[0]["record"].endswith(mcp_guard.result_line(RESULT))


def test_pre_and_post_both_on_judge_the_call_and_then_its_result(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    config = config_from_env({"SANCHOPANZA_GUARD_MCP": "1", "SANCHOPANZA_GUARD_MCP_POST": "1"})
    decider = Seeing(0.1)
    sq, _ = squire(decider)
    guardian = Guardian(sq, config)
    pre = {**_post_event(cwd=str(tmp_path)), "hook_event_name": "PreToolUse"}
    pre.pop("tool_response")
    asyncio.run(handle(pre, guardian))
    asyncio.run(handle(_post_event(cwd=str(tmp_path)), guardian))
    ends = [s["record"].splitlines()[-1] for s in decider.states]
    assert ends == [mcp_guard.action_line(PAY, ARGS), mcp_guard.result_line(RESULT)]


# --- install ----------------------------------------------------------------------------------


def test_install_leaves_the_post_matcher_as_it_was_without_the_flag() -> None:
    assert matchers(HarnessConfig())["PostToolUse"] == "Agent|Task"  # byte for byte


@pytest.mark.parametrize(
    ("name", "matched"),
    [("Agent", True), ("Task", True), ("mcp__x__y", True), ("TaskCreate", False),
     ("my_mcp__x", False), ("Read", False)],
)  # fmt: skip
def test_install_with_the_flag_adds_every_mcp_tool_anchored(name: str, matched: bool) -> None:
    post = matchers(HarnessConfig(guard_mcp_post=True))["PostToolUse"]
    assert post == "^(?:Agent|Task)$|^mcp__"
    assert bool(re.search(post, name)) is matched


def test_install_writes_the_variable_and_a_run_without_the_flag_takes_it_out(tmp_path) -> None:
    assert environment(HarnessConfig(guard_mcp_post=True))["SANCHOPANZA_GUARD_MCP_POST"] == "1"
    withhold = HarnessConfig(guard_mcp_post=True, mcp_post_withhold=True)
    assert environment(withhold)["SANCHOPANZA_GUARD_MCP_POST"] == "withhold"
    assert "SANCHOPANZA_GUARD_MCP_POST" not in environment(HarnessConfig())
    path = tmp_path / "settings.json"
    on = plan(path, HarnessConfig(guard_mcp_post=True))
    path.write_text(json.dumps(on.merged), encoding="utf-8")
    off = plan(path, HarnessConfig())
    assert "SANCHOPANZA_GUARD_MCP_POST" not in off.merged.get("env", {})
    post = [e["matcher"] for e in off.merged["hooks"].get("PostToolUse", [])]
    assert all("mcp__" not in m for m in post)


def test_the_cli_flags_default_off_and_turn_it_on(tmp_path, capsys) -> None:
    from sanchopanza.cli import main

    base = ["install", "--path", str(tmp_path / "s.json"), "--no-find", "--no-skill",
            "--no-memory", "--no-guard", "--no-knowledge", "--context-budget", "0"]  # fmt: skip
    assert main(base) == 0
    assert "GUARD_MCP_POST" not in capsys.readouterr().out
    assert main([*base, "--guard-mcp-post"]) == 0
    out = capsys.readouterr().out
    assert '"SANCHOPANZA_GUARD_MCP_POST": "1"' in out and "|^mcp__" in out
    assert main([*base, "--guard-mcp-withhold"]) == 0
    assert '"SANCHOPANZA_GUARD_MCP_POST": "withhold"' in capsys.readouterr().out


def test_the_sdk_matchers_follow_the_config() -> None:
    from sanchopanza.harness.claude_agent_sdk import post_matcher

    assert post_matcher(HarnessConfig()) == "Agent|Task"
    assert post_matcher(HarnessConfig(guard_mcp_post=True)).endswith(")$|^mcp__")
    assert OFF_MATCHER  # the PreToolUse matcher is the other test file's
