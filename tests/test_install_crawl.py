"""`sanchopanza install --crawl`: crawl's two hooks wired once, taken out cleanly, beside other
people's hooks and beside memory's SessionStart entry."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from sanchopanza.harness.crawl_hook import STRATEGY_LINE
from sanchopanza.harness.generic import HarnessConfig
from sanchopanza.harness.install import (
    CRAWL_COMMAND,
    CRAWL_HOOKS,
    CRAWL_INSTALL_HOOKS,
    MEMORY_COMMAND,
    apply,
    plan,
)


def _settings(tmp_path: Path) -> Path:
    path = tmp_path / "settings.json"
    theirs = {"matcher": "", "hooks": [{"type": "command", "command": "theirs"}]}
    path.write_text(
        json.dumps({"hooks": {"SessionStart": [theirs]}, "env": {"KEEP": "1"}}), "utf-8"
    )
    return path


def _commands(doc: dict, event: str) -> list[str]:
    return [h["command"] for e in doc["hooks"].get(event, []) for h in e["hooks"]]


def test_install_crawl_wires_its_hooks_once_and_keeps_theirs(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), crawl=True))
    doc = json.loads(path.read_text("utf-8"))
    for event, matcher in CRAWL_INSTALL_HOOKS.items():
        ours = [e for e in doc["hooks"][event] if e["hooks"][0]["command"] == CRAWL_COMMAND]
        assert len(ours) == 1 and ours[0]["matcher"] == matcher
    assert "theirs" in _commands(doc, "SessionStart") and doc["env"]["KEEP"] == "1"
    again = plan(path, HarnessConfig(), crawl=True)
    assert not again.added and not again.removed


def test_the_guard_matcher_reaches_every_server_and_nothing_else() -> None:
    import re

    matcher = re.compile(CRAWL_HOOKS["PreToolUse"])
    assert matcher.fullmatch("mcp__playwright__browser_evaluate")
    assert matcher.fullmatch("mcp__plugin_playwright_playwright__browser_evaluate")
    assert not matcher.fullmatch("mcp__playwright__browser_click")


def test_install_without_crawl_takes_ours_out_and_keeps_theirs(tmp_path: Path) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), crawl=True))
    removal = plan(path, HarnessConfig(), crawl=False)
    assert any("(crawl)" in line for line in removal.removed)
    apply(removal)
    doc = json.loads(path.read_text("utf-8"))
    assert CRAWL_COMMAND not in json.dumps(doc)
    assert _commands(doc, "SessionStart") == ["theirs"]


def test_crawl_and_memory_share_session_start_without_stepping_on_each_other(
    tmp_path: Path,
) -> None:
    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), crawl=True, memory=True))
    doc = json.loads(path.read_text("utf-8"))
    start = _commands(doc, "SessionStart")
    assert start.count(CRAWL_COMMAND) == 1 and start.count(MEMORY_COMMAND) == 1
    assert "theirs" in start
    apply(plan(path, HarnessConfig(), crawl=False, memory=True))
    start = _commands(json.loads(path.read_text("utf-8")), "SessionStart")
    assert CRAWL_COMMAND not in start and start.count(MEMORY_COMMAND) == 1
    apply(plan(path, HarnessConfig(), crawl=True, memory=False))
    start = _commands(json.loads(path.read_text("utf-8")), "SessionStart")
    assert MEMORY_COMMAND not in start and start.count(CRAWL_COMMAND) == 1


def test_the_installed_command_runs_the_crawl_hook(tmp_path: Path) -> None:
    """The command the settings name answers a session start with the line."""
    event = {"hook_event_name": "SessionStart", "source": "startup", "session_id": "s",
             "cwd": str(tmp_path)}  # fmt: skip
    run = subprocess.run(
        [sys.executable, "-m", "sanchopanza", "crawl-hook"],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=dict(os.environ),
        timeout=60,
        check=False,
    )
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout)["hookSpecificOutput"]["additionalContext"] == STRATEGY_LINE


# --- S seal (2026-10-05): every event the crawl hook answers, inert without its env ----------


def test_install_crawl_wires_every_event_the_hook_answers(tmp_path: Path) -> None:
    """v8 and v8.1 (`LINE_AT=prompt`, `ECHO=short`, `NOTES_AT=front`, `SHOT=snapshot-first`) are
    switched on by env alone; with only SessionStart and the evaluate wired, `LINE_AT=prompt`
    dropped the line altogether and the other three did nothing (S seal draft)."""
    from sanchopanza.harness.crawl_hook import V8_HOOKS, V81_HOOKS

    path = _settings(tmp_path)
    apply(plan(path, HarnessConfig(), crawl=True))
    doc = json.loads(path.read_text("utf-8"))
    wired = {
        event: [e["matcher"] for e in entries if e["hooks"][0]["command"] == CRAWL_COMMAND]
        for event, entries in doc["hooks"].items()
    }
    assert {e: m for e, m in wired.items() if m} == {
        e: [m] for e, m in {**CRAWL_HOOKS, **V8_HOOKS, **V81_HOOKS}.items()
    }
    again = plan(path, HarnessConfig(), crawl=True)
    assert not again.added and not again.removed
    apply(plan(path, HarnessConfig(), crawl=False))
    assert CRAWL_COMMAND not in path.read_text("utf-8")


def test_the_extra_crawl_events_do_nothing_without_their_env() -> None:
    from sanchopanza.harness import crawl_hook

    events = [
        {"hook_event_name": "UserPromptSubmit", "prompt": "count every product across pages"},
        {"hook_event_name": "PostToolUse", "tool_name": "mcp__playwright__browser_evaluate",
         "tool_response": [{"type": "text", "text": "### Ran Playwright code\n```js\nx\n```"}]},
        {"hook_event_name": "PreToolUse", "tool_name": "mcp__playwright__browser_take_screenshot",
         "tool_input": {}, "session_id": "s"},
    ]  # fmt: skip
    for event in events:
        assert crawl_hook.handle(event, {}) is None
