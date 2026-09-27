# Page triage on multi-part questions: the shipped cut loses the answer, a contribution question keeps it

Two pre-registered runs on HotpotQA (distractor setting, validation split, CC BY-SA 4.0):
each question comes with 10 paragraphs, 2 of which hold the facts the answer needs. Those
labels are by construction and were written by neither this repository nor its author. Every
question is multi-part: `bridge` (find an entity, then a fact about it) or `comparison`.
The metric that matters is **joint recall**, both supporting paragraphs kept. Keeping both
is necessary for a correct answer, not sufficient; a third run answers the questions.

- `prereg.md`: the first run, 300 questions. Registered verdict: **negative**.
- `prereg-confirm.md`: the confirmatory run, 300 new questions, threshold fixed from the
  first run. Registered verdict: **confirmed**.
- `prereg-answers.md`: Haiku answers those 300 from what each arm kept. P10 holds, P11 fails.

Cost: 12,300 Jev decisions, about 0.25 USD, and 0.4 USD of Haiku for the answers.
Everything replays from `fixtures/triage-sets.jsonl` (`tests/test_triage_sets.py`, skipped without the local
HotpotQA export).

## The confirmed result

300 questions (238 bridge, 62 comparison), none of them seen before the cut was fixed.

| arm | joint recall | text kept |
|---|---|---|
| contribution question, cut 0.28 (fixed from the first run) | **0.933** | 0.523 |
| BM25, top 6: the smallest k keeping at least as much text | 0.803 | 0.563 |
| shipped relevance question, cut 0.45 (the shipped default) | **0.197** | 0.106 |
| shipped relevance question, cut 0.04 (derived like the others) | 0.953 | 0.609 |

- **The shipped cut loses the answer on multi-part questions.** At 0.45 it keeps both
  paragraphs in 19.7 % of questions, and in 4.8 % of comparison questions. The first run said
  15.9 %. This is the 10/10 to 6/10 of `../2026-09-24-fixed-sequence/`, measured on data
  nobody here wrote.
- **The contribution question beats a lexical baseline given more budget**: 93.3 % against
  80.3 %, with BM25 keeping more text. On bridge questions, 93.3 % against 77.7 %.
- **Most of the gain is leaving the 0.45 cut.** The shipped question at a derived cut of 0.04
  reaches 95.3 %, but keeps 61 % of the text against 52 %: the new question buys about 9
  points of text at 2 points of joint recall. Both are far from what ships.

## And the answers: the same accuracy from 54 % of the tokens

`prereg-answers.md`: `claude-haiku-4-5` (Batch API, 0.4 USD) answers the 300 confirmatory
questions from four inputs. Scored against HotpotQA's gold answer, normalised.

| input | correct | token F1 | input tokens |
|---|---|---|---|
| all 10 paragraphs | 67.7 % | 0.557 | 460,062 |
| kept by the contribution question | **69.0 %** | 0.598 | **249,329 (54 %)** |
| kept by the shipped cut 0.45 | 50.7 % | 0.422 | 71,683 |
| BM25 top 6 | 62.3 % | 0.555 | 270,848 |

- **P10 holds**: no accuracy lost (+1.3 points, inside the noise) at 54 % of the input tokens.
- **P11 fails**: the gap over the shipped cut is 18.3 points, under the 20 registered. The
  shipped arm lost the second paragraph in four questions of five and still answered half:
  HotpotQA is Wikipedia, which the answering model partly knows, and a comparison question is
  a coin flip between yes and no. Both prop up every arm that lost evidence, so the gaps here
  are smaller than the evidence gaps above. On private documents, which the model cannot
  know, the shipped cut would cost more than this.
- Against BM25 with more tokens: 6.7 points better.

## The first run, and why it was not enough

Registered criteria: P3 (contribution >= 0.90 joint recall at <= 0.50 text kept, +10 over
shipped), P4 (the one-call set question at <= 0.40), P5 (beat BM25 at matched recall). All
three failed. P3 by budget: 0.960 joint recall at 0.560 kept. P4 outright: a Choice over the
ten paragraphs puts its mass on the one it likes best, and no cut above zero reached 95 %
joint recall. P5 by its own design: BM25 only reached 95 % by keeping all ten paragraphs,
so "matched recall" meant "keep everything" and nothing could beat it. That last one was a
flaw in how the criterion was written, which is why the second run compares at matched
budget, with the budget favouring BM25.

## What this does not settle

- The answering model was Haiku 4.5, on Wikipedia text it partly knows.
- HotpotQA paragraphs are short (about 530 characters each), clean Wikipedia text. A fetched
  web page is longer and noisier; `excerpt` sends a 1,500-character window of it.
- The questions are English; Indagis's purposes are often Spanish over Spanish pages.
- The confirmed cut, 0.28, is derived to a 95 % joint-recall target on 300 questions. A
  harness with a different recall target derives its own.

## What changed

- `sanchopanza`: `triage.contribution_questions` and `Squire.triage_part` (cut
  `Thresholds.contributes = 0.28`); `triage_page`'s docstring now says it must not be used on
  a multi-part purpose at its shipped cut. `set_questions` stays, documented as failed.
- Indagis: page and search-result triage ask the contribution question in its own call and
  keep on it (`decisor/politica.py`, `umbral_aporte`), see its `DEUDA.md`.
