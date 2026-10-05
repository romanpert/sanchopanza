"""fetch v2: `fetch_passages` behind `SANCHOPANZA_FETCH_VERSION=2`, and the page budget of
`fetch_hook` behind `SANCHOPANZA_FETCH_MAX_PAGES`.

Version 2 cuts pages with `webpage_v2` and answers a guessed URL that 404s, or a disambiguation
page, with one short line saying to search first. The page budget counts a session's pages
(fetch_passages or WebFetch) since its last WebSearch and, past N, adds one short line after the
passages; it never blocks. Version 1 and the hook without the setting stay as measured. No
network in these tests."""

from __future__ import annotations

import socket
import urllib.error
from pathlib import Path

import pytest

from sanchopanza.harness import fetch_hook, fetch_tool

WIKI = (
    b"<html><head><title>Lake - Wiki</title></head><body>"
    b'<div id="p-lang-btn" class="vector-dropdown"><ul><li>Afrikaans</li></ul></div>'
    b"<h1>Lake</h1><p>The lake is deep and cold all the year round, in every season.</p>"
    b'<h2>History<span class="mw-editsection">[edit]</span></h2>'
    b"<p>The first survey of the lake was carried out in 1873.</p></body></html>"
)
DISAMBIGUATION = (
    b"<html><head><title>Jumper - Wiki</title></head><body><h1>Jumper</h1>"
    b"<p>Jumper or Jumpers may refer to:</p><ul><li>Jumper (2008 film)</li>"
    b"<li>Jumper (novel)</li></ul></body></html>"
)


def _public(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(fetch_tool.socket, "getaddrinfo", fake)


def _serving(body: bytes):
    def opener(url: str) -> fetch_tool.Response:
        return fetch_tool.Response(url, "text/html; charset=utf-8", body)

    return opener


def _missing(url: str) -> fetch_tool.Response:
    raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)


V2 = {"SANCHOPANZA_FETCH_VERSION": "2"}


# --- the tool ----------------------------------------------------------------------------------


def test_version_two_strips_the_chrome_and_version_one_does_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public(monkeypatch)
    url = "https://en.example.org/wiki/Lake"
    two = fetch_tool.PageFetcher(opener=_serving(WIKI), env=V2).fetch(url, "first survey")
    one = fetch_tool.PageFetcher(opener=_serving(WIKI), env={}).fetch(url, "first survey")
    assert "1873" in two and "Afrikaans" not in two and "[edit]" not in two
    assert "Afrikaans" in one


def test_version_two_says_a_404_was_probably_guessed(monkeypatch: pytest.MonkeyPatch) -> None:
    _public(monkeypatch)
    url = "https://en.example.org/wiki/Guessed_title"
    two = fetch_tool.PageFetcher(opener=_missing, env=V2).fetch(url, "p")
    one = fetch_tool.PageFetcher(opener=_missing, env={}).fetch(url, "p")
    assert two.startswith(f"Could not fetch {url}: HTTP 404.")
    assert "search" in two.lower() and len(two) < len(url) + 200
    assert one == f"Could not fetch {url}: HTTP 404."


def test_version_two_names_a_disambiguation_page(monkeypatch: pytest.MonkeyPatch) -> None:
    _public(monkeypatch)
    url = "https://en.example.org/wiki/Jumper_(film)"
    out = fetch_tool.PageFetcher(opener=_serving(DISAMBIGUATION), env=V2).fetch(url, "cast")
    assert "disambiguation" in out.lower() and "Jumper (2008 film)" in out
    one = fetch_tool.PageFetcher(opener=_serving(DISAMBIGUATION), env={}).fetch(url, "cast")
    assert "disambiguation" not in one.lower()


# --- the page budget ---------------------------------------------------------------------------


def _post(tool: str = fetch_hook.TOOL_NAME, session: str = "s1") -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "session_id": session,
        "tool_name": tool,
        "tool_input": {"url": "https://a.example/x", "purpose": "p"},
        "tool_response": "ok",
    }


def _search(session: str = "s1") -> dict:
    return {"hook_event_name": "PreToolUse", "session_id": session, "tool_name": "WebSearch",
            "tool_input": {"query": "q"}}  # fmt: skip


def _note(payload: dict | None) -> str:
    return str(((payload or {}).get("hookSpecificOutput") or {}).get("additionalContext") or "")


def test_without_the_setting_the_hook_counts_nothing(tmp_path: Path) -> None:
    env = {"SANCHOPANZA_FETCH_DIR": str(tmp_path)}
    assert all(fetch_hook.handle(_post(), env) is None for _ in range(40))
    assert fetch_hook.handle(_search(), env) is None
    assert not list(tmp_path.iterdir())


def test_past_n_pages_with_no_search_each_page_gets_a_short_note(tmp_path: Path) -> None:
    env = {"SANCHOPANZA_FETCH_DIR": str(tmp_path), "SANCHOPANZA_FETCH_MAX_PAGES": "2"}
    assert fetch_hook.handle(_post(), env) is None
    assert fetch_hook.handle(_post(tool="WebFetch"), env) is None
    third = fetch_hook.handle(_post(), env)
    assert third["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "search" in _note(third).lower() and "3" in _note(third) and len(_note(third)) < 300
    assert _note(fetch_hook.handle(_post(), env))


def test_a_search_starts_the_count_again_and_sessions_count_apart(tmp_path: Path) -> None:
    env = {"SANCHOPANZA_FETCH_DIR": str(tmp_path), "SANCHOPANZA_FETCH_MAX_PAGES": "1"}
    fetch_hook.handle(_post(), env)
    assert _note(fetch_hook.handle(_post(), env))
    assert fetch_hook.handle(_search(), env) is None  # a search is never denied or noted
    assert fetch_hook.handle(_post(), env) is None
    assert fetch_hook.handle(_post(session="s2"), env) is None


def test_other_tools_do_not_count(tmp_path: Path) -> None:
    env = {"SANCHOPANZA_FETCH_DIR": str(tmp_path), "SANCHOPANZA_FETCH_MAX_PAGES": "1"}
    for _ in range(5):
        assert fetch_hook.handle(_post(tool="Read"), env) is None
    assert fetch_hook.handle(_post(), env) is None


def test_the_webfetch_deny_is_unchanged_with_the_budget_on(tmp_path: Path) -> None:
    env = {"SANCHOPANZA_FETCH_DIR": str(tmp_path), "SANCHOPANZA_FETCH_MAX_PAGES": "1"}
    event = {"hook_event_name": "PreToolUse", "session_id": "s1", "tool_name": "WebFetch",
             "tool_input": {"url": "https://a.example/x", "prompt": "p"}}  # fmt: skip
    first = fetch_hook.handle(event, env)
    assert first["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert fetch_hook.handle(event, env) is None


def test_a_bad_setting_leaves_the_budget_off(tmp_path: Path) -> None:
    env = {"SANCHOPANZA_FETCH_DIR": str(tmp_path), "SANCHOPANZA_FETCH_MAX_PAGES": "many"}
    assert all(fetch_hook.handle(_post(), env) is None for _ in range(10))
