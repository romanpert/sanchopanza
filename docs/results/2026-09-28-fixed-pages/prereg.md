# Pre-registration: in-context page triage on the fixed-sequence A/B

Written 2026-09-28, before any live call of this run. **Not run yet.** `benchmarks/ab/fixed.py`
refuses a live `--lever pages` run unless `prereg.sha256` holds the sha256 of this file (line
endings normalised to LF).

## Why

The fixed-sequence A/B of 2026-09-24 (`docs/results/2026-09-24-fixed-sequence/`) is the one
end-to-end avoidance result in this repository that survives a paired interval: page-by-page
triage cut input tokens by 75.2 % and lost four answers in ten (10/10 to 6/10), each time by
dropping the answer document. Two shapes explained all four: a compound question that no single
page satisfies, and a long document judged by an excerpt. The points shipped since address both:
`triage_many` judges pages with the others in view, and here the unit is the passage (paragraphs
of at most 900 characters, `chunks.PAGE_LIMIT`), so a long document is judged by all of its text.

## Design

`python -m benchmarks.ab.fixed --lever pages`, 10 tasks, 20 documents per task, one repeat, as
on 2026-09-24. Both arms walk the same deterministic sequence; the bare arm sends every document,
the squire arm sends the passages `Squire.triage_many` keeps at the shipped cuts (0.18 first
round, 0.40 final), in document order, and withholds a document with none left. One answering
call per arm, `claude-sonnet-5`, effort low, the system prompt of `fixed.py`.

**The corpus is pinned**: `--corpus-ref c168363`. It is built from this repository's own
documents, which change almost daily; at that commit every task's facts sit in exactly one
document inside its sequence (the dry run checks it and refuses otherwise).

**Both arms are rerun.** The recorded bare arm of 2026-09-24 cannot stand in: its document
sequences match no commit (at best 7 of 10 tasks, at `6107f4f`); it was run on an uncommitted
tree. `fixed.py --reuse-bare` refuses it for that reason.

**Answering path**: `--via claude-cli` (the subscription, list-price accounting), both arms.
Numbers from this path are not placed beside the 2026-09-24 API figures as if comparable; the
comparison that counts is the paired one inside this run.

## Criteria

- **Success**: the squire arm answers **at least 9 of 10** correctly (the `answer_contains`
  rule of `run.py`) **and** its input tokens are **at least 50 % below** the bare arm's (paired
  ratio point estimate <= -50 %).
- **Precondition**: the bare arm answers at least 9 of 10. Below that the run is reported as
  uninformative about the lever.
- Reported whatever the outcome: per task, the passages kept and withheld (in `rows.json`), and
  for every miss whether a passage holding its `pin` was withheld, computed from `rows.json` and
  the pinned corpus (the attribution table of 2026-09-24).

## Prediction

8-10 correct in the squire arm at 55-70 % fewer tokens; success with about 55 % confidence. The
risk is the compound tasks (`spread-adapters`, `spread-costs`), where each passage is a partial
answer.

## Cost and caps

- Jev: 299 calls in the fake-decider dry run (about 30 per task, 20-page pools of about 250
  passages). These are 30-page calls, not the 29-millionth single decisions of the README:
  at the recorded 0.35-0.49 thousandths USD per in-context call, **about 0.10-0.15 USD**.
- Answering model through `claude -p`: 20 sessions, about 38,000 input tokens each for the bare
  arm (a four-characters-a-token estimate) and fewer for the squire arm: **about 1.0 USD at list
  price** on the subscription, not the API key. `--max-usd 3` stops the run; the CLI's session cache
  makes a rerun free.
