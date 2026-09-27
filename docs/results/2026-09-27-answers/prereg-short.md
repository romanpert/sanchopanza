# Pre-registration, second run: the same question with the answer's length controlled

Written 2026-09-27 after the first run (`prereg.md`) and before any call of this one. Hash in
`prereg-short.sha256` (line endings normalised to LF).

## Why a second run, stated plainly

The first run's registered verdict is negative (P21, P22 and P24 failed) and stands as
published. Its descriptive diagnostics (`diagnostics.json`) show why the metric may not measure
what the question asks: through the CLI there is no `max_tokens` (the API run capped replies at
60 tokens), and Haiku's replies grow with the context it is given. Median length is 30 words
with all ten pages, 9 with the kept pages, 4 with the kept sentences. The registered score counts
a reply as correct when the gold answer appears inside it, so a long reply collects answers.
Exact match runs the other way (20 % all pages, 33 % pages kept, 36 % sentences kept).

This run removes that confound and nothing else. It uses the same 300 questions and the same
kept sets, so it is **not independent** of the first: the kept sets and the questions were seen.
Its value is to separate "the kept text loses the answer" from "the metric rewards length".

## Fixed here

- Model, path, system prompt and user message: as in `prereg.md`, plus `--json-schema`
  `{"answer": string}` so the answer is a single field. The system prompt already asks for "the
  answer only: a short span, a name, a number, or yes or no ... unknown".
- The scored text is the `answer` field.
- Arms, data, kept sets, cuts: as in `prereg.md`. Path check: `all` on the seed-2027 questions.
- Scoring: as in `prereg.md` (normalised containment), with exact match and token F1 reported
  beside it.

## Criteria

- **P21s**: `CB` accuracy >= `all` accuracy minus 3 points.
- **P22s**: `C` accuracy >= `all` accuracy minus 3 points.
- **P24s** (path): CLI `all` on the seed-2027 set within 3 points of the API's 67.7 %.

Verdict: P21s and P22s = **the sentences answer as well as the pages, length controlled**;
otherwise reported as it falls. Either way the first run's verdict is not replaced.

## Cost

1,500 sessions of Haiku 4.5 with a structured-output turn, about 5 USD at list price against the
subscription, 0 USD against any key. Ceiling in code: 8 USD. Cached in
`fixtures/cli/answers-short.jsonl`.
