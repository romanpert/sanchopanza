# check_done under Jev 1.14 on unseen AgentDojo trajectories: confirmed no worse, and both versions block too many finished stops here

Jev only, no call to Claude. Both versions were asked live on 2026-10-16:

- `jev-1.13.0` at its shipped `done` cut of 0.5;
- `jev-1.14.0` at 0.30, the cut in `policy.MODEL_PROFILES`.

The trajectories are 950 that neither the recalibration nor its confirmation saw: AgentDojo's own
published runs of Claude 3.7 Sonnet, in suites this repository had never asked about.

**The seal.** Pre-registered in `prereg.md` (sha256 `bb20b9c1…`, in `prereg.sha256`). The inputs
are fixed in `data.sha256` (`e82c4f87…`).

- The sealing commit `aff4cff` adds those two files and nothing else, on top of the instrument
  commit `a8cd589`.
- Before sealing, `revisor-prereg` reviewed the registration against the code in two passes.

## Verdict

**"confirmado (no peor)" by the sealed rule.** The Stop hook may rely on the 0.30 cut under 1.14
as much as it relies on 0.5 under 1.13. The profile is unchanged.

- **The primary comparison.** 1.14 at 0.30 is right on 745 of 950 stops and 1.13 at 0.5 on 737.
  - The difference is +0.8 points, [−1.1, +3.2] with user tasks as the resampling unit.
  - 21 stops favour 1.14 and 13 favour 1.13, exact McNemar p 0.23 (unclustered).
- **The guard holds.** 1.14 makes 150 false blocks of 795 finished stops, against 165 for 1.13.
  - That is 1.9 points fewer: the cluster interval of "not falsely blocked" is [0.0, +4.5].
  - It never exceeds 1.13's false-block rate.
- **Answers and launch.** Every stop has an answer from both versions, and the launch completed.

**What the verdict does not say.** On these trajectories **both versions block about one finished
stop in five**:

- 1.13 blocks 165 of 795 (20.8 %), and 1.14 blocks 150 (18.9 %).
- Block precision is 0.39 and 0.40, and AUC 0.81 for both.
- On the recalibration's slack half the same check made 7 and 8 false blocks.
- The comparison between versions is fair. The absolute level is a separate problem, read below.

## What ran

| | |
|---|---|
| Trajectories | 950: banking 169, travel 167, workspace 614; 106 user-task clusters |
| Labels | AgentDojo's `utility`: 795 done, 155 not done |
| Calls | 1,900, plus 2 preflights; all answered in pass 1, none missing |
| Launch | one, by WMI, from a worktree detached at `aff4cff`; 11:13:58 to 11:18:22, exit 0 |
| Order | the registered shuffle (seed 20261016), both versions per stop in one slot |

## Results

**The arms:**

| Arm | Right | Blocks | False blocks | Precision of a block | Recall on not_done |
|---|---|---|---|---|---|
| 1.13 at 0.5 | 737 / 950 | 272 | 165 | 0.393 | 0.690 |
| **1.14 at 0.30** | **745 / 950** | 250 | **150** | 0.400 | 0.645 |
| 1.14 at 0.5 (descriptive) | 731 / 950 | 290 | 177 | 0.390 | 0.729 |

**The comparisons, 1.14 minus 1.13:**

| Comparison | Difference | 95 % interval, user-task clusters | 1.14 only / 1.13 only | Reading |
|---|---|---|---|---|
| **Primary: right decisions** | **+0.8 points** | **[−1.1, +3.2]** | 21 / 13 | **no peor** |
| Guard: finished stops not blocked | +1.9 points | [0.0, +4.5] | 20 / 5 | holds (upper bound of false blocks ≤ +2) |

**Descriptive, as registered:**

| | Difference | 95 % interval | Note |
|---|---|---|---|
| **Recall on not_done** (blocks among 155 unfinished stops) | **−4.5 points** | **[−10.2, −0.5]** by cluster | 1 / 8. The lower cut lets more unfinished stops through: 100 of 155 caught against 107. |
| Without the 22 hijacked runs (`security` true) | +0.9 points on 928 | [−1.1, +3.3] | no peor; the hijacked runs change nothing |
| Clustered by injection task instead | +0.8 points | [−0.2, +1.8] | no peor |
| 1.14 at 0.5 against 1.13 at 0.5 | −0.6 points | [−2.8, +1.9] | no concluyente; 18 / 24 |
| AUC for ranking unfinished below finished | 0.814 against 0.812 | +0.001 [−0.017, +0.021] | the two versions rank alike |

**By suite**, right decisions (1.13 / 1.14):

| Suite | Right (1.13 / 1.14) | Recall (1.13 / 1.14) | Block precision (1.13 / 1.14) |
|---|---|---|---|
| banking | 131 / 132 of 169 | 0.90 / 0.88 | 0.53 / 0.54 |
| travel | 142 / 140 of 167 | 0.70 / 0.57 | 0.75 / 0.79 |
| workspace | 464 / 473 of 614 | 0.55 / 0.55 | 0.23 / 0.24 |

Benign runs: 89 against 90 of 106. Attacked runs: 648 against 655 of 844.

**The trade the profile makes, visible here.** 0.30 takes 15 false blocks away and lets 7 more
unfinished stops through: 8 lost against 1 gained, mostly in travel. On these stops that nets out
in 1.14's favour, because finished stops outnumber unfinished ones five to one. The registered
guard watches false blocks, not recall, so the recall loss is reported, not tested.

## Power against what came out

The registration's simulation priced this outcome:

- The arms disagreed on 34 of 950 stops (3.6 %). That is the pessimistic rate the registration
  simulated, three times the recalibration's.
- For that rate it gave P("no peor") of 0.47 to 0.91, depending on clustering.
- The interval came out at ±2.2 points, the simulation's ρ ≈ 0.3-0.6 range.
- The point estimate favours 1.14, which put the lower bound at −1.1.

## Why both versions block so many finished stops (post hoc, not registered)

The stops both versions block were read on the machine; no text is published. Two patterns
account for most of them.

- **The record cuts the evidence.** `completion/run.py` keeps the first 1,500 characters of each
  tool result.
  - Workspace tool results, such as a drive listing or an inbox, run far longer.
  - The agent then answers from the full result, but the judge sees an answer it cannot check
    and calls it unsupported.
  - Of 1.14's 150 false blocks, 115 have at least one tool result cut. Among the 645 finished
    stops it lets through, 278 do (77 % against 43 %).
  - Several of the largest clusters of shared false blocks were read and are of this kind:
    workspace user tasks 26, 27, 35 and 38, about "the largest file" and "files shared with…".
- **AgentDojo's `utility` passes some stops where the agent asked instead of acting.**
  - In the banking user tasks 8 and 10 that were read, the agent asks the user which bill or
    which year it means.
  - The benchmark's checker scores these as done, because nothing changed in the environment that
    should not have.
  - check_done calls them not done, which is what its question asks.

Neither pattern favours one version: they are where both versions block. The first pattern is a
limit of how the record is built, and is shared by L2 and the recalibration. It costs little on
slack's short tool results and a lot on workspace's.

## What this licenses

- **Under 1.14, the Stop hook at 0.30 is no worse than under 1.13 at 0.5,** on agents, tasks and
  suites the cut was not read from. The opt-in profile's `done` stays at 0.30.
- **It is not a claim that check_done is good on such tasks.** With long tool outputs cut to
  1,500 characters, both versions block about a fifth of finished stops.
- Before the Stop hook is advertised beyond the slack-like setting it was measured on, the record
  builder should keep the part of each tool result the answer rests on, and be measured again.
  That would be a new registration.

## Bill

| | |
|---|---|
| Jev, billed | **0.1371 USD** for batch `jev114-checkdone`: 0.0685 per version and two preflights, median 65 µUSD a call. Expected 0.130 at the registration; cap 0.25. |
| Shared ledger | 3.8515 → 3.9886 of 4.50 USD |
| Claude | 0 |

## Not done

- **Re-measuring with the tool results kept.** That is a new request shape and needs a new
  registration.
- **A second draw.** One draw per version. Recalconf found 1.14 flips about 1.8 % of decisions
  between draws, against 34 disagreements here.
- **Other agents.** These are an older model's trajectories under AgentDojo's pipeline, not
  Claude Code sessions.
- **The known limits stand, as registered:**
  - the files are public with their labels, so Jev may have seen them;
  - one of the question's own examples copies banking `user_task_0`.

## Reproducing

```bash
python benchmarks/jev114/checkdone114.py fetch            # the 950 public files, checked by blob sha
python benchmarks/jev114/checkdone114.py rows             # replays fixtures/jev114/checkdone114-*.jsonl
python benchmarks/jev114/checkdone114_analysis.py         # analysis.json
python -m pytest tests/test_checkdone114.py tests/test_jev114_lot.py
```

## Files

- `prereg.md`, `prereg.sha256`, `data.sha256`: the sealed registration and inputs.
- `inputs.jsonl`: the 950 AgentDojo paths and their git blob shas.
- `launches.jsonl`: the one launch, with HEAD and HEAD^ and the recordings' line counts.
- `done-scored.jsonl`: per stop, its path in AgentDojo's repository, suite, clusters, attack,
  `security`, label, and both probabilities. No text.
- `analysis.json`: every number above.
- `fixtures/jev114/checkdone114-{13r,14}.jsonl`: the answers, under hashed keys. No text.
