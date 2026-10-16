# DRAFT, NOT SEALED. Pre-registration: A10, a local check_done classifier trained on public labels, against Jev on unseen stops

Status: **draft**, written 2026-10-16. Not reviewed by `revisor-prereg`, not sealed. Nothing has
been scored on the test set: `eval.py run` refuses until `prereg.sha256` exists and matches.

## Question

Can a local classifier, trained only on a public benchmark's own labels, decide check_done
("did the agent fully do what the task asked, as far as the record shows?") on unseen stops of
another agent, in other suites, as well as Jev does?

This is roadmap item A10 and the first measurement of "the path from hosted to local"
(`docs/providers.md`). A local classifier would plug in as a `LocalDecider`, an offline fallback
or a provider kept on the machine. It is not a saving: Jev costs micro-dollars a decision.

## Free, no model calls, MCA-clean

- **No model is called.** Training, CV, the dry run and the evaluation are pure Python on this
  machine. The bill is 0 USD for Jev and for Claude.
- **TypeSafe's MCA 2.3(b)** forbids training on Jev's outputs. Jev's probabilities and decisions
  are not a feature, a label, or a selection criterion here.
  - The CV picks the knobs by out-of-fold AUC against AgentDojo's labels.
  - The cut rule reads only those labels.
- **What the classifier reads.** Only check_done's `state["task"]` and `state["record"]`.
- **What it learns from.** Only AgentDojo's `utility` on the 655 training stops.
- **Every input of this lot, exactly:**
  1. The 655 AgentDojo v1.2.2 slack trajectories of 2026-09-24. These are this repository's own
     runs, untracked under `docs/results/2026-09-24-agentdojo-{e2e,haiku}/runs/`. The lot reads
     their `messages` and their `utility` label.
  2. The 950 AgentDojo trajectories of lot checkdone114, AgentDojo's published runs at commit
     `089ed468`, checked by blob sha against `../2026-10-16-checkdone114/inputs.jsonl`. The lot
     reads their `messages` and their `utility` label.
  3. **For the comparison only, never for training:**
     - Jev's recorded probabilities on the 950, in `../2026-10-16-checkdone114/done-scored.jsonl`
       (`p_14`, `p_13r`);
     - on the 655, in `../2026-10-15-jev114-recal/done-scored.jsonl`, read by the dry run after
       the model was fixed.

## Data

| | Train | Test |
|---|---|---|
| Stops | 655 | 950 |
| Suites | slack | banking 169, travel 167, workspace 614 |
| Agents | Sonnet 5 under four pipelines, Haiku 4.5 | `claude-3-7-sonnet-20250219` |
| Labels | 342 done, 313 not done | 795 done, 155 not done |
| User-task clusters | 26 | 106 |
| Fixed by | `train_digest` `df2eb0dc…` (`a10_data.digest`) | checkdone114's `data.sha256` (`e82c4f87…`) |

**Overlap** (`eval.py overlap`, `overlap.json`): no shared cluster (suite/task), no shared request
text, no shared record, no shared file, no shared agent.

- The bare directory names `user_task_0`… and `injection_task_1`… recur in every suite: 26 of
  them appear in both sets.
- They name different tasks in different suites. No request text is shared.

**The record** is check_done's, built the way Jev's requests were built in both lots:

- `benchmarks/completion/run.py` `render(messages)`, with `evidence=False`;
- each tool result cut to its first 1,500 characters;
- then `points.completion.questions`: task cut at 1,000 characters, record at 24,000.

## Model

TF-IDF and L2-regularised logistic regression, pure Python, since the venv has no numpy or
scikit-learn. Code: `benchmarks/a10_local/`.

**Fixed by convention before the CV:**

- **Tokens.** Lower-cased `[a-z0-9_]+` words over task and record. Four token families:
  - `w`: word n-grams;
  - `c`: character 3-5-grams inside words;
  - `l`: word 1-2-grams of the agent's last message;
  - `s`: structure tokens from the record lines (bucketed counts of actions, results, messages,
    errors and results at the 1,500 cut; the last step's kind; whether the last message asks).
    29 of them are kept in the fitted vocabulary.
- **Weighting.** min_df 2 on the fitting set. Sublinear tf, smoothed idf (scikit-learn's
  defaults). Each family L2-normalised and scaled by 1/sqrt(k), so each vector has norm 1.
- **Objective.** C · Σ log-loss + ½‖w‖², intercept unpenalised.
- **Solver.** L-BFGS, memory 10, Armijo backtracking, at most 500 iterations. It stops at max
  |gradient| < 1e-6 · max(1, C·n).
- **The saved model.** Weights rounded to 6 significant digits. The test is scored with the
  saved model.

**Fixed by CV on TRAIN only** (`train.py cv`, `cv.json`, `oof.jsonl`):

- **Folds.** 5-fold CV grouped by user task, so a fold never scores a task it was fitted on. The
  folds hold 150/130/125/125/125 stops and 5/6/5/5/5 clusters.
- **Grid.** Views A = w(1-2)+l+s, B = A + c, C = w(1)+l+s, D = l+s. C ∈ {0.1, 1, 10, 100}.
- **Selection rule.** The highest pooled out-of-fold AUC to 3 decimals. A tie goes to the lower
  out-of-fold log-loss.

| View | C = 0.1 | 1 | 10 | 100 |
|---|---|---|---|---|
| A, words 1-2 | 0.919 | 0.939 | 0.947 | 0.948 |
| B, A + chars | 0.929 | 0.945 | 0.950 | 0.951 |
| **C, words 1** | 0.922 | 0.942 | 0.950 | **0.952** (log-loss 0.320) |
| D, last message + structure | 0.895 | 0.921 | 0.940 | 0.943 |

**Chosen: view C, `w+l+s|w1|C=100`**, min_df 2.

- Out-of-fold AUC 0.9516. The folds score 0.912, 0.924, 0.993, 1.000 and 0.939.
- Accuracy at 0.5 is 0.889.
- C = 100 is the grid's edge. A descriptive run at C = 1000 gives the same AUC (0.952) with a
  worse log-loss (0.400). The rule would keep C = 100 on a wider grid.

**The fitted model** (`train.py fit`): `fixtures/a10_local/model.json`, 309,233 bytes, 9,539
terms, sha256 `da25d002…`.

- L-BFGS stopped at 53 iterations on the gradient tolerance.
- Two fits give the same bytes.
- The vocabulary is AgentDojo's synthetic slack world: names, channels, `external_0`, `gmail`.
  It holds no path and no credential.

## The cut

**Block when p(done) < 0.09.**

**The rule.** Rule D at 90 %, the rule that gave Jev 1.14 its 0.30 on these same 655 stops (lot
jev114-recal), applied to the out-of-fold probabilities:

- among cuts 0.01 to 0.99, take the one with the most recall on unfinished stops;
- the block precision's 95 % Wilson lower bound must be at least 0.90;
- on a tie, take the lowest cut.

It reads labels only. At 0.09 the out-of-fold record is:

- 271 blocks, 254 of them right;
- 17 false blocks of 342 finished stops;
- 81 % of the 313 unfinished stops caught;
- accuracy 0.884.

**Why this rule and not maximum accuracy.** The two cuts compared against are Jev's operating
points. 1.14's 0.30 was set by this rule on these stops, and a false block costs the user a turn.

**Descriptive, not used.** The accuracy-maximising out-of-fold cut is 0.28. It gives accuracy
0.912, with 25 false blocks and 280 caught.

**Known when the rule was chosen.** The test set's label mix is published: 84 % done. A lower cut
blocks less, which helps on a done-heavy set. The rule was chosen to match Jev's derivation, not
for that mix.

## Dry run on TRAIN (out of fold; `train.py dry`, `dry.json`)

The whole evaluation pipeline was run on the 655. It compared the out-of-fold `p_local` with
Jev's recorded probabilities on the same stops. Jev's 0.30 was derived on half of these, so
Jev's row is partly in-sample.

| Arm | Right | False blocks (of 342) | Caught (of 313) | AUC |
|---|---|---|---|---|
| local at 0.09 | 579 (88.4 %) | 17 | 254 | 0.952 |
| Jev 1.14 at 0.30 | 615 (93.9 %) | 13 | 286 | 0.970 |
| Jev 1.13 at 0.5 | 616 (94.0 %) | 12 | 286 | 0.982 |

**Local minus 1.14:** −5.5 points, cluster interval [−10.5, −1.3]. 7 stops favour local and 43
favour 1.14 (exact McNemar p < 0.001). The rule below would read **"peor"** on TRAIN.

**Stated before any test score.** The classifier trails Jev by 5.5 points on its own suite,
before any shift. The test suites, agent and tool vocabulary differ. **The expected verdict on
the test set is "peor".**

The lot is still worth running:

- it is free;
- it is the first measured number for A10;
- a surprise in either direction is informative.

## Hypotheses and verdict rule (fixed now)

Every arm blocks when its p(done) is below its cut: local 0.09, Jev 1.14 0.30, Jev 1.13 0.5.
These are the cuts checkdone114 scored, written as constants in `a10_analysis.JEV_CUTS` and
pinned by a test against `policy.Thresholds`.

**Primary.** On the 950 stops, compare right decisions, **local minus Jev 1.14 at 0.30**. The
interval is a paired bootstrap over the **106 user-task clusters**, the unit checkdone114
registered: `l4_stats.paired_binary`, 10,000 replicas, seed 20261015.

- **"mejor"** if the interval's lower bound is above 0.
- **"no peor"** if the lower bound is above **−5 points** (the non-inferiority margin).
- **"peor"** if the lower bound is at or below −5 and the upper bound is below 0.
- **"no concluyente"** otherwise.

Also reported:

- the unclustered paired-bootstrap interval (`ci95`);
- exact McNemar p and the discordant counts.

**Secondary**, each reported, none changing the primary:

1. The same comparison against **Jev 1.13 at 0.5**, read by the same rule.
2. **False blocks.** Finished stops not falsely blocked, local minus each Jev arm, with the
   cluster interval. Jev's figures: 1.14 makes 150 false blocks of 795 and 1.13 makes 165.
3. **Catches.** Unfinished stops blocked, local minus each Jev arm, with the cluster interval.
4. **AUC** of p(done) for finished above unfinished. Each arm's rank AUC and the paired cluster
   bootstrap of the difference (`lot_stats.paired_auc`, 2,000 replicas).
5. Per arm: accuracy, false-block rate and catch rate with Wilson 95 % intervals, and block
   precision; also by suite.

**Missing values.** None are expected: Jev answered all 950 in both versions. A row without a
probability stops the analysis.

## Power at n = 950 (`power.py`, `power.json`)

**The setup.** The simulation uses checkdone114's cluster sizes (mean cluster size 12.5).

- It sets a true difference Δ (local minus 1.14) and a rate of stops where exactly one arm is
  right.
- Each cluster draws its own rate and win share, beta with intra-cluster correlation ρ.
- 150 simulations per cell; a cluster bootstrap of 400 replicas each.

**The plausible rate.** On TRAIN the two disagree on 7.6 % of stops. On the test it should be
higher: Jev itself is wrong on 21.6 % there. So 15-25 %.

| Δ | rate | ρ | P(no peor or mejor) | P(peor) | Half-width, simulated / analytic |
|---|---|---|---|---|---|
| 0 | 0.15 | 0 | 0.97 | 0.01 | ±2.4 / ±2.5 points |
| 0 | 0.15 | 0.3 | 0.72 | 0.02 | ±3.7 / ±5.2 |
| 0 | 0.25 | 0 | 0.85 | 0.01 | ±3.2 / ±3.2 |
| 0 | 0.25 | 0.3 | 0.52 | 0.03 | ±5.1 / ±6.7 |
| −2.5 | 0.15 | 0 | 0.45 | 0.52 | ±2.4 |
| −2.5 | 0.25 | 0.3 | 0.21 | 0.16 | ±5.1 |
| −5 | 0.15 | 0 | 0.01 | 0.97 | ±2.4 |
| −5 | 0.25 | 0.3 | 0.06 | 0.48 | ±5.1 |
| −10 | any | any | 0.00 | 0.97-1.00 | |

**The interval** will be about ±2.5 to ±5 points.

**At parity**, "no peor" comes out with probability 0.5 to 0.97, depending on clustering.

**What the margin allows.** A classifier truly 5 or more points behind reads "no peor" with
probability at most 0.06. A true deficit of 2.5 points, inside the margin, is about a coin toss
between "no peor" and "peor" when ρ is 0.

**What "peor" means here.** Under this rule it means the interval excludes parity and reaches
past the margin. It does not prove a deficit larger than 5 points.

## What this does not settle

- **Not a coding session.** These are AgentDojo stops, as in checkdone114.
- **One local model family.** It is trained on one suite and five pipelines of two Anthropic
  models. A model trained on public labels from the test's own suites could do much better. For
  example, the 1,572 stops of `../2026-10-16-checkdone-w17/`, which use other agents and the same
  suites and user tasks. That is a different question (transfer across agents, not across
  suites) and would need its own registration and an overlap rule by user task.
- **Jev may have seen the public test files**, as checkdone114 noted. The local model has not:
  it was fitted on the slack runs only.

## Sealing and running (the owner's steps)

1. Review this registration against the code with `revisor-prereg`, then remove "DRAFT" from the
   title.
2. Run `python benchmarks/a10_local/eval.py hash`. It hashes this file, `cv.json`, the model, the
   lot's code, the record builder and loaders, the statistics, and checkdone114's inputs, data
   seal and Jev rows (`eval.SEALED`).
3. Run `python benchmarks/a10_local/eval.py seal` once. It writes `prereg.sha256` and refuses to
   overwrite it.
4. Commit the seal on its own.
5. Run `python benchmarks/a10_local/eval.py run` from a worktree detached at the sealing commit.
   - It refuses before reading any test stop unless the seal matches.
   - It then checks the 950 stops against checkdone114's `data.sha256`.
   - It writes `scored.jsonl` (id, cluster, label, p_local; no text) and `analysis.json`.

## Reproducing what is here

```bash
python benchmarks/a10_local/train.py cv   [--runs-root CHECKOUT]   # cv.json, oof.jsonl (~10 min)
python benchmarks/a10_local/train.py fit  [--runs-root CHECKOUT]   # fixtures/a10_local/model.json
python benchmarks/a10_local/train.py dry                            # dry.json, TRAIN only
python benchmarks/a10_local/eval.py overlap                         # overlap.json, no scoring
python benchmarks/a10_local/power.py                                # power.json
python -m pytest tests/test_a10_local.py
```

The training runs are untracked. `--runs-root` points at a checkout that holds
`docs/results/2026-09-24-agentdojo-{e2e,haiku}/runs/`. Without them, `load_train` refuses: it
expects 655 stops, 342 of them done.
