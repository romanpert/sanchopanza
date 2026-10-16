# A10: a local check_done classifier on public labels, against Jev on unseen stops

**The result:** by the sealed rule, **"no concluyente"**, and the classifier does not transfer.
Trained only on AgentDojo's own labels for 393 slack stops, a local TF-IDF and logistic-regression
classifier ranked checkdone114's 950 unseen stops (banking, travel, workspace, another agent) at
**AUC 0.655**, against **0.814** for Jev 1.14: **−0.159, cluster bootstrap 95 %
[−0.272, −0.048]**, against a −0.05 margin. The interval is wholly below zero; its upper bound
misses the "peor" zone by 0.002. At its cut it caught **18 of the 155 unfinished stops**, against
Jev 1.14's 100.

Out of fold on its own suite it reached AUC 0.944, level with Jev there (+0.006 [−0.062, +0.072]);
on suites it never saw it fell to 0.655, near chance on workspace (0.525). A local classifier
trained on one public suite is not a stand-in for Jev on check_done; it stays a design for an
offline fallback that would need labels from the setting it serves.

Pre-registered in [`prereg.md`](prereg.md), free (no model call):
- reviewed twice by `revisor-prereg` against the code before the seal;
- no Jev output reaches the model: the two training pipelines that ran with Jev as the injection
  detector are excluded, since their labels and text are effects of Jev's decisions (TypeSafe's
  MCA 2.3(b) forbids training on Jev's outputs);
- sealed in `ac61ad0` (`prereg.sha256` `7ad0d12c…`), the model fixed before (sha256 `df370586…`);
- scored once, from a worktree detached at the seal commit, on 2026-10-16.

## What ran

- **Training:** the 393 slack stops of `docs/results/2026-09-25-completion/` whose pipelines did not
  involve Jev (Sonnet 5 undefended and with spotlighting, Haiku 4.5 undefended; 286 done), labels
  from AgentDojo's check of the environment's final state. Word and character n-grams of the request
  and the record check_done's builder produces, logistic regression; every choice by 5-fold
  cross-validation grouped by user task (26 clusters): AUC 0.944 out of fold, cut 0.45 by a ladder
  fixed on training only (0.90 block precision found no cut; then 0.80).
- **Test:** checkdone114's 950 stops (795 done, 106 user-task clusters), checked against that lot's
  sealed `data.sha256`; Jev's arms are its recorded decisions (1.14 at 0.30, 1.13 at 0.5), read for
  comparison only.
- **Known when the rules were chosen:** the test's label mix, that never blocking is right on 795
  of 950, Jev's counts and its AUC of 0.81. That is why the primary is the AUC, which a classifier
  cannot raise by blocking less.

## Primary result

| | AUC on the 950 | Local minus Jev | Cluster bootstrap 95 % | Verdict at −0.05 |
|---|---|---|---|---|
| Local | 0.655 | | | |
| Jev 1.14 | 0.814 | **−0.159** | **[−0.272, −0.048]** | **no concluyente** |
| Jev 1.13 (secondary) | 0.812 | −0.157 | [−0.265, −0.050] | |

## At the cuts (secondary)

| Arm | Right of 950 | False blocks of 795 finished | Caught of 155 unfinished |
|---|---|---|---|
| Local at 0.45 | 768 (80.8 %) | 45 | **18** |
| Jev 1.14 at 0.30 | 745 (78.4 %) | 150 | 100 |
| Jev 1.13 at 0.5 | 737 (77.6 %) | 165 | 107 |
| Never block | 795 (83.7 %) | 0 | 0 |

The local arm is right more often than Jev (+2.4 points, cluster [−5.4, +10.6]) only because it
blocks less, and never blocking does better still; it catches 52.9 points fewer unfinished stops
than Jev 1.14, cluster [−68.1, −37.2]. By suite (local / Jev 1.14 AUC): banking 0.763 / 0.885,
travel 0.670 / 0.908, workspace 0.525 / 0.752; caught 16 / 37, 0 / 27 and 2 / 36.

## What this licenses, and what it does not

- **Not a stand-in:** trained on one suite's public labels, the classifier loses most of its
  ranking on others. Its in-domain parity was the training suite's vocabulary, not the question.
- **Not tested:** training on labels from the setting it would serve (the transfer here was
  across suites and agents at once), an encoder or a fine-tuned model instead of n-grams, other
  points. A local provider stays a design: one more `LocalDecider`, trained on the user's own
  labels, measured on data it never saw.

## Files

- `prereg.md`, `prereg.sha256`, `cv.json`, `oof.jsonl`, `dry.json`, `overlap.json`, `power.json`:
  the registration, its seal and the training-side artifacts.
- `fixtures/a10_local/model.json`: the fitted model (vocabulary from AgentDojo's synthetic slack
  world).
- `analysis.json`, `scored.jsonl`: the scoring (`eval.py run`), each stop's id, cluster, label and
  local probability, no text.
