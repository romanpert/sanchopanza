# The Jev > Sonnet 5 cascade: the registered primary verdict, run at last (partial)

P1, P2 and P9 of the 2026-09-25 cascade registration (`../2026-09-25-cascade/prereg.md`,
`prereg-codex.md`) compare the cascade with `claude-sonnet-5`. Its batches were cancelled that
night and the three were never run. They ran on 2026-09-27 with Sonnet through the Claude Code
CLI (`prereg-cli.md`, registered before any Sonnet call; the only change is the path). Jev's
answers replay from `fixtures/cascade-jev.jsonl`; Sonnet's sessions are cached in
`fixtures/cli/cascade-sonnet.jsonl`. `benchmarks/cascade/sonnet_cli.py` writes `analysis.json`;
`tests/test_cascade_sonnet.py` pins it.

## Result: partial, as the registration defines it

Held-out halves, tau derived on each set's derivation half by the registered rule:

| set | tau* | Jev alone | Sonnet 5 alone | **cascade** | diff (95 % CI) | cost / Sonnet | escalated | verdict |
|---|---|---|---|---|---|---|---|---|
| **P1** R-Judge, 274 | 0.80 | 86.5 % | 92.3 % | **92.3 %** | 0.0 (0.0, 0.0) | **57.7 %** | 159 | **fails on cost** |
| **P2** register, 172 | 0.90 | 83.1 % | 80.2 % | **81.4 %** | +1.2 (-1.2, +3.5) | **46.0 %** | 82 | holds |
| **P9** ATBench-Codex, 242 | 0.00 | 78.5 % | 78.9 % | **78.5 %** | -0.4 (-4.1, +3.7) | **0.4 %** | 0 | holds |

- **P1 fails**, on cost alone: the cascade matches Sonnet exactly on R-Judge's held-out half but
  pays for 159 escalations of 274. It is the same shape as the Opus arm of 2026-09-25 (tau 0.80,
  57 % of the cost): on R-Judge the frontier model is about six points better than Jev, and the
  registered rule ("reach X alone's accuracy on the derivation half") buys its last case with
  many escalations. The registered split is on the unlucky side: over 500 random re-splits
  (secondary, registered) the median cost ratio is **47.7 %**, under the bar, with the 95th
  percentile at 54.7 % and a median accuracy difference of -0.35 points. The verdict is the
  registered split's and stands; the re-splits say it is a near miss, not a clear failure.
- **P2 holds**, and Jev alone is the best of the three on the register (83.1 % against Sonnet's
  80.2 %): closed-vocabulary classification is where the typed model is strongest.
- **P9 holds** with tau* = 0: on Codex's derivation half Jev alone already reached Sonnet, so the
  registered rule escalates nothing. The cascade is Jev, at 0.4 % of Sonnet's cost and 0.4 points
  below it on the held-out half, well inside the interval.
- Registered verdict for P1 and P2: **partial**. Published as it fell.

All cases: Sonnet 94.75 % on R-Judge (571), 82.9 % on the register (298), 78.2 % on Codex (499
answered, 1 cancelled). False allows on R-Judge's held-out half: 10.6 % for Jev, Sonnet and the
cascade alike; false blocks 16.5 % for Jev, 4.5 % for Sonnet and the cascade.

## Descriptive only: the threshold confirmed with Opus

`../2026-09-27-cascade-frontier/` confirmed tau **0.45** on ATBench-Codex against Opus 5. That tau
was chosen on R-Judge, so applying it to R-Judge here is not a test. Read descriptively, on
R-Judge's held-out half against Sonnet:

| tau | cascade | Sonnet alone | cost / Sonnet | escalated |
|---|---|---|---|---|
| 0.35 | 92.3 % | 92.3 % | 25.3 % | 69 |
| 0.45 | 92.7 % | 92.3 % | 29.9 % | 82 |
| 0.65 | 92.3 % | 92.3 % | 39.9 % | 110 |

The same lesson as the Opus frontier: accuracy is flat from 0.35 up, and a rule that asks for
"equal on the derivation half" pays for the last case. A rule of "within half a point", fixed in
advance, is what the Codex confirmation used.

## What this changes

Nothing in code: `CascadeDecider` ships no threshold. The documented value stays 0.45, confirmed
against Opus on unseen data; against Sonnet it is untested on unseen data. The honest summary
across both frontier models and three sets: where the frontier model is clearly better than Jev
(R-Judge), a cascade reaches it but the registered derivation rule overpays; where it is not
(register, Codex), Jev alone or nearly alone is as good at a fraction of a percent of the cost.

## Cost and reproducing

1,369 Sonnet sessions (2 cancelled after a retry), **17.42 USD** at list price against the
subscription (the pilot of 3 sessions: 0.05 USD), 0 USD against any key.

```bash
python benchmarks/cascade/sonnet_cli.py --rjudge R-JUDGE-CLONE --register REGISTER.json \
    --codex ATBENCH-CODEX-test.json      # free, from the session cache
```

R-Judge (at the registered commit), ATBench-Codex and the register are not redistributed.
