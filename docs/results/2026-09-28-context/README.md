# Pruning a coding agent's context by decision: negative on its registered criteria

Pre-registered in `prereg.md` (hash in `prereg.sha256`, pinned by
`tests/test_context_bench.py`), with Amendment 1 written before any decider call. The
question: at compaction, does `Squire.prune_context` (rules, then one in-context Jev decision,
stubs archived) keep more of what the rest of the trajectory used than the fast-jev-compaction
replica and than observation masking (M = 10, arXiv:2508.21433), **while freeing at least as
much**?

**No.** All four registered criteria fail. The decision arm keeps far more of what the future
used than any baseline (80 % against 9-19 %), but it does so by freeing far less (25 % against
69-82 %), and the registered comparison was at equal or higher freed fraction. The diagnosis
below says why: on this question, Jev barely separates needed from unneeded results (AUC 0.57
on test), so the decision adds little to the rules. The fast-jev replica fails worse: it frees
81 % and keeps 9 % of what was needed, the same as clearing all but the last three results.

## Data

40 trajectories of `nebius/SWE-rebench-openhands-trajectories` (CC-BY-4.0, revision
`35455389`; OpenHands v0.54.0 with Qwen3-Coder-480B on real GitHub issues), sampled with seed
20260928 from 300 downloaded rows; 15 dev, 25 test. History = up to 60 % of each trajectory's
characters; 1,846 history tool results (730 dev, 1,116 test). NEEDED (the future's assistant
text or tool inputs use a distinctive token found only in that result): 10.6 % dev, 11.9 %
test. Why public data and a lower size floor: Amendment 1.

## Results on the 25 test trajectories

95 % intervals: percentile bootstrap over trajectories. "Recoverable": needed results stubbed
with the full text archived and named in the stub. "Token recall" (secondary, Amendment 1):
share of the future's used tokens still present in some kept result.

| arm | freed | recall of NEEDED | needed lost (of 133) | recoverable | token recall | Jev calls | USD |
|---|---|---|---|---|---|---|---|
| keep_all | 0 % | 100 % | 0 | - | 100 % | 0 | 0 |
| last_3 (API `clear_tool_uses` default) | 82.1 % [77.2, 86.9] | 9.0 % [5.2, 13.2] | 121 | 0 | 15.1 % | 0 | 0 |
| mask_10 (arXiv:2508.21433) | 69.5 % [63.0, 76.2] | 18.8 % [13.0, 25.4] | 108 | 0 | 23.8 % | 0 | 0 |
| rules only | 19.6 % [14.8, 24.5] | 85.7 % [79.5, 91.9] | 19 | 19 | 98.8 % | 0 | 0 |
| fastjev replica (0.5) | 81.2 % [76.2, 86.1] | 9.0 % [5.2, 13.2] | 121 | 0 | 15.1 % | 75 (all 40) | 0.042 |
| sanchopanza (cut 0.00) | 25.3 % [18.2, 33.7] | 79.7 % [70.0, 88.3] | 27 | 27 | 92.4 % | 48 (all 40) | 0.034 |

Dev (15 trajectories, 77 needed): fastjev 81.4 % freed, 10.4 % recall; sanchopanza 41.3 %
freed, 62.3 % recall; rules 20.5 % freed, 87.0 % recall; mask_10 78.2 % / 16.9 %.

### The registered criteria

- **Cut derivation: missed.** No cut reached 95 % dev recall; the registered fallback, 0.00,
  was used (dev recall 62.3 % at 41.3 % freed). Why no cut could reach it is in the diagnosis.
- **P1 (vs fastjev): fails, on the freed side.** Recall difference +70.7 points [61.2, 78.9],
  needed results kept only by sanchopanza 94, only by fastjev 0 (McNemar p < 0.001). But
  sanchopanza frees 55.9 points **less** [-64.5, -46.4] and frees at least as much in 0 of 25
  trajectories. The criterion asked for more recall at an equal or higher freed fraction.
- **P2 (vs mask_10): fails, on the freed side.** Recall +60.9 points [50.4, 70.4]; freed 44.2
  points less [-54.0, -34.3]; at least as much freed in 1 of 25.
- **P3 (sanchopanza test recall >= 90 %): fails.** 79.7 % [70.0, 88.3].
- **P4 (rules free >= 20 % at recall >= 95 %): fails.** 19.6 % freed at 85.7 %. Every needed
  result the rules stubbed is recoverable, and token recall is 98.8 %: what they stub is mostly
  a read superseded by a later read of the same file, whose tokens are still in the later one.

Against rules alone (not a registered criterion): sanchopanza frees 5.7 more points
[0.0, 13.9] and loses 8 more needed results [recall -6.0 points, CI -16.3 to 0.0].

## The fast-jev replica

At its own cut of 0.5 it frees as much as the API's last-three clearing and keeps exactly as
little of what the future used (121 of 133 needed results lost on test, none recoverable:
the replica drops or truncates, as the original does). Its result question separates needed
from unneeded no better than chance (AUC 0.56 [0.50, 0.62] test, 0.53 [0.42, 0.64] dev); the
few results it gave p >= 0.75 were all unneeded ones (29 dev, 16 test).

## Diagnosis (replay of the recordings, no new calls: `benchmarks/context/diagnose.py`)

The replay matched every recorded decision (0 unanswered, same 0.076 USD). Figures in
`diagnosis.json`.

- **Jev's probabilities on our prune question are compressed and barely ranked.** Of the 553
  results asked on test, none got p >= 0.5; 98 % are below 0.25 (95 of 99 needed, 449 of 454 unneeded).
  AUC of p against NEEDED: **0.57 [0.50, 0.65] test, 0.61 [0.51, 0.69] dev.**
- **Where the needed results were lost** (test / dev): rules 19 / 10 (`read_superseded` 15 / 7,
  `command_repeated` 4 / 3), the tournament's first round 8 / 19, the final cut 0 / 0.
- **Why the derived cut is 0.00.** `context_keep` only acts on the final round, and at 0.00 it
  stubs nothing. The losses come before it: the rules (10 on dev) and, in the 4 dev and 2 test
  trajectories with more than 30 candidates, the first round at `FIRST_ROUND_CUT = 0.25`, which
  eliminates nearly every candidate because nearly every p is below 0.25 (19 needed on dev).
  Those two stages alone put dev recall at 62 %, so no value of `context_keep` could reach 95 %.
  In trajectories with 30 or fewer candidates (one call), the arm at cut 0.00 keeps everything
  the rules left: there, the decision changes nothing.
- **What the probability would buy at a higher cut.** With AUC near 0.6 and the needed and
  unneeded distributions nearly on top of each other, any cut stubs needed results about as
  fast as unneeded ones (below p = 0.10: 27 % of needed and 29 % of unneeded results on test).

A hypothesis, not measured: each candidate is shown as a 700-character head and tail of a
result that averages several thousand characters, and the question asks about "a fact that
appears only in" that output. Jev may not see the facts the future used.

## Amendment 2: the autopilot's arrival cut and recall, simulated (2026-09-28)

Registered in `prereg.md`, Amendment 2, before any decider call of these runs; registered cuts,
none derived; criteria on the 25 test trajectories, dev as a sanity check. `jev-1.13.0`, one
event loop per run, every call counted: 236 arrival and 936 recall decisions, **0 failed,
0 empty, 1 event loop each: both runs complete.** Figures in `simulate-arrival.json` and
`simulate-recall.json`; `benchmarks/context/simulate.py`, `baselines.py`, `criteria.py`.

**Arrival: negative (A1 and A2 fail; A3 holds only because almost nothing was cut).** Of the
109 test results at or above the 6,000-character gate, the cut changed 10. For the others
the decider kept so many blocks that the saving was under the 20 % minimum, and the result
passed whole (152 of 169 on both splits; 3 more where it kept no block).

| test, results >= gate (109; 42 NEEDED) | saving | NEEDED with every used token kept | token retention |
|---|---|---|---|
| arrival (registered defaults) | 3.7 % [1.4, 6.7] | 95.2 % [88.6, 100] | 98.0 % |
| head+tail, same characters per result | same | 97.6 % [92.1, 100] | 99.0 % |
| BM25 blocks, same characters | same | 97.6 % | 99.0 % |
| random blocks, same characters | same | 97.6 % | 99.0 % |

- **A1 fails**: token retention arrival minus head+tail -1.0 point [-2.8, 0.0]. At these
  savings every baseline kept as much or more.
- **A2 fails**: 3.7 % saved, against the registered 40 %.
- **A3 holds**: 95.2 % of NEEDED results keep every used token. With 2 of 42 NEEDED results
  cut, it measures the pass-through, not the cut. The 2 that lost a token are recoverable
  from the archive.
- Dev agrees: 4 of 60 cut, 2.4 % saved, 96.3 % all-kept, head+tail 100 %.

**Recall: R1 fails on the characters side; the audit is clean.** Leakage audit 0 on both splits.

| test (25 trajectories, 108 NEEDED masked results) | hit rate | hits | injected characters |
|---|---|---|---|
| Jev recall (BM25 top 5, one in-context call) | **70.4 %** | 76 | 972,244 |
| BM25@1 | 43.5 % | 47 | 897,916 |
| BM25@3 | 68.5 % | 74 | 1,054,503 |

- **R1 fails**: the hit rate is 26.9 points higher than BM25@1's [13.1, 40.0], but the Jev
  recall injected 8.3 % **more** characters, and the criterion required no more.
- **R2 (descriptive)**: against BM25@3, +1.9 points [-6.1, 9.1] at 7.8 % fewer characters: the
  same hits for slightly less text, not a detectable difference in hits.
- Dev: 71.9 % against 28.1 % (BM25@1) and 65.6 % (BM25@3).

**Cost**: 0.081 USD arrival, 0.073 USD recall, 0.154 USD together, against the registered
ceiling of 0.60 (estimate: 0.128 and at most 0.148). Recordings in
`~/.cache/sanchopanza/context/recordings-autopilot/` for free replay.

## What this does not settle

- **The label is a lexical proxy.** A result that shaped a decision without leaving a token in
  the future is invisible to it; a result credited for a token the model would have written
  anyway is a false positive. `needed_before_refetch` and `needed_sole` bound it from two sides.
- **Our fast-jev replica simplifies the original's state fitting.** It asks the original's two
  questions per call at its 0.5 cut over a state fitted in three fixed stages under 75,000
  characters; the plugin's own staged fitting and batching are not reproduced exactly.
- **One agent and one model.** OpenHands with Qwen3-Coder on SWE-rebench issues, not Claude
  Code; its tools are mapped to Claude Code names so the rules apply (`public.py`).
- **No agent was re-run.** Whether a pruned context changes what the agent does next is the
  end-to-end measurement in the handoff, not this one.

## Cost

123 Jev decisions (`jev-1.13.0`): sanchopanza 48 calls, 816,273 input tokens, 0.034 USD;
fastjev 75 calls, 989,830 tokens, 0.042 USD. Total 0.076 USD against an estimate of 0.094 and
a ceiling of 1 USD.

## Reproducing

```bash
python benchmarks/context/build.py --fetch        # public sample into ~/.cache, never the repo
python benchmarks/context/run.py --dry            # full pipeline, fake decider, zero cost
python benchmarks/context/run.py --estimate       # Jev calls, tokens and USD, no call
python benchmarks/context/run.py --live --max-usd 1.0   # refuses unless registered
python benchmarks/context/run.py --replay         # free, from ~/.cache recordings
python benchmarks/context/diagnose.py             # free, from the same recordings
python benchmarks/context/simulate.py arrival --estimate    # Amendment 2, no call
python benchmarks/context/simulate.py recall --replay       # free, from its recordings
```

The dataset is public and rebuilt by `build.py --fetch`; the recordings stay in ~/.cache and
`analysis.json` and `diagnosis.json` (aggregates) are published here.
