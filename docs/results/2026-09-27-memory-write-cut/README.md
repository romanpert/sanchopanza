# The `memory_write` cut, derived to a precision target (2026-09-27, free)

Pre-registered in `prereg.md` (sha256 in `prereg.sha256`) before anything here was computed.
Every number replays from `fixtures/*.jsonl`; nothing was called. Reproduce with
`python benchmarks/memory_write_cut.py` (writes `analysis.json`); `tests/test_memory_write_cut.py`
pins every figure below and the hash of the pre-registration.

## Design

One parameter: store iff the weakest margin `min(durable, specific, 1 - derivable) >= c`,
which is `decide_write` with `remember = c` and `derivable = 1 - c`. Derived on half A of the
100 cases (stratified by label, seed 20260927, 51 cases) to an **80 % precision target on the
95 % Wilson lower bound**, most recall, ties to the highest cut. Judged on half B (49 cases)
and on 108 cases never used for any `memory_write` threshold (`memory-e/f/g`, their recorded
three-question call). The comparison is the conjunction 0.70 / 0.70 / 0.75.

## Result: it holds

`c = 0.54` on A (19 stored, 0 of them wrong, recall 73 %).

| set | policy | stored | hits | costly (store when skip) | precision | recall |
|---|---|---|---|---|---|---|
| B, held out (49) | conjunction 0.70 / 0.70 / 0.75 | 17 | 37 | 2 | 88 % | 60 % |
| B, held out (49) | **one cut, 0.54** | 17 | **39** | **1** | **94 %** | 64 % |
| secondary (108) | conjunction | 8 | 60 | 4 | 50 % | 8 % |
| secondary (108) | **one cut, 0.54** | 16 | **74** | **1** | 94 % | 31 % |

All four pre-registered checks pass: precision on B >= 80 %, costly on B no worse, hits on B
higher, costly on the secondary set no worse. By batch on the secondary set: memory-e 37/48
with 1 costly (conjunction 25 with 3), memory-f 24/36 with 0 (23 with 1), memory-g 13/24 with
0 (12 with 0). It stores 4 of the 36 standing client instructions, where the conjunction
stores none; the opt-in `common` question is still what fixes that family.

The gain on B is two cases out of 49, not a large effect; what the derivation buys is the
direction: fewer stores that should not happen, on both held-out sets, at no loss of recall.

## Descriptive only

- **Reverse split** (derive on B, report on A): no cut reaches the target. B has 25 positives
  and the lower bound never clears 80 %. This is the sample-size floor of
  `benchmarks/thresholds.py`, not a contradiction: one half is barely enough.
- **The whole procedure resampled** on the 100: 10-fold x 5 gives 81.8 hits and 3.8 costly per
  run of 100, cuts from 0.45 to 0.54; leave-one-out 80 hits and 4 costly (precision 90 %), cuts
  0.49 to 0.54. The conjunction on the same 100: 72 and 5. These include cases the derivation
  of A already saw, so they are a range, not a test.

## What changed in code

- `Thresholds.remember` 0.70 -> **0.54**, `Thresholds.derivable` 0.75 -> **0.46**
  (`src/sanchopanza/policy.py`). `decide_write` is unchanged.
- `decide_write_common` (opt-in) was measured at 0.70 / 0.75 and now reads its own
  `Thresholds.common_durable` / `common_derivable` at those values, so it does not move.
- Pinned bench numbers under the shipped policy: the fifty-case bench 200/212 (was 197), with
  `memory_write` 29/34; the new-point bench 82/88 (was 83): the cut loses `mw-08`, a store at
  margin 0.51, and every policy error is still a refusal to store. The substitution table
  under this policy is in `fifty/` (200/211 against 202 at a plain cut and 204 for Opus 5).
- `benchmarks/policy_shape.py` pins the conjunction it compares against.
