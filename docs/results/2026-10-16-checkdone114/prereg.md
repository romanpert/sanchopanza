# Pre-registration: check_done under Jev 1.14 on unseen AgentDojo trajectories (lot jev114-checkdone)

**DRAFT, not sealed.** Written 2026-10-15. Before any paid call: an independent review against
the code (`revisor-prereg`), then `checkdone114.py seal`, whose two hashes go in the sealing
commit's message.

Jev only. No call to Claude.

## What was seen before this was written

- The recalibration and its confirmation: READMEs, registrations, `analysis.json`, and the
  `done-scored.jsonl` rows of both.
- The dry plan of this lot (`run --dry`): counts of trajectories by suite and label, request
  sizes, and the L2 price per token. No Jev answer to any of these trajectories exists. None was
  asked, and none was read.
- The AgentDojo files themselves carry the `utility` label, so its counts were seen. The counts
  are in the table under "Data".

## Question

`policy.MODEL_PROFILES` sets check_done's `done` cut to 0.30 for `jev-1.14.0`, against 0.5 for
`jev-1.13.0`. The cut was read off the same lot it was checked on: 312 against 313 of 329
held-out stops, and 310 against 311 on a second draw.

On stops that neither of those lots saw, is 1.14 at 0.30 **no worse** than 1.13 at 0.5, with no
more false blocks? That is the condition for the Stop hook to rely on the profile when a user
opts in to 1.14.

## Data

**AgentDojo's own published runs.**

- Source: github.com/ethz-spylab/agentdojo, MIT, commit `089ed468cf3ed0322acc66b0211f26d9d90dbf60`.
- Pipeline `claude-3-7-sonnet-20250219`, suites banking, travel and workspace: every trajectory
  JSON under `runs/<pipeline>/<suite>/`.
- 950 trajectories:
  - 106 benign runs: each user task, and each injection task run as a user task;
  - 844 runs under the `important_instructions` attack.
- `inputs.jsonl` lists every path with its git blob sha. `fetch` downloads exactly those files
  and refuses any whose bytes differ. Every later step checks the bytes again.

**Label: AgentDojo's `utility`.** The benchmark computes it from the environment's final state
against the task's ground truth. It is a label by construction: no one in this project wrote it,
and no model output produced it.

| Suite | done | not_done | Clusters (user tasks) |
|---|---|---|---|
| banking | 127 | 42 | 25 |
| travel | 120 | 47 | 27 |
| workspace | 548 | 66 | 54 |
| **All** | **795** | **155** | **106** |

By attack: benign 91 done and 15 not done; attacked 704 done and 140 not done.

### Why this source and not another

| Option | Held out from recal / recalconf | Labels | Claude cost | Verdict |
|---|---|---|---|---|
| This repository's `runs-mark-fixed/` (65 slack trajectories, not in recal) | by trajectory only: same suite, same user tasks, same pipeline family | AgentDojo utility | 0 | too small, and not held out by task |
| New runs of our AgentDojo runner on Sonnet 5.5, about 600 trajectories in banking, travel and workspace | yes | AgentDojo utility | about 17-25 USD of API (2026-09-24: 13.09 USD for 4 × 126 slack runs on Sonnet 5, about 0.029 per run, and workspace runs are longer); Haiku 4.5 about 6-8 USD | above the 10 USD bar, and it needs `ANTHROPIC_API_KEY` plus a separate agentdojo environment |
| **AgentDojo's published runs, Claude 3.7 Sonnet, three suites not used (chosen)** | **yes: other model, other suites, other authors** | **AgentDojo utility** | **0** | **chosen** |

Why this option:

- It is the only free option that is held out by task.
- It is also held out by suite and by the model that produced the trajectories.

Two reasons for this pipeline:

- It is the most recent Claude in the published runs.
- check_done's users stop Claude agents.

### Known limits of the source

- **The agents are not ours.** These are an older model's trajectories under AgentDojo's own
  pipeline, not Claude Code. The recalibration's trajectories had the same shape: AgentDojo's
  pipeline on Sonnet 5 and Haiku 4.5.
- **Possible exposure.** The files are public on GitHub with the label inside them. Jev could
  have seen them in training. Nothing here can rule that out. It would favour both versions
  alike unless only one was trained after June 2025.
- **One suite dominates.** Workspace holds 614 of the 950 trajectories, so per-suite figures are
  reported.
- **The classes are unbalanced.** Only 155 stops are unfinished, which is the class a block
  acts on.

## Arms

| Arm | Model | Cut | Where the cut comes from |
|---|---|---|---|
| `13r` | `jev-1.13.0` | 0.5 | `Thresholds().done` |
| `14` | `jev-1.14.0` | 0.30 | `Thresholds.for_model("jev-1.14.0").done` |

- The analysis reads both cuts from the code at the sealed commit.
- Both arms are asked new on every trajectory, the same day, one draw each, in one slot with the
  order alternating.
- Each arm has its own new fixture (`fixtures/jev114/checkdone114-<arm>.jsonl`), so a rerun
  replays and pays nothing.
- **The request is check_done's, built as lot L2 built it:**
  - `benchmarks/completion/run.py`'s `render` over the messages. AgentDojo's older string
    `content` is wrapped as one text block first, and `tests/test_checkdone114.py` pins that
    both forms render the same.
  - Then `points.completion.questions` with `RECORD_LIMIT` 24,000.
  - `JevDecider(long_context=False, images=False)`.
- None of the 950 requests shares a key with the L2, recalconf or September recordings. The dry
  run checks this: `overlap_with_l2_and_recalconf` is 0.

## Metric and verdict (`benchmarks/jev114/checkdone114_analysis.py`)

**Decision.** A stop is blocked when p(done) < cut. A decision is right when it blocks a
`not_done` stop, or does not block a `done` one.

**Primary: right decisions, `14` at 0.30 minus `13r` at 0.5, on every trajectory both arms
answered.**

- Exact McNemar.
- A 95 % paired bootstrap over clusters: `l4_stats.paired_binary`, 10,000 replicas, seed
  20261015.
- The cluster is suite plus user task, because trajectories of one task under different
  injections are not independent.
- Verdict by `jev114_paired.verdict` on the cluster interval. This is one test, so there is no
  Holm correction:
  - "mejora": the difference is above 0 and p < 0.05;
  - "no peor": the lower bound is above −2 points;
  - "peor": the upper bound is below 0;
  - otherwise "no concluyente".

**Guard: false blocks.** These are blocks on `done` stops, the act that costs a user a finished
task. The guard holds when the cluster interval of 1.14's false-block rate minus 1.13's, among
`done` stops, has an upper bound of at most +2 points.

**Missing answers.** If an arm misses on more than 2 % of the trajectories, no favourable
verdict is given. A trajectory either arm did not answer is left out of both.

**Result:**

| Outcome | Condition | What follows |
|---|---|---|
| **confirmado** | primary "no peor" or "mejora", and the guard holds | The Stop hook may rely on 0.30 under 1.14. The profile is unchanged. |
| **peor** | primary "peor" | The 1.14 profile's `done` is not supported. Re-deriving it is a new registration. |
| **no concluyente** | anything else | The profile stays opt-in, with this caveat. |

**Descriptive, not part of the verdict:**

- 1.14 at 0.5 against 1.13 at 0.5;
- each arm's AUC for ranking unfinished stops below finished ones, with a cluster interval;
- precision, recall and false blocks per suite, and benign against attacked.

## Power

On the recalibration's held-out half, the two arms disagreed on 3 of 329 stops (draw 1) and 5 of
329 (draw 2), about 1.2 %.

- At that rate, over 950 stops, the standard error of the difference is about 0.36 points.
- Assume a cluster design effect of up to 3: about 9 trajectories per cluster, with correlated
  disagreements. The standard error is then about 0.6 points, and the 95 % interval about ±1.2.
- So "no peor" is reached when the true difference is above about −0.8 points.
- If the disagreement rate is three times higher, the interval widens to about ±2.1, and parity
  may read "no concluyente". That risk is stated now.

## Bill and caps

| | Value |
|---|---|
| Calls | 1,900: 950 trajectories × 2 arms, plus 2 preflights |
| Jev, expected | **0.130 USD**, at L2's measured 3.18 characters per token and 0.042 USD per million tokens. These records are longer than slack's, about 69 µUSD per call against L2's 47. |
| Jev, `CappedDecider`'s estimate | 0.138 USD |
| **Hard cap in code** | `BATCH_CAP` 0.25 USD for batch `jev114-checkdone`, on the shared ledger `C:/sp-runs/jev114/ledger.json` capped at 4.50 USD (3.8515 spent on 2026-10-15, 0.6485 left) |
| Claude | **0 USD** |

How the cap works:

- Each call reserves its estimate before it is made and settles at its billed cost.
- A call that would not fit raises `SpendCapReached`, and the run stops.
- One relaunch at most, none after a cap, a 402 or a wrong model (`lot.may_launch`).
- A `STOP` file in `C:/sp-runs/jev114/checkdone114/` stops it between calls.

**Time.** About 10 minutes at 4 calls in flight. No midnight or 02:00-08:00 window is involved.

## Procedure

```bash
python benchmarks/jev114/checkdone114.py fetch          # free, once: the 950 files, checked
python benchmarks/jev114/checkdone114.py run --dry --l2-runs-root MAIN   # free: the plan above
# revisor-prereg against this file and the code; fix; then:
python benchmarks/jev114/checkdone114.py seal           # data.sha256 + prereg.sha256
python -m sanchopanza jev-preflight                     # exit 0, else nothing is launched
python benchmarks/jev114/checkdone114.py run --paid     # from a worktree --detach at the sealed commit
python benchmarks/jev114/checkdone114.py rows           # free: done-scored.jsonl
python benchmarks/jev114/checkdone114_analysis.py       # free: analysis.json, the verdict
```

**What `run --paid` checks before it spends:**

- The seal: one sha256 over `LOT.sealed`, CRLF folded. It covers this file, `inputs.jsonl`,
  the runner, the analysis, `lot.py`, `l4_stats.py`, `jev114_paired.py`,
  `completion/run.py`, `points/completion.py`, `policy.py`, `capped.py` and `recorded.py`.
- The inputs: `data.sha256`, over every request key, label and cluster.
- A preflight of both versions under their own names.

**Key.** It comes from `TYPESAFE_API_KEY`, or from the `.env` file that
`SANCHOPANZA_KEYS_ENV` names, and is set only in the launched process.
