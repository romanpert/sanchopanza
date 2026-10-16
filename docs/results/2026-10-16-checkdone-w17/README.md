# check_done's record with evidence windows on unseen AgentDojo stops: fewer false blocks, but it lets unfinished work through, so it is not adopted

Jev only, no call to Claude. `jev-1.14.0` at its shipped `done` cut of 0.30 was asked live on
2026-10-16 about two records of the same stops:

- `old`: the record every earlier lot asked about, with each tool result cut to its first 1,500
  characters (`completion/run.py`, `render(messages)`);
- `new`: the same record with `points.done_evidence`, which keeps each result's head and adds
  short windows around the values the agent wrote afterwards (`render(messages, evidence=True)`,
  the function the Stop hook calls with `SANCHOPANZA_DONE_EVIDENCE=1`).

The stops are 1,572 that no lot had read: AgentDojo's own published runs of
`claude-3-5-sonnet-20241022` and `gemini-2.0-flash-001`.

**The seal.** Pre-registered in `prereg.md`, sealed by `prereg.sha256` (`ea6c686a…`, one hash
over `prereg.md`, the inputs, the launcher and the code). The stops are fixed in `data.sha256`
(`a1032f27…`).

- The sealing commit `1f83f8b` adds those two files and nothing else, on top of `9e4254a`.
- Before sealing, `revisor-prereg` reviewed the registration against the code. Its title and
  opening still read "DRAFT": they are part of the sealed text, so they stay as written.

## Verdict

**"no se adopta (la guarda no se sostiene)" by the sealed rule.** `SANCHOPANZA_DONE_EVIDENCE`
stays opt-in.

- **The primary improves.** On the 828 finished stops, the new record makes **123 false blocks
  against 165**.
  - Not falsely blocked: 85.1 % against 80.1 %, **+5.07 points, [+1.53, +9.77]** with user tasks
    as the resampling unit.
  - 43 stops favour the new record and 1 the old, exact McNemar p ≈ 5e−12 (unclustered).
  - That is "mejora": above 0, p < 0.05 and the cluster interval's lower bound above 0.
- **The guard fails.** On the 744 unfinished stops, the new record catches **583 against 598**.
  - **−2.02 points, [−5.37, +0.26]**: the lower bound is below the registered −2.
  - 18 unfinished stops the old record blocked now pass, and 3 go the other way (p 0.0015).
- **Answers and launch.** Every stop has an answer in both arms (0 missing), and the launch
  completed.

## What ran

| | |
|---|---|
| Stops | 1,572: `claude-3-5-sonnet-20241022` 622, `gemini-2.0-flash-001` 950; banking 338, travel 334, workspace 900; 106 user-task clusters |
| Labels | AgentDojo's `utility`: 828 done, 744 not done |
| Records the builder changes | 223 of 1,572 (141 finished, 82 unfinished). On the other 1,349 both arms are one request and cannot differ. |
| Requests | 1,633, each asked once: 1,156 confirmation old, 221 confirmation new, 256 development new; plus the preflight. All answered in pass 1, none missing. |
| Launch | one, by WMI, from a worktree detached at `1f83f8b`; 16:54:08 to 17:00:10, exit 0; the preflight was served by `jev-1.14.0` |
| Order | the registered shuffle (seed 20261016), at most 4 in flight |

## Results

**The arms**, all 1,572 confirmation stops, cut 0.30:

| Arm | Right | False blocks (of 828 finished) | Caught (of 744 unfinished) | Precision of a block |
|---|---|---|---|---|
| `old` | 1,261 | 165 | 598 | 0.784 |
| **`new`** | **1,288** | **123** | **583** | 0.826 |

**The registered comparisons, new minus old:**

| Comparison | Difference | 95 % interval, user-task clusters | new only / old only | Reading |
|---|---|---|---|---|
| **Primary: finished stops not falsely blocked** (828) | **+5.07 points** | **[+1.53, +9.77]** | 43 / 1 | **mejora** |
| **Guard: unfinished stops caught** (744) | **−2.02 points** | **[−5.37, +0.26]** | 3 / 18 | **fails** (lower bound below −2) |

**Descriptive, as registered:**

| | Difference, new minus old | 95 % interval by cluster | Note |
|---|---|---|---|
| Right decisions, all 1,572 | +1.72 points | [−0.51, +4.18] | 46 / 19, p 0.0011 |
| Changed stops only (223) | +12.1 points | [−3.2, +28.6] | right 127 → 154; false blocks 72 → 30 of 141; caught 58 → 43 of 82 |
| Without the 67 hijacked runs (`security` true), 1,505 | +2.33 points | [+0.20, +4.98] | false blocks 161 → 119 of 800; caught 579 → 572 of 705 |
| Both arms at 0.5 | +1.59 points | [−0.77, +4.24] | false blocks 200 → 155; caught 623 → 603 |
| AUC for ranking unfinished below finished | 0.875 against 0.865 | +0.010 [−0.002, +0.023] | |

**By pipeline:**

| Pipeline | Right (old / new) | Difference, cluster interval | False blocks (old / new) | Caught (old / new) |
|---|---|---|---|---|
| `claude-3-5-sonnet-20241022` | 485 / 509 of 622 | +3.86 [+0.71, +7.78] | 89 / 63 of 476 | 98 / 96 of 146 |
| `gemini-2.0-flash-001` | 776 / 779 of 950 | +0.32 [−2.78, +3.29] | 76 / 60 of 352 | 500 / 487 of 598 |

**By suite:**

| Suite | Right (old / new) | False blocks (old / new) | Caught (old / new) |
|---|---|---|---|
| banking | 258 / 258 of 338 | 71 / 71 of 204 | 125 / 125 of 134 |
| travel | 274 / 270 of 334 | 9 / 8 of 140 | 143 / 138 of 194 |
| workspace | 729 / 760 of 900 | 85 / 44 of 484 | 330 / 320 of 416 |

The builder changes nothing in banking. Its gain is in workspace, where tool results run long:
42 of the 43 finished stops it unblocks are there.

## Development: checkdone114's 950 stops (descriptive, not part of the verdict)

The builder's anchors, radius and budget were read on these stops, so they are not a clean read.
Old = checkdone114's recorded 1.14 answers; new = the new records of the 258 changed stops, asked
in this launch.

| | Old | New | Difference, cluster interval | new only / old only |
|---|---|---|---|---|
| Right, of 950 | 745 | 789 | +4.63 points [−1.23, +11.11] | 80 / 36 |
| False blocks, of 795 finished | 150 | **73** | not falsely blocked +9.69 [+3.68, +17.13] | 78 / 1 |
| Caught, of 155 unfinished | 100 | **67** | −21.29 [−35.22, −7.87] | 2 / 35 |

The registration put the fix's ceiling at 87 of the 150 false blocks (a value the agent wrote
lies past the cut and nowhere visible). The new record lifts 78. On the same stops it lets 35 of
the 100 caught unfinished stops through: the guard's failure was already larger here than on the
fresh stops.

## What the guard's failure is

Read from `done-scored.jsonl`. The case-by-case reading below was done on the machine, post
hoc, and no text is published.

- **18 unfinished stops change from blocked to passed**, all with a changed record:
  - 16 from `gemini-2.0-flash-001` and 2 from `claude-3-5-sonnet-20241022`;
  - 13 in workspace and 5 in travel;
  - 8 of them are hijacked runs, where the agent also did the injected task.
- **They are not near the cut.** The old record gave them 0.05 to 0.29. The new one gives 0.31
  to 0.88, and 15 of the 18 would pass at 0.5 too.
- **One task makes most of them.** 10 of the 18 are `gemini-2.0-flash-001` on workspace
  `user_task_19`: two tasks in a row, counting and summarising the day's appointments, then doing
  the actions listed in an email. 2 more are `user_task_13`, that email's actions alone.
- **What the windows show.** They put in view the values the agent quoted from long results, so
  the parts of the answer that rest on those values now check out. They do not show that every
  part of the task was done, and AgentDojo's checker scores these stops as not done.
- **The two stops whose records pass the request limit** (`gemini-2.0-flash-001`, workspace
  `user_task_29`) are blocked by both arms and play no part in the loss.

**What the power table said.** Among changed stops, the new record lifts 43 of the 72 false
blocks (60 %) and lets 18 of the 58 catches through (31 %). The registration's simulation gave
P(guard holds) 0.03 at a loss of 0.3. This is the failure the guard was there to catch, not a
lack of power.

## What this means for the product

- **`SANCHOPANZA_DONE_EVIDENCE` stays opt-in.** The Stop hook's default record is unchanged.
- **The fix works on what it was built for.** On unseen stops it removes a quarter of the false
  blocks (165 → 123), almost all in workspace, where long tool results were cut.
- **It costs catches.** Passing an unfinished stop is the error the Stop hook exists to prevent:
  the agent stops with work left. Losing 15 of 598 catches overall, and 18 of the 58 the changed
  records held, is what keeps it opt-in.
- **Next proposal.** Diagnose the lost catches on the development stops, where the loss is
  larger (35 of 100) and reading them costs nothing, starting with multi-part tasks like
  workspace `user_task_19`. Change the builder there, measure on development, and confirm on
  stops no lot has read under a new registration.

## Bill

| | |
|---|---|
| Jev, ledger (input tokens × list price) | **0.1283 USD** for batch `jev114-checkdone-w17`, median 68 µUSD a request. Expected 0.130 at the registration; cap 0.25. |
| Shared ledger | 4.0163 → 4.1446 of 4.50 USD |
| Claude | 0 |

## Not done

- **A second draw.** One draw per request. Recalconf found 1.14 flips about 1.8 % of decisions
  between draws.
- **Claude Code sessions.** These are AgentDojo pipelines of older models. The builder is the one
  the hook uses, but Claude Code's own tool outputs (file reads, shell) were not measured.
- **The known limits stand, as registered:**
  - the files are public with their labels, so Jev may have seen them;
  - one of the question's own examples copies banking `user_task_0`;
  - the two confirmation pipelines were chosen after seeing their label and changed-record
    counts, before any answer existed.

## Reproducing

```bash
python benchmarks/jev114/checkdone_w17.py fetch            # the 1,572 public files, checked by blob sha
python benchmarks/jev114/checkdone_w17.py rows             # replays fixtures/jev114/checkdone-w17-14.jsonl
python benchmarks/jev114/checkdone_w17_analysis.py         # analysis.json
python benchmarks/jev114/checkdone_w17.py dev              # the development ceiling, free
python -m pytest tests/test_checkdone_w17.py
```

`rows` also reads checkdone114's 950 stops and its recorded 1.14 answers for the development set.

## Files

- `prereg.md`, `prereg.sha256`, `data.sha256`: the sealed registration and stops.
- `benchmarks/jev114/w17_inputs.jsonl`: the 1,572 AgentDojo paths and their git blob shas.
- `launches.jsonl`: the one launch, with HEAD and HEAD^ and the recording's line count.
- `done-scored.jsonl`: per stop (1,572 confirmation and 950 development), its path in
  AgentDojo's repository, pipeline, suite, cluster, attack, `security`, label, whether the
  builder changed the record, and both probabilities. No text.
- `analysis.json`: every number above but the post-hoc counts, which `done-scored.jsonl` gives.
- `fixtures/jev114/checkdone-w17-14.jsonl`: the 1,633 answers, under hashed keys. No text.
