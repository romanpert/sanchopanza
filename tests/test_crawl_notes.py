"""The crawl notes: the evaluate guard's wrapper, run in Node against a stub page and a stub
fetch. No model, no browser, no money."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from sanchopanza.harness import crawl_hook as crawl
from sanchopanza.harness import crawl_notes as notes

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="needs node")

# A stub browser: `window` is the global object, `fetch` answers from ROUTES, and `document` is
# the open page (its text, its pagination links and its next link).
STUB = """
globalThis.window = globalThis;
const ROUTES = __ROUTES__;
globalThis.fetch = async (url) => {
  const hit = ROUTES[String(url)];
  if (!hit) throw new TypeError('Failed to fetch');
  const r = {ok: hit[0] < 400, status: hit[0], text: async () => hit[1]};
  return {...r, clone: () => r};
};
globalThis.ORIGINAL_FETCH = globalThis.fetch;
globalThis.DOMParser = class { parseFromString(t) {
  return {querySelectorAll: () => [], body: {textContent: t.replace(/<[^>]+>/g, ' ')}}; } };
const PAGE = __PAGE__;
globalThis.document = {
  body: {innerText: PAGE.text},
  querySelectorAll: () => PAGE.links.map((x) => ({textContent: x})),
  querySelector: () => (PAGE.next ? {href: PAGE.next} : null),
};
"""


def _run(function: str, routes: dict | None = None, page: dict | None = None, limit_s: int = 5):
    page = {"text": "", "links": [], "next": "", **(page or {})}
    wrapped = crawl.wrap(function, limit_s, notes=True)
    script = (
        STUB.replace("__ROUTES__", json.dumps(routes or {})).replace("__PAGE__", json.dumps(page))
        + f"const f = {wrapped};\n"
        "const say = (o) => { console.log(JSON.stringify(o)); process.exit(0); };\n"
        "f().then((v) => say({ok: v, restored: window.fetch === ORIGINAL_FETCH}),"
        " (e) => say({err: String(e.message || e), restored: window.fetch === ORIGINAL_FETCH}));"
    )
    done = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8",
                          timeout=30)  # fmt: skip
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_a_call_that_fetched_nothing_quotes_the_size_the_open_page_states():
    page = {"text": "Name Office\nShowing 1 to 10 of 57 entries\nPrevious 1 2 3 Next"}
    out = _run("() => 3", page=page)
    assert out["ok"]["result"] == 3
    note = out["ok"]["sanchopanza"]
    assert "fetched nothing" in note and "Showing 1 to 10 of 57 entries" in note


@pytest.mark.parametrize(
    ("page", "said"),
    [
        ({"text": "Showing 1–16 of 755 results"}, "Showing 1–16 of 755 results"),
        ({"text": "Showing 1 to 15 of 75 (5 Pages)"}, "of 75 (5 Pages)"),
        ({"text": "Page 1 of 94"}, "Page 1 of 94"),
        ({"text": '{"info":{"count":826,"pages":42,"next":"x"}}'}, '"count":826, "pages":42'),
        ({"links": ["1", "2", "3", "13"], "next": "https://s/pagination/2"},
         "pagination links up to page 13 | next link https://s/pagination/2"),
    ],
)  # fmt: skip
def test_each_kind_of_size_statement_is_quoted(page, said):
    assert said in _run("() => 0", page=page)["ok"]["sanchopanza"]


def test_with_nothing_to_say_the_value_comes_back_unchanged_and_fetch_is_restored():
    out = _run("() => ({rows: 3})", page={"text": "a page with no size on it"})
    assert out == {"ok": {"rows": 3}, "restored": True}
    routes = {"/p/1": [200, "<body>one</body>"], "/p/2": [200, "<body>two</body>"]}
    code = (
        "async () => { for (const u of ['/p/1', '/p/2']) await (await fetch(u)).text(); return 2; }"
    )
    assert _run(code, routes, page={"text": "Showing 1 to 10 of 57 entries"})["ok"] == 2


def test_failed_fetches_are_counted_by_status():
    routes = {f"/p/{i}": [200, f"<body>page {i}</body>"] for i in (1, 2)}
    routes |= {"/p/3": [429, "<!doctype html>slow down"], "/p/4": [429, "slow down"]}
    code = (
        "async () => { let n = 0; for (const i of [1, 2, 3, 4, 5]) { try { "
        "const r = await fetch('/p/' + i); if (r.ok) n++; } catch (e) {} } return n; }"
    )
    out = _run(code, routes)["ok"]
    assert out["result"] == 2
    assert "2 of 5 fetches answered 429" in out["sanchopanza"]
    assert "1 of 5 fetches answered network error" in out["sanchopanza"]


def test_a_page_served_twice_under_two_urls_is_named_and_the_same_url_twice_is_not():
    routes = {
        "/shop": [200, "<body>Bulbasaur 63</body>"],
        "/shop?page=2": [200, "<body>Bulbasaur 63</body>"],
    }
    loop = "async () => { for (const u of %s) await (await fetch(u)).text(); return 1; }"
    twice = loop % "['/shop', '/shop?page=2']"
    note = _run(twice, routes)["ok"]["sanchopanza"]
    assert "1 fetched pages had exactly the text of an earlier, different URL" in note
    assert "/shop?page=2 = /shop" in note
    assert _run(loop % "['/shop', '/shop']", routes)["ok"] == 1


def test_an_error_keeps_its_message_and_gains_the_notes():
    routes = {"/api?page=2": [429, "<!doctype html>"]}
    code = (
        "async () => { const r = await fetch('/api?page=2'); return JSON.parse(await r.text()); }"
    )
    out = _run(code, routes)
    assert "is not valid JSON" in out["err"] or "Unexpected token" in out["err"]
    assert "1 of 1 fetches answered 429" in out["err"] and out["restored"] is True


def test_the_time_limit_still_stops_a_hung_loop_and_puts_fetch_back():
    hung = "async () => { while (true) { await new Promise((r) => setTimeout(r, 10)); } }"
    out = _run(hung, limit_s=1)
    assert "stopped after 1 s" in out["err"] and out["restored"] is True


def test_the_notes_keep_the_guards_mark_so_a_wrapped_call_is_never_wrapped_twice():
    event = {"hook_event_name": "PreToolUse", "tool_name": "mcp__playwright__browser_evaluate",
             "tool_input": {"function": "() => 1"}}  # fmt: skip
    once = crawl.handle(event, env={"SANCHOPANZA_CRAWL_NOTES": "1"})["hookSpecificOutput"]
    wrapped = once["updatedInput"]["function"]
    assert wrapped.startswith(crawl.MARK) and notes.NOTES_MARK in wrapped
    assert "permissionDecision" not in once, "the notes approve nothing either"
    again = {**event, "tool_input": {"function": wrapped}}
    assert crawl.handle(again, env={"SANCHOPANZA_CRAWL_NOTES": "1"}) is None


@pytest.mark.parametrize(("raw", "on"), [("1", True), ("on", True), ("", False), ("0", False)])
def test_the_notes_are_off_unless_asked_for(raw, on):
    event = {"hook_event_name": "PreToolUse", "tool_name": "mcp__playwright__browser_evaluate",
             "tool_input": {"function": "() => 1"}}  # fmt: skip
    out = crawl.handle(event, env={"SANCHOPANZA_CRAWL_NOTES": raw})
    assert (notes.NOTES_MARK in out["hookSpecificOutput"]["updatedInput"]["function"]) is on


@pytest.mark.parametrize(
    "function", ["() => 41 + 1", "() => 42 // the answer", "function () { return 42; }"]
)
def test_code_that_returns_with_nothing_to_note_returns_what_it_always_returned(function):
    assert _run(function)["ok"] == 42
