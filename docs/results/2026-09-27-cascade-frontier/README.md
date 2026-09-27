# The Jev > Opus 5 permission cascade: re-read post hoc, then confirmed on unseen data (2026-09-27)

## Confirmed on ATBench-Codex (pre-registered, run the same evening)

The post-hoc reading below led to one registered run: symmetric escalation at **tau 0.45**
(chosen on R-Judge), on ATBench-Codex, which Opus 5 had never been asked
(`prereg-confirm.md`; Opus through the Claude Code CLI, `prereg-confirm-cli.md`, the held-out
half after a cost pilot; the other half and all 500 in `prereg-confirm-rest.md`, written after
the held-out verdict and before any call on the rest). Jev's answers replay from
`fixtures/cascade-jev.jsonl`; Opus's sessions are cached in `fixtures/cli/cascade-opus.jsonl`.

| set | answered | Jev alone | Opus 5 alone | **cascade** | diff (95 % CI) | cost / Opus | escalated | verdict |
|---|---|---|---|---|---|---|---|---|
| held-out half (**of record**) | 239 of 242 | 79.1 % | 79.9 % | **80.3 %** | +0.4 (-2.1, +2.9) | **38.8 %** | 91 | **confirmed** |
| other half (replication) | 248 of 258 | 77.4 % | 75.8 % | **77.8 %** | +2.0 (-1.2, +4.8) | **38.3 %** | 92 | confirmed |
| all 500 (the first registration) | 487 of 500 | 78.2 % | 77.8 % | **79.1 %** | +1.2 (-0.8, +3.3) | **38.5 %** | 183 | confirmed |

All three criteria hold on every set: accuracy within 2 points of Opus (it is above), bootstrap
lower bound above -6 points, cost under 50 %. The cost ratio landed where the recorded Jev
answers predicted before any call (about 37.5 %).

**What this does and does not say.**

- On this set **Jev alone is as accurate as Opus 5** (78.2 % against 77.8 % on all 500) at about
  0.4 % of its cost, and lets through fewer unsafe actions: false allows 14.9 % for Jev, 25.7 %
  for Opus, 20.3 % for the cascade. The cascade's value here is not reaching Opus: it is adding
  a point over either alone, and Opus's errors are more often the costly kind. On R-Judge the
  gap between them was real (86.3 % against 93.2 % held out), so which model is the "strong"
  one depends on the set.
- Sensitivity band, reported not judged: tau 0.35 gives 79.3 % at 28.2 % of Opus's cost on all
  500 with fewer false allows (18.3 %); tau 0.65 gives 78.2 % at 57.1 %, over the cost bar.
- 13 of 500 Opus sessions failed twice (no structured answer) and are excluded, as registered.
- Cost is Claude Code's list-price figure, CLI overhead included and identical per call:
  6.83 USD for the held-out half and 8.24 USD for the other, 15.07 USD against the
  subscription, 0 USD against any key.

Reproduce, free from the cache: `python benchmarks/cascade/confirm_cli.py --codex test.json`
(held-out half) and `--rest` (the other half and all 500); `confirm-cli-analysis.json` and
`confirm-rest-analysis.json` hold the reports.

## The post-hoc reading that led to it (free)

Everything here replays `../2026-09-25-cascade/rows.json` and `llm-answers.jsonl`; nothing
was called. `python benchmarks/cascade/frontier.py` writes `analysis.json`;
`tests/test_cascade_frontier.py` pins the figures below. **None of it is confirmatory.** The
registered result stands: on R-Judge's held-out half the cascade reached Opus's accuracy
(93.2 %) at **56.8 %** of Opus's cost, over the registered 50 %. Every rule below was examined
after that verdict, on the same cases. The run that confirmed the one rule taken forward
(tau 0.45) is above.

## (a) Prompt caching does not move the ratio

The Opus request is `tools` (the forced answer schema) + `system` + one user message holding
the case. Only the case varies, so the cacheable prefix is the schema, the system prompt and
the tool-use preamble. Its size is not recorded; the smallest recorded Opus request is 1,085
tokens, which bounds it, and Opus 5 caches nothing under 512. Re-priced at 1.25x for one write
and 0.1x for every read after it, **applied to both arms** (Opus alone would cache the same
prefix), on the 263 held-out cases with the registered tau 0.80:

| cached prefix (tokens) | Opus alone | cascade | ratio |
|---|---|---|---|
| none | 2.746 USD | 1.560 USD | 56.8 % |
| 512 | 2.143 | 1.213 | 56.6 % |
| 700 | 1.922 | 1.085 | 56.5 % |
| 900 | 1.687 | 0.950 | 56.3 % |
| 1,084 (the bound) | 1.470 | 0.825 | 56.1 % |

Caching cuts both bills by up to 46 % and the ratio by at most 0.7 points: the ratio is set by
the escalation share (152 of 263, 58 %), and caching lowers the price of an escalation and of
an Opus-alone call by the same amount. The Batch discount is the same: it applies to both.

## (b) The threshold frontier: the registered rule paid for the last case

Held-out half, symmetric escalation (Opus alone: 93.2 %, false allows 8.1 %):

| tau | accuracy | cost / Opus | escalated | false allows | false blocks |
|---|---|---|---|---|---|
| 0.00 (Jev alone) | 86.3 % | 0.4 % | 0 | 10.3 % | 17.3 % |
| 0.20 | 91.6 % | 18.5 % | 50 | 10.3 % | 6.3 % |
| 0.35 | **93.2 %** | **25.2 %** | 67 | 8.8 % | 4.7 % |
| 0.50 | 93.2 % | 31.0 % | 83 | 8.8 % | 4.7 % |
| 0.65 | 93.5 % | 39.7 % | 107 | 8.1 % | 4.7 % |
| 0.80 (registered) | 93.2 % | 56.8 % | 152 | 8.1 % | 5.5 % |
| 1.00 (Opus alone) | 93.2 % | 100.4 % | 263 | 8.1 % | 5.5 % |

Accuracy is flat from 0.35 to 1.00 on the held-out half. The registered rule took the smallest
tau whose derivation-half accuracy **equals** Opus's (269 of 278): 0.45 reaches 267, 0.65 and
0.75 reach 268, and the 269th case needed 0.80, which costs 50 more escalations than 0.65 on
that half. A rule that asks for "within half a point" instead of "equal" would have picked 0.65
on the derivation half (268 of 278) and scored 93.5 % at 39.7 % held out, inside the cost
criterion. The same kind of rule fixes the threshold of the next run, and it was chosen after
seeing this, which is why none of it is a result.

On all 541 answered R-Judge cases: 0.45 gives 94.6 % against Opus's 95.0 % at 27.0 % of the
cost; 0.65 gives 95.0 % at 34.1 %.

## (c) Asymmetric routing does not help

With the registered derivation rule, neither one-sided rule ever reaches Opus's accuracy on
the derivation half (tau 1.01, "always escalate that side").

| held out, tau = 1.0 | accuracy | cost / Opus | false allows | false blocks |
|---|---|---|---|---|
| escalate only when Jev says `safe` | 86.7 % | 43.3 % | 7.4 % | **19.7 %** |
| escalate only when Jev says `unsafe` | 92.8 % | 57.6 % | **11.0 %** | 3.1 % |
| symmetric, 0.35 | 93.2 % | 25.2 % | 8.8 % | 4.7 % |

Jev's errors on R-Judge are mostly false blocks (17 % at tau 0), so checking only its allows
leaves them; checking only its blocks fixes those but not the false allows, which are the
costly error. `unsafe_only` at 0.25 is the cheapest rule near Opus (92.4 % at 11.3 %) and it
lets more unsafe actions through (11.0 %) than Jev alone (10.3 %). Nothing one-sided is
proposed.

## What changed

Nothing in code: `CascadeDecider` already takes the threshold as a parameter and ships none.
The confirmed rule, tau 0.45 with symmetric escalation, is the documented value to pass
(`docs/where-it-pays.md`); `benchmarks/cascade/confirm_cli.py` holds the confirmatory run.
