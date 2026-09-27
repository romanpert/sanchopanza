# Pre-registration, confirmatory: the contribution question against BM25 at matched budget

Written 2026-09-25 after the first run (`prereg.md`, verdict **negative** as registered) and
before any call of this one. Its hash is recorded in `prereg-confirm.sha256`.

## Why a second run

The first run's registered verdict was negative: the contribution question kept both
supporting paragraphs in 96.0 % of held-out questions but at a kept share of 0.56, above the
0.50 registered; and P5 compared against BM25 only at BM25's derived operating point, which
turned out to be "keep all 10", so no arm could beat it. Read descriptively on the held-out
half, the contribution question beat BM25 at every budget (e.g. 0.960 against 0.735 joint
recall at about 0.55 kept share), but those curves were read on held-out data and are not a
result. This run tests that reading on questions nothing was chosen on.

## Fixed here

- **Data**: 300 new HotpotQA distractor validation questions with 10 paragraphs, drawn with
  `random.Random(2027).sample` from the 7,345 with 10 paragraphs **minus the 300 of the first
  run**. Same parquet file.
- **Contribution cut**: c = **0.28**, derived on all 300 first-run questions with the first
  run's rule (joint recall >= 0.95 at the smallest kept share). Not tuned again.
- **Shipped question**: reported at the cut Indagis ships (relevance 0.45) and at **0.04**,
  derived on all 300 first-run questions by the same rule.
- **BM25 at matched budget**: on the new questions, k = the smallest top-k whose mean kept
  share is **at least** the contribution arm's mean kept share. BM25 gets at least as many
  characters as the question it is compared against.

## Criteria

- **P6**: contribution joint recall >= 0.90, and >= BM25's joint recall at matched budget
  plus 10 points.
- **P7**: contribution joint recall >= the shipped question at 0.45 plus 50 points (the gap
  Indagis carries today).
- **P8** (secondary, reported either way): contribution against the shipped question at its
  derived 0.04, at their own kept shares.

Verdict: P6 and P7 = **confirmed**; otherwise **not confirmed**, published as such.

## Cost

About 3,000 Jev calls (the shipped triage and the contribution question per paragraph; the
set question is not asked again, it failed), about 0.06 USD.
