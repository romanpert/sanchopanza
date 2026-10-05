"""The opt-in `PreToolUse` hook that sends WebSearch and WebFetch to the knowledge server.

The first call per normalised query or URL in a session is denied with one line naming the
tool; the second runs (capability is never taken away). WebSearch runs at once when the last
real search found the chain down."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from sanchopanza import serp
from sanchopanza.harness import knowledge_hook


def _env(tmp_path: Path) -> dict[str, str]:
    return {"SANCHOPANZA_KNOWLEDGE_DIR": str(tmp_path)}


def _search(query: str, session: str = "s1") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "WebSearch", "session_id": session,
            "tool_input": {"query": query}}  # fmt: skip


def _fetch(url: str, session: str = "s1") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "WebFetch", "session_id": session,
            "tool_input": {"url": url, "prompt": "x"}}  # fmt: skip


def _denied(payload: dict | None) -> str:
    assert payload is not None
    out = payload["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"]


def test_the_first_websearch_of_a_query_is_sent_to_search_once(tmp_path: Path) -> None:
    env = _env(tmp_path)
    reason = _denied(knowledge_hook.handle(_search("Lake  history"), env))
    assert knowledge_hook.SEARCH_TOOL in reason
    assert knowledge_hook.handle(_search('"lake history"?'), env) is None
    assert knowledge_hook.handle(_search("lake depth"), env) is not None


def test_each_session_has_its_own_marks(tmp_path: Path) -> None:
    env = _env(tmp_path)
    knowledge_hook.handle(_search("lake"), env)
    assert knowledge_hook.handle(_search("lake", session="s2"), env) is not None


def test_the_first_webfetch_of_a_url_is_sent_to_read_once(tmp_path: Path) -> None:
    env = _env(tmp_path)
    reason = _denied(knowledge_hook.handle(_fetch("https://www.example.org/a/"), env))
    assert knowledge_hook.READ_TOOL in reason
    assert knowledge_hook.handle(_fetch("https://example.org/a#part"), env) is None


def test_websearch_runs_when_the_chain_is_down(tmp_path: Path) -> None:
    env = _env(tmp_path)
    state = {"ok": False, "at": __import__("time").time()}
    serp.chain_path(env).parent.mkdir(parents=True, exist_ok=True)
    serp.chain_path(env).write_text(json.dumps(state), "utf-8")
    assert knowledge_hook.handle(_search("lake"), env) is None
    assert knowledge_hook.handle(_fetch("https://example.org/"), env) is not None


def test_it_can_be_switched_off_and_ignores_other_events(tmp_path: Path) -> None:
    env = {**_env(tmp_path), "SANCHOPANZA_KNOWLEDGE_HOOK": "0"}
    assert knowledge_hook.handle(_search("lake"), env) is None
    on = _env(tmp_path)
    assert knowledge_hook.handle({**_search("lake"), "hook_event_name": "PostToolUse"}, on) is None
    assert knowledge_hook.handle({**_search("lake"), "tool_name": "Bash"}, on) is None
    assert knowledge_hook.handle(_search(""), on) is None


def test_main_fails_open(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    assert knowledge_hook.main() == 0
    captured = capsys.readouterr()
    assert captured.out == "" and "let the call run" in captured.err
