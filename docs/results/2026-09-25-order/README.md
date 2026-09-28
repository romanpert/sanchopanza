# Does the order of a Choice's options move the answer? (2026-09-25)

Pre-registered before the first call (the hypothesis is in `benchmarks/option_order.py`),
measured on the 50 labelled `facts` cases, the three-option Choice (agree, conflict,
unrelated) whose recorded answers in the shipped order date from 2026-09-24. Three arms were
asked live on 2026-09-25: the reversed order, a rotation, and **the shipped order again**,
so that the provider's day-to-day drift is measured on the same cases and can be told apart
from the effect of the order. 150 decisions, 0.0045 USD, all recorded to
`option-order.jsonl` and replayed by `tests/test_option_order.py`.

Re-recorded after pseudonymization hardening (2026-09-28): the text of fa-12, fa-13 and fa-19
was generalized, those nine decisions were asked again and every number below is re-derived.

| arm | order | flips vs shipped | median delta p | max delta p | mass on first | hits / decided |
|---|---|---|---|---|---|---|
| shipped | agree, conflict, unrelated | 0 | 0.0 | 0.0 | 0.455 | 36/40 |
| reversed | unrelated, conflict, agree | 3 | 0.015 | 0.31 | 0.214 | 39/42 |
| rotated | conflict, unrelated, agree | 2 | 0.02 | 0.28 | 0.376 | 38/41 |
| today | agree, conflict, unrelated | 0 | 0.01 | 0.15 | 0.453 | 36/40 |

"Flips" counts cases whose top label differs from the shipped recording. "Delta p" is the
change in the probability of the shipped top label. "Mass on first" is the mean probability
on whichever option is listed first. "Hits / decided" applies the shipped policy: the point
acts only at confidence 0.60 or above.

## What it says

- **The pre-registered hypothesis failed.** H3 allowed at most 2 flips per order; the
  reversed order flipped 3 of 50 and the rotation 2. Re-asking the shipped order on the
  same day flipped 0, with a median move of 0.01 and a maximum of 0.15: the order effect is
  above the day's drift.
- **Every flip sits under the policy's cut.** The five flips fall on three cases whose
  shipped answer carried confidence 0.29 to 0.41; the abstention band absorbed all of them, and the
  policy's hits moved from 36/40 to 39/42 and 38/41, within what 50 cases can resolve.
- **What moves is a low-confidence `agree`.** All three cases (fa-07, fa-10, fa-24)
  were answered `agree` in the shipped order at confidence 0.29 to 0.41, and all five
  flips land on the label (four to `unrelated`, one to `conflict`). Before the re-recording
  fa-13 flipped too, from one wrong option to another; its hardened text no longer does. `unrelated` is the option whose
  criteria carry no examples (`docs/results/2026-09-24-fourth-batch/`). No crude "first
  option wins" bias shows in the mass on the first option, which follows the label mix
  rather than the position.
- **A recording could not measure this until today.** `key_of` sorts keys, so two orders
  shared a fingerprint and a replay of the second silently returned the first. Recordings
  now carry `order_of(questions)`; older recordings match any order, as before
  (`tests/test_recorded_order.py`).

## What it does not resolve

Three options and 50 cases. The external report of 88 % against 57 % by position was made
on arithmetic questions with the correct option last, a task the vendor lists among the
model's weaknesses; whether a ten-option `classify` moves more is unmeasured here. The
shipped recording is a day older than the arms, so a part of the per-case deltas, bounded
by the `today` arm at 0.15, is drift and not order.

## Reproducing

```bash
python benchmarks/option_order.py --offline            # free, from option-order.jsonl
python benchmarks/option_order.py --env-file PATH/TO/.env   # asks only what is missing
```
