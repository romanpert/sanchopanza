# Browse: confirmation on new steps, pre-registration

Written 2026-09-30 after Phase 1 (`prereg.md`, `analysis.json`) and before any model saw the
steps below.

## What Phase 1 found, and what it did not

Phase 1 failed its registered bar: the JEV arm kept a positive in its top 10 in 71.0 % of 169
steps (Wilson 63.8-77.3 %), under the 0.80 required, so its Phase 2 was not run. A free analysis
of its recording (the development set) found the cause in the design: the final round, which
re-judges the 30 best together, ranked worse than round one alone (Recall@10 70.4 % against
76.9 %), and an even mix of the two rounds ranked best at every k (R@1 40.8 %, R@10 77.5 %,
R@20 85.8 %, R@30 90.5 %). That mix (`browse.BLEND = 0.5`) was chosen on the same data it
scored, so none of those numbers is a result. This registration is what can make one.

## Data

New Mind2Web steps: the same three test splits, 60 row offsets per split half a step on from
Phase 1's (`benchmarks/browse/data.py --confirm`), dropping any row whose task appears in the
development sample (consecutive rows are steps of one task) and any whose positive is not in
the cleaned HTML. Every remaining step is used; the counts are reported.

## Phase 1c: ranking

Arms: **BM25** (free) and **JEV-BLEND**: `browse.rank` with its defaults (every element, groups
of 30, the best 30 re-judged, `blend=0.5`), `jev-1.13.0`.

Primary: JEV-BLEND Recall@20. Decision rule: point estimate >= 0.80 and Wilson lower bound >=
0.70 means confirmed; the browse hook's default of 20 kept elements is then recommended as an
opt-in, and Phase 2c runs. Otherwise the ranking is published as measured, with no
recommendation, and Phase 2c does not run. Reported alongside: R@1, R@10, R@30, and the paired
difference to BM25 at 20.

Money: Jev at most 1.50 USD.

## Phase 2c: does Sonnet choose as well from the top 20? (only if 1c confirms)

The first 20 confirmation steps of each split in file order, `claude-sonnet-5` through
`claude -p` (our evaluation harness, list prices), one session per step and arm, the prompt and
schema of `prereg-phase2-amendment.md`: **FULL** (every element, page order) against **TOP**
(JEV-BLEND's first 20, rank order). Metric: element accuracy, paired difference TOP minus FULL
with a bootstrap interval; input tokens and list dollars per arm, Jev dollars added to TOP.

Decision rule: TOP is recommended when its accuracy is within 5 points of FULL with the interval's
lower bound above -0.10, at a lower total cost. Otherwise it is published as a negative.

Money: 8.00 USD at list price, 0.60 USD per session; a pilot of 3 steps per arm first, excluded.
