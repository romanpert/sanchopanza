# D offline: a check of the returned documents in BrowseComp-Plus (2026-10-07)

Replay, not a session: Jev `triage_part` (jev-1.13.0) asked about documents the BrowseComp-Plus
confirmation's searches already returned (`benchmarks/h2h/d_replay.py`, h2h-d 73789ce). Owner's
OK for up to 0.40 USD of Jev; spent **0.112 USD** for 2,674 decisions, 0 failed. Report:
`report-d.json`. Counts and probabilities only; no query, document or answer text.

## Question

In the Sonnet 5.5 confirmation (2026-10-06), 17 sessions (8 N, 9 S) got a gold document (one that
holds the answer, official qrels) back from a search and still answered wrong. Would a cheap
check of each returned document ("does this hold a fact the answer would use?") have pointed the
agent at it, and at what cost in false alarms?

Sessions: all 17 wrong with a gold document seen, 15 right ones with a gold document and 10 wrong
ones that never saw one (fixed samples, seed 20261007). Each unique (query, document) judged once.

## Results

- Separation: AUC **0.95** gold against every other document, 0.953 against documents that are not
  even evidence. Jev recognises the answer's document well from a 1,500-character excerpt.
- Flags per session at each cut (gold flagged / false flags, mean):

| Cut | Wrong with gold (17) | Right with gold (15) | Wrong, never gold (10) |
|---|---|---|---|
| 0.7 | 12 / 3.8 | 15 / 2.3 | 0 / 4.8 |
| 0.8 | 6 / 1.6 | 13 / 1.4 | 0 / 1.7 |
| 0.9 | 4 / 0.0 | 10 / 0.3 | 0 / 0.2 |

- **But 10 of the 17 had already opened the gold document** (`get`) and answered wrong anyway: a
  reading failure that a flag does not change. Of the 7 that never opened it, the gold is flagged
  at 0.9 in **3** (2 N, 1 S), with almost no false alarms.

## What it says

The ceiling of D as a nudge ("this returned document likely answers: read it") is about 3 answers
in 180 sessions, 1 in S's 90. It is not where S can win BrowseComp-Plus. Where the wrong answers
are: 58 of 75 wrong sessions never saw a gold document (retrieval), and 10 of the other 17 read it
and still missed (reading). The AUC is worth keeping for any later use of document-level checks.
