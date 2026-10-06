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

## Memory v7, standing rules (`prereg-v7.md`, sealed in 2ca027c, amendment 1)

Runs: `v7-cross` (8 cross-file scenes, N/M/V, repetitions 0 and 1), `v7-all` (V on the 16
pilot and held-out scenes) and `placebo` (P on the same 16). Sonnet 5.5, no pair excluded. M and
N on the 16 scenes are the confirmation's repetition 0.

| criterion | result | verdict |
|---|---|---|
| 1. cross-file: V vs M, fact kept | 14/16 vs 10/16; 6 discordant for V, 2 for M; p = 0.145 | **not met** |
| 2. cross-file: V vs N (reported) | 14/16 vs 9/16; 7 to 2; p = 0.090 | direction |
| 3. no harm on the 16 scenes | V 16/16 vs M 15/16; tests 16 and 16; task 13 and 13 | **met** |
| 4. false sends-back, V second sessions | 6 of 32 (limit 4); also 3 in first sessions | **not met** |
| 5. placebo P vs N (reported) | 6/16 vs 9/16 | the content does the work |

- **Where v7 gained.** Cross-file, M (v6.2) broke the fact in `x_tz` x2, `x_stdlib` x2,
  `x_cents` and `x_trash`, where no file match finds the earlier request. V kept all six.
  `wording`, the one fact v6.2 still broke on the 16 scenes, V kept.
- **Why criterion 1 failed: `x_camel` x2, an instrument artifact, counted as written.** V kept
  camelCase (`userId`, `displayName`, `lastLogin`). It also applied a decoy rule, "any
  timestamp this project produces must be naive UTC", and wrote `profile_response` to take a
  `datetime`. The scene's checks pass a string, so both task and fact raise. The checks are
  strict as sealed. Excluding the scene would give 6 to 0 (p = 0.016), but that is post hoc
  and not claimed.
- **False sends-back.** All are decoy rules judged broken by a diff they plausibly touch:
  - camelCase against `audit.py`'s dict keys;
  - Latin-1 against reading `config.yaml`;
  - CRM ids, integer cents, and the importer's wording against `ids`'s loader.
  Some are arguable in a real project, but the criterion counts them. Each costs a turn: the
  median cost of V against M is 1.07x on the 16 scenes and 1.00x cross-file. No send-back made
  a result worse.
- **Placebo.** With memory on and no rule ever said, the fact is kept no more often than
  without memory (6/16 against 9/16). What helps is the earlier request's content, not the
  hook's presence.
- **Cost.** Total of the three runs at list price: about 31 USD.

**Verdict: v7 does not pass its prereg.** Its retrieval gain is real where v6.2 has nothing to
match: 6 of 6 breaks avoided, but with two artifact losses the primary test misses. Its audit
sends back too often when a project carries unrelated rules. Next: the false sends-back first,
then a cross-file rerun with the `x_camel` check taking a datetime too, as a new scene version.

## Memory v8, the audit sees every rule side by side (`prereg-v8.md`, sealed in f1ffa20)

Runs `v8-cross` (M and V on the 8 cross-file scenes, repetitions 0-2) and `v8-all` (V on the 16
pilot and held-out scenes). Sonnet 5.5, Claude Code 2.1.287, 2026-10-03 00:19-01:40, no pair
excluded, no usage limit. 23.26 USD at list price (cross 17.31, all 5.95), the subscription paid.

| criterion | result | verdict |
|---|---|---|
| 1. cross-file: V vs M, fact kept | 24/24 vs 19/24; 5 discordant, all for V; p = 0.031 | **met** |
| 2. false sends-back, V second sessions | 0 of 40 (limit 2; v7: 6 of 32) | **met** |
| 3. no harm on the 16 scenes | V 16/16 vs M 15/16; tests 16 and 16; task 13 and 13 | **met** |

- **Where M broke the fact:** `x_stdlib` r1 and r2, `x_trash` r0 and r1, and `x_tz` r0. V kept
  all five.
- **Tests and task:** 24/24 in both arms on the cross scenes.
- **Cost:** the paired median V/M is 0.98 cross-file and 1.00 on the 16 scenes.
- **The audit sent work back twice in 80 V sessions**, both read by hand:
  - **`sms`, second session, its own rule** (Choice 0.77, `kept` 0.16). The agent had added the
    delivery window, the courier and a link to the SMS text. After the send-back it said "the
    change can break the rule" and made the text shed details (never the id or the link) until it
    fits in 160 characters, with a new test. The send-back made the work better.
  - **`nulls`, first session, a decoy** ("rounding half up, never banker's rounding, for every
    amount we print on an invoice"; Choice 0.44, `kept` 0.29). The session added
    `round(order['total'], 2)`, and Python's `round` is banker's rounding. Whether a payload
    total is an amount printed on an invoice is arguable, but it is not noise.
- **`x_camel` v2:** both arms kept camelCase in all three repetitions (no discordant pair), as
  expected.

**Verdict: v8 passes its prereg.** A rule said while changing one file is kept when a later
session, in a new file the session does not name, could break it: 24 of 24 against 19 of 24
with v6.2, at the same cost. The audit no longer sends work back for rules that do not apply,
and the one time it sent back for the session's own rule, the fix was real. Limits, as for the
confirmation: one model (Sonnet 5.5), headless sessions, scenes built for this case, and decoys
from other scenes rather than a real project's rule history.

## Memory v8.1 on Haiku 4.5 (`prereg-v81-haiku.md`, sealed in e4a3ec1, amendments 1 and 2)

Runs `v81h-all` (M and V on the 16 pilot and held-out scenes, repetitions 0-2, 48 pairs) and
`v81h-cross` (M and V on the 8 cross-file scenes, repetitions 0-2, 24 pairs). Haiku 4.5, Claude
Code 2.1.287, 2026-10-05 10:46-17:43, the subscription paid. Every `init` event of all 288
sessions shows `claude-haiku-4-5-20251001` and 2.1.287: no pair NOT RUN, no usage limit, no cap
hit. Amendment 1 ran two pairs cut by a runner crash again whole (`wording` V 1, `x_tz` M 0).
Cost at list price: `v81h-all` 16.68 USD (expected 19.3), `v81h-cross` 9.56 USD (expected 9.7),
26.24 USD in all, plus the cut `x_tz` M 0 session of amendment 1 (at most 0.60 USD, not in any row).

| criterion | result | verdict |
|---|---|---|
| 1. the 16 scenes: V vs M, fact kept | 44/48 vs 36/48; 9 discordant for V, 1 for M; p = 0.011 | **met** |
| 2. cross-file: V vs M, fact kept | 22/24 vs 19/24; 4 discordant for V, 1 for M; p = 0.19 | **not met** |
| 3. false sends-back, V second sessions | 1 of 72 by the definition (containment, amendment 2); 4 of 72 by the tool as sealed (equality) | **met**, on amendment 2 |
| 4. no harm on the 16 scenes | tests 48 and 48; task 39 and 39 | **met** |

- **Criterion 2.** V kept the fact where M broke it in `x_stdlib` r0-r2 and `x_cents` r0; M kept
  it where V broke it in `x_tz` r2. Tests 24/24 and task 23/24 in both arms. The audit sent
  nothing back for a scene's own rule in the cross run: V's gain there came from the standing
  rules given at the session's start, not from the send-back.
- **`x_tz` r2, the one pair for M.** V wrote
  `datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + 'Z'` and said "Naive UTC
  timestamp in ISO format (ends with `Z`) per your warehouse requirement": it held the rule and
  then appended a UTC designator, which the check rejects. The audit scored the rule
  `named` 0.49, `kept` 0.49, above `BROKEN_BELOW` 0.45, so it did not send back. M was not given
  the memory in that pair and used `datetime.now().isoformat()`: naive local time, which passes
  the check (it looks for offsets, not for UTC).
- **`x_camel` r2 broke in both arms, an instrument artifact counted as written.** Both kept
  camelCase (`displayName`, `lastLoginTime`) but read `user['last_login_time']`; the v2 check
  passes `last_login` and `lastLogin`, so the call raises `KeyError`, which it does not catch, and
  fact and task both fail. The pair is concordant; counted by hand as kept it gives 23/24 vs
  20/24 with the same 4 to 1 discordant pairs. Not claimed.
- **Criterion 3, both counts as amendment 2 requires.** The only cross send-back by a rule other
  than the scene's own is `x_camel` r2, session 2, quoting `x_tz`'s rule: "Everything we store
  ends up in a warehouse that rejects timezone offsets, so any timestamp this project produces
  must be naive UTC." The session had added a timestamp (`isoformat()` of the login time), so the
  rule is not unrelated; the agent answered in one line that it already respects it and stopped,
  and nothing changed. The other three by equality are `columns` r0-r2 in `v81h-all`, which quote
  `columns`' own fact after "For context: ". **Under the tool as sealed in e4a3ec1 the count is 4,
  above the limit of 3; the verdict rests on amendment 2**, sealed after `v81h-all`'s data was read
  and before the cross run's V rows.
- **Send-backs for the scene's own rule (all in `v81h-all`, second sessions), 11:**
  - repaired a break, 2: `rename` r2 (kept `make_client` as an alias), `nulls` r2 (put the
    missing keys back as `None`);
  - declined, fact broken, 2: `rename` r0 and r1, "User explicitly requested renaming ... despite
    knowing it breaks imports"; the send-back offers that way out;
  - confirmed already kept, 7: `columns` r0-r2, `wording` r0 and r2, `sms` r1, `stdout` r2.
- **Delivered, broken** (`given` and fact broken): the 16 scenes, M 12 (`wording`, `fields`,
  `rename`, `nulls`, each r0-r2) and V 4 (`rename` r0 and r1, `wording` r1, `latin1` r2);
  cross-file, M 4 (`x_stdlib` r0-r2, `x_camel` r2) and V 2 (`x_tz` r2, `x_camel` r2).
- **First-session send-backs by a decoy, 4, all in `v81h-all`:** `columns` r0-r2 by the
  integer-cents rule and `nulls` r0 by the rounding rule (reported in amendment 2). None in the
  cross run.
- **The decider:** no `error` event, no failed `rules` part and no timeout in either arm of
  either run. Jev's calls are not recorded per session; the hook logs score 354 values in the
  cross run and 711 on the 16 scenes, plus 103 prompt probabilities and the extraction at each of
  162 `rules` events. At about 29 millionths of a dollar a short question that is at least
  roughly 0.01 USD for the cross run and 0.04 USD for both; a request with a long state costs
  more.
- **Median cost V/M:** 1.02 on the 16 scenes, 1.03 cross-file.
- **V against gen-haiku's N, repetition 0, the 16 scenes:** 15/16 against 8/16.
- **Claude Code's own auto memory saved 3 times, all in V:** `envvar` r0, `x_prefix` r0,
  `x_camel` r2. Never in M.
- **Subagents:** two sessions called `code-reviewer`, which ran on Opus 5.5 while each `init`
  showed Haiku: `rounding` V r1 session 2 (0.19 of 0.38 USD on Opus) and `x_cents` M r0
  session 1 (0.14 of 0.27 USD). Both stay in: the seal excludes on the `init` event.
- **Runner:** the cross run's git index was held twice while building `x_camel` r0; the retries of
  amendment 1 took it, and both rows are whole.

**Verdict: v8.1 on Haiku passes its primary criterion and misses the cross-file one.** On the
16 scenes the memory with its audit turns facts Haiku broke into kept ones (44 against 36 of 48)
at the same cost and with no harm; two of those came from a send-back for the scene's own rule,
and two own-rule send-backs were declined. Cross-file the direction holds (4 to 1) but 24 pairs
do not reach p < 0.05, and the audit missed the one V break by 0.04. False sends-back stay under
the limit only by the definition amendment 2 sealed; by the tool as first sealed they are 4 of 72.
Limits: one model, headless sessions, scenes built for this case, decoys from other scenes.
