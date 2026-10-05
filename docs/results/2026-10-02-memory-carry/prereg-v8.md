# Memory v8 (the audit sees every rule side by side): written before its data (2026-10-02)

Sealed by the commit that adds `prereg-v8.sha256`. Code: branch `memoria-v8` at that commit.

## What changed against v7

v7 failed its prereg on two counts (`prereg-v7.md`): the cross-file test missed (p = 0.145, two
`x_camel` pairs lost to an instrument artifact) and it sent back 6 of 32 second sessions for a
decoy rule. v8 changes two things and nothing else:

1. **The audit at Stop is a cascade.** One Choice holds every rule side by side, with where each
   was said, plus `none` (`points.rules.questions_for_rules`). `kept` is asked only of a rule
   that Choice names at 0.4 or more, and the agent is sent back when `kept` < 0.5. The v7 three-way
   relation gate is gone.
2. **`x_camel` checks, version 2.** The last login may come as text or as a datetime
   (`scenes_cross.XCAMEL_CALL`). Rescored with v2, all six v7 sessions of `x_camel` (N, M and V)
   keep camelCase, so the scene now gives no discordant pair; it stays in as written.

3. **Where each decoy was said.** V's store now seeds each decoy with the files its own scene
   changes in session 1 (`carry.said_while`), as `memory_rules.extract` would record them and as
   the audit bench measured. v7 seeded `app/other.py` for every decoy.

After an adversarial review (7587968), rule texts in the Choice's options are masked like any
state (none of the bench's rules holds a secret, so the measured question is unchanged), and a
named rule that `kept` failed on leaves the request to be asked again.

Extraction of standing rules and what is given at session start are v7's, unchanged.

## Development numbers (offline, all on data already seen)

`benchmarks/memory_carry/audit_bench.py`, 175 recorded carry sessions (pilot, confirmation,
Haiku, Opus, v7, placebo), each against its own rule and the seven decoys `carry.decoys` seeds:

| audit | own breaks caught | sessions sent back for a decoy | sent back for an own rule kept |
|---|---|---|---|
| v7 | 43 / 43 | 31 / 175 | 11 / 132 |
| v8 | 43 / 43 | 0 / 175 | 10 / 132 |

- Eleven decoy pairs, where a session's new annotations really break "Production still runs
  Python 3.8", are counted as neither. The scenes' own repositories already use 3.10
  annotations.
- The 43 breaks were read by hand.
- The 10 own-rule sends-back are borderline cases, read by hand:
  - an SMS text that grew with a tracking URL;
  - a CSV column added at the end;
  - `log.info` under a no-stdout rule.
- A generative second judge was measured and did not pay. Haiku caught 42/43 with 18 own-rule
  sends-back. Sonnet caught 42/43 with 6 own-rule sends-back, at about 250 times Jev's price.

## Runs (Sonnet 5.5, `claude -p`, the subscription pays)

| run | scenes | arms | repetitions | cap |
|---|---|---|---|---|
| `v8-cross` | the 8 cross-file scenes, `x_camel` v2 | M, V | 0, 1, 2 | 20 USD |
| `v8-all` | the 16 pilot and held-out scenes | V | 0 | 8 USD |

- M is v6.2, as in v7's prereg.
- V is v8, with the same 7 decoys seeded as in v7.
- N is not run. v7's N on the cross scenes is reported beside the result for reference, and is
  not a criterion.

## Criteria

1. **Primary (cross-file).** V keeps the fact in more of the 24 cross pairs than M, with a
   one-sided exact McNemar p < 0.05.
2. **False sends-back.** A V second session sent back by a rule other than its scene's own counts
   as false. Criterion: at most 2 of V's 40 second sessions (24 cross and 16 in `v8-all`).
   v7's rate was 6 of 32.
3. **No harm (`v8-all`).**
   - V keeps the fact in at least 14 of 16.
   - V's tests and task each fall no more than 2 below M's in the confirmation, repetition 0.
4. **Reported, not criteria:**
   - sends-back for the scene's own rule, and what happened after each;
   - the median cost V/M on the cross pairs;
   - every V session in which a decoy rule was sent back, read by hand and quoted.

## Exclusions

A usage limit, or a session that ended before its result, means NOT RUN. Nothing is retried,
except a pair cut by a runner bug, which runs again whole and goes in an amendment.

## Order and coordination

These runs start only after two others are over: the adoption chain for memory amendment 6,
part A, and indagis-e3's Haiku rerun of adoption phase A. All three share the weekly limit of
one subscription.
