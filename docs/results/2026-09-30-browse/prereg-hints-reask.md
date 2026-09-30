# Browse, Phase 1e: the description of unnamed elements, against the noise of asking again

Written 2026-09-30 before any Phase 1e call. Runner: `benchmarks/browse/hints_reask.py`.

## Why

Phase 1d (`prereg-hints.md`) failed its registered bound at R@20 (-1.4 [-3.5, 0.0]) and the
description stayed opt-in. Its design could not separate two things: DESCRIBED asked Jev again
about every group holding a changed line, BEFORE replayed every call, and Jev answers a group
asked again differently even when nothing in it changed. Where the description touched the
target it lifted or kept 5 of 6; both steps that fell out of the top 20 were untouched by it.

## Design

The same 142 steps. DESCRIBED is Phase 1d's arm, replayed (no new call). REASK is BEFORE's
reading (no description) where exactly the calls DESCRIBED served from Phase 1c's recording
(1,684) are served the same way and every other call (1,044) is asked again live, recorded in
`fixtures/browse-jev-hints-reask.jsonl`. Both arms then carry the noise of asking again on the
same groups; DESCRIBED minus REASK is the description alone.

## Decision rule, fixed now

The description becomes the reader's default if DESCRIBED minus REASK has a paired-bootstrap lower
bound (5,000 resamples, seed 2030) above -3 points at both R@10 and R@20. Otherwise it stays
opt-in. Phase 1d's own result stands as published either way.

## Money

At most 1.00 USD of Jev; expected about 0.36.

## What would make this wrong

It reuses Phase 1d's steps and DESCRIBED's answers, so it is a second look at the same sample
with a better control, not a new sample. Asked again, Jev's noise in REASK is a fresh draw, not
the same draw DESCRIBED had.
