"""fetch v3: `fetch_passages` falls back to WebFetch where it cannot read a page.

GAIA confirmation, 2026-10-06 (`docs/results/2026-10-05-h2h-gaia/README-conf.md`): 89 of 231
calls failed (25 HTTP 403, 8 429, 24 404, 18 with no text, 10 PDF, 2 UnicodeEncodeError), and
after a failure the agent tried WebFetch on the same URL in 13 of them, where it read the page in
11. Version 3, behind `SANCHOPANZA_FETCH_VERSION=3`, says so in the reply and leaves a mark the
WebFetch hook honours, so the WebFetch runs at once instead of being sent back to the tool. A
404 or 410 is a guessed address: WebFetch would meet the same answer, so it keeps v2's line.
Every version encodes a non-ASCII address instead of failing on it. No network in these tests."""

from __future__ import annotations

import socket
import urllib.error
from pathlib import Path

import pytest

from sanchopanza.harness import fetch_hook, fetch_tool

PAGE = (
    b"<html><head><title>Lake</title></head><body><h1>Lake</h1>"
    b"<p>The lake is deep and cold all the year round, in every season.</p></body></html>"
)
EMPTY = b"<html><head><title>App</title></head><body><div id='root'></div></body></html>"


def _public(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(fetch_tool.socket, "getaddrinfo", fake)


def _env(tmp_path: Path, version: str = "3") -> dict[str, str]:
    return {"SANCHOPANZA_FETCH_VERSION": version, "SANCHOPANZA_FETCH_DIR": str(tmp_path)}


def _failing(code: int):
    def opener(url: str) -> fetch_tool.Response:
        raise urllib.error.HTTPError(url, code, "No", {}, None)

    return opener


def _serving(body: bytes, ctype: str = "text/html; charset=utf-8"):
    def opener(url: str) -> fetch_tool.Response:
        return fetch_tool.Response(url, ctype, body)

    return opener


def _webfetch(url: str, session: str = "s1") -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": "WebFetch", "session_id": session,
            "tool_input": {"url": url, "prompt": "p"}}  # fmt: skip


URL = "https://example.org/page"


def _denied(url: str, env: dict[str, str]) -> bool:
    out = fetch_hook.handle(_webfetch(url), env)
    return bool(out) and out["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("code", [403, 429, 500, 503])
def test_a_refusing_server_sends_the_agent_to_webfetch_and_the_webfetch_runs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, code: int
) -> None:
    _public(monkeypatch)
    env = _env(tmp_path)
    reply = fetch_tool.PageFetcher(_failing(code), env=env).fetch(URL, "depth")
    assert f"HTTP {code}" in reply and fetch_tool.FALLBACK in reply
    assert fetch_hook.handle(_webfetch(URL), env) is None  # runs at once, no second trip


@pytest.mark.parametrize("code", [404, 410])
def test_a_guessed_address_is_not_sent_to_webfetch(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, code: int
) -> None:
    _public(monkeypatch)
    env = _env(tmp_path)
    reply = fetch_tool.PageFetcher(_failing(code), env=env).fetch(URL, "depth")
    assert fetch_tool.GUESSED in reply and fetch_tool.FALLBACK not in reply
    assert _denied(URL, env)


def test_a_page_with_no_text_falls_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _public(monkeypatch)
    env = _env(tmp_path)
    reply = fetch_tool.PageFetcher(_serving(EMPTY), env=env).fetch(URL, "depth")
    assert "No text on the page" in reply and fetch_tool.FALLBACK in reply
    assert fetch_hook.handle(_webfetch(URL), env) is None


@pytest.mark.parametrize(("body", "ctype"), [(b"%PDF-1.7 ...", "application/pdf"),
                                             (b"\x89PNG....", "image/png")])  # fmt: skip
def test_a_pdf_or_binary_page_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, body: bytes, ctype: str
) -> None:
    _public(monkeypatch)
    env = _env(tmp_path)
    reply = fetch_tool.PageFetcher(_serving(body, ctype), env=env).fetch(URL, "depth")
    assert fetch_tool.FALLBACK in reply
    assert fetch_hook.handle(_webfetch(URL), env) is None


def test_a_network_error_falls_back(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _public(monkeypatch)
    env = _env(tmp_path)

    def timeout(url: str) -> fetch_tool.Response:
        raise TimeoutError("timed out")

    reply = fetch_tool.PageFetcher(timeout, env=env).fetch(URL, "depth")
    assert "TimeoutError" in reply and fetch_tool.FALLBACK in reply
    assert fetch_hook.handle(_webfetch(URL), env) is None


def test_a_refused_address_never_falls_back(tmp_path: Path) -> None:
    env = {**_env(tmp_path), "SANCHOPANZA_FETCH_DENY_HOSTS": "example.org"}
    reply = fetch_tool.PageFetcher(_serving(PAGE), env=env).fetch(URL, "depth")
    assert reply.startswith("Refused") and fetch_tool.FALLBACK not in reply
    assert _denied(URL, env)


def test_a_page_read_leaves_no_mark(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _public(monkeypatch)
    env = _env(tmp_path)
    reply = fetch_tool.PageFetcher(_serving(PAGE), env=env).fetch(URL, "depth")
    assert "deep and cold" in reply and fetch_tool.FALLBACK not in reply
    assert _denied(URL, env)


def test_version_two_keeps_its_replies_and_leaves_no_mark(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _public(monkeypatch)
    env = _env(tmp_path, "2")
    reply = fetch_tool.PageFetcher(_failing(403), env=env).fetch(URL, "depth")
    assert reply == f"Could not fetch {URL}: HTTP 403."
    assert _denied(URL, env)


def test_a_stale_mark_does_not_let_the_webfetch_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _public(monkeypatch)
    env = _env(tmp_path)
    fetch_tool.PageFetcher(_failing(403), env=env).fetch(URL, "depth")
    later = fetch_hook.time.time() + fetch_hook.PASS_S + 1
    monkeypatch.setattr(fetch_hook.time, "time", lambda: later)
    assert _denied(URL, env)


def test_version_three_names_a_browser_and_earlier_ones_name_the_tool() -> None:
    assert "Chrome/" in fetch_tool.user_agent({"SANCHOPANZA_FETCH_VERSION": "3"})
    assert fetch_tool.user_agent({"SANCHOPANZA_FETCH_VERSION": "2"}) == fetch_tool.USER_AGENT
    assert fetch_tool.version({"SANCHOPANZA_FETCH_VERSION": "3"}) == 3


@pytest.mark.parametrize("version", ["1", "2", "3"])
def test_a_non_ascii_address_is_encoded_not_a_unicode_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, version: str
) -> None:
    _public(monkeypatch)
    asked = []

    def opener(url: str) -> fetch_tool.Response:
        url.encode("ascii")  # what http.client does with the request line
        asked.append(url)
        return fetch_tool.Response(url, "text/html; charset=utf-8", PAGE)

    url = "https://en.wikipedia.org/wiki/Café_Müller?q=ñ#Año"
    reply = fetch_tool.PageFetcher(opener, env=_env(tmp_path, version)).fetch(url, "depth")
    assert "deep and cold" in reply
    assert asked == ["https://en.wikipedia.org/wiki/Caf%C3%A9_M%C3%BCller?q=%C3%B1#A%C3%B1o"]


def test_ascii_url_leaves_an_encoded_address_as_it_is() -> None:
    url = "https://example.org/a%20b?x=1&y=%C3%B1"
    assert fetch_tool.ascii_url(url) == url
    assert fetch_tool.ascii_url("https://bücher.example/") == "https://xn--bcher-kva.example/"
