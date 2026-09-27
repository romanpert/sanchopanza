# Pre-registration: return only the sentences that contribute, and judge pages in each other's context

Written 2026-09-27 before any call of this run. `benchmarks/chunks/run.py --live` refuses to
spend unless the sha256 of this file plus `src/sanchopanza/points/chunks.py` matches
`prereg.sha256`.

## Why

Page triage by contribution (`../2026-09-25-triage/`, confirmed) keeps or drops whole pages:
93.3 % joint recall of the supporting paragraphs at 52 % of the text. Two questions from the
owner: can it return only the relevant parts of each page, and does seeing the other pages
help? A long document (a 117,000-character PDF in a real Indagis job) is where the first
matters; the second costs one call per set instead of one per page.

## Data

The same HotpotQA distractor validation export. **Derivation**: the 300 questions of the first
triage run (seed 2026). **Held-out**: the 300 of the confirmatory run (seed 2027, disjoint).
Neither arm below has been asked on either set. Sentence labels are HotpotQA's
`supporting_facts` (title, sentence index): 718 supporting sentences on the derivation set, all
in range.

## Arms

- **A, page contribution** (recorded, no new calls): `triage.contribution_questions` at 0.28;
  a kept page returns all its sentences.
- **B, sentence contribution**: `chunks.sentence_questions`, one call per page, one question
  per sentence; a sentence is kept when p >= b.
- **E, hybrid**: a sentence is kept when A keeps its page and B's p >= e. Free from A and B.
- **C, pages in context**: `chunks.context_questions`, one call per question over the 10
  pages; a page is kept (all its sentences) when p >= c.
- **D, BM25 over sentences**: the triage run's tokeniser, query = question, each sentence
  prefixed with its page title; keep the top k per question.

## Metrics

**Sentence joint recall**: every supporting sentence of the question kept. **Page joint
recall**: every supporting page keeps at least one sentence. **Kept share**: characters kept /
characters of all 10 pages.

## Derivation rule

Each knob (b, e, c over 0.00..1.00 step 0.01; k over 1..40) is the one reaching **sentence
joint recall >= 0.90 on the derivation set at the smallest mean kept share**; if none reaches
it, the one with the highest sentence joint recall.

## Criteria, on the held-out set

- **P15**: B or E reaches sentence joint recall >= 0.90 at kept share <= 0.35 (A keeps 0.52).
- **P16**: C reaches page joint recall within 2 points of A's (0.933) at a kept share no
  higher than A's (0.523), in one call per question instead of ten.
- **P17**: the better of B and E, against D given at least its kept share: sentence joint
  recall higher by >= 10 points.

## Secondary, only if P15 holds

`claude-haiku-4-5` answers the held-out questions from the best of B/E's kept sentences, with
`prereg-answers.md`'s prompt and scoring from the triage run, beside its recorded answers from
all pages (67.7 %) and from A (69.0 %). Reported whichever way it falls.

## Cost

About 6,600 Jev calls (B: 10 per question, C: 1), about 0.35 USD. The Haiku answers, if run,
about 0.15 USD in batch.
