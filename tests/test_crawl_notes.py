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
globalThis.HTMLElement = class { click() { if (this.onclick) this.onclick(); } };
globalThis.ORIGINAL_CLICK = HTMLElement.prototype.click;
globalThis.document = {
  body: {innerText: PAGE.text, textContent: PAGE.text},
  querySelectorAll: () => PAGE.links.map((x) => ({textContent: x})),
  querySelector: () => (PAGE.next ? {href: PAGE.next} : null),
};
"""


def _run(
    function: str,
    routes: dict | None = None,
    page: dict | None = None,
    limit_s: int = 5,
    notes_version: int = 1,
):
    page = {"text": "", "links": [], "next": "", **(page or {})}
    wrapped = crawl.wrap(function, limit_s, notes=notes_version)
    script = (
        STUB.replace("__ROUTES__", json.dumps(routes or {})).replace("__PAGE__", json.dumps(page))
        + f"const f = {wrapped};\n"
        "const say = (o) => { console.log(JSON.stringify(o)); process.exit(0); };\n"
        "const back = () => window.fetch === ORIGINAL_FETCH"
        " && HTMLElement.prototype.click === ORIGINAL_CLICK;"
        "f().then((v) => say({ok: v, restored: back()}),"
        " (e) => say({err: String(e.message || e), restored: back()}));"
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


@pytest.mark.parametrize("version", [1, 2])
@pytest.mark.parametrize(
    "function", ["() => 41 + 1", "() => 42 // the answer", "function () { return 42; }"]
)
def test_code_that_returns_with_nothing_to_note_returns_what_it_always_returned(function, version):
    assert _run(function, notes_version=version) == {"ok": 42, "restored": True}


# --- notes v2 (v8 in development, `SANCHOPANZA_CRAWL_NOTES=2`): clicks and JSON rows ---------

PAGER = (
    "async () => { const b = new HTMLElement(); b.onclick = () => { %s };"
    " for (let i = 0; i < 4; i++) { b.click(); await new Promise((r) => setTimeout(r, 5)); }"
    " return 40; }"
)


def test_clicks_that_never_changed_the_page_text_are_counted_with_no_advice():
    out = _run(PAGER % "", page={"text": "Name Last 40 rows"}, notes_version=2)
    assert out["restored"] is True, "click and fetch are put back"
    assert out["ok"]["result"] == 40
    assert (
        "4 clicks did not change the page text: the rows were already loaded"
        in (out["ok"]["sanchopanza"])
    )


def test_clicks_that_changed_the_page_text_say_nothing():
    turn = "document.body.textContent += ' next';"
    out = _run(PAGER % turn, page={"text": "Name Last"}, notes_version=2)
    assert out == {"ok": 40, "restored": True}


def test_one_click_is_not_enough_for_a_note():
    one = "() => { new HTMLElement().click(); return 1; }"
    assert _run(one, notes_version=2)["ok"] == 1


def test_fetched_json_rows_are_counted_total_and_distinct_with_no_advice():
    routes = {
        "/api?page=1": [200, json.dumps({"total": 3, "results": [{"id": 1}, {"id": 2}]})],
        "/api?page=2": [200, json.dumps({"total": 3, "results": [{"id": 2}, {"id": 3}]})],
        "/flat": [200, json.dumps([{"id": 9}])],
    }
    code = (
        "async () => { for (const u of ['/api?page=1', '/api?page=2', '/flat'])"
        " JSON.parse(await (await fetch(u)).text()); return 4; }"
    )
    out = _run(code, routes, notes_version=2)
    assert out["ok"]["result"] == 4 and out["restored"] is True
    note = out["ok"]["sanchopanza"]
    assert "fetched JSON rows 5, distinct 4." in note
    assert "should" not in note and "dedup" not in note


def test_html_and_json_with_no_rows_are_not_counted():
    routes = {"/p": [200, "<body>one</body>"], "/n": [200, json.dumps({"count": 2})]}
    code = "async () => { for (const u of ['/p', '/n']) await (await fetch(u)).text(); return 1; }"
    assert _run(code, routes, notes_version=2)["ok"] == 1


def test_v7s_notes_do_not_count_rows_or_clicks():
    routes = {"/a": [200, json.dumps([{"id": 1}, {"id": 1}])]}
    fetched = "async () => { await (await fetch('/a')).text(); return 1; }"
    assert _run(fetched, routes, notes_version=1)["ok"] == 1
    assert _run(PAGER % "", notes_version=1)["ok"] == 40


def test_notes_v2_keep_v7s_notes_and_its_time_limit():
    page = {"text": "Showing 1 to 10 of 57 entries"}
    assert (
        "Showing 1 to 10 of 57 entries"
        in _run("() => 3", page=page, notes_version=2)["ok"]["sanchopanza"]
    )
    hung = "async () => { while (true) { await new Promise((r) => setTimeout(r, 10)); } }"
    out = _run(hung, limit_s=1, notes_version=2)
    assert "stopped after 1 s" in out["err"] and out["restored"] is True


def test_v7s_sealed_wrapper_is_unchanged_by_v2():
    import hashlib

    sealed = "9ad6a00ef38827c3d304fdac7db813b602891770605a3f006ba1eebbe46e1b67"
    wrapped = crawl.wrap("() => 1", 120, notes=True)
    assert hashlib.sha256(wrapped.encode()).hexdigest() == sealed
    assert crawl.wrap("() => 1", 120, notes=1) == wrapped
    assert crawl.wrap("() => 1", 120, notes=2) != wrapped
