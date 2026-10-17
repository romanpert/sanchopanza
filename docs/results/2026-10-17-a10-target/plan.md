# Plan: A10 with labels from the target environment (check_done, in-domain)

Written 2026-10-17, before any in-domain classifier scored a single held-out stop. Committed with
the code (`benchmarks/a10_local/a10_target.py`, `target.py`) before `target.py run`; the run
refuses while this file or that code differs from the commit, and records the commit and this
file's sha256 in `analysis.json`. Free: no model is called (no Jev, no Claude, no OpenAI).

## Question

A10 ([`../2026-10-16-a10-local/`](../2026-10-16-a10-local/README.md)) trained a local check_done
classifier on AgentDojo's slack labels and scored it on banking, travel and workspace: AUC 0.655
against Jev 1.14's 0.814. It ranked as well as Jev on its own suite (out of fold) and lost most
of that elsewhere. Its README left one free follow-up open: train on labels from the setting the
classifier would serve.

**Does the same classifier, trained on labels from the very suites it is scored on (never on the
same user task), rank finished stops above unfinished ones as well as Jev 1.14 does, within
−0.05 AUC?**

## Data: ground-truth labels only

| | |
|---|---|
| Stops | 2,522: checkdone114's 950 (`claude-3-7-sonnet-20250219`) and checkdone-w17's 1,572 confirmation stops (`claude-3-5-sonnet-20241022` 622, `gemini-2.0-flash-001` 950) |
| Source | AgentDojo's published runs (MIT) at commit `089ed468`, every file checked by git blob sha against `../2026-10-16-checkdone114/inputs.jsonl` and `benchmarks/jev114/w17_inputs.jsonl`; the 950 also against checkdone114's sealed `data.sha256` |
| Suites | banking 507, travel 501, workspace 1,514 |
| Clusters | 106 user tasks (`suite/task dir`, pooled across the three agents): 25, 27 and 54 |
| Injection tasks | 30 (9, 7 and 14); 2,212 attacked stops, 310 benign |
| Label | AgentDojo's `utility`: its own check of the environment's final state |
| What the classifier reads | check_done's `state["task"]` and `state["record"]`, built as every earlier lot built Jev's requests (`completion/run.py` `render`, tool results cut at 1,500 characters, then `points.completion.questions`) |

**Provenance and TypeSafe's MCA 2.3(b).** The trajectories are AgentDojo's authors' own runs of
three undefended pipelines: no Jev anywhere in their loop, so neither the text nor the label is an
effect of a Jev decision. The label is AgentDojo's `utility`. Jev's recorded probabilities
(`p_14` in checkdone114's `done-scored.jsonl`, `p_old` of the confirmation rows of checkdone-w17's,
both `jev-1.14.0` on this same record) are read **only to score Jev** on the same stops. They are
never a feature, a label, a selection criterion or a fold criterion. The fitting code takes
`a10_data.Example`, which has no field for them; a test pins it.

## Model: nothing tuned on this data

A10's configuration, fixed by its own CV on slack and unchanged here: view B
(`w+c+l+s|w2|C=1`, word 1-2-grams, character 3-5-grams, the last agent message, structure
tokens), min_df 2, L2 logistic regression (`a10_model.fit`). Each fit builds its vocabulary and
idf from its fitting stops only. There is no grid, no early stop, and no cut: the measure is AUC.

## The splits (fixed now)

**Primary: user-task cross-fitting.** Five folds of whole user-task clusters, assigned within each
suite by A10's rule (`train.folds`: largest cluster first, to the lightest fold, ties by name), so
every fold holds about a fifth of each suite and all three agents' runs of a task stay together.
For each fold, fit on the other four and score it. Every stop gets one out-of-fold
`p_target`. A stop is never scored by a model that saw its user task, under any agent.

**The leak this leaves, stated:** every user task is run with every injection task, so an
injected payload seen in a scored stop also appears, under other user tasks, in the fitting folds;
and an injection task run as a user task (`injection_task_M/none`) has the request text that the
attacked stops carry as payload. S1 removes both.

**S1, strict: disjoint in user task and injection task.** User-task clusters get the primary's
folds. The 30 injection tasks get five folds of their own, the same rule within each suite (an
injection task's size: its attacked stops plus its `injection_task_M` cluster). A stop's injection
group is `suite/injection_task_M` from its file name when attacked, its own cluster when it is an
`injection_task_M` directory, none when it is a benign user-task stop. In fold k:

- **scored:** benign user-task stops whose user task is in fold k; `injection_task_M` stops whose
  injection task is in fold k; attacked stops whose user task **and** injection task are both in
  fold k;
- **fitted on:** stops whose user task is not in fold k and whose injection group (if any) is not
  in fold k.

No scored stop shares a user task or an injection task with any stop its model was fitted on (a
test pins it). Attacked stops whose two folds differ are never scored (about four fifths); they
only train. `p_strict` is null for them.

**S2, the agent's own labels.** The primary's folds, but each fit sees only the scored stop's own
agent: for agent a and fold k, fit on agent a's stops outside fold k, score agent a's stops in
fold k (15 fits). Every stop gets `p_agent`. The closest analogue here to "a destination's own
sessions".

**S3, no target labels (context).** A10's fitted model (`fixtures/a10_local/model.json`, slack
labels only), scored on the same 2,522: `p_a10`.

## Analysis (fixed now)

- **Primary:** AUC of `p_target` minus AUC of Jev 1.14 on all 2,522 stops, rank AUC with ties at
  half (`a10_analysis.paired_auc`), paired bootstrap over the **106 user-task clusters**
  (`l4_stats.bootstrap`, 10,000 replicas, seed 20261015), read on unrounded bounds by A10's rule
  at **−0.05**: "mejor" if the lower bound is above 0; "no peor" if above −0.05; "peor" if the
  upper bound is below −0.05; otherwise "no concluyente".
- **Secondary, each reported, none changing the primary:**
  1. S1: `p_strict` against Jev on the stops S1 scores (same bootstrap and rule).
  2. S2: `p_agent` against Jev on all 2,522, and by agent.
  3. The primary by suite and by agent, with the same interval.
  4. S3: `p_a10` against Jev and against `p_target` on all 2,522.
  5. Each arm's AUC within each fold, and their mean, descriptively: the pooled out-of-fold AUC
     mixes five models' scales.
- **Missing values:** none expected; a stop without Jev's probability stops the analysis.

## Known when this was written

- Jev 1.14's AUC on these stops' record: 0.814 on the 950 (checkdone114), 0.865 on the 1,572
  (checkdone-w17, `old` arm); the label mix: 795 of 950 and 828 of 1,572 finished.
- A10's model on the 950: AUC 0.655. Its AUC on the 1,572 has not been computed.
- No in-domain fit has been run on any of these stops. The configuration was fixed by A10 on
  slack before this plan; the only choices made here are the folds and the arms above.

## Expectations and power (stated before)

- A10's out-of-fold AUC on slack was 0.944 against Jev's 0.938 there. If labels from the setting
  are what was missing, `p_target` should approach Jev; the agents still differ inside the
  pool, and the injection payload leak may flatter the primary, which is why S1 is reported.
- The interval is driven by the 106 clusters, not the 2,522 stops: A10's was 0.22 wide at 950
  stops on the same clusters. A width near 0.10 is expected here, so "no concluyente" is the
  likely reading at parity; "no peor" needs the local arm at or above Jev.

## What this does not settle

- AgentDojo stops, not coding sessions; one model family (n-grams and logistic regression).
- In-domain here means same suites, tools and task distribution, new user task. A user whose own
  sessions repeat the same tasks would see a smaller shift; one whose tasks change, a larger one.
- Jev may have seen these public files in training; the local model sees only its fitting folds.
- No cut, so no false-block or catch counts: a cut fixed on the fitting folds would need its own
  nested rule.

## Running

```bash
python benchmarks/a10_local/target.py run      # analysis.json, scored.jsonl (no text)
python -m pytest tests/test_a10_target.py
```
