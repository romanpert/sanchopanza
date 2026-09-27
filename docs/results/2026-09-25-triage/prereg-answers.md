# Pre-registration: does the model still answer from what triage kept?

Written 2026-09-25 after the confirmatory triage run (`prereg-confirm.md`, confirmed) and
before any call of this one. Hash in `prereg-answers.sha256`.

## Question

Keeping both supporting paragraphs is necessary for a correct answer, not sufficient. This
run answers the 300 confirmatory questions from four inputs, with the kept sets exactly as
recorded in `confirm-rows.json`:

- `all`: the 10 paragraphs.
- `contribution`: the paragraphs with P(contributes) >= 0.28.
- `shipped`: the paragraphs the shipped triage keeps (relevance >= 0.45).
- `bm25`: BM25 top 6 (the matched-budget k of the confirmatory run).

Paragraphs keep their dataset order; a dropped one is simply absent. An arm with nothing kept
is still asked, with no paragraphs.

## Model and prompt, fixed here

`claude-haiku-4-5` through the Message Batches API, `max_tokens` 60, temperature default.
System: "Answer the question using only the paragraphs given. Reply with the answer only: a
short span, a name, a number, or yes or no. If the paragraphs do not contain the answer,
reply: unknown." User: the paragraphs as `Title: text` blocks, then `Question: <question>`.

## Scoring, fixed here

HotpotQA's normalisation (lowercase, strip punctuation and articles, collapse whitespace).
**Correct** when the normalised gold answer equals the normalised reply, or appears in it as
a whole-word substring. Token F1 reported beside it. Input tokens from the API usage.

## Criteria

- **P10**: contribution accuracy >= all-paragraphs accuracy minus 3 points, with input
  tokens <= 65 % of all-paragraphs.
- **P11**: contribution accuracy >= shipped accuracy plus 20 points.
- **P12** (secondary): contribution against BM25 top 6, reported either way.

Verdict: P10 and P11 = **the saving is real on this set**; otherwise reported as it falls.

## Cost

1,200 requests, about 1.1 MTok of input at batch prices for Haiku 4.5, about 0.6 USD.
