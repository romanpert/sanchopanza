# Jev 1.14 against 1.13 as a corpus labeller: pre-registration (batch jev114-l3)

Written 2026-10-15, before any Jev 1.14 answer on these items and before today's 1.13 run.
Instrument: commit `67bfa66` (`benchmarks/label/jev114.py`, `benchmarks/label/data114.py`,
`tests/test_label_jev114.py`). The runner refuses to spend if the prereg's sha256 differs from
`prereg.sha256` or the instrument has uncommitted changes.

What was seen before writing this: AG News and DBpedia-14 are the sets of 2026-09-30, where 300
items of each were answered by 1.13 and Haiku (`docs/results/2026-09-30-label/`). Of SIB-200,
only the first test row in Spanish and English and the test split's topic counts, while checking
the download. No model has seen a SIB-200 item in this repository.

## Question

As a corpus labeller with the closed rubrics of 2026-09-30, is `jev-1.14.0` at least as accurate
as `jev-1.13.0`, both asked today on the same items? And does it gain more outside English, where
TypeSafe expects 1.14's largest gain?

## Data

- **AG News** (4 topics) and **DBpedia-14** (14 types), test splits, 1,000 items each: the 300
  positions of 2026-09-30, plus 700 evenly spaced over the test rows those did not take
  (`data114.positions`). Rubrics: `benchmarks/label/data.py:RUBRICS`, unchanged.
- **SIB-200** (topic classification of FLORES-200 sentences, 7 topics, CC BY-SA 4.0): the whole
  test split, 204 sentences, in `eng_Latn`, `spa_Latn`, `fra_Latn`, `deu_Latn`, `zho_Hans` and
  `arb_Arab`, so 1,224 items. The sentences are translations of each other. Rubric:
  `data114.SIB_RUBRIC`, the dataset's seven topic names, each with a one-line description written
  today. It is in English for every language.
- Gold labels are the datasets' own. `add_other` is off.

## Arms

- **13r**: `jev-1.13.0`, live today.
- **14**: `jev-1.14.0`, live today.

Neither arm sends a Danger Zone header. Both arms use the question and policy of 2026-09-30:
`label.label_one` (the `classify` point), with one Choice over the rubric's options per item and
`Thresholds.classify` = 0.60.

Each item gets its two calls back to back, and which arm goes first alternates.
In AG News and DBpedia-14, 13r goes first on even positions and 14 on odd ones.
SIB-200 runs sentence by sentence, with the six languages of a sentence together, so that a cut
hits every language alike. There the first arm alternates by sentence and by language at once,
so each language has each arm first on half of its sentences. At most 4 items are in flight, so
at most 4 requests. The answers recorded on 2026-09-30 are a historical reference only.

- **Retries.** The client retries a 429 or 529 up to 3 times. The runner makes at most 2 live
  attempts at an answer, and none once the run is halted.
- **Halt.** Every answer must come from the arm's model. An answer from another model halts the
  run, and that answer is neither recorded nor used. A refusal from the cap, or an out-of-funds
  reply, also halts the run. The runner then exits with 2.
- **Rows** are written without the item text: the third-party data stays out of the repository.

## Metrics

Families: AG News, DBpedia-14, and SIB-200 outside English, which pools the five non-English
languages (1,020 items). SIB-200 in English is reported apart, as the reference for the gap.

- **Primary:** argmax accuracy. An unanswered item counts as wrong.
- **With the production threshold:** coverage and accuracy at p1 >= 0.60.
- **Without a threshold:** AUROC of p1 for "the argmax is right".
- **Paired difference (14 - 13r):** a 95 % percentile bootstrap with 4,000 replicas and seed
  20261015. For AG News and DBpedia it resamples items. For SIB-200 it resamples sentences,
  each with all its languages. Each family also gets an exact two-sided McNemar test on argmax
  correctness, with Holm's correction across the three families. In SIB-200 the 1,020 pooled
  items cluster in 204 sentences, and McNemar treats them as independent, so its p is
  optimistic there. That is why "mejora" and "peor" also require the sentence-bootstrap interval.
- **p1** is the probability of the option Jev chose, as in the policy. The report counts the items
  where that option is not the most probable one.
- **Secondary, SIB-200:**
  - accuracy per language and arm;
  - the difference in differences: 1.14's gain outside English minus its gain in English, with
    the sentence bootstrap.
- **Noise check:** on the 300 items per English set shared with 2026-09-30, today's 1.13 is
  compared with that recording (accuracy, label agreement, McNemar).

## Decision rules, fixed now

For each family, on the primary metric:

- **mejora**: the difference is above 0, the Holm-adjusted p is below 0.05 and the lower bound of
  the interval is above 0.
- **peor**: the difference is below 0, the Holm-adjusted p is below 0.05 and the upper bound is
  below 0.
- **no peor**: neither of the above, and the lower bound is above -2 points.
- **no concluyente**: otherwise.

Both the computed verdict and the reported one are kept (see "incompleto" below).

The recommendations follow from those verdicts:

- **Move `label` to 1.14:** only if all three families are "mejora" or "no peor". This batch
  does not change `DEFAULT_MODEL` or `policy.py`.
- **Recalibrate `classify` for 1.14:** if, in any family, the coverage at 0.60 moves by more
  than 2 points (|difference| > 0.02) with its interval excluding 0, or the accuracy at 0.60 has its interval below 0
  while the family's reported argmax verdict is "no peor" or better.
- **Claim that 1.14 gains more outside English:** only if the lower bound of the
  difference-in-differences interval is above 0.

If more than 1 % of all answers are missing, the result is labelled incomplete. The verdicts are
still computed, with the missing answers counted as wrong. A family where more than 1 % of
either arm's answers are missing (the cap cutting it short, say) is reported as "no concluyente
(incompleto)".

## Money

- **Plan:** 6,448 Jev calls, 3,224 per arm.
- **Expected cost:** 0.152 USD. This comes from the runner's size-based estimate times 1.70, the
  ratio of recorded cost to estimate on the 600 answers of 2026-09-30.
- **Hard caps in code:**
  - every call goes through `CappedDecider` on the shared ledger `C:\sp-runs\jev114\ledger.json`;
  - the batch `jev114-l3` is capped at 0.20 USD and the ledger at 4.50 USD;
  - the runner refuses to start unless the expected cost times 1.25 fits in what is left under
    both caps.
- **What the caps miss:** a request abandoned at its 10 s timeout settles at 0 in the ledger, but
  the server may still charge it. The amount is small.
- **Before the run:** a preflight (`providers.jev.preflight`) once for each model. It runs
  outside the ledger and costs about 12 micro-dollars each. Done before sealing: both models
  answered 200 on 289 input tokens. There were three calls, 36 micro-dollars, because a script
  error repeated the 1.13 one.
- **No pilot.** The whole chain (replay, guard, recorder, cap, ledger) was checked with a fake
  model in place of Jev (`--dry`, with a scratch ledger and scratch fixtures) and by
  `tests/test_label_jev114.py`. Within the first 40 items of a set, a set stops if an arm has 10
  unanswered items.
- **Duration:** about 20 to 40 minutes. Every reservation re-reads the shared ledger.
- **Order of the sets:** AG News, DBpedia-14, SIB-200.
- **Claude:** zero calls.
