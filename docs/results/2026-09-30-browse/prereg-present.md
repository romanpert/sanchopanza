# Browse, Phase 2d: the kept elements shown in page order

Written 2026-09-30 before any confirmation session ran. Follows Phase 2c (`prereg-confirm.md`),
which failed: Sonnet shown Jev's top 20 **in rank order** chose right 5 points less often than
from the whole page.

## Why a second try

`benchmarks/browse/diagnose.py` (free, replays Phase 2c) found that in 6 of the 7 steps TOP lost,
the target was among the 20 shown. Two were identical lines ("View more", an unnamed phone field)
that the page's order tells apart and a ranked list does not; three were picks among the first
three rows. `browse.in_page_order` now shows the kept elements in the page's order, and a line
repeated on the page carries a note: which of the alike it is and the nearest different element
before it. `browse.render` uses it (the CLI and the `rank_elements` MCP tool).

On Phase 2c's own 60 steps (development: the steps the fix was designed on; `present-dev.json`):
FULL 58.3 %, PAGE20 58.3 % (0.0 [-8, +8]), PAGE30 61.7 % (+3.3 [-5, +12]). Seen data: claims
nothing.

## Steps

The 82 Phase 1c steps Phase 2c did not use (website 24, domain 33, task 25; 564 elements on
average, at most 4,993). Jev's ranking is replayed from Phase 1c's recording
(`fixtures/browse-jev-confirm.jsonl`): no new Jev call.

## Arms

`claude-sonnet-5` through `claude -p` (our evaluation harness, list prices, not the API), one
isolated session per step and arm, Phase 2c's system prompt and schema, the reply a number.

- **FULL**: every element, in page order, Phase 2c's prompt (asked anew on these steps).
- **PAGE30** (primary): Jev's top 30 through `in_page_order`, notes after repeated lines.
- **PAGE20** (secondary): the same with the top 20.

A session that fails (CLI error, budget) counts as wrong, as in Phase 2c.

## Decision rule, fixed now

Phase 2c's rule, unchanged: PAGE30 is recommended as a replacement for the whole page if its
accuracy minus FULL's is at least -5 points and the lower bound of the paired bootstrap interval
(5,000 resamples, seed 2032) is above -10 points. PAGE20 is reported against the same rule,
secondary. Anything else is published as it comes out.

## Money

At most 15.00 USD at list price through the subscription (expected about 11.5: FULL 0.113 a step,
PAGE30 0.014, PAGE20 0.012), 0.60 USD per session as in Phase 2c. No Jev spend.

## What would make this wrong

82 steps give an interval of about +-10 points on a paired difference. The note format was chosen
on development steps; a gain there may be partly fitted to them, which is why this runs on new
steps. Sessions through `claude -p` are not deterministic.
