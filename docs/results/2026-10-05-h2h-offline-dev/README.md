# BrowseComp-Plus and LongBench v2 head to head, dev: N against S0

A development run of the two offline suites on Sonnet 5.5 (`claude-sonnet-5-5`), Claude Code
alone (N) against Claude Code with the S0 install line (S), to check both comparisons end to end
before the S line is sealed. **It is not a confirmation and no threshold was set from it.** Its
ids (`benchmarks/h2h/bcp-dev-ids.txt`, `benchmarks/h2h/longdoc-dev-ids.txt`) are left out of
every other phase by the runners. Only ids and numbers are written here: no question, document,
answer or quote.

## Set-up

- Runners `benchmarks/h2h/h2h_bcp.py` and `h2h_longdoc.py`; sanchopanza `src` frozen at
  be2818a (h2h with main and s-seal merged). Claude Code 2.1.287, pinned. One headless session
  per item and arm, arms interleaved within each item, one run, cap 3.00 USD per session, one
  ceiling of 49 USD in code for both suites together (each runner counts the other's spend and
  one session in flight per suite), plus 1 USD for the judge.
- Draws: 10 of the 100 prepared BrowseComp-Plus queries and 10 of the 60 prepared LongBench v2
  tasks, `random.Random(20261005).sample` of the sorted ids. LongBench dev: easy/hard 2/8,
  short/medium/long 3/6/1.
- Both arms: no web (WebSearch and WebFetch disallowed; `local_hook.py` denies a shell's network,
  paths outside the session's folder, S's fetch server and any MCP call carrying a URL), clean
  user per session. BrowseComp-Plus: the `bcp` MCP server (bm25s over the corpus, `search` and
  `get_document`) in both arms, the official QUERY_TEMPLATE, exact match then the official judge
  template on Haiku 4.5, then a blind hand read of the doubtful rows. LongBench v2: the document
  as `document.txt` in the folder, the official 0-shot template pointing at it, the official
  letter extraction.
- S0 = `sanchopanza install --guard --guard-profile coding --context-budget 160000 --memory
  --candor --find --find-auto --skill --scan-content --check-done --content-tools
  WebFetch,WebSearch,mcp__sanchopanza-fetch__fetch_passages --crawl --prune --fetch --provider
  jev`, with `SANCHOPANZA_CRAWL_LINE_VERSION=6`, `CRAWL_NOTES=3`, `CRAWL_ECHO=short`,
  `CRAWL_LINE_AT=prompt`, `CRAWL_NOTES_AT=front`, `CRAWL_SHOT=snapshot-first`,
  `FETCH_VERSION=2`, `GUARD_CHOOSER=keep` (`benchmarks/h2h/s_install.json`, unsealed). Every S
  session's install digest matched the preflight's (1cb296ac7bf02e8b); every Jev decision came
  from `jev`, none failed.

## BrowseComp-Plus (10 queries)

| | N | S |
|---|---|---|
| correct, official (EM, else Haiku judge; hand verdicts first) | 5/10 | 7/10 |
| correct, exact match only | 4/10 | 5/10 |
| cost, total / mean / median (USD) | 4.60 / 0.46 / 0.22 | 7.78 / 0.78 / 0.50 |
| turns, mean / median | 11.9 / 9 | 21.2 / 16 |
| wall, mean / median (s) | 65.9 / 38.9 | 106.3 / 68.0 |
| tokens per session, mean: cache read / cache write / output / input | 587k / 74k / 4.5k / 21 | 959k / 124k / 8.3k / 4.0k |
| `search` / `get_document` calls | 87 / 7 | 161 / 12 |
| evidence / gold recall of what the searches returned, mean | 0.40 / 0.55 | 0.56 / 0.65 |
| sessions at the cap | 0 | 0 |

Paired: S-only 2 (1076, 58), N-only 0, McNemar p = 0.5; on exact match alone S-only 1 (1076),
p = 1.0. Cost S/N 1.69 [1.15, 2.63], wall 1.61 [1.20, 2.36] (paired bootstrap, 95 %).

## LongBench v2 (10 tasks)

| | N | S |
|---|---|---|
| correct (official extraction) | 7/10 | 7/10 |
| cost, total / mean / median (USD) | 0.65 / 0.065 / 0.049 | 1.23 / 0.123 / 0.122 |
| turns, mean / median | 3.4 / 3 | 5.7 / 4.5 |
| wall, mean / median (s) | 18.4 / 17.1 | 39.3 / 32.5 |
| tokens per session, mean: cache read / cache write / output / input | 58k / 11k / 0.9k / 6 | 137k / 19k / 1.8k / 11 |
| tool calls (Grep / Read / Bash) | 14 / 10 / 0 | 23 / 16 / 1 |

The same 7 tasks right in both arms (no discordant pair, p = 1.0). Cost S/N 1.90 [1.38, 2.70],
wall 2.14 [1.56, 2.86].

## What S did

Of the line, offline, only five components acted; crawl, prune, fetch and the content scan have
no browser or web tool to act on, and find_in_repo was never called.

- **check-done sent back almost every session.** Its Jev `completion` question judged the
  request not done in all 10 BrowseComp-Plus sessions (p 0.05 to 0.42) and in 7 of 10 LongBench
  sessions; each of those was sent back once and answered a second time. **The second answer
  never changed a grade**: same exact-match result in all 10 BCP sessions (two changed their
  wording, wrong both times) and the same letter in all 7 LongBench ones. It is the bulk of S's
  extra turns and cost.
- **Candor** asked every prompt for its four-line status block (22 prompts) and logged every
  call (509 hook runs); its block never reached a grade (the extractors read the answer line
  only).
- **The guard's context budget** compacted two long BCP sessions (1076 once, 1098 twice) and
  re-injected the request verbatim; 1076 ended right, 1098 wrong.
- **Memory** ran on every prompt and stop (115 runs) and injected nothing (a fresh store each
  session).
- **Jev**: 22 decisions (20 `completion`, 2 `triage_pages`), 0.0044 USD in all.
- S called `fetch_passages` once (BCP 1076); the local hook denied it, as it denies WebFetch.

## The discordant pairs and the numbers that favour S, read by hand

- **1076** (S right, N wrong): S's first answer was already right, before the send-back; N
  stopped after 23 searches and 1 document at confidence 8 % and 1.58 USD, S went on to 41
  searches and 4 documents (one compaction) and reached every gold document. One more search
  budget, not a component, explains it; with one run it cannot be told from run-to-run variation.
- **58** (S right only through the judge): neither arm matches exactly. The judge said yes to
  S's answer and no to N's. Read blind: S's answer contains every gold token, in order, but
  behind another name it offers first; N's carries 5 of the 7. Left as the judge graded it, and
  doubtful.
- **15**: both arms judged right without an exact match (the gold, then a description); hand
  verdict yes for both. **168** S: the judge's reply had no verdict; hand verdict no.
- S's higher mean evidence and gold recall come from more searches (161 against 87), mostly in
  the long sessions that the send-back and the compactions prolonged.

## The retrieval index

Our bm25s index over the 100,195 documents with the raw query as the search, all 830 queries:
evidence recall @5 / @100 / @1000 = 1.3 / 4.9 / 14.2 %, gold 1.5 / 6.7 / 17.9 %. The
BrowseComp-Plus paper (Chen et al., 2025, table 2, the full question as the query,
BM25): evidence 1.2 / 4.7 / 13.7 %, gold 1.4 / 6.1 / 17.3 %. Within a point everywhere: the
index is a faithful BM25, and the low recall is the set's, not ours.

## Cost

BrowseComp-Plus 12.38 USD, LongBench v2 1.87 USD, judge 0.21 USD, Jev 0.004 USD: **14.47 USD**
at list, against a ceiling of 50.
