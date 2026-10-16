# Confirming the Jev 1.14 threshold profile: it does not hold

Jev only, no call to Claude. Both versions were asked live on 2026-10-15: `jev-1.13.0` at its
shipped cuts, and `jev-1.14.0` with the profile in `policy.MODEL_PROFILES`.

Pre-registered in `prereg.md` and sealed in commit 8e3c8c6 before any answer. `prereg.sha256`
covers the registration, the runner, the analysis and the code that builds the requests and holds
the cuts; `data.sha256` covers every part's requests and labels. Before sealing, `revisor-prereg`
reviewed the registration twice against the code.

## Verdict

**The DEFAULT_MODEL switch is "no admisible" by the sealed rule. `DEFAULT_MODEL` stays
`jev-1.13.0`.**

- **On the counterfactuals no cut has seen, 1.14 with its profile is "peor".** These are 910
  candor reports from rounds 2-5:
  - 1.13 at 0.83 is right on 800 of them, and 1.14 at 0.90 on 770.
  - The difference is −3.3 points [−5.4, −1.2] with sessions as the resampling unit, McNemar
    p 0.001.
  - At 0.90, 1.14 catches fewer misstatements and flags more paraphrases than 1.13 does at 0.83.
  - It ranks worse too: AUC 0.958 against 0.972.
- **The second draw does not reproduce the recalibration's parity.** Over the 646 evaluation
  items:
  - 551 right for 1.14 against 555 for 1.13, a difference of −0.6 points [−2.3, +0.9]: "no
    concluyente". The first draw gave 556 against 556.
  - **redundant_page is "peor"**: 44 against 48 of 50, −8.0 [−16.0, −2.0], all four disagreements
    against 1.14.
  - Five points stay "no peor", and two are "no concluyente".
- **Not run: new labelled cases for the six L1 points.** None exist with the same definition, in
  the repository or in public data, and this lot does not write labels. check_done on new
  trajectories was not run in this lot. [checkdone114](../2026-10-16-checkdone114/README.md)
  ran it on 2026-10-16 on AgentDojo's published runs of Claude 3.7 Sonnet (950 trajectories, no
  agent run needed): confirmed no worse at 0.30.

## Part B: a second draw of the recalibration's 1,298 cases

These are the same cases and partitions as the recalibration, with each version asked a second
time. The verdicts are on the 646 evaluation items, with the cuts fixed in code:

| Point | Cuts 1.13 / 1.14 | 1.13 at its cut | 1.14 with the profile | Difference, points [95 % CI] | 14 only / 13 only | Verdict | First draw (recal) |
|---|---|---|---|---|---|---|---|
| redundant_page | 0.59 / 0.61 | 48/50 | **44/50** | −8.0 [−16.0, −2.0] | 0 / 4 | **peor** | 47 vs 45, no concluyente |
| memory_write | 0.54 / 0.54 | 115/157 (2 costly) | 114/157 (4 costly) | −0.6 [−4.5, +3.2] | 5 / 6 | no concluyente | 113 vs 115, no concluyente |
| goal_met | 0.70 / 0.57 | 12/14 | 14/14 | +14.3 [0.0, +35.7] | 2 / 0 | no peor | 12 vs 14, no peor |
| repeats_check | 0.70 / 0.60 | 11/12 | 11/12 | 0.0 [0.0, 0.0] | 0 / 0 | no peor | 12 vs 12, no peor |
| extract_gate | 0.25 / 0.27 | 15/16 | 16/16 | +6.2 [0.0, +18.8] | 1 / 0 | no peor | 15 vs 16, no peor |
| recall | 0.25 / 0.10 | 14/14 | 14/14 | 0.0 [0.0, 0.0] | 0 / 0 | no peor | 14 vs 14, no peor |
| check_done (block) | 0.5 / 0.30 | 311/329 (9 false blocks) | 310/329 (10) | −0.3 [−1.5, +0.9] | 2 / 3 | no peor | 313 vs 312, no peor |
| candor holistic (errata) | 0.83 / 0.90 | 29/54 | 28/54 | −1.9 [−9.3, +3.7] | 1 / 2 | no concluyente | 30 vs 28, no concluyente |
| **All eight** | | **555/646** | **551/646** | **−0.6 [−2.3, +0.9]** | 11 / 15 | **no concluyente** | 556 vs 556, no peor |
| The six L1 points | | 215/263 | 213/263 | −0.8 [−4.2, +2.3] | 8 / 10 | no concluyente | 213 vs 216, no peor |

How the table was computed:

- Paired bootstrap with 2,000 replicas (seed 7) and exact McNemar.
- Holm across the eight points. Every Holm p is 1.0, so no point reaches "mejora".
- "peor" for redundant_page is the interval's upper bound below 0.
- No case is missing an answer in any part.

**Without a cut (AUC on the evaluation part, secondary):**

- **check_done:** 0.986 against 0.974, −0.012 [−0.023, −0.003]. The interval lies entirely below 0,
  but the verdict is "no concluyente" because its lower bound crosses the −0.02 margin.
- **memory_write:** 0.905 against 0.891, also "no concluyente".
- **holistic on errata:** 0.667 against 0.615, also "no concluyente".
- The four loop and gate points and redundant_page rank perfectly on both versions (AUC 1.0).

### The noise between draws

Every case, each version at its own cut, draw 1 against draw 2:

| Version | Decisions flipped | Mean \|Δp\| by point | Largest \|Δp\| | Evaluation items right, draw 1 → draw 2 |
|---|---|---|---|---|
| 1.13 | 10 of 1,298 (0.8 %) | 0.005-0.019 | 0.12 | 556 → 555 |
| 1.14 | 23 of 1,298 (1.8 %) | 0.005-0.020 | 0.14 | 556 → 551 |

- **1.14 moves more than 1.13 between draws.** It flips about twice as many decisions:
  - six on memory_write, five on holistic and three on goal_met;
  - against two, one and none for 1.13.
- **The profile's parity was within that movement.** On the first draw the pooled gap was 0 items,
  and on this one it is 4. 1.14 alone moved by 5.
- **redundant_page stands out.** Here the profile's 0.61 drops 12 of the 18 held-out `drop`
  pages, against 16 for 1.13 at 0.59. 1.14 at 0.59 would drop 13.
  - Precision is 1.00 for every arm.
  - The ordering is perfect for both versions.
  - The loss comes from the cut, not from the model's ranking: the same finding as the
    recalibration.

## Part C: the candor counterfactuals of rounds 2-5

The data:

- 910 reports from 168 honest sessions: 570 misstatements (M1-M5) and 340 paraphrases (C0).
- The holistic `misstates` question, asked over the same state as in candor.
- No cut was fitted on these rounds: 1.13's 0.83 came from round 1, and 1.14's 0.90 from errata.

| Arm | Cut | Right | Misstatements caught (TPR) | Paraphrases flagged (FPR) | AUC |
|---|---|---|---|---|---|
| 1.13, 2026-09 recording | 0.83 | 799/910 | | | 0.972 |
| **1.13 today** | 0.83 | **800/910** (87.9 %) | 469/570 (82.3 %) | 9/340 (2.6 %) | 0.972 |
| **1.14, profile** | 0.90 | **770/910** (84.6 %) | 443/570 (77.7 %) | 13/340 (3.8 %) | 0.958 |
| 1.14 at 1.13's cut (descriptive) | 0.83 | 830/910 | 539/570 (94.6 %) | 49/340 (14.4 %) | |

**Primary result:**

- The difference is −3.3 points.
- The 95 % interval is [−5.4, −1.2] by session, and [−5.3, −1.4] by report.
- 26 reports favour 1.14 and 56 favour 1.13, McNemar p 0.0012.
- **Verdict: peor.**

**The guard.** 1.14 at 0.90 does meet candor's own criterion (≥ 70 % caught at ≤ 8 % FPR), but
that does not help it here, because the primary comparison already failed.

**AUC without a cut:**

- The difference is −0.014 [−0.022, −0.007].
- This is "no concluyente" by the −0.02 rule, with the whole interval below 0.

**By round:** the difference is −2.0, −3.2, −4.0 and −5.9 points for rounds 2 to 5, and below 0 in
each round.

**Reading the result:**

- **1.13 reproduces itself.** Today's 1.13 matches September's: 800 against 799 right, AUC 0.972
  both times.
- **1.14 is behind at both cuts.**
  - At 0.90 it catches 26 fewer misstatements and flags 4 more paraphrases than 1.13 at 0.83.
  - At 0.83 it would catch more, but flag 14.4 % of honest paraphrases.
- **The profile's transfer goes the wrong way here.** It moved the cut up to keep errata's false
  flags where 1.13 had them. On counterfactuals that trade costs recall without saving false
  flags.
- **The gap is in the ranking, not only in the cut.** 1.14 ranks the counterfactuals worse than
  1.13 does.

## Recommendation

**Do not switch `DEFAULT_MODEL` to `jev-1.14.0`.** The sealed rule says "no admisible" on two counts:

- a point of Part B is "peor" (redundant_page), and the pool is "no concluyente";
- Part C is "peor".

**The profile.** It stays opt-in (`SANCHOPANZA_JEV_MODEL=jev-1.14.0`), as the recalibration left
it. This lot changes no threshold, and these findings bear on anyone who opts in:

- **candor holistic.** On unseen counterfactuals, 1.14 at 0.90 is 3.3 points behind 1.13 at 0.83.
  At 0.83 it flags 14 % of honest reports. The ranking itself is worse, so no single 1.14 cut was
  shown to match 1.13 on both axes.
- **redundant_page.** 0.61 loses held-out drops on both draws: 45 and 44 of 50, against 47 and 48
  for 1.13. The fix the recalibration proposed still applies: about 90 new labelled `drop` cases
  so that a 90 % derivation does not hinge on one page.
  - 2026-10-16: [redundant-drop](../2026-10-16-redundant-drop/README.md) added them. The
    derivation no longer hinges on one page but lands at 0.04, inside the `keep` pages' scores,
    and fails the costly-drops guard (8 against 0): no proposal. 0.61 lost drops a third time
    (−6.0 points [−11.6, −1.7]).
- **check_done.** It holds on a second draw: 310 against 311, false blocks 10 against 9.
  1.14 at 0.5 would make 14 false blocks.

**Still unconfirmed on unseen cases:**

- The six L1 points have been checked against two draws only. Writing new labelled cases (about
  420) remains the way to settle them; it does not change this verdict.
- check_done is settled on unseen trajectories: on 950 AgentDojo stops no lot had seen
  ([checkdone114](../2026-10-16-checkdone114/README.md)), 1.14 at 0.30 is no worse than 1.13 at
  0.5, +0.8 points [−1.1, +3.2].

## Bill

**0.1976 USD of Jev, measured from the shared ledger.** That covers two preflights and 4,416
calls, against an expected 0.197 and the lot's 0.45 cap. The shared ledger went from 3.654 to
3.852 of 4.50 USD. There was one launch, completed with no stop and no failed call.

## Not measured

- **Part A:** new labelled cases for redundant_page, memory_write, goal_met, repeats_check,
  extract_gate and recall.
  - Every labelled case of these points in the repository is one of the 533 in
    `benches/*.jsonl`, all asked by L1.
  - No public dataset labels the same questions.
- **check_done on new trajectories**, measured afterwards by checkdone114 (above).
- **Candor round 1**, where 1.13's cut was fitted.

## Reproducing

```bash
python benchmarks/jev114/recalconf.py check --runs-root PATH   # same requests as draw 1, free
python benchmarks/jev114/recalconf.py rows --runs-root PATH    # fixtures -> rows, free
python benchmarks/jev114/recalconf_analysis.py                 # analysis.json, free
python -m pytest tests/test_jev114_recalconf.py
```

`PATH` names the checkout that holds the untracked inputs: the AgentDojo `runs/` and candor's
`counterfactual-*.jsonl`. `data.sha256` fixes them. The answers are in
`fixtures/jev114/recalconf-<part>-<arm>.jsonl`, with hashed keys and no text.

## Files

- `prereg.md`, `prereg.sha256`, `data.sha256`: the sealed rules and inputs.
- `analysis.json`: every number above.
- `rows-l1.jsonl`, `done-scored.jsonl`, `errata-scored.jsonl` and `cf-scored.jsonl`: per case, the
  ids, labels and probabilities of both arms, with no text.
- Instruments: `benchmarks/jev114/recalconf.py` and `recalconf_analysis.py`.
