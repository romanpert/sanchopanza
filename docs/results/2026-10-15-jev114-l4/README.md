# Jev 1.14 against 1.13 on find_in_repo and on candor with public data (lot L4)

**The result:** on the two primary metrics of find, 1.14 performs the same as 1.13. On tau2
it ranks a little better and classifies a little worse at the 0.5 cut. On errata it does
not rank better, and at the 0.83 cut it flags twice as many answers.

**None of the nine comparisons comes out "no peor" under the sealed rule.** One comes out
"mejora": tau2's AUC, +0.032, from 0.549 to 0.581, Holm p 0.002. It is still near chance. The
other eight are "no concluyente o peor".

On find, any@1 was identical: 50.4 % in both arms, with 3 issues gained and 3 lost. The rule
fails only because a 117-item CI cannot exclude −2 points.

Pre-registered in `prereg.md`:
- commit 8f83b1c, sealed in 7698fc3;
- `prereg.sha256` fbf111b1…;
- reviewed twice by `revisor-prereg` before the seal.

Both models were asked live on 2026-10-15, interleaved item by item on the same inputs. Jev
spent **0.5479 USD** in the batch ledger, under the 0.60 cap, with no call refused and no item
lost. Claude: 0.

## The nine registered comparisons (j14 − j13r, both live today)

| Comparison | n | 1.13 today | 1.14 | Difference [95 % CI, items] | CI by cluster | Holm p | Verdict |
|---|---|---|---|---|---|---|---|
| **find prod any@1** (F2's metric) | 117 | 50.4 % | 50.4 % | 0.0 [−4.3, +4.3] (3 won, 3 lost) | [−3.4, +3.4] | 1.0 | no concluyente o peor |
| **find prod any@5** (F1's metric) | 117 | 65.0 % | 64.1 % | −0.9 [−4.3, +1.7] (1 won, 2 lost) | [−4.1, +1.9] | 1.0 | no concluyente o peor |
| find free any@1 (no keep cut) | 117 | 50.4 % | 50.4 % | 0.0 [−4.3, +4.3] | [−3.4, +3.4] | 1.0 | no concluyente o peor |
| find free any@5 | 117 | 66.7 % | 65.8 % | −0.9 [−3.4, +1.7] | [−4.2, +1.7] | 1.0 | no concluyente o peor |
| **tau2 accuracy at 0.5** (`check_done` in production) | 320 | 54.4 % | 52.8 % | −1.6 [−4.7, +1.3] (9 won, 14 lost) | [−4.3, +1.0] | 1.0 | no concluyente o peor |
| tau2 AUC | 320 | 0.549 | 0.581 | **+0.032 [+0.014, +0.051]** | [+0.011, +0.054] | **0.002** | **mejora** |
| errata correct at 0.83 | 110 | 51.8 % | 49.1 % | −2.7 [−11.8, +6.4] | [−10.0, +4.5] | 1.0 | no concluyente o peor |
| errata AUC (objected vs accepted) | 110 | 0.573 | 0.530 | −0.043 [−0.098, +0.010] | [−0.097, +0.006] | 0.94 | no concluyente o peor |
| errata AUC (unverified vs accepted) | 81 | 0.670 | 0.614 | −0.056 [−0.128, +0.015] | [−0.119, +0.003] | 0.94 | no concluyente o peor |

How to read the table:
- The primary comparisons are in bold.
- The CI by cluster resamples whole units: repositories (find), domain and task (tau2) and tasks
  (errata). It gives the same verdict as the item CI in all nine.
- **Failures:** 0 in every live arm and set, so the 2 % failure gap never applied. Counting a
  failure as a wrong answer changes nothing.
- **"No concluyente o peor" here means "not shown", not "worse".** Every one of these CIs
  straddles 0 (prereg, Power).

## The originals' hypotheses, per arm

`rec13` is the 2026-09-29 recording, replayed. On find it skips the 3 pylint instances whose
recorded inputs no longer reproduce (n = 114).

| Hypothesis | rec13 | 1.13 today | 1.14 |
|---|---|---|---|
| F1 any@5 >= 45.0 % | holds (64.0 %) | holds (65.0 %) | holds (64.1 %) |
| F2 any@1 >= 18.7 % | holds (50.0 %) | holds (50.4 %) | holds (50.4 %) |
| F3 median cost <= 0.005 USD | holds (0.0016) | holds (0.0016) | holds (0.0015) |
| X2 errata AUC >= 0.65 | fails (0.560) | fails (0.573) | fails (0.530) |
| X3 errata AUC unverified >= 0.70 | fails (0.663) | fails (0.670) | fails (0.614) |
| T1 tau2 AUC >= 0.75 | fails (0.557) | fails (0.549) | fails (0.581) |
| T2 tau2 beats trusting (66.6 %) by 10 points | fails (54.1 %) | fails (54.4 %) | fails (52.8 %) |

Every original verdict stands under 1.14. Nothing that failed on 1.13 holds on 1.14.

## What moved, beyond the verdicts

- **find: same hits, slightly fewer calls.**
  - 1.14 keeps 12.1 fragments per issue against 13.1 for 1.13.
  - It needed 430 calls against 454, and 0.2026 USD against 0.2155.
  - The ranking quality is the same at every k. The free ranking (no keep cut) matches the
    product ranking at any@1, and in both arms it is 1.7 points higher at any@5 and 3-4 points
    higher at any@10.
- **errata: 1.14 answers "misstates" higher on almost everything.**
  - Mean shift +0.10, correlation with 1.13 0.91.
  - At the 0.83 cut set on the 1.13 candor bench, it flags 21/55 objected and 22/55 accepted
    answers, against 10 and 8 for 1.13.
  - The cut does not transfer to 1.14, and the ordering got no better either: AUC 0.53 against
    0.57, not significant.
- **tau2: 1.14 says "done" less often.**
  - Mean p(done) is 0.59 against 0.66, correlation 0.97.
  - It orders runs slightly better: AUC +0.032, the one "mejora".
  - At 0.5 it loses 1.6 points of accuracy, because it calls more runs not done and tau2 rewards
    most runs (66.6 %).
  - Trusting the agent still beats both arms by 12-14 points. 1.14 does not change the
    2026-09-29 reading that tau2's label is not what `check_done` asks.
- **1.13 against itself:** today's 1.13 against the recording moved
  - errata AUC by +0.013;
  - tau2 AUC by −0.008;
  - find any@5 by about 1 point.

  That is the size of Jev's day-to-day noise on these sets. It is why only the live pair is
  compared.

## What this does and does not show

- **It shows:** on these three sets, with production inputs and limits, 1.14 is
  indistinguishable from 1.13 on find_in_repo. It is no better at candor's holistic question on
  real sessions. It ranks tau2 runs marginally better, which changes no decision at the
  production cut. All of the difference is the model's: no long-context header, no image, the
  same 900-character pages.
- **It does not show:** "no peor" on find. The registered rule asks for a CI lower bound above
  −2 points. 117 issues with 6 discordant pairs cannot give that, even at an observed difference
  of exactly 0.
- **The find path** measured is the one registered on 2026-09-29: BM25 over every file, then the
  tournament. Today's `find_in_repo` defaults to code-only sources, and that path was not
  measured here.
- **Skipped for budget**, as registered:
  - MALT, about 0.064 USD for the two arms;
  - the candor counterfactuals of rounds 3-5, which are phase 2 (the
    [confirmation](../2026-10-15-jev114-recalconf/README.md) then asked rounds 2-5);
  - errata's `check_done` and per-sentence questions, which no registered verdict reads.

## Spend

| | USD |
|---|---|
| find, 1.13 / 1.14 | 0.2155 / 0.2026 |
| tau2, 1.13 / 1.14 | 0.0553 / 0.0553 |
| errata, 1.13 / 1.14 | 0.0096 / 0.0096 |
| **Batch `jev114-l4` in the ledger** | **0.5479** (cap 0.60) |
| Ledger after this lot, all lots | 0.9729 (cap 4.50) |
| Preflights, outside the ledger | 0.00005 |

## Recommendation

- **Do not switch find_in_repo or the candor holistic question to 1.14 on this evidence.**
  - find gains nothing, apart from about 5 % fewer calls and 6 % less cost.
  - On errata the ranking does not improve, and the 0.83 cut no longer means the same.
- If 1.14 becomes the default anyway (1.13 will be retired), **recalibrate**
  `errata.HOLISTIC_CUT` and the candor holistic cut on 1.14 recordings before trusting them. On
  1.14 the 0.83 cut flags 40 % of accepted answers. What followed: the
  [recalibration](../2026-10-15-jev114-recal/README.md) set the holistic cut at 0.90 on 1.14, and
  its [confirmation](../2026-10-15-jev114-recalconf/README.md) found 1.14 at 0.90 worse than 1.13
  at 0.83 on 910 counterfactuals no cut had seen (−3.3 points [−5.4, −1.2]; AUC 0.958 against
  0.972). Candor stays on 1.13.
- `check_done`'s 0.5 cut sits on the 2026-09-25 AgentDojo calibration, not on tau2. tau2 does
  not argue for moving it: the gain is in ranking only, near chance.

## Files

- `prereg.md`, `prereg.manifest.json`, `prereg.sha256`: the sealed registration.
- `{find,tau2,errata}-answers-{j13r,j14}.jsonl`: every live answer, with a hashed key, the
  model, the cost and the answers. No text. They replay for free.
- `{find,tau2,errata}-scored.jsonl`: per item, ids and scores of the three arms.
- `summary.json`: everything above. To reproduce it, free:
  `python benchmarks/jev114/l4.py` (analysis), or
  `python benchmarks/jev114/l4.py --run` (replay, then analysis).
