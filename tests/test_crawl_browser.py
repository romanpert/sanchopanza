"""Crawl's line only where there is a browser: `SANCHOPANZA_CRAWL_LINE_AT=browser`.

In the h2h confirmations (2026-10-06) the line spoke at the prompt in 46 GAIA sessions, 10 BCP
and 3 LongBench sessions, none of which had a browser tool, naming `browser_evaluate` to an agent
that did not have it (and twice on a local file). In browser mode the line comes with the result
of the session's first `browser_navigate` or `browser_evaluate`, once, and only when the request
gathers (`GATHERS`, read from the session's transcript); a session with no browser never runs
the hook for it. Off by default: SessionStart and `LINE_AT=prompt` stay as measured. No model.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from sanchopanza.harness import crawl_hook as crawl
from sanchopanza.harness.install_hooks import CRAWL_INSTALL_HOOKS

NAVIGATE = "mcp__playwright__browser_navigate"
EVALUATE = "mcp__playwright__browser_evaluate"
GATHER = "How many products are listed across all pages of the shop?"
ACT = "Log in and add the blue mug to the cart."


def _transcript(tmp_path: Path, prompt: str | None) -> Path:
    path = tmp_path / "t.jsonl"
    lines = [{"type": "system", "subtype": "init"}]
    if prompt is not None:
        lines.append({"type": "user", "message": {"role": "user", "content": prompt}})
    lines.append({"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "x", "content": "count every page"}]}})  # fmt: skip
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return path


def _env(tmp_path: Path, **more: str) -> dict[str, str]:
    return {"SANCHOPANZA_CRAWL_LINE_AT": "browser", "SANCHOPANZA_CRAWL_DIR": str(tmp_path / "c"),
            **more}  # fmt: skip


def _post(tool: str, transcript: Path, session: str = "s1", text: str = "### Page") -> dict:
    return {"hook_event_name": "PostToolUse", "tool_name": tool, "session_id": session,
            "transcript_path": str(transcript), "tool_input": {"url": "https://example.org"},
            "tool_response": [{"type": "text", "text": text}]}  # fmt: skip


def _line(out: dict | None) -> str:
    return ((out or {}).get("hookSpecificOutput") or {}).get("additionalContext") or ""


def test_the_line_comes_with_the_first_navigate_of_a_gathering_request(tmp_path: Path) -> None:
    env, t = _env(tmp_path), _transcript(tmp_path, GATHER)
    first = crawl.handle(_post(NAVIGATE, t), env)
    assert _line(first) == crawl.line_for(env)
    assert first["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert crawl.handle(_post(NAVIGATE, t), env) is None  # once per session
    assert _line(crawl.handle(_post(NAVIGATE, t, session="s2"), env))  # another session


def test_no_line_for_a_request_that_acts(tmp_path: Path) -> None:
    env, t = _env(tmp_path), _transcript(tmp_path, ACT)
    assert crawl.handle(_post(NAVIGATE, t), env) is None


def test_an_unreadable_prompt_still_gets_the_line_where_there_is_a_browser(tmp_path: Path) -> None:
    env = _env(tmp_path)
    assert _line(crawl.handle(_post(NAVIGATE, _transcript(tmp_path, None)), env))
    event = {**_post(NAVIGATE, tmp_path / "missing.jsonl", session="s3")}
    assert _line(crawl.handle(event, env))


def test_no_line_at_session_start_or_prompt_in_browser_mode(tmp_path: Path) -> None:
    env = _env(tmp_path)
    assert crawl.handle({"hook_event_name": "SessionStart"}, env) is None
    prompt = {"hook_event_name": "UserPromptSubmit", "prompt": GATHER}
    assert crawl.handle(prompt, env) is None


def test_other_browser_tools_and_other_tools_do_not_bring_the_line(tmp_path: Path) -> None:
    env, t = _env(tmp_path), _transcript(tmp_path, GATHER)
    for tool in ("mcp__playwright__browser_snapshot", "WebFetch", "Read"):
        assert crawl.handle(_post(tool, t), env) is None


def test_the_first_evaluate_carries_the_line_beside_its_rewritten_result(tmp_path: Path) -> None:
    env = _env(tmp_path, SANCHOPANZA_CRAWL_ECHO="short")
    echoed = ("### Result\n3\n### Ran Playwright code\n```js\nawait page.evaluate('"
              f"{crawl.MARK} async () => 1');\n```")  # fmt: skip
    out = crawl.handle(_post(EVALUATE, _transcript(tmp_path, GATHER), text=echoed), env)
    spec = out["hookSpecificOutput"]
    assert spec["additionalContext"] == crawl.line_for(env)
    assert crawl.ECHO_LINE in spec["updatedToolOutput"][0]["text"]


def test_without_browser_mode_post_tool_use_brings_no_line(tmp_path: Path) -> None:
    t = _transcript(tmp_path, GATHER)
    for env in ({}, {"SANCHOPANZA_CRAWL_LINE_AT": "prompt"}):
        assert crawl.handle(_post(NAVIGATE, t), env) is None


def test_the_line_can_still_be_switched_off(tmp_path: Path) -> None:
    env = _env(tmp_path, SANCHOPANZA_CRAWL_LINE="0")
    assert crawl.handle(_post(NAVIGATE, _transcript(tmp_path, GATHER)), env) is None


@pytest.mark.parametrize(
    "tool", [NAVIGATE, EVALUATE, "mcp__plugin_playwright_playwright__browser_navigate"]
)
def test_install_wires_post_tool_use_on_navigate_and_evaluate(tool: str) -> None:
    assert re.fullmatch(CRAWL_INSTALL_HOOKS["PostToolUse"], tool)
    assert not re.fullmatch(CRAWL_INSTALL_HOOKS["PostToolUse"], "mcp__playwright__browser_snapshot")
