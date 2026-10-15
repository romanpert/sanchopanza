# A threshold profile for Jev 1.14: no worse than 1.13 with it, and no better

Free: no call to Jev or to Claude. Every number replays from recordings already in the
repository: the L1 rows, the L2 check_done fixtures and the L4 errata scores, all asked live on
2026-10-15. Pre-registered in `prereg.md` (sha256 `4ae33222...0d2351`, in `prereg.sha256`),
sealed in commit 671546e before any cut was computed on a 1.14 answer.

## Verdict

**With its recalibrated profile, `jev-1.14.0` is no worse than `jev-1.13.0` at 1.13's own cuts,
taken together and on every point that can reach a verdict. It is not better.**

- **Together:** 556 against 556 right of 646 evaluation items. The difference is 0.0 points
  [−1.5, +1.5], with 13 discordant items each way: **no peor**.
- **On the six L1 points alone:** 216 against 213 of 263, +1.1 points [−1.9, +4.6]: **no peor**.
- **Per point:** five are "no peor": goal_met, repeats_check, extract_gate, recall and
  check_done. Three are "no concluyente": redundant_page, memory_write and the candor holistic
  cut. None is "peor".
- **What the profile buys.** At 1.13's cuts, 1.14 scores 550 of the same 646. The profile
  recovers 6 of them, mostly on check_done (305 → 312 of 329, with costly blocks falling from 15
  to 8).
- **Not fixed: `redundant_page`**, the loss that started this. Its registered derivation gives
  0.61, not lower, and scores 45 of 50, against 47 for 1.13 and 46 for 1.14 at 0.59.

`DEFAULT_MODEL` stays `jev-1.13.0`. The profile is in `policy.MODEL_PROFILES` and applies only
when the effective model is `jev-1.14.0`.

## Method

**Arms.** Both arms are the live answers of 2026-10-15, one draw each:

- `13r`: 1.13 at its shipped cuts;
- `14`: 1.14 at the profile's cuts.

Two arms are descriptive only:

- `14` at 1.13's cuts, which is what L1-L4 measured;
- `13r` put through the same rule.

**Partition.** Each point has a calibration part and an evaluation part. The cuts are computed on
the calibration part only, and every verdict comes from the evaluation part. Six partitions
predate 1.14:

- redundant_page and memory_write use the splits their own cuts were derived on;
- the four loop and gate points use the fifty run's split: derive on the `-b` batches, report on
  the first batches;
- check_done uses its own run's hash halves.

The errata task halves are new. They were fixed in the registration, before any cut, by the
sha256 of the task id.

**Two rules, each matched to how the shipped cut was set.**

- **D, re-run the derivation on record** (redundant_page, memory_write). The cut is
  `thresholds.derive` at a 90 % precision target, or `memory_write_cut.derive` at 80 %, both on
  the 95 % Wilson lower bound. Run on today's 1.13, D returns the shipped values exactly (0.59
  and 0.54), so the procedure reproduces.
- **T, transfer 1.13's operating point** (every other point). The 1.14 cut is the strictest
  grid cut at which 1.14 acts on at least as many calibration cases as 1.13 does at its shipped
  cut. It reads no label. T applies in three situations:
  - the cut was chosen, not derived: `saturated` 0.70 and `1 - act` 0.25;
  - the derivation on record does not return the shipped value on 1.13's own recording:
    check_done's 90 % rule gives 0.60 on the September recording and 0.66 today, not 0.5;
  - the derivation set has no 1.14 answers: the holistic cut was derived on candor round 1.

**Verdicts** follow the lot L1 rule. A paired bootstrap gives a 95 % interval (2,000 replicas,
seed 7), with an exact McNemar test and Holm across the eight points:

- "mejora": the difference is above 0 and the Holm p is below 0.05;
- "no peor": the interval's lower bound is above −2 points;
- "peor": the interval's upper bound is below 0;
- otherwise "no concluyente".

**One case the registration did not cover.** D is unreachable for memory_write on 1.14's half
A: no cut has a Wilson lower bound of precision that clears 80 %. The cut stays at 0.54,
following the fifty run's precedent ("unreachable at n": nothing moves).

## Cuts

| Point (knob) | Rule | 1.13 shipped | **1.14 profile** | 1.13 by the same rule | The other rule, descriptive (1.14 / 1.13) | Calibration / evaluation |
|---|---|---|---|---|---|---|
| redundant_page (`adds_nothing`) | D, 90 % | 0.59 | **0.61** | 0.59 | T: 0.37 / 0.59 | 75 / 50 |
| memory_write (`remember`, `derivable`) | D, 80 % | 0.54 / 0.46 | **unreachable: stays** | 0.54 | T: 0.60 / 0.54 | 51 / 157 |
| goal_met (`goal_met`, was `saturated`) | T | 0.70 | **0.57** | 0.70 | D 80 %: 0.17 / 0.35 | 36 / 14 |
| repeats_check (`repeats_check`, was `saturated`) | T | 0.70 | **0.60** | 0.70 | D 80 %: 0.31 / 0.51 | 38 / 12 |
| extract_gate (`extract_skip`, was `1 - act`) | T | 0.25 | **0.27** | 0.25 | D 80 %: unreachable / unreachable | 34 / 16 |
| recall (`recall_skip`, was `1 - act`) | T | 0.25 | **0.10** | 0.25 | D 80 %: 0.10 / 0.13 | 36 / 14 |
| check_done (`done`) | T | 0.5 | **0.30** | 0.5 | D 90 %: 0.30 / 0.66 | 326 / 329 |
| candor holistic (`holistic`) | T | 0.83 | **0.90** | 0.83 | D, ≤ 5 % false flags: 0.96 / 0.88 | 56 / 54 |

How to read the cuts:
- The 1.14 cuts move the way L1-L4 saw the probabilities move: down for "done" and for the
  loop's two questions, and up for "misstates".
- **check_done** is where the two rules agree: both give 0.30 on 1.14. That is also the
  accuracy-maximising cut L2 reported post hoc, reached here by a rule that reads no accuracy.

## Results on the evaluation parts

Each cell gives right / n, the precision and recall of the acting direction, and the costly acts
(acting where the label says not to).

| Point | 1.13 at its cuts | 1.14 at 1.13's cuts (L1-L4) | **1.14 with the profile** | Difference, points [95 % CI] | 14 only / 13r only | Holm p | Verdict |
|---|---|---|---|---|---|---|---|
| redundant_page | 47/50 (P 1.00, R 0.83, 0) | 46/50 (1.00, 0.78, 0) | **45/50** (1.00, 0.72, 0) | −4.0 [−12.0, +4.0] | 1 / 3 | 1.00 | no concluyente |
| memory_write | 113/157 (0.94, 0.42, 2) | 115/157 (0.90, 0.48, 4) | **115/157** (0.90, 0.48, 4) | +1.3 [−3.2, +5.7] | 7 / 5 | 1.00 | no concluyente |
| goal_met | 12/14 (1.00, 0.67, 0) | 13/14 (1.00, 0.83, 0) | **14/14** (1.00, 1.00, 0) | +14.3 [0.0, +35.7] | 2 / 0 | 1.00 | no peor |
| repeats_check | 12/12 (1.00, 1.00, 0) | 11/12 (1.00, 0.83, 0) | **12/12** (1.00, 1.00, 0) | 0.0 [0.0, 0.0] | 0 / 0 | 1.00 | no peor |
| extract_gate | 15/16 (1.00, 0.89, 0) | 16/16 (1.00, 1.00, 0) | **16/16** (1.00, 1.00, 0) | +6.2 [0.0, +18.8] | 1 / 0 | 1.00 | no peor |
| recall | 14/14 (1.00, 1.00, 0) | 14/14 (1.00, 1.00, 0) | **14/14** (1.00, 1.00, 0) | 0.0 [0.0, 0.0] | 0 / 0 | 1.00 | no peor |
| check_done (block) | 313/329 (0.95, 0.94, 7) | 305/329 (0.90, 0.94, 15) | **312/329** (0.95, 0.94, 8) | −0.3 [−1.2, +0.6] | 1 / 2 | 1.00 | no peor |
| candor holistic (errata) | 30/54 (0.67, 0.22, 3) | 30/54 (0.59, 0.37, 7) | **28/54** (0.57, 0.15, 3) | −3.7 [−11.1, +3.7] | 1 / 3 | 1.00 | no concluyente |
| **All eight, pooled** | **556/646** | 550/646 | **556/646** | **0.0 [−1.5, +1.5]** | 13 / 13 | p 1.0 | **no peor** |
| The six L1 points, pooled | 213/263 | | 216/263 | +1.1 [−1.9, +4.6] | 11 / 8 | p 0.65 | no peor |

### Where the profile works, and where it does not

- **check_done: the gap is closed.** At 0.30, 1.14 blocks 146 held-out stops, 138 of them
  unfinished. 1.13 at 0.5 blocks 145, 138 of them unfinished. That is the same recall (93.9 %)
  and one more false block (8 against 7). At 0.5, 1.14 makes 15 false blocks. This is the change
  that matters most for a user of the Stop hook.
- **The loop and gate points: parity at small n.** No costly act appears in any arm. goal_met
  recovers the true goals 1.14 scores between 0.57 and 0.70, and repeats_check recovers its one
  miss. With 12 to 16 cases, "no peor" only means that the arms do not disagree against 1.14.
- **redundant_page: one case decides the derivation.** On `retrieval-c`, 1.14 scores every
  `keep` page at 0.02 or less except one, `rd-118`, at 0.60. 1.13 scores the same page 0.58,
  just under its 0.59. With that page dropped, no cut at or below 0.60 keeps the Wilson lower bound over 90 %:
  at 0.30 the cut acts on 48 pages with 47 right, a lower bound of 0.891. So the rule returns
  0.61, above the 13 `drop` pages 1.14 scores between 0.12 and 0.56. The ordering is not the problem: AUC
  is 0.995. The problem is the sample-size floor of `benchmarks/thresholds.py`, made sharper by
  one hard case.
- **memory_write: 1.14 stores more and errs more.** At the same cut, 1.14 stores 39 of 157
  against 33, with 4 costly stores against 2 (precision 0.90 against 0.94). The 80 % derivation
  does not clear on its half A, so there is no 1.14 cut to defend. The profile leaves the knob
  alone.
- **Candor holistic: the errata set cannot settle it.** Both versions rank errata near chance
  (AUC 0.57 and 0.53 in L4). Transferring 1.13's flag rate, 0.90 flags 7 answers in the
  evaluation half, against 9 for 1.13 at 0.83. 1.14 at 0.83 would flag 17, with 7 of them
  accepted answers. The cut keeps the false flags where 1.13 had them (3) and catches less.

### Cross-validation, descriptive

Each rule was refitted on four of five stratified folds over every case of a point, five seeds,
and scored on the held-out fold. The table gives the mean number of right decisions.

| Point | n | 1.13 at its shipped cut | 1.14, the profile's rule | 1.13, the same rule |
|---|---|---|---|---|
| redundant_page | 125 | 115 | 122.8 | 122.8 |
| memory_write | 208 | 156 | 155.2 | 161.6 |
| goal_met | 50 | 46 | 45.4 | 46.0 |
| repeats_check | 50 | 50 | 48.8 | 50.0 |
| extract_gate | 50 | 45 | 44.0 | 45.0 |
| recall | 50 | 50 | 48.8 | 50.0 |
| **Six points** | **533** | **462** | **465.0** | **475.4** |

Three readings:
- With more data per fit, redundant_page's derivation finds a lower cut for both versions, and
  they tie at 122.8. The registered split's 0.61 is the floor effect described above, not a
  model gap.
- Put through the same rules, 1.13 stays about 10 decisions ahead of 1.14 on these 533 cases,
  most of them on memory_write.
- This is resampling over cases the registered split already used, so it is a range, not a
  test.

## What changed in code

- `policy.MODEL_PROFILES` maps `jev-1.14.0` to the seven moved knobs, as read-only data, and
  `Thresholds.for_model(model)` lays a profile over the defaults. The 1.14 profile is
  `adds_nothing` 0.61, `goal_met` 0.57, `repeats_check` 0.60, `extract_skip` 0.27, `recall_skip`
  0.10, `done` 0.30, `holistic` 0.90.
- **Where the profile is chosen.** It follows the model the decider asks: `SANCHOPANZA_JEV_MODEL`,
  else `DEFAULT_MODEL`. It is chosen by:
  - a `Squire` given no thresholds;
  - the Claude Code hooks (`squire_from_env`), where `SANCHOPANZA_T_*` overrides lay over the
    profile;
  - `sanchopanza compact`.

  Explicit thresholds always win. `RecordedDecider.model` exposes a keyed replay's version, so
  a 1.14 replay reads the 1.14 profile.
- **New knobs, at 1.13's values:**
  - `goal_met` and `repeats_check`: None reads `saturated`.
  - `extract_skip` and `recall_skip`: None reads `1 - act`.
  - `done`, 0.5: read by `Squire.check_done`. `HarnessConfig.done_cut` now defaults to None,
    which means the squire's value.
  - `holistic`, 0.83: read by `candor.judge.holistic` when the squire carries thresholds.
- **1.13 is unchanged.** `tests/test_threshold_profiles.py` pins every value 1.13 reads and
  checks that only a profiled model moves anything. The full suite passes.

## Limitations

- **Small evaluation parts.** The loop and gate points have 12 to 16 cases each. Their "no peor"
  holds because the arms agree, and one disagreement against 1.14 would make them "no
  concluyente".
- **One draw per model.** Jev moves by up to 0.09 on the same state within a day. L1 found 1.13
  against itself changing about 1.5 decisions in 100.
- **Post hoc.** The need for recalibration, and which points to recalibrate, was read off L1-L4.
  The partition keeps each cut off its own evaluation cases, but not off the lot. The cuts are
  therefore a candidate, not a confirmed policy.
- **The candor holistic cut transfers 1.13's flag rate on errata.** That is not the set the
  cut was derived on (candor round 1), and on errata both versions rank near chance.
- **Not recalibrated.** These points showed a shift in L1-L4 but have no single derived cut and
  no significant change:
  - edge: 50 → 46 of 73 under the policy, p 0.29, with abstention bands on `citation` and
    `relax` that other points share;
  - collision: 95 → 93 on `act`;
  - citation: 19 → 18.

  label's `classify` (L3) and the permission cascade's tau (L2) needed none by their own rules.

## Recommendation

**Do not switch `DEFAULT_MODEL` to 1.14 on this evidence.**

The registered rule allows proposing the switch, since the pooled verdict is "no peor" and no
point is "peor". But four findings argue against making it now:

- At best the profile reaches parity: 556 against 556.
- It does not fix redundant_page, the regression that motivated it.
- It leaves memory_write with twice the costly stores.
- In cross-validation, 1.13 recalibrated by the same rules stays ahead.

1.14's gains are elsewhere: Score calibration, supersession and R-Judge (L1, L2).

**Keep the profile.** It makes `SANCHOPANZA_JEV_MODEL=jev-1.14.0` a safe opt-in now, and when
1.13 is retired the switch starts from cuts that are no worse.

**Before the switch, a confirmation on cases neither version was asked**, estimated in Jev at
today's per-call costs (31.6 µUSD per L1 call, about 47 per check_done trajectory, 87 per errata
holistic call), both arms:

| What | Cases | Jev USD |
|---|---|---|
| New labelled cases for the six L1 points, to the 90 %-target floor (about 70 each) | about 420 | about 0.03 |
| check_done on new AgentDojo trajectories (another suite) | about 600 | about 0.06, plus the agent runs that produce them (not Jev) |
| The candor holistic cut on the counterfactual rounds it was derived for | about 1,100 | about 0.19 |
| A second draw of both versions on every case here, for the day-to-day noise | 1,298 | about 0.11 |
| **Total** | | **about 0.4 USD of Jev** |

The shared Jev ledger stood at 0.97 of 4.50 USD after lot L4. redundant_page needs the most
attention: about 90 new `drop` cases would let a 90 % derivation clear without hinging on one
page.

## Reproducing

```bash
python benchmarks/jev114/jev114_recal.py                         # analysis.json, free
python benchmarks/jev114/jev114_recal.py --extract-done --runs-root PATH   # rebuild done-scored.jsonl
python -m pytest tests/test_jev114_recal.py tests/test_threshold_profiles.py
```

`done-scored.jsonl` holds the check_done probability per trajectory and arm, with ids, halves
and labels only and no text. It is rebuilt by replaying the L2 fixtures over the AgentDojo
`runs/` directories, which are not tracked.

## Files

- `prereg.md`, `prereg.sha256`: the sealed rules and partitions.
- `analysis.json`: every number above.
- `done-scored.jsonl`: the 655 check_done scores of both arms.
- Instrument: `benchmarks/jev114/jev114_recal.py`.
