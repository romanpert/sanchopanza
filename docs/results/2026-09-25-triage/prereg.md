# Pre-registration: page triage that keeps every part of a multi-part answer

Written 2026-09-25, before any call of this experiment. `benchmarks/triage_sets/run.py`
refuses to spend unless the sha256 of this file plus `src/sanchopanza/points/triage.py`
matches `prereg.sha256`.

## The failure this addresses

With the document sequence held fixed, the shipped triage cut input tokens by 75 % and took
correct answers from 10/10 to 6/10; every failure dropped the answer, and on the two
composite questions it dropped every answer document (`../2026-09-24-fixed-sequence/`). A
question asked once per page, "does this page address the purpose?", says no to each page
of a multi-part answer, correctly, until the answer is gone. Those 10 tasks revealed the
failure, so they are not used here.

## Data

HotpotQA, distractor setting, validation split (Yang et al., EMNLP 2018; CC BY-SA 4.0),
from `huggingface.co/datasets/hotpotqa/hotpot_qa`, file
`distractor/validation-00000-of-00001.parquet`. Each question comes with 10 paragraphs, of
which the `supporting_facts` titles (2 per question) hold the facts the answer needs: labels
by construction, written by neither this repository nor its author. Every question is
multi-part by construction: `bridge` (find an entity, then a fact about it) or `comparison`
(one fact about each of two entities).

Sample: 300 questions with exactly 10 paragraphs, drawn with `random.Random(2026).sample`
from the 7,345 that have 10. Nothing else is filtered.

## Arms

A paragraph's text is its sentences joined with a space; its title goes in the `title` field.

- **A, shipped**: `Squire.triage_page(purpose=question, title, text)` with the shipped
  thresholds; a paragraph is kept when the policy keeps it (relevance >= 0.45). One call per
  paragraph. Also reported with its relevance threshold derived (rule below).
- **B, contribution**: `triage.contribution_questions`, one call per paragraph; kept when
  P(contributes) >= c.
- **C, set**: `triage.set_questions` over the 10 paragraphs in their dataset order, one call
  per question; kept when the paragraph's probability >= s.
- **D, BM25**: Okapi BM25 (k1 1.5, b 0.75) over title plus text, query = question,
  lowercase, punctuation stripped, English stopwords removed and a plural `s` stripped; keep
  the top k. Given its best chance: k is derived with the same rule as the others.

## Metrics

Per question: **joint recall** = both supporting paragraphs kept; **kept share** = characters
kept / characters of all 10 paragraphs. Reported: mean joint recall, per-paragraph recall of
supporting paragraphs, mean kept share, for `bridge` and `comparison` apart and together.

## Split and derivation rule, fixed here

DERIVATION when `int(sha256(id).hexdigest()[:8], 16)` is even, HELD-OUT otherwise. For every
arm with a knob (A-derived's relevance cut, B's c, C's s over 0.00..0.50 step 0.01, D's k
over 1..10), the knob is the one that reaches **joint recall >= 0.95 on the derivation half
with the smallest mean kept share**; if none reaches it, the knob that maximises joint
recall. Held-out numbers only.

## Criteria, fixed here

- **P3**: B on the held-out half reaches joint recall >= 0.90 with mean kept share <= 0.50,
  and its joint recall beats A (shipped, 0.45) by >= 10 points.
- **P4**: C on the held-out half reaches joint recall >= 0.90 with mean kept share <= 0.40.
- **P5**: the better of B and C beats D (BM25 at its derived k) on kept share at matched
  joint recall, i.e. its kept share is lower by >= 0.05 while its joint recall is within 2
  points of D's or higher.

Verdict: P3 or P4, plus P5 = **solid**; P3 or P4 without P5 = **works but a free baseline
does it**; neither = **negative**. All three are published whichever way they fall.

## Cost, said before running

A: 3,000 calls of four questions (the shipped triage asks relevance, evidence, injection
and source kind together), B: 3,000 calls of one, C: 300 calls over ~1,500 tokens. About
2.5 MTok of Jev input in total, about 0.11 USD. Every answer is recorded to
`fixtures/triage-sets.jsonl` and every number here is replayed from it by
`tests/test_triage_sets.py`.

## What this does not measure

Whether an answering model then answers correctly from what was kept. Keeping both
supporting paragraphs is necessary for a correct answer, not sufficient; this run measures
the necessary part, which is where the shipped triage failed.
