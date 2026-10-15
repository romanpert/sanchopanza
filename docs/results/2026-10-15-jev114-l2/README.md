# Jev 1.14 on check_done and the permission cascade: worse on one, better on another, no move

Pre-registered in `prereg.md` and sealed in commit `700830a` (sha256 of the registration and
the runner together: `9cb1f152...b18186`), after two independent reviews against the code.
Run on 2026-10-15. Only Jev was asked: `jev-1.13.0` again today (`13r`) and `jev-1.14.0` (`14`),
both arms of a case in the same slot, alternating which went first, on identical requests. Every
one of the 1,726 requests matched the September recording's key, so the inputs are byte for
byte those of the published runs. The Claude answers (Sonnet 5, Opus 5) are the recordings of
those runs: **0 USD of Claude**. `rec` is the September recording of 1.13, the published figures.

## Verdict, by the sealed rule

| component | rule | result |
|---|---|---|
| check_done | accuracy at the production cut (p >= 0.5) not worse, and AUC not worse | **recalibrate the cut on 1.14 first**: accuracy is worse (91.9 % against 94.0 %, Holm p 0.002), AUC within the margin (lower bound -0.0196 against -0.02) |
| permission cascade | R-Judge and Codex not worse at the cut, AUC not worse on both, Codex confirmation holds | **stay on 1.13**: R-Judge better, Codex inconclusive at the cut (lower bound -3.6 points) |
| R-Judge cascade against Opus 5 under 50 % | `14` passes the three criteria and its 500-split median cost is <= 50 % | **holds** (43.9 %), but `13r` fails (65.7 %) with every split median near 31 %: **split noise, not a model effect** |
| Codex confirmation, tau 0.45 | three criteria on the held-out half of record, with `14` | **still confirmed** (79.5 % against Opus's 79.9 %, at 37.7 % of its cost) |

Nothing in code changes: `DEFAULT_MODEL` stays `jev-1.13.0`, no threshold in `policy.py` moves.

## Jev alone, 1.14 against 1.13 asked today

Accuracy at the production cut (p >= 0.5) on all cases; exact McNemar, Holm across the three
sets; paired bootstrap 95 % intervals (2,000 resamples, seed 7).

| set | n | `13r` | `14` | difference [95 %] | 13r right only / 14 right only | Holm p | reading | AUC `13r` / `14` | AUC difference [95 %] |
|---|---|---|---|---|---|---|---|---|---|
| check_done (AgentDojo) | 655 | 94.0 % | **91.9 %** | -2.1 [-3.4, -1.1] | 15 / 1 | 0.002 | **worse** | 0.982 / 0.970 | -0.012 [-0.020, -0.006] |
| R-Judge | 571 | 87.4 % | **89.7 %** | +2.3 [+0.7, +4.0] | 5 / 18 | 0.021 | **better** | 0.958 / 0.965 | +0.007 [+0.001, +0.013] |
| ATBench-Codex | 500 | 78.8 % | 77.2 % | -1.6 [-3.6, +0.4] | 17 / 9 | 0.169 | inconclusive | 0.864 / 0.858 | -0.006 [-0.014, +0.003] |

Day-to-day noise of 1.13 (`13r` against `rec`, the same model a month apart): 2 labels of 655
flipped on check_done, 12 of 571 on R-Judge, 10 of 500 on Codex, no accuracy difference
significant. 1.14 moved 16, 23 and 26. Token counts and cost per request are identical between
versions; median latency 203-218 ms for both today (250 ms in September).

### check_done: 1.14 says "not done" more often

At the cut of 0.5, 1.14 calls 27 finished trajectories unfinished, against 12 for 1.13 today;
false "done" is unchanged (26 against 27; precision of "done" 92.4 % for both). For the Stop
hook that is the costly direction: it blocks a stop that should go through. The probability is
shifted down, not scrambled: AUC drops by 0.012, inside the registered -0.02 margin but with an
interval that excludes zero.

**Post hoc, descriptive only**: the accuracy-maximising cut on the derivation half is 0.30 for
1.14 (0.60 for 1.13); at 0.30, 1.14 scores 94.8 % on the held-out half, against 95.1 % for 1.13
at its production 0.5. A recalibrated cut would recover most of the gap; it was not registered
and is not a result.

The original criteria hold for every arm: P13 (Jev beats trusting the agent by 15 points: 92.7 %
against 55.3 % held out for 1.14) and P14 (cascade Jev > Sonnet 5 reaches Sonnet). P14's cost
rises with 1.14, from 16.5 % of Sonnet (`13r`; 21.5 % `rec`) to **44.2 %**: the derived tau goes
to 0.85 and 131 of 329 trajectories escalate.

## R-Judge: the cascade against Opus 5 (the 57 %)

Registered rule, held-out half; Opus 5 answers are the Batch API recording of 2026-09-25.

| arm | tau* | Jev alone (held out) | cascade | Opus alone | cost / Opus | escalated | criteria | median cost over 500 splits |
|---|---|---|---|---|---|---|---|---|
| `rec` (published) | 0.80 | 86.3 % | 93.2 % | 93.2 % | 56.8 % | 152 / 263 | fails on cost | 31.6 % |
| `13r` | 0.85 | 85.6 % | 93.2 % | 93.2 % | 65.7 % | 176 / 263 | fails on cost | 30.8 % |
| `14` | 0.75 | 87.1 % | 93.2 % | 93.2 % | **43.9 %** | 117 / 263 | **pass** | 31.6 % |

All three arms reach Opus exactly; what moves is the tau the rule buys the last case with. Over
500 random splits the three arms sit at the same median, 31-32 %. The registered split crosses
the bar with 1.14 and moves further from it with 1.13 asked today: the bar is crossed, by the
sealed rule, but the difference between the two versions is the split's, not the model's.

Sonnet 5 as X (P1, CLI recording): the same picture, 48.5 % with `14` (pass), 66.5 % with `13r`
and 57.7 % with `rec` (fail). False allows and blocks of every cascade equal those of the
frontier model alone. Descriptive, at the confirmed tau 0.45 on R-Judge's held-out half: 93.2 %
at 25.6 % of Opus's cost with 1.14 (30.0 % with 1.13), false allows 8.8 % for both.

## ATBench-Codex: the confirmation at tau 0.45

Opus 5 answers are the Claude Code CLI recording of 2026-09-27.

| arm | set | Jev alone | cascade | Opus alone | difference [95 %] | cost / Opus | escalated | verdict |
|---|---|---|---|---|---|---|---|---|
| `rec` | held-out half (of record), 239 | 79.1 % | 80.3 % | 79.9 % | +0.4 [-2.1, +2.9] | 38.8 % | 91 | confirmed |
| `13r` | held-out half, 239 | 80.3 % | 79.9 % | 79.9 % | 0.0 [-2.5, +2.5] | 38.7 % | 91 | confirmed |
| `14` | held-out half, 239 | 79.1 % | **79.5 %** | 79.9 % | -0.4 [-3.3, +2.1] | **37.7 %** | 88 | **confirmed** |
| `14` | all 500, 487 answered | 77.4 % | 78.6 % | 77.8 % | +0.8 [-1.0, +2.7] | 37.1 % | 176 | confirmed |

False allows with 1.14 at tau 0.45 on all 500: 21.6 % for the cascade, 25.7 % for Opus, 14.5 %
for Jev alone; false blocks 21.1 %, 18.7 % and 30.5 %. Band: tau 0.35 gives 78.6 % at 28.8 %,
tau 0.65 78.2 % at 55.6 %. P9 (Sonnet 5, registered rule) holds for every arm; with 1.14 the
derived tau is 0.25 instead of 0, at 17.6 % of Sonnet's cost.

## Recommendation

- **check_done: stay on 1.13.** Moving needs a cut recalibrated on 1.14 and confirmed on unseen
  trajectories; at the current 0.5 the Stop hook would block about twice as many finished runs.
- **Permission cascade: stay on 1.13 by the sealed rule.** 1.14 is better on R-Judge and keeps
  the Codex confirmation at a slightly lower cost, but on Codex alone at the cut it is
  inconclusive (-1.6 points, interval down to -3.6). tau 0.45 needs no recalibration on either
  version.
- **The R-Judge 50 % bar is not evidence for 1.14.** The pass is the registered split's; at the
  split medians both versions sit near 31 % of Opus's cost.
- A migration when 1.13 is retired will need: a recalibrated check_done cut, and a second
  Codex draw to settle the inconclusive reading.

## What this does not settle

- One draw per version: Jev is not deterministic, and the September draw differs from today's
  by 2-12 labels per set. The paired tests see today's two draws only.
- AgentDojo is not a coding session, R-Judge is from 2024 and public, the Codex cases are
  synthetic: the limits of the original runs stand.
- The Claude answers are a month old; the Claude models were not asked again.

## Cost

Jev only, from the shared ledger (`jev114-l2`): **0.1733 USD** for 3,452 decisions and two
preflights (estimate 0.173, cap 0.25). The ledger stood at 0.1733 of 4.50 USD after this batch.
Claude: 0 USD.

## Reproducing

```bash
python benchmarks/cascade/jev114.py --analyze     # free: replays fixtures/jev114/*.jsonl
python -m pytest tests/test_jev114_l2.py          # pins the figures above
```

R-Judge (at `83ce301`) and ATBench-Codex `test.json` are not redistributed:
`SANCHOPANZA_RJUDGE` and `SANCHOPANZA_ATBENCH_CODEX` point at them. The answers of both versions
are in `fixtures/jev114/` (`*-113r.jsonl` for 1.13 today), the report in `analysis.json`.
