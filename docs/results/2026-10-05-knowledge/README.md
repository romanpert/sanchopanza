# The knowledge layer: search, read and pick, replayed for free

One MCP server, `sanchopanza-knowledge`, for agents that have to find and read in large results
and large knowledge bases. It is not a search engine: it finds what to read and hands over little
and good text, with no reader model in between.

- `search(query, k=8)`: Wikipedia's search API merged with a free web chain (ddgs Bing, then ddgs
  Yahoo, then a local SearXNG if one answers), no repeated URLs, a day of cache by the normalised
  query, "already searched" on a session's repeat, one call a second to Wikipedia with
  `Retry-After` honoured, and a circuit breaker per backend that only real answers move
  (`sanchopanza.serp`).
- `read(url_or_path, purpose, budget)`: fetch v2's passages for a web page, and the same for local
  files (PDF, DOCX, XLSX, CSV, TSV, Markdown, text, HTML; `sanchopanza.documents`), every passage
  under its place (`p. 12`, `Results > By region`, `Sheet > rows 2-21`) for citing. A document past
  20,000 characters, when a decision provider is configured, goes through the judged cascade:
  `select_passages` (tournament over passages, then sentences with a window of two) over a BM25
  shortlist of 60 passages, under 0.03 USD a read. After three guessed addresses in a row that
  came back 404 or as a disambiguation page, the next URL is not fetched: `read` searches for the
  purpose and returns the results.
- `pick(purpose, sources, budget)`: folders, files, globs or URLs to the documents that serve the
  purpose (one BM25 index over every passage, or the `triage_many` tournament with a provider) and
  their best passages.
- `sanchopanza install --knowledge`: the server with `alwaysLoad` (a project's `.mcp.json`, or the
  `claude mcp add-json` line for a user install) and a `PreToolUse` hook that denies the first
  WebSearch of a query and the first WebFetch of a URL with one line naming the tool, and lets the
  second run; WebSearch runs at once when the last real search found the chain down. It takes
  `--fetch`'s place. With `--scan-content` the three tools are scanned. Off by default
  (`KNOWLEDGE_DEFAULT = False`) until confirmed in live sessions.

Everything below is offline and free (`benchmarks/knowledge/offline.py`, no model, no money):
recorded sessions, cached pages and cached backend answers. Reports hold counts and sizes only.

## Search: the pilots' own queries (`search.json`)

The 196 WebSearch calls (193 distinct queries) of the first FRAMES pilot's base sessions, each
replayed through the backends' cached top-ten answers. Per session, the task's gold Wikipedia
articles that any of its searches returned.

| | Sonnet, 16 sessions: gold found | tasks with one | Haiku, 20 sessions: gold found | tasks with one |
|---|---|---|---|---|
| WebSearch (its results in the transcript) | 22/50 (44.0 %) | 12 | 30/63 (47.6 %) | 15 |
| Wikipedia alone, k=8 | 28/50 (56.0 %) | 15 | 38/63 (60.3 %) | 18 |
| **`search`, k=8** | **35/50 (70.0 %)** | **16** | **46/63 (73.0 %)** | **19** |
| `search`, k=10 | 35/50 (70.0 %) | 16 | 46/63 (73.0 %) | 19 |
| `search` or WebSearch | 37/50 (74.0 %) | 16 | 48/63 (76.2 %) | 19 |

One query of 193 had no result from any backend. The gold is Wikipedia articles, which favours a
Wikipedia backend: read this as "the article the task needs came back", not as web search quality.

Size: WebSearch's result in the transcript was 530 tokens a call (median 521, p90 656). `search` on
40 of the same queries, live: 539 tokens (median 532, p90 605), 7.9 results a query, none empty,
3.0 s median, no backend down. `search` has no reader and no fee; WebSearch's reader and fee cost
0.0227 USD a call on these pilots (`2026-10-05-browse-frames`, fitted).

## Read: the pilots' WebFetch pages (`read.json`)

The 187 WebFetch calls of both FRAMES pilots that returned 200 and whose page is cached as HTML;
the agent's WebFetch prompt as purpose. Gold: the task's answer under the grader's rule, on the 66
pages that hold it.

| | gold, of 66 | tokens mean (median, p90) |
|---|---|---|
| WebFetch's summary | 22 | 140 (129, 230) |
| fetch v2 passages, 4,000 characters | 57 | 839 (991, 1,084) |
| `read`, 4,000 | 57 | 841 (994, 1,086) |
| fetch v2 passages, 8,000 (default) | 62 | 1,344 (1,448, 2,089) |
| **`read`, 8,000 (default)** | **62** | **1,346 (1,448, 2,102)** |

`read` is fetch v2 on web pages (the two extra tokens are the longer header of the 29 pages past
20,000 characters; with no provider those are cut as fetch v2 cuts them).

## Long documents: QASPER (`longdocs.json`)

One question per QASPER test paper (the 300 of `benchmarks/longdocs/run.py`, its seed; 297 whose
answer sentences are found in the text), each paper read as one document with its sections as
places and the question as purpose. Recall: every answer sentence (QASPER's highlighted evidence)
found whole in what is returned. Papers average 5,530 tokens; 163 pass 20,000 characters.

| 297 questions | every answer sentence | any | tokens mean | text kept |
|---|---|---|---|---|
| the whole paper | 100 % | 100 % | 5,530 | 100 % |
| fetch v2 passages, 4,000 | 49.2 % | 62.6 % | 936 | 21.1 % |
| BM25 cascade (places, passages, sentences), 4,000 | 44.1 % | 56.2 % | 926 | 20.1 % |
| fetch v2 passages, 8,000 | 71.7 % | 82.2 % | 1,832 | 40.6 % |
| BM25 cascade, 8,000 | 55.2 % | 68.4 % | 1,558 | 32.1 % |
| fetch v2 passages, 16,000 | 83.8 % | 91.9 % | 3,211 | 69.1 % |
| BM25 cascade, 16,000 | 61.3 % | 73.1 % | 2,138 | 41.2 % |

A cascade by BM25 alone loses at every budget, so it is not shipped: without a provider, `read`
gives fetch v2's passages for a long document too. Ablations on the 163 long papers placed the
loss in the sentence step (a matching sentence's neighbours are often the answer and share no word
with the question; whole passages in its place recover part of it) and in leaving out the
document's lead and the sections the question names, which fetch v2 keeps.

The judged cascade, replayed from Jev's recorded answers of the 2026-09-27/28 QASPER runs (the
fixtures in `fixtures/`), on the 195 papers whose every call was recorded (60 passages or fewer,
one passage per paragraph, as those runs asked):

| 195 questions | every answer sentence | any | tokens mean | text kept |
|---|---|---|---|---|
| judged cascade, 4,000 | 81.0 % | 88.7 % | 720 | 17.1 % |
| fetch v2 passages, 4,000 | 59.5 % | 71.3 % | 932 | 23.0 % |
| **judged cascade, 8,000** | **88.7 %** | **95.4 %** | **995** | **22.4 %** |
| fetch v2 passages, 8,000 | 81.0 % | 88.7 % | 1,810 | 43.9 % |
| judged cascade, 16,000 | 91.3 % | 96.4 % | 1,122 | 24.7 % |
| fetch v2 passages, 16,000 | 92.3 % | 96.9 % | 3,234 | 76.2 % |

10.6 decisions and 0.0015 USD a read at recorded prices. These questions are the ones the
cascade's rule (gate 0.75, window 2) was derived on, so this replay checks the wiring, not the
rule: the rule's confirmation is the 2026-09-28 run on 219 new questions (87.2 % at 21 % of the
text, `2026-09-28-lateral-wholedocs`).

A live smoke of the server (stdio, no provider): the IPCC AR6 Synthesis Report's longer report
(PDF, 345,000 characters) read in 10 s for "how much has global surface temperature increased
since 1850-1900", 5,357 characters returned with the answer under `## p. 8`.

## Pick: the pilots' pages as one knowledge base (`pick.json`)

The 116 unique pages of part 2 as one corpus; each of the 18 tasks with an answer-bearing page of
its own asks `pick` with its question as purpose (BM25, top 5, default budget).

| tasks | a chosen document is one of the task's own answer pages | answer in the returned passages | tokens mean |
|---|---|---|---|
| 18 | 17 | 14 | 2,113 |

On average 3.3 of the 5 chosen pages were the task's own. The pool holds only pages the agents
found for these tasks, so this is a small, easy corpus; the judged choice (`triage_many`) was not
replayed.

## Per session (`sessions.json`)

The first pilot's base sessions, with their own calls: what WebSearch and WebFetch put in the
context against the same calls through `search` and `read`, and the readers' cost that goes away.

| | sessions | searches | fetches | context tokens a session, WebSearch+WebFetch | search+read | readers avoided a session |
|---|---|---|---|---|---|---|
| Sonnet | 16 | 70 | 27 | 2,515 | 4,144 | 0.140 USD |
| Haiku | 20 | 126 | 0 | 3,378 | 3,396 | 0.143 USD |

On Sonnet the 1,629 extra tokens cost about 0.008 USD at the pilots' cache pattern (written once,
read by about four later calls: 4.83 USD a million), against 0.140 USD of readers avoided. The
calls are the sessions' own: whether an agent searches or opens pages differently with these tools
is what live sessions must show.

## Guessed addresses, on the fetch v2 confirmation (`guess.json`)

The confirmation of fetch v2 did not pass: Haiku's price came to 0.808 of the base where 0.80 was
required, with answers level. Its worst session (FR719) made 38 page calls, 14 of them 404s
answered with a note to search that it ignored, never searched and gave no answer. `read` now
substitutes the search itself after three such misses in a row. Replayed on the 120 -FETCH2
sessions (every page call and search in time order; a search starts the count again):

| arm | page calls (missed) | sessions where it fires | firings | page calls after the first | spend after the first | arm spend |
|---|---|---|---|---|---|---|
| HAIKU-FETCH2 | 243 (44) | 1 (FR719) | 3 | 32 (13 missed) | 0.270 USD | 7.580 USD |
| SONNET-FETCH2 | 49 (0) | 0 | 0 | 0 | 0 | 9.681 USD |

It fires in that session only and nowhere else. The spend after its first firing is the most it
could save: with it all, Haiku's arm would have cost 7.310 against the base's 9.379 (0.779); if
the agent then spent a median session's 0.082 reading from the results, 7.392 (0.788). That is
arithmetic on one session, not a confirmation.

## What it does not say

- Nothing here ran an agent. Search's gain is in what comes back for the agents' own queries;
  read's is what reaches the agent; whether sessions search, read and answer better or for less
  with these tools is the next measurement.
- The judged path of `read` and `pick` was not run live; `read`'s is a replay of recordings on
  derivation questions, and `pick`'s was not replayed.
- The guessed-address count lives in the server, which does not see WebSearch: with the hook, a
  session's first WebSearch is sent to `search`, which does reset it.
- `search` takes 3 s at the median against WebSearch's single call: Wikipedia is paced to one call
  a second, its OR fallback is a second call, and Yahoo is asked when Bing has nothing.

## Reproduce

```
python benchmarks/knowledge/offline.py search --live-sample 40   # cached answers; 40 live, free
python benchmarks/knowledge/offline.py read
python benchmarks/knowledge/offline.py longdocs --qasper ~/.cache/sancho/qasper-test.jsonl
python benchmarks/knowledge/offline.py pick
python benchmarks/knowledge/offline.py sessions
python benchmarks/knowledge/offline.py guess
```

The backend answers, pages and sessions are in the private cache (`~/.cache/sanchopanza/free/`).
