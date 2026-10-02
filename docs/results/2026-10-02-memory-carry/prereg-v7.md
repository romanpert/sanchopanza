# Memory v7 (standing rules): written before its data (2026-10-02)

Sealed by the commit that adds this file. Code: branch `memoria-v7` at that commit.

## What changed against v6.2

1. **Standing rules.** Each sentence of the person's prompt is asked whether it is a lasting
   rule. The ones that are are kept verbatim and given at every session start.
2. **Audit at Stop.** The request's own diff (the files it wrote, plus the ones it created) is
   held against the rules it did not state. A rule judged broken and related sends the agent
   back once, quoting the rule.

Offline development numbers, with the decider's examples taken from domains no scene uses:
- **Extraction:** 16/16 rules found; 3/36 other scene sentences and 14/366 real SWE-chat
  sentences flagged.
- **Audit:** 15/15 breaks caught; 5/49 false on related pairs and 8/320 on unrelated ones.

## Runs (Sonnet 5.5, `claude -p`, the subscription pays)

| run | scenes | arms | repetitions | cap |
|---|---|---|---|---|
| `v7-cross` | the 8 cross-file scenes (`scenes_cross.py`, written before any session) | N, M, V | 0, 1 | 22 USD |
| `v7-all` | the 16 pilot and held-out scenes | V | 0 | 9 USD |
| `placebo` | the 16 pilot and held-out scenes | P | 0 | 8 USD |

The arms:
- **N** is Claude Code as it ships.
- **M** is memory with the standing rules off, which is v6.2.
- **V** is v7. Its store starts with 7 decoy rules from other scenes, never the scene's own fact
  or a near one (`carry.SAME`).
- **P** is v6.2 with the rule sentence of session 1 replaced by a neutral one.

## Criteria

1. **Primary (cross-file).** V keeps the fact in more of the 16 cross pairs than M, with a
   one-sided exact McNemar p < 0.05.
2. **V against N** on the same pairs: reported with the same test, not a criterion.
3. **No harm (pilot and held-out, repetition 0).**
   - V keeps the fact in at least 14 of 16 (M kept 15 of these 16 in the confirmation).
   - V's tests and task each fall no more than 2 below M's in the confirmation, repetition 0.
4. **False sends-back.** A V second session sent back by a rule other than its scene's own
   counts as false. Criterion: at most 4 of V's 32 second sessions.
5. **Reported, not criteria:**
   - the paired median cost V/M;
   - how often V was sent back, and what happened after;
   - `wording` under V;
   - P against N on fact kept (the placebo: if P keeps more than N, the hook's presence and
     not the rule's content would be doing work).

## Exclusions

Usage limit, or a session that ended before its result, means NOT RUN. No retries, except a
pair cut by a runner bug, which runs again whole and goes in an amendment.
