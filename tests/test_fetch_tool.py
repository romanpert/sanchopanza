"""`fetch_passages` (MCP) and its optional `PreToolUse` hook on WebFetch.

The tool downloads a page itself and returns the passages the declared purpose needs, so no
reader model runs; the hook sends WebFetch there once per URL and lets a second WebFetch of the
same URL through (a PDF, a page the tool cannot read). No network in these tests."""

from __future__ import annotations

import io
import json
import socket
import urllib.request
from pathlib import Path

import pytest

from sanchopanza.harness import fetch_hook, fetch_tool

PAGE = (
    b"<html><head><title>Lake Example</title></head><body><h1>Lake Example</h1>"
    b"<p>Lake Example is a lake.</p><h2>History</h2>"
    b"<p>The first survey of the lake was carried out in 1873.</p>"
    + b"".join(
        b"<h2>Other %d</h2><p>Unrelated text about birds number %d.</p>" % (i, i) for i in range(80)
    )
    + b"</body></html>"
)


def _public(monkeypatch: pytest.MonkeyPatch, ip: str = "93.184.216.34") -> None:
    def fake(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(fetch_tool.socket, "getaddrinfo", fake)


class Opener:
    def __init__(self, body: bytes = PAGE, ctype: str = "text/html; charset=utf-8") -> None:
        self.body, self.ctype, self.calls = body, ctype, []

    def __call__(self, url: str) -> fetch_tool.Response:
        self.calls.append(url)
        return fetch_tool.Response(url, self.ctype, self.body)


# --- the address check -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "ftp://example.com/x", "http://", "javascript:alert(1)"],
)
def test_only_http_and_https_urls_are_fetched(url: str) -> None:
    with pytest.raises(fetch_tool.Refused):
        fetch_tool.check_url(url)


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1"])
def test_private_loopback_and_metadata_addresses_are_refused(
    monkeypatch: pytest.MonkeyPatch, ip: str
) -> None:
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET

    def fake(host, *args, **kwargs):
        return [(family, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(fetch_tool.socket, "getaddrinfo", fake)
    with pytest.raises(fetch_tool.Refused):
        fetch_tool.check_url("https://looks-public.example/")


def test_a_public_address_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    _public(monkeypatch)
    fetch_tool.check_url("https://en.example.org/wiki/Lake")


def test_denied_hosts_match_the_host_and_its_subdomains(monkeypatch: pytest.MonkeyPatch) -> None:
    _public(monkeypatch)
    env = {"SANCHOPANZA_FETCH_DENY_HOSTS": "example.com, hf.co"}
    with pytest.raises(fetch_tool.Refused):
        fetch_tool.check_url("https://example.com/a", env)
    with pytest.raises(fetch_tool.Refused):
        fetch_tool.check_url("https://datasets.example.com/a", env)
    fetch_tool.check_url("https://notexample.com/a", env)


def test_a_redirect_to_a_private_address_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake(host, *args, **kwargs):
        ip = "127.0.0.1" if host == "inside.example" else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(fetch_tool.socket, "getaddrinfo", fake)
    handler = fetch_tool._CheckedRedirects({})
    request = urllib.request.Request("https://outside.example/")
    with pytest.raises(fetch_tool.Refused):
        handler.redirect_request(request, io.BytesIO(), 302, "Found", {}, "http://inside.example/")


# --- the tool ----------------------------------------------------------------------------------


def test_the_tool_returns_the_passages_for_the_purpose_not_the_whole_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public(monkeypatch)
    tool = fetch_tool.PageFetcher(opener=Opener())
    out = tool.fetch("https://en.example.org/wiki/Lake", "when was the first survey", budget=300)
    assert "1873" in out and "Lake Example" in out
    assert "birds number 79" not in out
    assert out.splitlines()[1] == "https://en.example.org/wiki/Lake"
    assert " of " in out.splitlines()[2] and "characters" in out.splitlines()[2]


def test_a_second_purpose_on_the_same_page_does_not_download_it_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _public(monkeypatch)
    opener = Opener()
    tool = fetch_tool.PageFetcher(opener=opener)
    tool.fetch("https://en.example.org/wiki/Lake", "first survey")
    out = tool.fetch("https://en.example.org/wiki/Lake", "birds number 42", budget=300)
    assert len(opener.calls) == 1
    assert "birds number 42" in out


def test_the_budget_is_clamped(monkeypatch: pytest.MonkeyPatch) -> None:
    _public(monkeypatch)
    tool = fetch_tool.PageFetcher(opener=Opener())
    small = tool.fetch("https://en.example.org/wiki/Lake", "birds", budget=1)
    assert len(small) >= fetch_tool.MIN_BUDGET // 2
    big = tool.fetch("https://en.example.org/wiki/Lake", "birds", budget=10**9)
    assert len(big) <= fetch_tool.MAX_BUDGET + 2_000


def test_a_pdf_or_binary_page_says_to_use_webfetch(monkeypatch: pytest.MonkeyPatch) -> None:
    _public(monkeypatch)
    tool = fetch_tool.PageFetcher(opener=Opener(b"%PDF-1.7 ...", "application/pdf"))
    out = tool.fetch("https://en.example.org/a.pdf", "anything")
    assert "WebFetch" in out and "application/pdf" in out


def test_json_and_plain_text_are_served_by_lines(monkeypatch: pytest.MonkeyPatch) -> None:
    _public(monkeypatch)
    body = "\n".join(f'{{"day": {i}, "value": {i * 3}}}' for i in range(400)).encode()
    tool = fetch_tool.PageFetcher(opener=Opener(body, "application/json"))
    out = tool.fetch("https://api.example.org/series", "day 250 value", budget=500)
    assert '"day": 250' in out


def test_a_refused_or_failed_download_is_a_short_message_not_an_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def broken(url: str) -> fetch_tool.Response:
        raise OSError("connection reset")

    _public(monkeypatch)
    tool = fetch_tool.PageFetcher(opener=broken)
    assert "could not" in tool.fetch("https://en.example.org/x", "p").lower()
    assert "refused" in tool.fetch("file:///etc/passwd", "p").lower()


def test_the_tool_name_counts_as_a_web_call_for_the_sources_hook() -> None:
    from sanchopanza.harness.sources_hook import WEB_TOOL

    assert WEB_TOOL.match(f"mcp__{fetch_tool.SERVER}__{fetch_tool.TOOL}")


# --- the hook ----------------------------------------------------------------------------------


def _event(url: str, session: str = "s1", tool: str = "WebFetch") -> dict:
    return {
        "hook_event_name": "PreToolUse",
        "session_id": session,
        "tool_name": tool,
        "tool_input": {"url": url, "prompt": "find the year"},
    }


def test_the_first_webfetch_of_a_url_is_sent_to_the_tool_the_second_passes(
    tmp_path: Path,
) -> None:
    env = {"SANCHOPANZA_FETCH_DIR": str(tmp_path)}
    first = fetch_hook.handle(_event("https://a.example/x"), env)
    out = first["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert fetch_tool.TOOL in out["permissionDecisionReason"]
    assert fetch_hook.handle(_event("https://a.example/x"), env) is None
    assert fetch_hook.handle(_event("https://a.example/y"), env) is not None
    assert fetch_hook.handle(_event("https://a.example/x", session="s2"), env) is not None


def test_the_hook_leaves_other_tools_alone_and_can_be_switched_off(tmp_path: Path) -> None:
    env = {"SANCHOPANZA_FETCH_DIR": str(tmp_path)}
    assert fetch_hook.handle(_event("https://a.example/x", tool="WebSearch"), env) is None
    off = {**env, "SANCHOPANZA_FETCH_HOOK": "0"}
    assert fetch_hook.handle(_event("https://a.example/x"), off) is None


def test_the_hook_fails_open_on_a_bad_event(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(fetch_hook, "stdin_text", lambda: "not json")
    assert fetch_hook.main() == 0
    captured = capsys.readouterr()
    assert captured.out == "" and "fetch" in captured.err


def test_the_hook_names_the_tool_the_server_registers() -> None:
    assert f"mcp__{fetch_tool.SERVER}__{fetch_tool.TOOL}" == fetch_hook.TOOL_NAME


def test_the_hook_reason_is_short() -> None:
    assert len(fetch_hook.REASON) < 400
    json.dumps(fetch_hook.REASON)
