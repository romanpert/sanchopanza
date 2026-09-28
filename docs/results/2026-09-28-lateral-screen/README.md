# A lexical screen and one in-context call do the tournament's work on an off-topic crowd, in one call instead of five

Pre-registered in `prereg.md` (hash in `prereg.sha256`) before any call. The 200 held-out
questions of `../2026-09-27-hierarchy/` (HotpotQA distractor, validation, CC BY-SA 4.0), each
with 100 pages: its own ten and 90 paragraphs of other questions, shuffled. **SCREEN**: BM25
keeps the 30 pages it ranks highest (what one call holds, `chunks.PAGE_MAX`), then one
`Squire.triage_pages` call judges those 30 together at the shipped cut 0.40. Nothing was
derived. The tournament's answers replay from `fixtures/hierarchy.jsonl`.

## Result: confirmed

| arm, 200 held-out questions | both supporting pages kept (95 % CI) | text kept | pages kept | Jev calls | Jev cost per question |
|---|---|---|---|---|---|
| **SCREEN**: BM25 top 30, one call at 0.40 | **96.0 %** (92.3-98.0) | **3.4 %** | 4.1 | **1** | **0.49 thousandths USD** |
| TOUR (`triage_many`, published) | 96.5 % (93.0-98.3) | 3.1 % | 3.7 | 5 | 1.76 thousandths (replayed, 1,000 calls, 0.353 USD) |
| FLAT (groups alone, published) | 94.0 % | 4.3 % | 5.0 | 4 | |
| BM25 top 30 alone (the screen's ceiling) | 99.0 % | 31.7 % | 30 | 0 | |

- **S1 holds**: 96.0 % against the tournament's 96.5 % (bar: at most 1 point below), with 3.4 %
  of the text against 3.1 % (bar: at most 1 point above).
- **S2 holds, at its edge**: SCREEN minus TOUR is -0.5 points, paired bootstrap 95 % CI
  [-3.0, +2.0]; the bar was a lower bound of at least -3 points, and it is exactly -3.0. The two
  disagree on 7 questions (3 kept only by the screen, 4 only by the tournament; McNemar p = 1.0).

One call replaces five, at 28 % of the tournament's Jev cost per question, and with one round
trip instead of two in sequence. The prediction (95-98 % at 3-4 %) held.

## The boundary: not for one long document

The screen is only as good as lexical retrieval over the crowd it screens. Here the crowd is off
topic, so BM25's top 30 holds both supporting pages in 99 % of questions and the in-context call
does the rest. On a single paper the crowd is the paper itself: on the 217 QASPER papers of
`../2026-09-27-longdocs/` with more than 30 paragraphs, BM25's top 30 holds all evidence in
**82.0 %** of questions, where the tournament's recorded keep holds it in **95.4 %** on the same
questions (both computed without a call; the 82.0 % was known before registration). No call can
recover a page the screen dropped, so on whole documents the screen would lose at least 13 points.

The rule that falls out, stated as a proposal and not measured beyond these two sets: a
heterogeneous pool (search results, many documents on many topics) is screened lexically and
judged in one call; a homogeneous one (one long document) goes through the tournament.

## Proposed library change (not made: `src/` is out of scope for this run)

An opt-in `screen` argument on `Squire.triage_many`, default off so nothing shipped changes:

```python
async def triage_many(self, *, purpose, pages, screen: int | None = None):
    # screen=chunks.PAGE_MAX: keep the `screen` pages BM25 ranks highest, in their order, and
    # judge them in one triage_pages call; every other page is dropped. For heterogeneous
    # pools only (docs/results/2026-09-28-lateral-screen/).
```

It needs a BM25 in `sanchopanza.text` (the benches' `bm25_scores` is 15 lines, no dependency).

## Paragraph ready for the paper (5.16) and the README

> **A tournament in one call, where the crowd is off-topic.** Round one of the tournament only has
> to be lenient, and over a crowd of off-topic pages lexical retrieval is lenient for free: BM25's
> top 30 of 100 pages held both supporting pages in 99 % of questions. Judging those 30 in one
> in-context call at the shipped 0.40 kept both in **96.0 %** of the 200 held-out questions at
> 3.4 % of the text, against 96.5 % at 3.1 % for the five-call tournament (paired difference -0.5
> points, 95 % CI -3.0 to +2.0), at 28 % of its Jev cost, pre-registered. On one long paper the
> same screen would hold all evidence in only 82 % of questions where the tournament keeps 95 %:
> screen heterogeneous pools, run the tournament over one document.

## Cost and reproducing

200 Jev calls, **0.0989 USD** (`fixtures/lateral-screen.jsonl`), mean latency 326 ms per call.

```bash
python benchmarks/lateral/screen/run.py --hotpot HOTPOT.jsonl --qasper QASPER-TEST.jsonl   # free
```

`tests/test_lateral_screen.py` pins every number above (needs `SANCHOPANZA_HOTPOT`; the boundary also
`SANCHOPANZA_QASPER`).

## Limits

- The 90 added pages are off-topic by construction; with a crowd of hard distractors the screen's
  ceiling would fall, as it does on papers.
- 200 questions: a 1-point difference is far inside the noise; the claim is non-inferiority at a
  3-point margin, met at its edge, not equality proved.
- Paragraphs are short English Wikipedia text; one call over 30 long pages truncates each at
  `chunks.PAGE_LIMIT` (900 characters).

## Status (2026-09-28)

Not replicated, and retired. On 200 fresh questions, pre-registered, SCREEN kept 96.5 % against
the tournament's 97.5 %, lower bound -4 points against the registered -3; six of its seven misses
were pages BM25 dropped before any call ([confirmation](../2026-09-28-lateral-screen-confirm/)).
Not a candidate for anything; this folder is the record.
