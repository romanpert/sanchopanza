# Pre-registration: sentences inside the paragraphs the tournament kept, on whole papers

Written 2026-09-27, after the paragraph run of this directory (P28 failed on compression: 94.7 %
of questions keep all evidence, 48.9 % of the text) and before any `select_sentences` call on
QASPER. `benchmarks/longdocs/sentences.py --live` refuses to spend unless the sha256 of this
file (line endings normalised to LF) matches `prereg-sentences.sha256`.

## Why

The paragraph README names this as the next thing to measure. On HotpotQA, `select_sentences`
inside the pages `triage_pages` kept took the text from 34 % to 22 % and kept every supporting
sentence in 90.3 % of questions (`../2026-09-27-chunks/`). Whether the same second stage makes
whole papers small enough to matter is open. Nothing is tuned here: the sentence cut is the
shipped `Thresholds.sentences` (0.28), confirmed on HotpotQA.

## Data

The 300 questions of `prereg.md` (same papers, same draws, same order) and the paragraphs the
recorded tournament kept for each (`fixtures/longdocs.jsonl`, the fixed method, replayed; no new
tournament call). QASPER marks, besides evidence paragraphs, `highlighted_evidence`: the spans
inside them that answer. A question enters this run when its first annotator's highlighted
spans are all non-empty and each one, whitespace collapsed and with a final full stop removed,
is a substring of one of its evidence paragraphs (whitespace collapsed). Counted before
writing this file, without any call: **261 of the 300**. The other 39 are excluded and listed.

- **Sentences**: each paragraph, whitespace collapsed, split after `.`, `!` or `?` followed by
  whitespace and an upper-case letter, a digit, `(` or `[`. No other rule.
- **Gold sentences**: those whose character range overlaps a highlighted span's range in its
  evidence paragraph.

## Arms

- **MS** (shipped two stages): `Squire.select_sentences(purpose=question, title=section,
  sentences=...)` on every paragraph MANY kept, at the shipped cut 0.28; a sentence is kept when
  its paragraph was kept and its own probability clears the cut (or it was not answered, or is
  past `chunks.SENTENCE_MAX`: kept, as shipped).
- **M** (paragraphs only, recorded): every sentence of a kept paragraph.
- **BM25 sentences**: every sentence of the paper ranked by BM25 of the question against the
  sentence (the triage runs' tokeniser), taken in order until its characters reach at least
  MS's kept characters for that question.

## Metrics

**All gold**: every gold sentence of the question kept. **Any gold**: at least one. **Kept share**:
characters of kept sentences over the characters of all the paper's paragraphs (whitespace
collapsed, section names not counted in either).

## Criteria

- **P30**: MS keeps all gold sentences in >= 85 % of the 261 questions with a kept share <= 25 %
  (the compression bar P28 set for paragraphs, unchanged).
- **P31**: MS's all-gold rate exceeds BM25 sentences' by >= 10 points.

Both: **two stages make whole papers small**; otherwise reported as it falls. No cut is derived
on these papers either way.

## What the earlier runs predict (stated before running)

If the HotpotQA ratios carry over (sentence stage keeps 22/34 of the page stage's text and loses
8 points of recall), MS lands near 85-87 % all gold at about 30-32 % of the text: P30 would fail
on compression again, narrowly. QASPER's highlighted spans are often several sentences long,
which makes "all gold" harder than on HotpotQA.

## Cost

About 21 kept paragraphs per paper, one call each: ~5,300 calls of a few hundred tokens,
roughly 0.2-0.4 USD of Jev. Hard cap in the script: 1.50 USD, counted from each decision's cost.
Recorded in `fixtures/longdocs-sentences.jsonl`.
