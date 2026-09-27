# Pre-registration: the `memory_write` cut, derived to a precision target

Written 2026-09-27 before any number of this analysis was computed. Free: every probability
is already recorded in `fixtures/*.jsonl`; nothing is called. `prereg.sha256` holds the
sha256 of this file and `tests/test_memory_write_cut.py` fails if it changes.

## What is already known, and therefore not evidence

The 100 cases below were examined by `../2026-09-25-policy-shape/`: shipped conjunction 72
hits with 5 costly stores, plain 0.5 cut on the weakest margin 86 with 4, a cut derived to
maximum accuracy per fold 89.6 with 6.4. From those figures the shipped policy stores 33 and
its precision is 28/33 = 85 %. Labels: 51 store, 49 skip. Nothing below reads that analysis;
it is why the split and the criterion are fixed here and not afterwards.

## Shape

One parameter `c`, the shape `decide_write` already has: store iff `durable >= c` and
`specific >= c` and `derivable <= 1 - c`, i.e. the weakest margin `min(d, s, 1 - r) >= c`.
In code that is `Thresholds.remember = c`, `Thresholds.derivable = 1 - c`, and no change to
`decide_write`. The shipped values (0.70 / 0.70 / 0.75) are not of this shape; they are the
comparison.

## Data and split

- The 100 `memory_write` cases of `benches/memory.jsonl`, `memory-b.jsonl`, `memory-c.jsonl`
  (the set of `benchmarks/policy_shape.py`, replayed the same way).
- Split, stratified by label: store-labelled ids and skip-labelled ids, each sorted, each
  shuffled with `random.Random(20260927)`; the first half (rounded up) of each goes to
  **A (derivation)**, the rest to **B (held out)**. A has 26 store + 25 skip, B 25 + 24.
- Secondary held-out set, never used for any `memory_write` threshold: the 108 cases of
  `benches/memory-e.jsonl`, `memory-f.jsonl`, `memory-g.jsonl`, replayed on their recorded
  three-question call (`write_questions(fact)`, as `benchmarks/memory_common.py` does).
  They were written to expose a known defect (standing instructions, general knowledge,
  pointers), so they are a stress test of the costly direction, not a representative sample.

## Target and derivation

- Acting = storing. Target: **80 % precision**, the only target the derivation half can
  reach: the 95 % Wilson lower bound clears 90 % only from 35 acted cases, and A has 26
  positives.
- On A only: over `c` in 0.05, 0.06, ..., 0.95, keep the cuts whose Wilson 95 % lower bound
  of precision on A is >= 0.80; choose the one with the most recall on A; ties go to the
  **highest** cut (fewer stores for the same true stores). No reachable cut: negative, stop.

## Criterion (all must hold to change the shipped default)

On B, against the shipped policy scored on the same 49 cases:

1. precision of the derived cut on B >= 0.80 (point estimate);
2. costly errors (store when the label is skip) on B <= those of the shipped policy on B;
3. hits on B > hits of the shipped policy on B.

And on the secondary set (108): costly errors of the derived cut <= those of the shipped
policy. Hits there are reported, not judged.

If all hold: `Thresholds.remember` and `Thresholds.derivable` move to `c` and `1 - c`, with a
test. If any fails: the result is reported as negative and nothing in code changes.

## Descriptive only (not judged)

The same derivation run the other way (derive on B, report on A); 10-fold x 5 repeats and
leave-one-out of the whole procedure on the 100 (fold seeds 100 + repeat, as
`policy_shape.folds`), reporting mean hits, costly errors, precision and the spread of `c`.
