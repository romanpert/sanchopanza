# How much of the gap is the policy's shape? (2026-09-25, free)

Every number here replays from recordings already in the repository; nothing was called.
`benchmarks/policy_shape.py` writes `summary.md` and `policy-shape.json`;
`tests/test_policy_shape.py` pins the fast rows.

Two pre-registered hypotheses (in the script's docstring), on the 100 `memory_write` cases
of the first three batches, whose three raw probabilities (durable, specific, derivable) are
all recorded, and on the six binary points of the fifty-case benches.

## H1: a fitted policy against the shipped conjunction

| policy | fitted on | hits | costly (store when skip) |
|---|---|---|---|
| shipped conjunction (0.70 / 0.70 / 0.75) | nothing | 72 | 5 |
| plain 0.5 cut on the weakest margin | nothing | 86 | 4 |
| one cut on the weakest margin, derived per fold | training folds | 89.6 | 6.4 |
| logistic regression on the three probabilities | training folds | 87.8 | 9.4 |

Cross-validation is 10-fold repeated 5 times; a fitted row is the mean hits per run of 100
on held-out folds. The derived cut landed between 0.44 and 0.45 in every fold. The
regression on all 100 cases weighs durable 2.54, specific 1.95 and derivable -2.71 with
bias -1.83. Wilson 95 % of the shipped accuracy: 0.625 to 0.799.

**H1 as pre-registered fails, and the trade is the finding.** A derived cut gains 17.6 hits
per run and costs 1.4 costly errors; the regression gains 15.8 and costs 4.4. The rule the
repository already states, that the costly direction needs a stricter gate than the cheap
one, is what the derived cut ignores: it maximises hits. What the numbers settle is the
diagnosis, not the fix. Three quarters of the gap between the model (86 at a plain cut) and
the shipped policy (72) is the policy's shape and threshold, on cases the fitted policy
never saw. The fix that was measured on new cases is the fourth question
(`benchmarks/memory_common.py`), not a looser cut: `benchmarks/thresholds.py` refused to
move the cut on 34 cases because a 90 % precision target needs 35 acted cases, and with 100
it is now a derivation worth running, to a precision target and not to accuracy.

## H2: recalibration of the deciding probability

| point | n | ECE before | ECE after | Brier before | Brier after |
|---|---|---|---|---|---|
| memory_write | 34 | 0.223 | 0.027 | 0.091 | 0.032 |
| redundant_page | 34 | 0.146 | 0.018 | 0.04 | 0.004 |
| goal_met | 36 | 0.109 | 0.055 | 0.038 | 0.042 |
| repeats_check | 38 | 0.133 | 0.011 | 0.03 | 0.001 |
| extract_gate | 34 | 0.073 | 0.085 | 0.071 | 0.087 |
| recall | 36 | 0.077 | 0.002 | 0.009 | 0.0 |

Platt scaling, leave-one-out: the two parameters are fitted on the other cases of the same
point, never on the case scored. **H2 holds on 4 of 6** (memory_write, redundant_page,
repeats_check, recall; goal_met halves ECE and worsens Brier; extract_gate worsens both).

Read it with the estimator in mind: ECE with 5 bins at n of 34 to 38 carries a bias of the
order of 0.13 to 0.15, the same order as most of the "before" column, so the ECE columns are
a direction, not a number. Brier has no such bias and moves the same way. What the table
supports is narrower than "Jev is miscalibrated": on four points the provider's probability
is under-confident in the direction the label goes, a monotone rescaling fixes it with two
parameters, and the raw probability already orders the cases (AUC 1.00 on these points,
`docs/results/2026-09-24-fifty-v2/`). Independent studies on other tasks report the same
shape: raw ECE of 0.12 to 0.21 falling to 0.01 to 0.03 after Platt or isotonic scaling.

## What this changes

Nothing shipped. Two things queued, both free to run and both needing a held-out batch
before a default moves: a per-point recalibration fitted on the journal (the `LocalDecider`
already takes a handler that could wrap the provider's answer), and a derivation of the
`memory_write` cut on 100 cases to a precision target. The thresholds stay where they are
until then.
