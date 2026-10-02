# Memory carry: a fact said in an earlier session, that the repository does not show (2026-10-02)

Development pilot, n = 1 per scene. Not a confirmation.

## Question

The person says something in passing in one session ("finance's macro reads this CSV by column
position"). A later, new session gets a task that tempts breaking it. Does Claude Code keep the
fact? Does sanchopanza's memory change that?

## Design (`benchmarks/memory_carry/`, 119b075)

- Eight scenes (`scenes.py`): column order, a legacy field, error wording, three log fields,
  string paging parameters, naive UTC, stdlib only, Python 3.8. Session 1 does a small task on a
  file and the fact is said in passing. Session 2, a new session (no `--resume`), gets a task on
  the same file that tempts breaking it.
- Arms:
  - `N` is Claude Code 2.1.285 as it ships, with its own auto memory on (it is by default).
  - `M` is the same plus sanchopanza's memory hooks as `install --memory` writes them, with
    the decider. The TypeSafe key reaches only the hook.
  - Both arms get the same prompts, tools (Bash, Read, Edit, Write, Glob, Grep), model
    (Sonnet 5.5) and caps.
- Checks fixed before any session (`tests/test_memory_carry.py`):
  - `task` exits 0 when session 2's task is done; two scenes have no task check.
  - `fact` exits 0 when the fact still holds.
  - The repository's tests are run too.
  - Per scene, a result that keeps the fact and one that breaks it, written by hand, are told
    apart.
  - No repository file, and no session-2 prompt, gives the fact away.

## Result (Sonnet 5.5, 32 sessions, 5.97 USD at list price, the subscription paid)

| | fact kept | tests | task | cost |
|---|---|---|---|---|
| N, Claude Code as it ships | 5 / 8 | 8 / 8 | 6 / 6 | 3.04 USD |
| M, with sanchopanza's memory | **7 / 8** | 8 / 8 | 6 / 6 | 2.93 USD |

- **The two discordant scenes both favour M.**
  - `naive`: N wrote `datetime.now(timezone.utc).isoformat()`, with an offset. M wrote the fact
    as a comment ("The warehouse loader rejects UTC offsets") and emitted naive UTC.
  - `fields`: N added a fourth ` | `-separated field. M put the request id inside the message.
- **`wording` fails in both arms.** M recalled the fact: its comment reads "Keep the 'Row N:
  missing email' prefix: support scripts grep for it". It kept the prefix and appended detail,
  but the check, fixed before the run, wants the exact message.
- **Claude Code's own auto memory** was on in every session: it created the project's memory
  folder and announced it at start. It saved nothing in any of the eight first sessions, so in
  `N` nothing carried.
- **M's memory gave the earlier request in all eight second sessions**:
  - seven at the first prompt (the decider; the prompt names the file);
  - one when the file was opened (`fields`).
- **Five scenes did not tempt Sonnet**: N kept the fact anyway in `columns`, `legacy`,
  `strings`, `stdlib` and `py38`. The pilot's power comes from three scenes.

What this does not show: with two discordant pairs, McNemar's exact p = 0.5. Direction only.
Rows are in `~/.cache/sanchopanza/memory-carry/2026-10-02-sonnet/carry.json`.

## Confirmation (sealed in fddff84 before its data; run 2026-10-02)

The run followed `prereg-confirm.md`:
- held-out scenes, repetitions 0 and 1;
- pilot scenes, one new repetition;
- Sonnet 5.5 on Claude Code 2.1.285, 96 sessions, 18.37 USD at list price;
- no pair excluded, no amendment.

| 24 pairs | fact kept | tests | task (20 with a check) | median cost M/N |
|---|---|---|---|---|
| N, Claude Code as it ships | 14 / 24 | 24 / 24 | 20 / 20 | |
| M, with sanchopanza's memory | **23 / 24** | 24 / 24 | 20 / 20 | 0.971 |

- **Primary test.** There were 9 discordant pairs, all for M, none for N. One-sided exact
  McNemar p = 0.0020.
- **Held-out scenes alone.** M kept the fact in 16 of 16 pairs, N in 10 of 16.
- **Tests and task.** Equal in both arms.
- **Verdict: confirmed on all four criteria.**
- **Where N broke the fact:**
  - `envvar` x2 and `rename` x2 (both renamed what ops or other repositories use by name);
  - `nulls` x2 (dropped the None keys);
  - `legacy`, `naive`, `fields` and `wording`.
- **M broke it once**, in `wording`: it kept the prefix and appended detail, as in the pilot.
- **The memory gave the earlier request in every M session**, and M's code cites the fact. For
  example: "Set by Ops under these exact names in every deployment; do not rename or prefix" and
  "Deprecated alias: three other repositories import make_client by name". The gain comes from
  the record's content, not from a hook that only makes the model more careful.
- **Claude Code's own auto memory** was on in all 48 runs and saved nothing in any first
  session.

Limits:
- One model, headless `claude -p`. Interactive sessions might save auto memory more often.
- The scenes are built for the case memory serves: a fact said earlier, not in the
  repository, that a later task tempts breaking.
- No placebo arm (a record unrelated to the task).

## Other models: Haiku 4.5 (`prereg-generalize.md`, amendment 1)

16 pairs (all 16 scenes, repetition 0), 5.30 USD at list price. `benchmarks/memory_carry/analyze.py`
gives the table.

| 16 pairs | fact kept | tests | task (13 with a check) | median cost M/N |
|---|---|---|---|---|
| N, Claude Code as it ships | 8 / 16 | 16 / 16 | 13 / 13 | |
| M, with sanchopanza's memory | 11 / 16 | 16 / 16 | 13 / 13 | 0.98 |

- **Does not hold.** There were 3 discordant pairs, all for M, but one-sided exact McNemar
  p = 0.125, above the 0.05 the prereg asks. Direction only.
- **Haiku breaks a fact it was given.** M gave the earlier request in all 16 second sessions, and
  Haiku still broke the fact in five of them: `fields`, `legacy`, `nulls`, `rename` and
  `wording`. Sonnet broke one in 24. Delivery is not enough on a small model; the check that v7
  adds at Stop is aimed at exactly this.
- **Claude Code's own auto memory saved twice, both times in M runs** (`naive`, `envvar`; files
  `warehouse_timestamp_format.md` and `ops_config_constraints.md`). It saved 0 of 16 times in N.

## Other models: Opus 5.5 (`prereg-generalize.md`, amendments 2 and 3)

16 pairs, 22.97 USD at list price.

| 16 pairs | fact kept | tests | task (13 with a check) | median cost M/N |
|---|---|---|---|---|
| N, Claude Code as it ships | 14 / 16 | 16 / 16 | 13 / 13 | |
| M, with sanchopanza's memory | **16 / 16** | 16 / 16 | 13 / 13 | 0.97 |

- **No room.** There were 2 discordant pairs (`fields`, `rename`), both for M; p = 0.25. N keeps
  nearly every fact already, which the prereg reports as "no room" and not as a failure.
- **Opus uses its own auto memory**, unlike Sonnet (0 of 48 runs): it saved in 7 of 32 first
  sessions, 3 in N and 4 in M. Even so, N broke two facts.
- **Across models:** the gain is largest where the model is mid-range.
  - Sonnet 5.5: 23/24 against 14/24, p = 0.002.
  - Haiku: 11/16 against 8/16; delivered facts still broken.
  - Opus: 16/16 against 14/16.
