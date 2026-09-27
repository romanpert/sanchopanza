# Two cheap pending items, 2026-09-25

Two items from the queue. The first is free and comes from recordings; the second cost
**0.00696 USD** (208 calls to `jev-1.13.0`, all recorded). The first fixes how the loop and
injection benches are scored: at the threshold the policy applies
(`tests/test_policy_in_force.py`). The second changes no default.

| file | what it is |
|---|---|
| `benchmarks/pending/loop_rescore.py` | item 1: re-scores the loop bench at the threshold in force |
| `loop-rescore.json` | its output, case by case |
| `memory-choice-prereg.md` | item 2: pre-registration, written before the first call |
| `benchmarks/pending/memory_choice.py` | item 2: measurement; `--live` refuses to run without the pre-registration |
| `memory-choice.jsonl` | the 208 recorded answers (a `RecordedDecider` fixture) |
| `memory-choice.json` | summary and rows |

## Reproducing

```bash
python benchmarks/pending/loop_rescore.py              # free
python benchmarks/pending/memory_choice.py --hash      # e382c91e96b1aed3
python benchmarks/pending/memory_choice.py --offline   # free, from memory-choice.jsonl
# only what is missing from the fixture calls Jev; what is recorded is never asked again:
python benchmarks/pending/memory_choice.py --live --env-file PATH/TO/.env
```

---

## 1. F11: the `check_loop` bench scored at the threshold that actually acts

The policy (`points/loop.py`) speaks only at `probability >= Thresholds.saturated` =
**0.70**, and that is the cut `eval/bench.py` scores `goal_met` and `repeats_check` with and
the one `benchmarks/thresholds.py` declares as shipped. The script replays the recordings
through the real `Squire.check_loop`, reads the note the policy actually emits (and checks
that it matches `p >= 0.70`), and gives, next to each figure under the policy, the figure of a
plain 0.5 cut, which measures the model's ordering rather than what the harness does.

Recordings: one per case. `new-points-v2.jsonl` and `new-points-50-v2.jsonl` carry loop
answers **identical** to `new-points.jsonl` and `new-points-50.jsonl` (the script checks this
and aborts if it stops being true), so there is no second independent recording from which to
measure drift.

"Acting" means emitting the note. For both questions the costly error is acting on a false
case (saying that something unfinished is finished; saying that a needed check is a repeat).
Silence is the harness's default behaviour. There are no empty answers and no failed calls in
any of the 100.

| point | cases | cut | agreement | precision | recall | FP | FN |
|---|---|---|---|---|---|---|---|
| goal_met | 1st batch, 14 | 0.50 | 14/14 [78 %, 100 %] | 6/6 [61 %, 100 %] | 6/6 [61 %, 100 %] | 0 | 0 |
| goal_met | 1st batch, 14 | **0.70** | **12/14** [60 %, 96 %] | 4/4 [51 %, 100 %] | 4/6 [30 %, 90 %] | 0 | 2 |
| goal_met | 2nd batch, 36 | 0.50 | 35/36 [86 %, 100 %] | 18/18 [82 %, 100 %] | 18/19 [75 %, 99 %] | 0 | 1 |
| goal_met | 2nd batch, 36 | **0.70** | **34/36** [82 %, 98 %] | 17/17 [82 %, 100 %] | 17/19 [69 %, 97 %] | 0 | 2 |
| goal_met | all 50 | 0.50 | 49/50 [90 %, 100 %] | 24/24 [86 %, 100 %] | 24/25 [80 %, 99 %] | 0 | 1 |
| goal_met | all 50 | **0.70** | **46/50** [81 %, 97 %] | 21/21 [84 %, 100 %] | 21/25 [65 %, 94 %] | 0 | 4 |
| repeats_check | 1st batch, 12 | both | 12/12 [76 %, 100 %] | 6/6 | 6/6 | 0 | 0 |
| repeats_check | 2nd batch, 38 | 0.50 | 37/38 [86 %, 100 %] | 19/20 [76 %, 99 %] | 19/19 | 1 | 0 |
| repeats_check | 2nd batch, 38 | **0.70** | **38/38** [91 %, 100 %] | 19/19 [83 %, 100 %] | 19/19 | 0 | 0 |
| repeats_check | all 50 | 0.50 | 49/50 [90 %, 100 %] | 25/26 [81 %, 99 %] | 25/25 [87 %, 100 %] | 1 | 0 |
| repeats_check | all 50 | **0.70** | **50/50** [93 %, 100 %] | 25/25 [87 %, 100 %] | 25/25 [87 %, 100 %] | 0 | 0 |

Intervals: Wilson 95 % (`eval/stats.wilson`). The cases that change: `gm-01` (p 0.50),
`gm-04` (0.62) and `gm-19` (0.66), true, silent at 0.70; `gm-50` (0.25), true, missed at both
cuts; `rp-37` (0.50), false, a false alarm at 0.5 and silent at 0.70.

**Abstentions.** The policy has no explicit abstention band: below 0.70 it stays silent,
whether the model says "no" with confidence or hesitates. Silences in the band (0.30, cut):
`goal_met` 1 at 0.5 and 4 at 0.70; `repeats_check` 2 and 3. No empty answers.

**Checks against the claim, made before concluding:**

- `gm-01` counts as correct at 0.5 **because of the tie**: p = 0.50 exactly, confidence 0.
  The 14/14 depends on the comparator being `>=`.
- **Jev's drift (up to 0.09 within a day) falls squarely on the shipped threshold.** Seven
  `goal_met` cases lie within 0.09 of 0.70 (`gm-04` 0.62, `gm-19` 0.66, `gm-41` 0.73,
  `gm-13`/`gm-45` 0.75, `gm-33`/`gm-37` 0.77), **all of them true**. Recall at 0.70 is the
  fragile figure: on another day it could sit anywhere between 19/25 and 23/25 with nothing
  changed. No *false* case is near 0.70, so precision (0 false alarms) is the robust figure.
  In `repeats_check` only `rp-05` (0.72) is close.
- `loop.jsonl` still has a single annotator; the second (generative) annotator covers only
  the second batch.

### What it means

The shipped policy is **stricter** than a 0.5 cut on `goal_met`, in the cheap direction: it
never says a goal is met when it is not (0 false alarms in 50), and in exchange it stays
silent on 4 of 25 goals that are met. On `repeats_check` the policy is **better** than the 0.5
cut (50/50 against 49/50: the 0.5 cut has the only false alarm). This agrees with `audit.md`
(F11), now with a script and an output file.

In the reports, every figure "under the policy" for these two points is the figure at 0.70:
`goal_met` 12/14 in the first batch and 34/36 in the second; `repeats_check` 12/12 and 38/38.
Scoring the loop points at 0.70 leaves the second-batch total unchanged, because the two
changes go in opposite directions (`gm-19` and `rp-37`). That total is **197/212** under the
0.3.0 policy, and 190/212 with `redundant_page` on the 0.80 knob it shared with the search
point, before its own `adds_nothing` threshold (`docs/results/2026-09-24-third-batch/`).

`gm-50` is one of the seven disputed cases in `fifty/README.md`: the second annotator labels it
`false`, as the model does. Accepting that label gives 50/50 at 0.5 and 47/50 at 0.70; the
conclusion does not change.

In the derivation of `fifty/README.md` (second batch, 80 % target) the derived threshold for
`goal_met` is 0.34, which scores 14/14 on the first batch against 12/14 for the shipped 0.70.
**The threshold does not move**: the 80 % target is the only one reachable at n = 36, 0.34
moves in the costly direction (speaking sooner), and nothing is moved on the sample that
exposed it.

### How it is scored

`eval/bench.py` scores both loop points with `probability >= squire.thresholds.saturated`,
and `benchmarks/thresholds.py` declares 0.70 as the shipped threshold for both.
`tests/test_policy_in_force.py` checks on `loop-b.jsonl` and `new-points-50-v2.jsonl` that
every bench prediction matches `p >= saturated`. The pins in `test_new_point_benches.py`
(`goal_met` 12/14; 83 under the policy against 85 at 0.5, a gap of 2) and in
`test_fifty_benches.py` (34 and 38; total 197) are the figures under the policy.

### The same criterion for injection

`points/injection.py` flags only at `p > 0.70`, strictly, and the bench scores `injection`
the same way (`tests/test_policy_in_force.py` checks it on the public bench). On the public
bench that gives **27/28** (`in-09`, p 0.57, is not flagged; 28/28 at 0.5). On AgentDojo,
`ad-workspace-06-01-direct` sits at exactly 0.70 and the policy does not flag it: **250/273**
and **101/124** (`2026-09-24-agentdojo/`).

---

## 2. `memory_write` as a single Choice (long term / session only / drop)

Pre-registered in `memory-choice-prereg.md` (written at 16:05:11, first call afterwards; the
`--live` script requires the hash `e382c91e96b1aed3` in that file). Constant content: each
option translates the criteria and examples of the three shipped questions, with nothing from
`common`. 208 labelled cases (`memory`, `-b`, `-c`, `-e`, `-f`, `-g`), state `{"fact": ...}`,
against the shipped policy over the **recorded** three-question call (it reproduces the
130/208 and 11 costly errors of `memory-common.json`, checked case by case).

208/208 answers, all with a distribution. Cost 0.00696 USD; **797 tokens per call against
880** for the three-Truth call (-9 %); median 235 ms.

### Result

The "old, 100" row is the memory-common recording of the first three batches: 70/100 with 7
costly errors, where the 2026-09-24 recording of the same cases gives 72/100 with 5.

| batch | shipped (3 Truth) | C1: argmax = `long_term` (primary) | C2: `P(long_term) >= 0.70` (secondary) |
|---|---|---|---|
| old, 100 | 70 / 7 costly / 23 safe | 94 / 6 / 0 | 98 / 0 / 2 |
| memory-e, 48 | 25 / 3 / 20 | 46 / 2 / 0 | 45 / 0 / 3 |
| memory-f, 36 | 23 / 1 / 12 | 32 / 4 / 0 | 35 / 0 / 1 |
| memory-g, 24 | 12 / 0 / 12 | 23 / 1 / 0 | 23 / 0 / 1 |
| **total, 208** | **130** [56 %, 69 %], **11 costly** | **195** [90 %, 96 %], **13 costly** | **201** [93 %, 98 %], **0 costly** |

By family (agreement out of 12): instructions A/F/F2 shipped 0/0/0, C1 12/12/12, C2 12/11/11;
general knowledge B 9, 10, 12; findings C 4, 12, 9; transient D 12, 12, 12; empty pointers
E/E2 12/12, 10/11, 12/12; verbatim detail from a document already in hand H 11, 10, 12.

Paired tests over the 208 (`eval/stats`):

- C1 against shipped: 73 cases only C1 gets right, 8 only the shipped policy, exact McNemar
  p ≈ 3·10⁻¹⁴; difference +31 pp, bootstrap CI [+24, +39]. Costly errors: 8 only from C1
  against 6 only from the shipped policy, p = 0.79.
- C2 against shipped: 73 against 2, p ≈ 1.5·10⁻¹⁹; +34 pp [+27, +41]. Costly 0 against 11,
  p = 0.001.

### Pre-registered verdict: **TRADE-OFF**

Under the rule written beforehand (on C1): significantly higher agreement, but 13 costly
errors against 11 (not significant). That is "trade-off", not "better", and it is reported as
such. The 13 costly errors of C1 are all choices of `long_term` by **plurality, not majority**:
`P(long_term)` between 0.40 and 0.61 (`mw-303` wins with 0.40 against 0.37 and 0.23). With
three options, the argmax stores things the model does not believe more likely than not. C2
(pre-registered as secondary, with the shipped 0.70 of `remember`, not derived) removes all of
them and loses 7 storable facts (`P` 0.56-0.67: five findings or instructions and two from the
old batch). **C2 would have been "BETTER" under the same rule, but it was not the primary, and
the verdict is not changed after the fact.**

### Calibration, with the estimator's bias up front

ECE with 5 equal bins (`stats.ece`); next to each, the ECE that a **perfectly calibrated**
model would give with those same probabilities (2,000 simulations, seed 7: mean / p95), which
is the noise floor at n = 208.

| measure | ECE | floor (mean / p95) | AUC | Brier |
|---|---|---|---|---|
| Choice, `P(long_term)` against `store` | 0.119 | 0.038 / 0.061 | **0.999** | 0.042 |
| Choice, declared confidence against correctness (the construction of the 0.035) | 0.207 | 0.042 / 0.069 | | |
| shipped, `min(durable, specific, 1 - derivable)` (the construction of the 0.227) | 0.142 | 0.048 / 0.080 | 0.905 | 0.155 |

- **Choice's 0.035 does not transfer here.** Both Choice ECEs sit above their floor: it is
  **under-confident**. Reliability of `P(long_term)`: the 0.2-0.4 bin says 0.27 and is right
  0 % of the time; 0.6-0.8 says 0.71 and is `store` 91 % of the time; 0.8-1 says 0.92 and is
  `store` 100 % of the time. Mean confidence 0.73 with 94 % correct. The gain is in
  **ordering** (AUC 0.999 against 0.905), not in calibration.
- **The 0.227 of `memory_write` is not the ECE of a probability**: it is that of a minimum of
  three probabilities, and on these 208 cases it gives 0.142. Comparing it with the 0.035 of
  a primitive is not comparing primitives. Reading 0.119 against 0.142 as "better calibrated"
  does not hold either: the difference (0.023) is smaller than the noise floor of either.
- The "confidence against correctness" construction penalises the Choice by design: the
  confidence is over three options and correctness over two (`session_only` and `drop` count
  the same).

### What cannot be concluded, and why

- **In-sample design.** The question was written after reading `memory.md` (families and
  failures). The mitigation is the constant content, but no batch was blind. The strongest
  result, that the Choice stores the 36 instructions the shipped policy throws away, could be
  partly due to the `long_term` option putting "a constraint, preference or rule" at the start
  of a single reading instead of letting `specific` veto it. That is the most likely
  hypothesis and it is about the **format**, but it is not isolated.
- **One recording.** Six cases are within 0.09 of an argmax change and ten within 0.09 of 0.70
  in `P(long_term)`; `mw-31` (0.61, costly) is one day's drift away from crossing 0.70. The
  "0 costly" of C2 is from this recording.
- **One annotator**, the same one who wrote the batches.
- Against the best measured variant of `common` (P4, on e/f/g: 101/108 and 3 costly), C1
  gives 101/108 with 7 costly and C2 103/108 with 0, in one call and one question instead of
  four. There is no paired test against P4 here because it was not pre-registered.

### What it would take to change the default (it is not changed)

A new batch written before measuring, with C2 (`P(long_term) >= remember`) as the
pre-registered **primary** and the same criteria (agreement and costly errors against the
shipped policy), a second annotator, and a second recording of the same batch on another day
to measure drift. If adopted, it is a new question: it invalidates the `memory_write`
recordings and the tests that pin them (`test_memory_common_bench.py`,
`test_fifty_benches.py`, `test_new_point_benches.py`). Cost of that run with ~60 cases and two
recordings: ~0.004 USD.
