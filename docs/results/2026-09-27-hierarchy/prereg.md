# Pre-registration: a tournament of in-context calls for sets larger than one call holds

Written 2026-09-27 before any call of this run. `benchmarks/hierarchy/run.py --live` refuses to
spend unless the sha256 of this file plus `src/sanchopanza/points/hierarchy.py` and
`src/sanchopanza/points/chunks.py` matches `prereg.sha256`.

## Why

`triage_pages` (one call, one Truth per page, every page in view) is confirmed on sets of 10:
98.3 % of questions keep every supporting page at 34 % of the text
(`../2026-09-27-chunks/prereg-confirm.md`). One call holds at most 30 pages (`PAGE_MAX`) and
32k tokens of state. Search results, catalogues and long documents are larger. Splitting a set
into groups judges each page among strangers, not among its real rivals. The tournament
(`points/hierarchy.py`, after LATTICE, arXiv:2510.13217) keeps the in-context shape: groups
first at a lenient cut, then the survivors judged together.

## Data

HotpotQA distractor, validation (CC BY-SA 4.0). 300 questions with exactly 10 paragraphs, drawn
with `random.Random(2029).sample` from those not used by any earlier run (seeds 2026, 2027,
2028). First 100 of the sample: **derivation**. Last 200: **held-out**.

Each question gets 100 pages: its own 10 (2 supporting, 8 retrieved distractors) and 90
paragraphs drawn from other questions outside the 300 and the earlier sets, skipping any whose
title equals one of the question's own titles, with `random.Random("2029-<id>")`. The 100 are
shuffled by the same generator. A page is `(title, sentences joined by a space)`.

Limit, stated before: the 90 added pages are off-topic, so this tests whether a crowd of pages
and splitting into groups degrade the judgement, not whether hard distractors are separated
(the 8 own distractors do that, as before).

## Arms

- **FLAT**: the 100 pages in 4 balanced groups of 25 (`hierarchy.groups(100, 30)`), one
  `chunks.context_questions` call per group; a page is kept when p >= 0.40, the confirmed cut.
- **TOUR**: the same round-one answers; pages with p >= r1 go to one final call together
  (`context_questions` over the survivors, in their shuffled order); kept when the final
  p >= 0.40. Unanswered pages are kept in either round.
- **BLEND** (secondary): TOUR's calls; kept when 0.5 * p_round1 + 0.5 * p_final >= 0.40.
- **BM25**: pages ranked by BM25 of the question against `title text` (the triage run's
  tokeniser), top k, with k the held-out mean pages kept by TOUR, rounded up.

## Derivation rule

r1 is read from round-one answers only, on the derivation set: the largest cut on 0.00..0.40
step 0.01 at which round one alone keeps both supporting pages in >= 99 % of questions. The
final cut is not tuned: 0.40.

## Metrics

**Page joint recall**: both supporting pages kept. **Kept share**: characters kept over the
characters of all 100 pages. **Calls** per question. **Pages kept** per question.

## Criteria, on the 200 held-out questions

- **P25**: TOUR page joint recall >= 0.95 with kept share <= 0.08.
- **P26**: TOUR page joint recall >= FLAT's minus 1 point, with a kept share below FLAT's.
- **P27** (secondary): TOUR minus BM25 page joint recall at k pages, reported; holds at
  >= 5 points.

Verdict: P25 and P26 = **confirmed**, and `Squire.triage_many` ships with r1 and 0.40;
otherwise not confirmed, and nothing ships.

## Cost

Round one 4 calls per question of ~9k tokens, the final 1 call: about 1,500 Jev calls,
about 0.6 USD at 0.042 USD per million input tokens. Recorded in `fixtures/hierarchy.jsonl`.
