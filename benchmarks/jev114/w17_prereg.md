# Pre-registration (DRAFT): check_done's record with the evidence kept (lot jev114-checkdone-w17)

**Draft, not reviewed, not sealed.** Written 2026-10-16. Before the seal:

1. `revisor-prereg` reviews it against the code.
2. It moves to `docs/results/2026-10-17-checkdone-w17/prereg.md`, the path `LOT.sealed` names.
3. `checkdone_w17.py seal` writes `prereg.sha256` and `data.sha256`. The sealing commit adds
   those files and nothing else.

Nothing in this lot has been asked of Jev. Jev only, no call to Claude. **An attended launch of
about 10 minutes.**

## What was seen before this was written

- The checkdone114 lot: README, registration, `analysis.json`, `done-scored.jsonl`, and its
  950 trajectories. That includes reading the false blocks the fix was designed on.
- The development figures below. They come from checkdone114's recorded 1.14 answers and from
  the new builder's records, free.
- For the two confirmation pipelines, before they were chosen: the dry plan's counts by
  pipeline, label and whether the builder changes the record. AgentDojo's files carry
  `utility`, so the label counts were seen. **No Jev answer to any confirmation stop exists,**
  and none was read.

## Question

check_done is the Stop hook's question "is this task finished?". On checkdone114's 950 unseen
AgentDojo stops, 1.14 at 0.30 blocked 150 of 795 finished stops.

- 115 of those 150 false blocks have a tool result longer than the 1,500 characters the record
  keeps of each result.
- The agent answered from the whole result, and the judge saw an answer it could not check.

`points.done_evidence` keeps each result's head as before. Past it, it adds short windows around
the values the agent wrote afterwards: numbers, ids, dates and times, addresses, file names,
quoted strings and capitalised names. It searches the agent's text and the arguments of its
later actions, and adds at most 1,500 more characters per result.

- It looks for at most 100 values per result. The agent's text comes first, its final answer
  before the rest, then the arguments of its actions.
- Each value is placed at its first whole occurrence past the head, rarest first: at most 50
  places are counted. A value is "visible" only when it appears whole inside the head.

**On stops no lot has read, does the new record make fewer false blocks on finished stops,
without catching fewer unfinished ones?** That is the condition for turning
`SANCHOPANZA_DONE_EVIDENCE` on by default for the Stop hook.

## Development (checkdone114's 950 stops, free, not part of the verdict)

`python benchmarks/jev114/checkdone_w17.py dev`, with 1.14 at 0.30 on the old record:

| Stops | n | A result cut | Record changed by the builder | Ceiling: a value the agent wrote is past the cut and nowhere visible | New record shows some / all of those values |
|---|---|---|---|---|---|
| finished, blocked (false blocks) | 150 | 115 | 110 | **87** | 87 / 76 |
| finished, passed | 645 | 278 | 68 | 51 | 51 / 46 |
| unfinished, blocked | 100 | 62 | 51 | 38 | 38 / 35 |
| unfinished, passed | 55 | 40 | 29 | 24 | 24 / 12 |

**Reading the table:**

- **The ceiling of the fix is 87 of the 150 false blocks.** In those 87, a value the agent wrote
  after its first cut result appears in a result only past the cut, and not in the task or any
  kept head. Counted on the agent's final answer alone, it is 80.
- A looser count that also matches values inside longer ones finds 100. The 87 uses the
  builder's own matching, which is stricter.
- The builder changes 258 of 950 records. A changed record grows by 859 characters at the median,
  4,088 at most. All 950 requests together grow by 8.5 %.
- The old records are byte for byte the ones checkdone114 asked: `checkdone114.py rows` replays
  all 950 from its recordings unchanged.

**What this does not show:**

- The values being visible does not mean the judge will accept the answer.
- Questions like "the largest file" also need the other files' sizes. A window shows the
  named file, not that the rest are smaller.

## Data: the confirmation

**AgentDojo's own published runs:**

- github.com/ethz-spylab/agentdojo, MIT, commit `089ed468cf3ed0322acc66b0211f26d9d90dbf60`;
- suites banking, travel and workspace;
- the two pipelines no lot has read whose agents are closest to the product: `claude-3-5-sonnet-20241022`, the
  newest Claude there besides checkdone114's 3.7, and `gemini-2.0-flash-001`, the other pipeline
  run on the same suite versions as checkdone114 (workspace with 614 runs);
- `benchmarks/jev114/w17_inputs.jsonl` lists every path with its git blob sha: 1,572
  trajectories.

`fetch` downloads exactly those files and refuses any whose bytes differ, and every later step
checks the bytes again.

**Label: AgentDojo's `utility`,** computed by the benchmark from the environment's final state.

| Pipeline | done (changed) | not_done (changed) |
|---|---|---|
| claude-3-5-sonnet-20241022 | 476 (79) | 146 (20) |
| gemini-2.0-flash-001 | 352 (62) | 598 (62) |
| **All** | **828 (141)** | **744 (82)** |

- **Clusters:** 106 user tasks, pooled across the two pipelines. The same task asked of two
  agents is not two independent draws.
- **Identical requests.** 1,572 stops make 1,156 distinct old requests: where an agent never
  read the injected tool output, the runs of one user task under different injections are the
  same transcript. No two stops sharing a request disagree on the label. One answer serves
  every stop with that request.

**Why fresh stops.** The 950 checkdone114 stops are where the problem was found and the builder
was designed: its anchors, radius and budget were read on them. A confirmation on them would
grade the fix on its own training data. They are asked only for their changed records and
reported as development.

## Arms

| Arm | Record | Model | Cut |
|---|---|---|---|
| `old` | `completion/run.py` `render(messages)`: each tool result's first 1,500 characters, as every earlier lot | `jev-1.14.0` | 0.30 |
| `new` | `render(messages, evidence=True)`: `done_evidence.record`, the same function the Stop hook calls with `SANCHOPANZA_DONE_EVIDENCE=1` | `jev-1.14.0` | 0.30 |

The cut is read from the code: `Thresholds.for_model("jev-1.14.0").done`, the shipped profile.

**How each request is asked:**

- **Each distinct request once** (`checkdone_w17.requests`):
  - both records of every confirmation stop;
  - the new record of every changed development stop. Its old answer is checkdone114's
    recorded 1.14 answer, the same request byte for byte.
  - A stop whose two records are the same request has one answer serving both arms. The builder
    did not touch that request, so the arms cannot differ there by construction.
- **1,633 requests:** 1,156 confirmation old, 221 confirmation new, 256 development new.
- One draw each, in the registered shuffled order (`lot.shuffled`, seed 20261016), at most 4
  in flight, through `CappedDecider` on the shared `SpendLedger`.
- Recordings go to `C:/sp-runs/jev114/checkdone-w17/checkdone-w17-14.jsonl`, outside the
  worktree. A relaunch replays them and pays nothing. `publish` copies them to `fixtures/jev114/`.
- The two requests of one stop are separate cases in the shuffled order, so they may or may not
  be in flight together. Jev is pinned to one version, and draw-to-draw noise is about 1.8 % of
  decisions (recalconf).
- **No request shares a key with any earlier check_done recording** (L2, recalconf, September,
  checkdone114): the dry run shows `overlap_with_earlier_recordings` 0.

**The request** is check_done's: `points.completion.questions`, `RECORD_LIMIT` 24,000,
`JevDecider(long_context=False, images=False)`.

- When the new record would pass the record limit and the old one does not, the builder returns
  the old one (`done_evidence.record(limit=...)`), so the windows never push out the request or
  the final answer.
- 4 confirmation records reach the limit. Above it, the bench keeps the record's head
  (`text.truncate`, as every earlier lot) and the Stop hook keeps its tail. For those 4 records
  the two arms read the same head-cut shape, and the hook would read another one. That
  difference predates this lot.

**Reading an answer.** Through `Decision.answer` (`usable`). A NaN or an absent answer is a
missing answer, never a "do not block".

## Metric and verdict (`benchmarks/jev114/checkdone_w17_analysis.py`)

**Decision.** A stop is blocked when p(done) < 0.30.

**Primary: false blocks on the confirmation's 828 finished stops.**

- The measure is "not falsely blocked", new record minus old, on every finished stop both arms
  answered.
- Exact McNemar on the items, unclustered.
- A 95 % paired bootstrap over user-task clusters: `l4_stats.paired_binary`, 10,000 replicas.
- Verdict by `lot_stats.verdict_of`:
  - "mejora": the difference is above 0, p < 0.05, **and** the cluster interval's lower bound is
    above 0;
  - "no peor": the lower bound is above −2 points;
  - "peor": the upper bound is below 0;
  - otherwise "no concluyente".

**Guard: catching unfinished stops,** on the confirmation's 744 unfinished stops. It compares
the blocks among them, new minus old. **The guard holds when the cluster interval's lower bound
is at least −2 points.**

**No verdict unless the last launch completed** (`launches.jsonl` ends in `complete`). A launch
paused on a 402 is not complete.

**Missing answers withhold a favourable verdict** when either of these holds:

- more than 2 % of confirmation stops lack an answer in either arm;
- the new arm leaves more than 2 points more unanswered than the old one.

**Result:**

| Outcome | Condition | What follows |
|---|---|---|
| **confirmado (mejora)** | launch complete, primary "mejora", guard holds, answers within limits | `SANCHOPANZA_DONE_EVIDENCE` defaults to on for the Stop hook. |
| **no se adopta** | primary "mejora", guard fails | Stays opt-in. The recall loss is reported. |
| **no peor / no concluyente** | anything else that is not "peor" | Stays opt-in, with the result as its caveat. |
| **peor** | primary "peor" | Stays opt-in. The builder is revisited on development data. |

**Descriptive, declared now, not part of the verdict:**

- right decisions on all confirmation stops, new minus old;
- AUC of each arm, with a cluster interval;
- changed stops only;
- per pipeline and per suite;
- without hijacked runs (`security` true);
- both arms at 0.5;
- **development:** the same figures on checkdone114's 950. Old = its recorded answers, new = the
  new records of the 258 changed stops.

## Power (free: `checkdone_w17.py run --dry`)

**The simulation.** Only changed stops can differ (141 finished, 82 unfinished). The simulation
draws by cluster, with the lot's real cluster sizes:

- each cluster draws its rates from beta distributions with intra-cluster correlation 0.3;
- each simulated lot is scored by the registered rule on a 500-replica cluster bootstrap;
- 300 simulated lots per setting.

**The assumed rates:**

- On a changed finished stop, the old record blocks with q = 0.618, development's share
  (110 of 178).
- The new record lifts a share f of those blocks, and turns 5 % of the old passes into blocks.
- On a changed unfinished stop, the old record catches with k = 0.637 (51 of 80).
- The new record lets a share h of those through, and catches 5 % of the old misses.

| f (blocks lifted) | 0.1 | 0.2 | 0.3 | 0.5 |
|---|---|---|---|---|
| P(primary "mejora") | 0.23 | 0.70 | 0.96 | 1.00 |

| h (catches lost) | 0.05 | 0.1 | 0.2 | 0.3 |
|---|---|---|---|---|
| P(guard holds) | 1.00 | 0.84 | 0.25 | 0.03 |

**Reading:**

- If the new record lifts a fifth or more of the false blocks it touches, the lot sees it.
- If it lets a fifth or more of the touched catches through, the guard fails. That is the
  intended reading, not a lack of power.
- A lift of a tenth is not detectable here.

## Cost and cap

- **Price per character, from checkdone114's own bill:** its 950 1.14 requests cost
  1.39 × 10⁻⁸ USD per request character. That is a median of 65 µUSD a request at 5,189
  characters on average.
- **Expected for the 1,633 requests:** 0.130 USD. Scaling the 71 µUSD median of a real request
  by these requests' size gives 0.128 USD. `CappedDecider`'s pessimistic estimate is 0.131 USD.
- **Cap:** `BATCH_CAP` 0.25 USD in code, batch `jev114-checkdone-w17`, on the shared ledger
  `C:/sp-runs/jev114/ledger.json`.
  - That ledger has its own 4.50 USD cap; 4.0163 USD was spent at the dry run, leaving 0.48 USD.
  - Either cap stops the run between calls. The run halts on the first cap, 402 or wrong model.
- `python -m sanchopanza jev-preflight` runs before the launch. Claude: 0.

## Launch

1. Seal; then `git worktree add --detach ..\sanchopanza-run-checkdone-w17 <seal commit>`.
2. Copy `checkdone-w17-run.cmd` to `C:\sp-runs\jev114\checkdone-w17\` and fill PY,
   SANCHOPANZA_KEYS_ENV and WT there. Run the filled copy with `dry` first.
3. Launch the filled copy by WMI (CreateFlags 512), outside any Claude Code session.
4. Watch the log and the PID. A STOP file in the run folder stops it between calls. Kill only
   by verified PID.
5. `publish`, `rows`, `checkdone_w17_analysis.py`.

The dry run ran end to end on 2026-10-16, through the runner and through a filled copy of the
launcher in dry mode, both exit 0: "nothing asked; a paid launch now would be allowed after the
seal". The runner's dry run and `dev` were run again after the last change to
`done_evidence.py`, and every figure in this draft is from that run.

## Known limits

- **Other agents.** These are AgentDojo pipelines of older models, not Claude Code sessions.
  The builder is the one the hook uses, but Claude Code's tool outputs (file reads, shell) are
  not measured here.
- **The anchors were designed on the development stops.** The confirmation is the only clean
  read.
- **Possible exposure.** The files are public with their labels.
- **One question example copies banking `user_task_0`,** as in checkdone114.
- **Selection of the confirmation pipelines** was made after seeing their label and
  changed-record counts. No Jev answer to them existed.
- **Dilution.** The primary and the guard are rates over all finished and all unfinished stops,
  and unchanged stops contribute no difference. The changed-only figures are reported beside
  them.
