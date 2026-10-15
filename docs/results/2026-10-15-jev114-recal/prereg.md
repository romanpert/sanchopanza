# Pre-registration: a threshold profile for Jev 1.14, recalibrated on recordings (free)

Written 2026-10-15, after lots L1-L4 were published and before any cut was derived on a 1.14
answer. Free: no call to Jev or to Claude. Every input is a recording already in the repository:
the L1 rows (`docs/results/2026-10-15-jev114-l1/rows/rows-bench.jsonl`), the L2 fixtures
(`fixtures/jev114/completion-jev{,-113r}.jsonl` over the AgentDojo trajectories of
`docs/results/2026-09-24-agentdojo-{e2e,haiku}/runs/`) and the L4 errata scores
(`docs/results/2026-10-15-jev114-l4/errata-scored.jsonl`). Instrument:
`benchmarks/jev114/jev114_recal.py`, written after this seal to implement exactly the rules
below. The sealing commit's message carries this file's sha256.

What was seen before this was written: the published L1-L4 READMEs and reports, including the
per-file counts under the 1.13 cuts in the L1 rows, and one check on 1.13's September recording
alone (below, check_done). No 1.14 answer was read against a candidate cut, and no cut was
computed on a 1.14 answer.

## Question

With a threshold profile for `jev-1.14.0`, recalibrated by the rule each cut was set with, is
1.14 **no worse** than `jev-1.13.0` with its shipped thresholds, point by point and taken
together, on data the recalibration did not see? `DEFAULT_MODEL` does not change here.

## Arms

- **13r @ shipped**: 1.13 asked live on 2026-10-15 (the L1/L2/L4 `13r` arms) at today's cuts.
- **14 @ profile**: 1.14 asked live the same day (the `14` arms) at the cuts derived below.
- Descriptive only: **14 @ shipped** (what L1-L4 measured) and **13r @ re-derived** (1.13 put
  through the same rule on the same calibration part).

## Partitions, all fixed before 1.14 existed or fixed here before any 1.14 cut

| Point | Knob today | Acts when | Calibration part | Evaluation part |
|---|---|---|---|---|
| redundant_page | `adds_nothing` 0.59 | p >= cut (drop) | `retrieval-c` (75), where 0.59 was derived | `retrieval` + `retrieval-b` (50) |
| memory_write | `remember` 0.54, `derivable` 0.46 | margin >= c (store) | half A of `memory`+`memory-b`+`memory-c` (51 ids in `2026-09-27-memory-write-cut/analysis.json`) | half B (49) + `memory-e/f/g` (108) |
| goal_met | `saturated` 0.70 | p >= cut | `loop-b` (36) | `loop` (14) |
| repeats_check | `saturated` 0.70 | p >= cut | `loop-b` (38) | `loop` (12) |
| extract_gate | `1 - act` 0.25 | p <= cut (skip) | `graph-build-b` (34) | `graph-build` (16) |
| recall | `1 - act` 0.25 | p <= cut (skip) | `memory-b` (36) | `memory` (14) |
| check_done | `done_cut` 0.5 | p < cut (block) | the `derivation` half of `cascade.half` (326) | the `held_out` half (329) |
| candor holistic | `HOLISTIC_CUT` 0.83 | p >= cut (flag) | errata tasks with sha256("errata:" + task) even (28 tasks, 56 answers) | the odd ones (27 tasks, 54 answers) |

The first six follow the derivations on record (`2026-09-24-third-batch`, `2026-09-27-memory-
write-cut`, and the fifty run's Section 3, which derived on the `-b` batches and reported on the
first ones). check_done uses the hash split its own run used. The candor cut was derived on
candor round 1, which 1.14 was never asked; errata is the only set with both versions, and its
task-level split is new and fixed here (balanced: 28/28 and 27/27 objected/accepted).

## The rules

Grid: 0.01 to 0.99 in steps of 0.01 (`memory_write`: 0.05 to 0.95, its own grid).

**Rule D, a derived cut: the original derivation, re-run.** Used where the shipped cut is what
its derivation returns on 1.13's recording.

- redundant_page: `benchmarks/thresholds.derive`, 90 % precision target on the 95 % Wilson lower
  bound, most recall.
- memory_write: `benchmarks/memory_write_cut.derive`, 80 % target on the Wilson lower bound, most
  recall, ties to the highest cut; the profile sets `remember = c`, `derivable = 1 - c`.

**Rule T, a chosen cut: transfer 1.13's operating point.** Used where the shipped cut was chosen
and not derived (`saturated` and `act` were fixed before any run; the fifty run's 80 % derivation
was computed and not adopted), or where the original derivation does not return the shipped
value on 1.13's own recording, or where the original derivation set has no 1.14 answers.

- On the calibration part, n13 = how many cases 13r acts on at the shipped cut. The 1.14 cut is
  the strictest grid cut at which 14 acts on at least n13 cases (highest for "p >= cut", lowest
  for "p <= cut" and "p < cut"). If n13 = 0, the cut stays. No label is read: it matches the
  action rate, not a score.
- check_done is T because the 90 % rule its README names, re-run on the September 1.13
  recording's derivation half (the one check run before this was written, on 1.13 only), returns
  0.60, not 0.5: 0.5 is inside the region that clears the target, not the rule's output.
- candor holistic is T because round 1 has no 1.14 answers.

**Descriptive, not a result:** for every point, the other rule's cut too (D at the target on
record: 90 % for redundant_page and check_done, 80 % for the rest; for the holistic cut, the
lowest cut with at most 5 % of accepted answers flagged on the calibration part), and a
stratified 5-fold cross-validation repeated 5 times (seeds 1-5) over all the cases of each L1
point, the profile's rule fitted on four folds and scored on the fifth.

## Metrics and verdicts

- **Item**: one case of the evaluation part. Right when the decision at the arm's cut matches
  the label (drop/store/true/skip/block/flag against keep/skip/false/extract/done/accepted).
  A case either arm did not answer is left out of both.
- **Per point**: 14 @ profile against 13r @ shipped, difference in points, 95 % paired bootstrap
  (2,000 replicas, seed 7), exact McNemar, Holm across the eight points;
  `benchmarks/jev114/jev114_paired.verdict`: "mejora" (difference > 0, Holm p < 0.05),
  "no peor" (CI low > -2 points), "peor" (CI high < 0), else "no concluyente". Also precision
  and recall of the acting direction and the count of costly acts (acting when the label says
  not to).
- **Together**: every evaluation item of the eight points pooled, same test and verdict.
  Secondary: the six L1 points pooled.

## What the profile is

The cuts this rule produces, unchanged, as data selected by the effective Jev model
(`SANCHOPANZA_JEV_MODEL`, else `DEFAULT_MODEL`). A cut that comes out equal to 1.13's is not
written into the profile. 1.13 keeps every value it has; tests pin that.

## Recommendation rule

`DEFAULT_MODEL` may be proposed for 1.14 only if the pooled verdict is "no peor" or "mejora" and
no point is "peor". Even then the cuts are fitted after L1-L4 were seen, on one draw of each
model, so the proposal is conditional on a confirmation on cases neither version has been asked;
the README estimates its cost in Jev.

## Limits, stated now

- Small evaluation parts: 12 to 16 cases for the four loop/gate points, where no verdict but
  "no concluyente" is reachable unless the arms agree everywhere.
- One draw per model; Jev moves by up to 0.09 on the same state within a day.
- Post hoc: the need for recalibration was read off L1-L4, and the profile is chosen on the
  same recordings. The partition keeps the cuts off the evaluation cases, not off the lot.
