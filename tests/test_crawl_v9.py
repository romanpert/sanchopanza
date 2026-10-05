"""Crawl notes v3 (v9 in development, `SANCHOPANZA_CRAWL_NOTES=3`), each from a miss of
confirmation 5 read by hand: a page whose size is only in the `Link` header (H1), a page that
states no size at all and returns a round number of rows (H4, Socrata's 1,000), size keys the
v7 note did not read (H5, `meta.pagination.records`), and a list loaded by XMLHttpRequest, which
the notes did not watch (H7, demoblaze). Run in Node against a stub page, fetch and XHR. No
model, no browser, no money."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess

import pytest

from sanchopanza.harness import crawl_hook as crawl

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="needs node")
OPEN = "https://s/api/houses"

# A stub browser. `fetch` answers from ROUTES ([status, body, headers]) and records each call's
# method; `XMLHttpRequest` answers from the same ROUTES, asynchronously; `document` is the open
# page at `location.href`.
STUB = """
globalThis.window = globalThis;
const ROUTES = __ROUTES__;
globalThis.CALLS = [];
globalThis.fetch = async (url, opts) => {
  const method = (opts && opts.method) || 'GET';
  CALLS.push(method + ' ' + String(url));
  const hit = ROUTES[method + ' ' + String(url)] || ROUTES[String(url)];
  if (!hit) throw new TypeError('Failed to fetch');
  const h = hit[2] || {};
  const r = {ok: hit[0] >= 200 && hit[0] < 300, status: hit[0], text: async () => hit[1],
             headers: {get: (k) => h[k.toLowerCase()] || null}};
  return {...r, clone: () => r};
};
globalThis.ORIGINAL_FETCH = globalThis.fetch;
class XHR {
  constructor() { this.l = []; this.status = 0; this.responseText = ''; this.responseType = ''; }
  open(m, u) { this.u = String(u); }
  addEventListener(k, f) { if (k === 'loadend') this.l.push(f); }
  getResponseHeader(k) { return (this.h || {})[k.toLowerCase()] || null; }
  send() { setTimeout(() => { const hit = ROUTES[this.u];
    if (hit) { this.status = hit[0]; this.responseText = hit[1]; this.h = hit[2] || {}; }
    this.l.forEach((f) => f()); }, 5); }
}
globalThis.XMLHttpRequest = XHR;
globalThis.ORIGINAL_XHR = [XHR.prototype.open, XHR.prototype.send];
globalThis.DOMParser = class { parseFromString(t) {
  return {querySelectorAll: () => [], body: {textContent: t.replace(/<[^>]+>/g, ' ')}}; } };
globalThis.HTMLElement = class { click() {} };
const PAGE = __PAGE__;
globalThis.location = {href: PAGE.url};
globalThis.document = {
  body: {innerText: PAGE.text, textContent: PAGE.text},
  querySelectorAll: () => [],
  querySelector: (s) => (s === 'a[rel=next]' ? null
    : s.includes('pre') && PAGE.pre !== undefined ? {textContent: PAGE.pre} : null),
};
"""


def _run(function: str, routes: dict | None = None, page: dict | None = None, version: int = 3):
    page = {"text": "", "url": OPEN, **(page or {})}
    wrapped = crawl.wrap(function, 5, notes=version)
    script = (
        STUB.replace("__ROUTES__", json.dumps(routes or {})).replace("__PAGE__", json.dumps(page))
        + f"const f = {wrapped};\n"
        "const say = (o) => { console.log(JSON.stringify(o)); process.exit(0); };\n"
        "const back = () => window.fetch === ORIGINAL_FETCH"
        " && XHR.prototype.open === ORIGINAL_XHR[0] && XHR.prototype.send === ORIGINAL_XHR[1];"
        "f().then((v) => say({ok: v, restored: back(), calls: CALLS}),"
        " (e) => say({err: String(e.message || e), restored: back(), calls: CALLS}));"
    )
    done = subprocess.run([NODE, "-"], input=script, capture_output=True, text=True,
                          encoding="utf-8", timeout=30)  # fmt: skip
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


PARSE_OPEN = "() => JSON.parse(document.body.innerText).length"
LINK = (
    '<https://s/api/houses?page=2&pageSize=10>; rel="next", '
    '<https://s/api/houses?page=1&pageSize=10>; rel="first", '
    '<https://s/api/houses?page=45&pageSize=10>; rel="last"'
)


def _rows(n: int) -> list[dict]:
    return [{"id": i, "name": f"row {i}"} for i in range(n)]


def test_the_link_header_of_the_open_page_is_quoted_when_the_call_fetched_nothing():
    """H1: 10 houses of 444, the next page named only in the `Link` header."""
    out = _run(PARSE_OPEN, {f"HEAD {OPEN}": [200, "", {"link": LINK}]},
               {"text": json.dumps(_rows(10))})  # fmt: skip
    assert out["ok"]["result"] == 10 and out["restored"] is True
    note = out["ok"]["sanchopanza"]
    assert "fetched nothing" in note
    assert (
        "Link header: next https://s/api/houses?page=2&pageSize=10, "
        "last https://s/api/houses?page=45&pageSize=10" in note
    )
    assert "fetches answered" not in note, "the notes' own request is not the agent's"


def test_a_head_the_server_refuses_falls_back_to_a_get_for_the_link_header():
    routes = {f"HEAD {OPEN}": [405, "", {}], f"GET {OPEN}": [200, "[]", {"link": LINK}]}
    out = _run(PARSE_OPEN, routes, {"text": json.dumps(_rows(10))})
    assert "Link header: next https://s/api/houses?page=2" in out["ok"]["sanchopanza"]
    assert out["calls"] == [f"HEAD {OPEN}", f"GET {OPEN}"]


def test_size_keys_the_v7_note_did_not_read_are_quoted_with_their_path():
    """H5: potterdb states `"last":55, "records":5410` under `meta.pagination`."""
    body = {"data": _rows(100),
            "meta": {"pagination": {"current": 1, "next": 2, "last": 55, "records": 5410}},
            "links": {"self": "https://s/c", "next": "https://s/c?page[number]=2"}}  # fmt: skip
    note = _run(PARSE_OPEN, page={"text": json.dumps(body)})["ok"]["sanchopanza"]
    assert "meta.pagination.next: 2" in note
    assert "meta.pagination.last: 55" in note and "meta.pagination.records: 5410" in note
    assert "links.next: https://s/c?page[number]=2" in note
    assert "exactly 100" not in note, "a page that states its size gets no round-number note"


def test_a_round_number_of_rows_with_no_size_stated_is_named():
    """H4: Socrata returns 1,000 rows of 3,023 and states no total and no link."""
    note = _run(PARSE_OPEN, page={"text": json.dumps(_rows(1000))})["ok"]["sanchopanza"]
    assert "a JSON array of exactly 1000 items and no total" in note


@pytest.mark.parametrize("n", [10, 20, 25, 50, 100, 1000])
def test_every_round_size_is_named(n):
    assert (
        f"exactly {n} items"
        in _run(PARSE_OPEN, page={"text": json.dumps(_rows(n))})["ok"]["sanchopanza"]
    )


def test_a_size_that_is_not_round_says_nothing_and_everything_is_restored():
    out = _run(PARSE_OPEN, page={"text": json.dumps(_rows(37))})
    assert out == {"ok": 37, "restored": True, "calls": [f"HEAD {OPEN}"]}


def test_the_json_is_read_from_the_viewers_pre_when_the_body_holds_more():
    page = {"text": "Pretty-print\n" + json.dumps(_rows(50)), "pre": json.dumps(_rows(50))}
    assert "exactly 50 items" in _run("() => 1", page=page)["ok"]["sanchopanza"]


def test_v7s_keys_are_not_quoted_twice_and_a_stated_total_silences_the_round_note():
    """H2: the World Bank's first element states `"pages":6, "total":295` beside 50 rows."""
    body = [{"page": 1, "pages": 6, "per_page": "50", "total": 295}, _rows(50)]
    note = _run(PARSE_OPEN, page={"text": json.dumps(body)})["ok"]["sanchopanza"]
    assert note.count("295") == 1 and '"total": 295' in note
    assert "exactly 50" not in note


def test_no_link_request_leaves_a_page_that_is_not_http():
    out = _run("() => 1", page={"text": "plain", "url": "about:blank"})
    assert out == {"ok": 1, "restored": True, "calls": []}


def test_xhr_rows_are_counted_like_fetched_rows():
    """H7: demoblaze loads its list by XMLHttpRequest; clicking Next 50 times read 303 cards of
    15 products, and no note counted them."""
    routes = {"/pagination": [200, json.dumps({"Items": [{"id": 1}, {"id": 2}, {"id": 3}]})],
              "/entries": [200, json.dumps({"Items": [{"id": 3}, {"id": 4}]})]}  # fmt: skip
    code = (
        "async () => { for (const u of ['/entries', '/pagination', '/pagination']) {"
        " const x = new XMLHttpRequest(); x.open('POST', u);"
        " await new Promise((r) => { x.addEventListener('loadend', r); x.send('{}'); }); }"
        " return 3; }"
    )
    out = _run(code, routes, {"url": "https://s/"})
    assert out["restored"] is True
    assert "fetched JSON rows 8, distinct 4." in out["ok"]["sanchopanza"]


def test_failed_xhrs_are_counted_by_status():
    routes = {"/ok": [200, "<body>fine</body>"], "/bad": [500, "oops"]}
    code = (
        "async () => { for (const u of ['/ok', '/bad', '/gone']) {"
        " const x = new XMLHttpRequest(); x.open('GET', u);"
        " await new Promise((r) => { x.addEventListener('loadend', r); x.send(); }); }"
        " return 1; }"
    )
    note = _run(code, routes, {"url": "https://s/"})["ok"]["sanchopanza"]
    assert "1 of 3 fetches answered 500" in note and "1 of 3 fetches answered network error" in note


def test_one_fetched_response_with_a_round_number_of_rows_and_no_total_is_named():
    routes = {"/r": [200, json.dumps(_rows(1000))]}
    code = "async () => JSON.parse(await (await fetch('/r')).text()).length"
    out = _run(code, routes)
    assert out["ok"]["result"] == 1000
    assert (
        "the one JSON response this call read held exactly 1000 rows and stated no total"
        in (out["ok"]["sanchopanza"])
    )


def test_one_fetched_response_whose_link_header_names_a_next_page_is_named():
    routes = {"/r": [200, json.dumps(_rows(37)), {"link": LINK}]}
    code = "async () => JSON.parse(await (await fetch('/r')).text()).length"
    note = _run(code, routes)["ok"]["sanchopanza"]
    assert "Link header: next https://s/api/houses?page=2&pageSize=10" in note


def test_a_walk_that_ended_on_a_short_page_says_nothing_new():
    routes = {"/r?p=1": [200, json.dumps(_rows(100))], "/r?p=2": [200, json.dumps(_rows(7))]}
    code = (
        "async () => { let n = 0; for (const u of ['/r?p=1', '/r?p=2'])"
        " n += JSON.parse(await (await fetch(u)).text()).length; return n; }"
    )
    note = _run(code, routes)["ok"]["sanchopanza"]
    assert "the one JSON response" not in note and "Link header" not in note


def test_v8s_sealed_wrapper_is_unchanged_by_v3():
    sealed = "a53df5997236e594a0e0a17d19264307df6d6de439c38470cadb86e6215c6e1e"
    assert hashlib.sha256(crawl.wrap("() => 1", 120, notes=2).encode()).hexdigest() == sealed
    v3 = crawl.wrap("() => 1", 120, notes=3)
    assert v3 != crawl.wrap("() => 1", 120, notes=2) and "XMLHttpRequest" in v3


@pytest.mark.parametrize(("raw", "version"), [("3", 3), ("2", 2), ("1", 1), ("", 0), ("4", 0)])
def test_notes_3_is_its_own_switch(raw, version):
    assert crawl.notes_on({"SANCHOPANZA_CRAWL_NOTES": raw}) == version


def test_the_guard_wraps_with_v3_when_asked():
    event = {"hook_event_name": "PreToolUse", "tool_name": "mcp__playwright__browser_evaluate",
             "tool_input": {"function": "() => 1"}}  # fmt: skip
    out = crawl.handle(event, env={"SANCHOPANZA_CRAWL_NOTES": "3"})
    assert "XMLHttpRequest" in out["hookSpecificOutput"]["updatedInput"]["function"]
    out2 = crawl.handle(event, env={"SANCHOPANZA_CRAWL_NOTES": "2"})
    assert "XMLHttpRequest" not in out2["hookSpecificOutput"]["updatedInput"]["function"]


def test_the_v3_note_is_moved_to_the_head_like_any_other():
    note = "sanchopanza: this call fetched nothing ... Link header: next https://s/x?page=2."
    text = '### Result\n{\n  "result": 10,\n  "sanchopanza": ' + json.dumps(note) + "\n}"
    moved = crawl.notes_first(text)
    assert moved.startswith(f"{crawl.NOTES_HEAD}\n{note}\n")


LONE = (
    '### Result\n{\n  "sanchopanza": "sanchopanza: this call fetched nothing."\n}\n'
    "### Ran Playwright code\nyour function, inside sanchopanza's evaluate guard (not repeated)"
)
V81_ENV = {"SANCHOPANZA_CRAWL_NOTES": "2", "SANCHOPANZA_CRAWL_NOTES_AT": "front"}


def test_a_note_that_is_the_whole_value_comes_first_with_v9():
    """v9's round, H8 run 1 of HAIKU-V9: a function that returned nothing came back as
    `{"sanchopanza": ...}`, with no comma before the key, and the note stayed where it was."""
    out = _post_text(LONE, {**V81_ENV, "SANCHOPANZA_CRAWL_NOTES": "3"})
    assert out.startswith(f"{crawl.NOTES_HEAD}\nsanchopanza: this call fetched nothing.\n")
    assert out.split("\n", 2)[2].startswith("### Result\nundefined\n### Ran Playwright code")


def test_v81_leaves_a_lone_note_where_it_was_as_it_was_measured():
    assert crawl.handle(_lone_event(), env=V81_ENV) is None


def _lone_event() -> dict:
    return {"hook_event_name": "PostToolUse", "tool_name": "mcp__playwright__browser_evaluate",
            "tool_input": {"function": "() => 1"},
            "tool_response": [{"type": "text", "text": LONE}]}  # fmt: skip


def _post_text(text: str, env: dict) -> str:
    event = {**_lone_event(), "tool_response": [{"type": "text", "text": text}]}
    return crawl.handle(event, env=env)["hookSpecificOutput"]["updatedToolOutput"][0]["text"]
