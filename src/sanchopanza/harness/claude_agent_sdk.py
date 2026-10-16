"""Hooks for the Claude Agent SDK (and Claude Code, which shares the protocol).

    from claude_agent_sdk import ClaudeAgentOptions, HookMatcher
    from sanchopanza.harness.claude_agent_sdk import pre_tool_use, post_tool_use

    options = ClaudeAgentOptions(hooks={
        "PreToolUse": [HookMatcher(matcher="Agent|WebSearch|Bash", hooks=[pre_tool_use(guardian)])],
        "PostToolUse": [HookMatcher(matcher="Agent", hooks=[post_tool_use(guardian)])],
    })

Hook input: {"hook_event_name", "tool_name", "tool_input", "tool_response"?}.
Hook output: {"hookSpecificOutput": {"hookEventName", "permissionDecision", ...}}.
This module imports nothing from the SDK, so it is testable without it; `hook_matchers`
builds the matcher objects when the SDK is installed.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

from .generic import Guardian, HarnessConfig, ToolCall, Verdict

Hook = Callable[..., Any]
MCP_MATCHER = "^mcp__"  # every MCP tool, as Claude Code names them: mcp__<server>__<tool>


def to_hook_output(event: str, verdict: Verdict) -> dict[str, Any]:
    if verdict.action == "allow":
        return {}
    if verdict.action == "deny":
        return {
            "hookSpecificOutput": {
                "hookEventName": event,
                "permissionDecision": "deny",
                "permissionDecisionReason": verdict.reason,
            }
        }
    return {
        "hookSpecificOutput": {
            "hookEventName": event,
            "permissionDecision": "allow",
            "permissionDecisionReason": verdict.reason,
            "updatedInput": dict(verdict.arguments or {}),
        }
    }


def pre_tool_use(guardian: Guardian) -> Hook:
    async def hook(input_data: dict[str, Any], _tool_use_id: Any = None, _context: Any = None):
        event = str(input_data.get("hook_event_name", "PreToolUse"))
        name = str(input_data.get("tool_name", ""))
        arguments = dict(input_data.get("tool_input") or {})
        call = ToolCall(name=name, arguments=arguments, event=event,
                        record=_record(guardian, input_data, name, arguments))  # fmt: skip
        return to_hook_output(event, await guardian.before_tool(call))

    return hook


def _record(guardian: Guardian, input_data: Mapping[str, Any], name: str,
            arguments: Mapping[str, Any]) -> str:  # fmt: skip
    """The session so far, from the transcript, for a call the MCP guard judges; else "". A
    transcript that cannot be read, or a bug here, is journaled once per guardian and the call
    is judged alone: it never escapes the hook."""
    config = guardian.config
    if not config.guards_mcp(name):
        return ""
    from . import mcp_guard

    def warn(message: str) -> None:
        said = guardian.__dict__.setdefault("_mcp_warned", set())
        if message in said:
            return
        said.add(message)
        guardian.squire.journal.record("warning", {"message": f"mcp guard: {message}",
                                                   "tool": name[:200]})  # fmt: skip

    try:
        return mcp_guard.record_from_transcript(
            input_data.get("transcript_path") or None, name, arguments,
            tool_use_id=str(input_data.get("tool_use_id") or ""),
            limit=config.mcp_record_chars, on_error=warn)  # fmt: skip
    except Exception as error:  # noqa: BLE001 - the record is an aid; the decision still runs
        warn(f"record failed, the call judged alone ({error.__class__.__name__})")
        return ""


def pre_matcher(config: HarnessConfig) -> str:
    """The PreToolUse matcher for `config`: its tool names, and every MCP tool when the MCP
    guard is on (which of them it judges is decided per call, `HarnessConfig.guards_mcp`).

    Claude Code (2.1.287) reads a matcher of only letters, digits, `_` and `|` as a list of exact
    names, and anything else as an unanchored regex (`new RegExp(m).test(name)`): so with MCP the
    names are anchored, or `Task` would match TaskCreate and `Bash` BashOutput. Without MCP the
    matcher stays the plain list, byte for byte."""
    names = sorted(config.delegate_tools | config.search_tools | config.shell_tools)
    pattern = "|".join(re.escape(n) for n in names)
    return f"^(?:{pattern})$|{MCP_MATCHER}" if config.guard_mcp else pattern


def post_tool_use(guardian: Guardian) -> Hook:
    async def hook(input_data: dict[str, Any], _tool_use_id: Any = None, _context: Any = None):
        event = str(input_data.get("hook_event_name", "PostToolUse"))
        call = ToolCall(
            name=str(input_data.get("tool_name", "")),
            arguments=dict(input_data.get("tool_input") or {}),
            event=event,
        )
        note = await guardian.after_tool(call, input_data.get("tool_response"))
        if not note:
            return {}
        output: dict[str, Any] = {"hookSpecificOutput": {"hookEventName": event}}
        if note.context:
            output["hookSpecificOutput"]["additionalContext"] = note.context
        # The operator's copy travels outside `hookSpecificOutput`, because a PostToolUse
        # hook cannot replace the tool result: `additionalContext` is the only channel to
        # the model, and it is the one the suspect text is best placed to talk over.
        if note.user:
            output["systemMessage"] = note.user
        return output

    return hook


def hook_matchers(guardian: Guardian) -> dict[str, list[Any]]:
    """The `hooks=` mapping for `ClaudeAgentOptions`. Requires the SDK to be installed."""
    from claude_agent_sdk import HookMatcher

    c = guardian.config
    pre = pre_matcher(c)
    post = "|".join(sorted(c.after_tools()))
    return {
        "PreToolUse": [HookMatcher(matcher=pre, hooks=[pre_tool_use(guardian)])],
        "PostToolUse": [HookMatcher(matcher=post, hooks=[post_tool_use(guardian)])],
    }
