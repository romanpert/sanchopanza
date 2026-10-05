"""Crawl notes: what the page and the network said during one `browser_evaluate`, appended to its
result by the evaluate guard (`crawl_hook.wrap(..., notes=True)`). No model and no decision: the
notes quote facts and the agent decides what they mean.

Why they exist (`docs/results/2026-10-03-browse-v6/`): with the strategy line, the cheap model's
largest kind of miss was a single call that read only the open page (10 rows of 57, 15 products
of 75, 16 of 755) while the page stated its size on screen. Next came pages served twice under a
guessed `?page=N`, and 429s that the code swallowed. Three versions of the line asked for that
check and the model did not make it. So the check is made where the result lands:

- the call made no `fetch`: quote what the open page states about its size (a "Showing 1 to 10
  of 57" line, a "Page 1 of N", numbered pagination links, a JSON count) and its next link;
- some fetches failed: count them by status (or `network error`);
- some fetched pages had exactly the same visible text as an earlier, different URL (what a
  guessed URL or a page past the end is served as; `benchmarks/browse/repeat_fingerprint.py`).

How: PreToolUse can rewrite a call's input but never its result, so the notes are computed
inside the wrapped function. The wrapper swaps `window.fetch` for a counting copy while the
function runs and puts the original back afterwards. When there is something to say, the value
comes back as `{result, sanchopanza}`. When there is nothing to say, it comes back unchanged. If
the function throws, its error message gains the notes. Only `fetch` is watched; XMLHttpRequest
is not.
"""

from __future__ import annotations

import json

NOTES_MARK = "/* sanchopanza notes */"
SETTLE_MS = 3000  # how long the notes wait for the fetched bodies they read to finish
MAX_PARSE_CHARS = 2_000_000  # a body larger than this is compared as raw text, not parsed

# The wrapper's code, joined into one line by `wrap_with_notes` (no line here splits a string or a
# regular expression). `__RUN__`, `__LIMIT__`, `__MESSAGE__` and the two sizes are filled in
# there. Kept short: Playwright MCP echoes the code it ran in every evaluate's result.
_TEMPLATE = r"""
async (...args) => { __NOTES_MARK__ const run = (__RUN__);
const sp = {n: 0, bad: {}, seen: new Map(), same: [], reads: []}; const of = window.fetch;
window.fetch = async (...a) => { sp.n++; const u = String((a[0] && a[0].url) || a[0]);
try { const r = await of.apply(window, a);
if (!r.ok) { sp.bad[r.status] = (sp.bad[r.status] || 0) + 1; }
else { sp.reads.push(r.clone().text().then((t) => { let k = t;
if (t.length < __MAXPARSE__ && /<html|<body/i.test(t)) {
const d = new DOMParser().parseFromString(t, 'text/html');
d.querySelectorAll('script,style').forEach((e) => e.remove());
k = d.body ? d.body.textContent : t; }
k = k.replace(/\s+/g, ' ').trim(); const was = sp.seen.get(k);
if (was === undefined) sp.seen.set(k, u); else if (was !== u) sp.same.push([u, was]);
}).catch(() => {})); } return r; }
catch (e) { sp.bad['network error'] = (sp.bad['network error'] || 0) + 1; throw e; } };
const notes = async () => {
const settle = new Promise((r) => setTimeout(r, __SETTLE__));
await Promise.race([Promise.allSettled(sp.reads), settle]);
const out = []; const bad = Object.entries(sp.bad);
if (bad.length) out.push(bad.map(([s, c]) => c + ' of ' + sp.n + ' fetches answered ' + s)
.join('; ') + ': those pages were not read.');
if (sp.same.length) out.push(sp.same.length + ' fetched pages had exactly the text of an'
+ ' earlier, different URL (' + sp.same[0][0] + ' = ' + sp.same[0][1]
+ '): a guessed URL or a page past the end is served as a copy.');
if (!sp.n && document.body) {
const t = document.body.innerText || document.body.textContent || ''; const said = [];
for (const re of [/Showing\s+\d[\d,]*\s*(?:-|\u2013|to)\s*\d[\d,]*\s+of\s+\d[\d,]*[^\n]{0,24}/i,
/\bPage\s+\d+\s+of\s+\d+/i, /\b\d[\d,]*\s+(?:results|entries|records)\b/i]) {
const m = t.match(re); if (m) { said.push(m[0].trim()); break; } }
const keys = 'count|total|totalCount|total_count|pages|last_page|total_pages|recordsTotal';
const js = t.match(new RegExp('"(?:' + keys + ')"\\s*:\\s*\\d+', 'g'));
if (js) said.push(js.slice(0, 3).join(', '));
const links = document.querySelectorAll(
'[class*=pagin] a, [id*=pagin] a, [data-testid*=pagin] a, nav a');
const nums = [...links].map((a) => a.textContent.trim()).filter((x) => /^\d+$/.test(x)).map(Number);
if (nums.length > 1) said.push('pagination links up to page ' + Math.max(...nums));
const next = document.querySelector('a[rel=next]');
if (next && next.href) said.push('next link ' + next.href);
if (said.length) out.push('this call fetched nothing, so it read only the open page, which says: '
+ said.join(' | ')
+ '. If the request covers more than this page, fetch the rest before answering.');
}
return out.length ? 'sanchopanza: ' + out.join(' ') : ''; };
let timer; const limit = new Promise((_, reject) => { timer = setTimeout(
() => reject(new Error(__MESSAGE__)), __LIMIT__); });
try { const v = await Promise.race([Promise.resolve().then(() => run(...args)), limit]);
const n = await notes(); return n ? {result: v, sanchopanza: n} : v; }
catch (e) { const n = await notes();
if (n) throw new Error(String((e && e.message) || e) + ' | ' + n); throw e; }
finally { clearTimeout(timer); window.fetch = of; } }
"""


# Notes v2 (v8 in development, `SANCHOPANZA_CRAWL_NOTES=2`), each from a miss of confirmation 4
# read by hand: clicks inside the call that never changed the page's text (G6: the rows were in
# the DOM, paged by CSS, and were read again after every click), and the rows of the fetched JSON
# against the distinct ones (G3: overlapping guessed pages, 332 rows of which 298 distinct). Both
# give numbers and no advice. `click` is only observed: the original runs, and is put back.
# Each (anchor, insertion, before) goes into v1's code beside the anchor, so v1's wrapper stays
# byte for byte what confirmation 4 sealed.
_V2 = (
    (
        "const of = window.fetch;",
        "Object.assign(sp, {clicks: 0, still: 0, last: null, rows: 0, uniq: new Set()}); "
        "const oc = window.HTMLElement && HTMLElement.prototype.click; "
        "const txt = () => (document.body && document.body.textContent) || ''; "
        "const ck = () => { if (sp.last !== null && txt() === sp.last) sp.still++; }; "
        "if (oc) HTMLElement.prototype.click = function (...a) { ck(); sp.clicks++; "
        "sp.last = txt(); return oc.apply(this, a); }; "
        "const rowsOf = (t) => { if (t.length >= __MAXPARSE__ || !/^\\s*[[{]/.test(t)) return; "
        "let j; try { j = JSON.parse(t); } catch (e) { return; } "
        "const isRows = (a) => Array.isArray(a) && a.length > 0 "
        "&& a.every((x) => x && typeof x === 'object' && !Array.isArray(x)); "
        "let best = isRows(j) ? j : null; "
        "if (!best && j && typeof j === 'object') for (const v of Object.values(j)) { "
        "if (isRows(v) && (!best || v.length > best.length)) best = v; } "
        "if (best) for (const x of best) { sp.rows++; sp.uniq.add(JSON.stringify(x)); } };",
        False,
    ),
    ("then((t) => { let k = t;", "rowsOf(t);", False),
    (
        "if (!sp.n && document.body) {",
        "if (sp.rows) out.push('fetched JSON rows ' + sp.rows + ', distinct ' + sp.uniq.size "
        "+ '.'); ck(); if (sp.clicks >= 2 && sp.still === sp.clicks) out.push(sp.clicks "
        "+ ' clicks did not change the page text: the rows were already loaded.');",
        True,
    ),
    ("window.fetch = of;", "if (oc) HTMLElement.prototype.click = oc;", False),
)


def _with_v2(code: str) -> str:
    for anchor, insertion, before in _V2:
        if code.count(anchor) != 1:
            raise ValueError(f"notes v2: the anchor {anchor!r} is not in v1's code once")
        joined = f"{insertion} {anchor}" if before else f"{anchor} {insertion}"
        code = code.replace(anchor, joined)
    return code


def wrap_with_notes(function: str, limit_s: int, message: str, mark: str, version: int = 1) -> str:
    """`crawl_hook.wrap`'s time limit, plus the notes. `mark` (the guard's own) goes first so
    the guard still recognises a call it has already wrapped. The function keeps lines of its
    own, so a trailing `// comment` in it cannot swallow what follows. `version` 2 adds the
    click and JSON-row notes (`_V2`); 1 is v7's wrapper, unchanged."""
    code = " ".join(line.strip() for line in _TEMPLATE.strip().splitlines())
    if version >= 2:
        code = _with_v2(code)
    for key, value in (
        ("__NOTES_MARK__", NOTES_MARK),
        ("__MAXPARSE__", str(MAX_PARSE_CHARS)),
        ("__SETTLE__", str(SETTLE_MS)),
        ("__MESSAGE__", json.dumps(message)),
        ("__LIMIT__", str(limit_s * 1000)),
    ):
        code = code.replace(key, value)
    return f"{mark} " + code.replace("__RUN__", "\n" + function + "\n", 1)
