# Compaction inside Claude Code: native summary against sanchopanza's pruning

## Correction (2026-09-29): the autopilot's phase B never saw the masked history

**The 12 of 12 against 6 of 12 below does not measure masking.** Re-reading this run's saved
transcripts (`../2026-09-28-context-lean/exploratory/`) showed that in every arm-A task the
model received the **unmasked** history in phase B:

- Phase B ran as `claude -p --resume`, and Claude Code rebuilds a resumed history along the
  transcript's `parentUuid` links. Our compaction hook returned the engine's own message objects
  (with their `handle`) for the messages it did not change, and the entries Claude Code wrote
  after the compaction chained to the pre-compaction entries. The chain phase B loaded skipped
  the compaction: 0 stubs and no `compact_boundary` on it in 12 of 12 tasks (the stubs were in
  the file, off the chain).
- The token counts agree: A's first phase-B context was 55.3k tokens on average, the same as at
  the end of phase A (55.5k), while N's summary brought it to 43.4k.
- So arm A compared **"no compaction, plus recall"** against the native summary. It is no
  evidence that masking keeps facts. No A success needed recall either: every planted fact was
  already in the unmasked context.
- The **+13.4 % input tokens** did not come from recall as written above. Phase A cost A +2.24M
  tokens over N, mostly three sessions that read one file per call (run-to-run variance), and
  recall about 0.35M; compaction plus phase B were 0.68M *lower* than N's. The recall
  injections were all in phase B, not "in both phases".
- A possible second confound, found while building the next run: the child sessions inherited
  environment variables of the coordinating Claude Code session (`CLAUDE_EFFORT=medium` and
  others). Both arms had the same environment, but the setting was not the default.

The bug is fixed (`compact_hook.ts`: returned messages never carry the engine's `handle`,
`tests/test_autopilot_compaction.py::test_returned_messages_never_carry_the_engine_handle`)
and checked end to end: with the fix a resumed session starts from the masked history (57.1k
tokens against 85.8k before the fix, `../2026-09-28-context-lean/probe/`). The masking
question is measured again, with compaction firing mid-session, in
`../2026-09-28-context-lean/`. Everything below is left as it was written, for the record.

## Summary

This is an end-to-end test inside Claude Code 2.1.282 (headless, agent Haiku 4.5), run
through our own evaluation harness. We wrote 12 generated Python tasks. In each one the agent
works through a first phase, the conversation is compacted, and then it makes a change that
needs facts seen before the compaction. Success means the hidden tests pass. Every round was
pre-registered in `prereg.md` before it ran.

**The autopilot** (`sanchopanza install --autopilot`: arrival gate, recall, and masking
compaction) **finished 12 of 12 tasks; Claude Code's native `/compact` finished 6 of 12**
(Fisher's exact test, two-sided p = 0.014). The facts that exist only in command output
survived more often with the autopilot: the probe's error code 12/12 against 8/12, the release
token 12/12 against 11/12. After compaction the agent re-read 0.25 files per task against 6.
**It did not save tokens.** The autopilot used 13.4 % more input tokens and cost 13.5 % more
(3.36 against 2.96 USD at list price, true cost), so the token hypothesis failed as registered.
Jev's share was 0.011 USD.

**Why it worked.** Masking keeps every assistant message and the results of the last turns
verbatim. It stubs older results into an archive, with no model call. The native summary
rewrites everything into about 4k tokens, and in 4 of 12 summaries the probe code was not
kept. The agent almost never read the archive: the facts it needed were already in the turns
masking keeps. Recall injected about 25k characters per task, mostly on tool calls, in both
phases. That, and not the compaction, is where the extra tokens went.

**What this does not show:**

- **The tasks favour the mechanism.** We wrote them, and their one-shot facts come at the end
  of the first phase, where keeping recent turns saves them. A fact made early and needed late
  would have to come back through the archive and recall, and that path was not tested.
- **N was not paired with A.** For t01-t06, N is round 1's sessions: independent of A's, and
  paired only by task.
- **One agent model**, Haiku 4.5, and one Claude Code version.
- **The arrival gate never fired.** No tool result reached its 6,000-character threshold, so
  whether Claude Code applies a cut tool output (`updatedToolOutput`) for Read and Bash is
  still untested end to end.
- **The cost figures were corrected after round 2.** Resumed sessions report cumulative totals
  ("Cost correction" below). Every cost here is the corrected one.

These numbers are not directly comparable with numbers obtained through the API.

Rounds: round 1 (native against rules-only pruning, which always fell back to the native
summary), round 2 (autopilot against native, t01-t06) and round 3 (t07-t12, pooled n = 12).
Details of each follow the amendments.

Pre-registered in `prereg.md` (sha256 in `prereg.sha256`, pinned by
`tests/test_context_e2e.py`) before any paid call. Results below the amendments.

## Amendments (written after the pilot, before any other task ran)

**A1, harness only.** The pilot (`t01-orders`, arms N and R) confirmed the mechanics: N's
forked session holds a `compact_boundary` and a summary; R's hook loaded, ran, exited 3
(freed 5 %, below the 25 % minimum) and Claude Code wrote its own summary. Two reading bugs in
`transcripts.py` were fixed and the pilot rows recomputed from the saved evidence
(`run_e2e.py recollect`): the compaction kind now looks only at the entries before phase B's
prompt (a phase-B `grep` output had been counted as a stub), and phase B is located by its
prompt rather than by a line count. One descriptive measure is added: `leftover_hits`, phase-B
tool results that contain the hook's `--out` file (see "The leftover file" below). Tasks,
prompts, arms, primary measures and decision rules are unchanged.

**A2, budget.** The pilot cost 1.01 USD list for one task with two arms (phase A 0.13, N
0.42, R 0.46: the native `/compact` alone is 0.15, as much as phase A), against 0.44
estimated. *[Corrected after round 2, see "Cost correction": those figures summed cumulative
totals. The pilot really cost 0.44 USD, and a native `/compact` about 0.02.]* 16 tasks x 4 arms cannot fit in 12 USD. So the run is restricted to **tasks
t01-t06**: N and R now (about 6 USD in all), leaving about 5 USD under the 11 USD stop for S
and F on the same six tasks later. Decided from the pilot's cost alone, before any other task
ran. With six tasks, only large differences are readable.

**A3, instructions.** Arms S and F are prepared and not run (no Jev key in this sitting; see
`prereg.md`).

## Setup, as run

Claude Code 2.1.282 headless, agent `claude-haiku-4-5-20251001`, run through our own
evaluation harness, per session `--max-budget-usd 0.40`,
`--setting-sources project --strict-mcp-config --permission-mode dontAsk`. One phase A per
task, forked into every arm (`--resume A --fork-session "/compact"`), then phase B on the fork.
R loads the plugin written by `sanchopanza install --compact --plugin-dir` through
`--plugin-dir`, with `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`; no `~/.claude` settings were
touched and no marketplace was registered (checked before and after). Six tasks, all with a
valid phase A (both one-shot tools consumed, visible suite green): phase A median 89.5 s,
0.134 USD, context 55k tokens at its end.

## Results (tasks t01-t06, arms N and R)

| | N native | R rules (as installed) |
|---|---|---|
| success (all hidden + visible tests) | **2/6** [9.7 %, 70.0 %] | **3/6** [18.8 %, 81.2 %] |
| fact `token` (command output only) | 5/6 | 6/6 |
| fact `probe` (failing command output only) | 3/6 | 5/6 |
| fact `window` (re-readable constant + helper) | 3/6 | 4/6 |
| visible suite | 6/6 | 6/6 |
| what the compaction was | summary 6/6 | **fallback 6/6** (exit 3, freed 4.8-5.7 %), then summary |
| phase B input tokens, sum (median) | 1,683,925 (271,060) | 3,038,661 (484,840) |
| phase B first-call context, median | 42,587 | 42,525 |
| phase B output tokens, sum | 20,403 | 24,539 |
| phase B turns, median | 22.5 | 30.5 |
| re-reads of phase-A files in phase B, mean | 5.00 | 6.33 |
| Grep/Glob in phase B, mean | 0.33 | 1.00 |
| archive reads / one-shot re-runs / leftover-file hits | 0 / 0 / 0 | 0 / 1 / **1** |
| cost per task, compaction + phase B (USD list, **corrected**) | 0.103 (0.022 + 0.081) | 0.134 (0.022 + 0.112) |
| whole task incl. shared phase A (USD, corrected) | 0.236 | 0.267 |
| wall time, compaction / phase B, median | 38.6 s / 46.8 s | 35.3 s / 67.1 s |
| Jev USD | 0 | 0 |

Intervals are 95 % Wilson. Numbers from `analysis.json`, computed by `analyze.py` from
`phase-a.jsonl` and `runs.jsonl`.

### Hypotheses

- **H1 (S against N) and H2 (S against F): not tested.** Arms S and F were not run (A3).
- **H3 (R against N): does not hold.** The success part holds (3 >= 2 - 1); the token part
  fails (3.04 M against 1.68 M phase-B input tokens). **But R never pruned**: its hook exited 3
  in all six tasks and Claude Code summarised, exactly as in N. So H3 compares two samples of
  the native summary, and the differences between the columns (one success, 1.35 M tokens,
  8 turns) are run-to-run variance of the same mechanism plus one side channel (below). The
  first-call context after compaction is the same in both (42.5k tokens, of which the summary
  is ~4.4k: `postTokens` 4,303-4,425 against `preTokens` 54,914 in the pilot).
- **H4 (re-reads): R 6.33 against N 5.00 per task**, paired mean difference +1.33, with the
  same caveat. Every session re-read 2-11 files it had already read.

The prediction in `prereg.md` held for the rules arm, more strongly than stated: on this
phase A the rules find one superseded read and nothing else (pilot: 22 of 23 calls kept,
`rules_only` 12, `small` 7, `error` 2, `recent` 1), so 25 % is out of reach.

### What the native summary loses (12 compactions, N and R pooled)

Read from the summary text itself (`summary_keeps` in each row):

| planted fact | carried by the summary | test passed in phase B |
|---|---|---|
| release token (command output) | 9/12 | 11/12 |
| probe error code (failing command output) | 9/12 | 8/12 (probe tests) |
| probe tolerance | 9/12 | |
| helper name / window module | 11/12 / 11/12 | 7/12 (window test) |

- **Every probe failure (4/12) is the error code missing from the `GuardError` message**; in
  three of them the summary did not carry the code. The failing command's output is what the
  summary drops most, and it is the one fact that cannot be had again.
- In t04-N the agent said so and did not guess: "I'm unable to locate the release token from
  the earlier session. The summary mentions it was issued but the actual value isn't
  available". That is what the prompt asked for.
- **The window failures (5/12) are not memory**: the agent used the decoy `GRACE_NOTICE_DAYS`
  (4) or imported `GRACE_WINDOW_DAYS` from the wrong module (1), after re-reading files. A
  harder-than-intended decoy for Haiku, the same in both arms.
- The native `/compact` itself costs **0.019-0.026 USD** on Haiku (one call, ~56k tokens in,
  mostly cache reads). *Corrected*: this section first said 0.148-0.164, which was the
  cumulative session cost including phase A. A pruning compaction that does not fall back
  makes no model call.

### The leftover file (a side channel, and a bug)

In t01-R phase B the agent ran `grep -r "PRB-" .` and matched
`.sanchopanza/compact-<session>.json`: the whole conversation, which `sanchopanza compact
--out` writes into the project directory and **leaves there even when it exits 3 and the hook
falls back** (the archive is written too, before the minimum-reduction check). That is how R
passed t01 although its summary, like N's, lacked the code. Scored as it ran (prereg) and
counted as `leftover_hits` (1 of 6 R sessions). Minimal repro, no model, no key: pipe
`{"messages": [...]}` with two `Read`s of the same file (3,000- and 30,000-character results)
and six short text messages into

    sanchopanza compact --stdin --arm rules --provider null --session s --out .sanchopanza/compact-s.json

It exits 3 ("freed 9 %, below the 25 % minimum"), yet `./.sanchopanza/compact-s.json` holds
every message verbatim and `./.sanchopanza/archive/s/u0.txt` exists.
`tests/test_context_e2e.py::test_wrapper_runs_the_rules_arm[1-3]` goes through the same path.
Consequences: an unredacted copy of the session (redaction applies only to what goes to Jev)
sits in the repository where `git add .` picks it up, and after a fallback the next phase can
recover what the summary dropped, which flatters any arm that falls back.

## Failures, one line each

| task | arm | failed | diagnosis |
|---|---|---|---|
| t01 | N | probe | summary carried neither code nor tolerance; `GuardError` raised without `PRB-9015` |
| t02 | N | probe, window | summary lacked the code; used `GRACE_NOTICE_DAYS` |
| t02 | R | window | used `GRACE_NOTICE_DAYS` |
| t04 | N | token, probe, window | summary lacked the token; agent declined to guess it; guard and deadline wrong too |
| t04 | R | window | used `GRACE_NOTICE_DAYS` |
| t05 | N | window | imported `GRACE_WINDOW_DAYS` from `pkg.limits`; it lives in `pkg/audit.py` |
| t06 | R | probe | summary lacked the code |

## Spend

Claude, at list price: **2.22 USD** at true cost (phase A 0.80, N 0.62,
R 0.80), ceiling 12.00, stop 11.00. Jev: 0. *Corrected*: this section first said 5.69 USD
(phase A 0.80, N 2.35, R 2.54), which summed three cumulative totals per arm; see "Cost
correction". The gates were therefore conservative, never lax.

## Running S and F later

With the owner's key in the runner's environment only:

    TYPESAFE_API_KEY=... python docs/results/2026-09-28-context-e2e/run_e2e.py run --arms S,F
    python docs/results/2026-09-28-context-e2e/analyze.py

It reuses the six phase A sessions and snapshots (forks, as N and R did), writes the key to a
file under `~/.cache/sanchopanza/context-e2e/` that only the hook's wrapper reads (the session
never carries it) and deletes it at the end, caps Jev at 0.05 USD per compaction and launches
no S/F session past 0.45 USD of Jev. (Its gate still sums the old overstated measure; with
true costs S and F would cost about 1.6 USD for six tasks.) Decide first on the leftover-file bug: fixed in `src/`, or kept and
reported (it favours any arm that falls back).

## Cost correction (found after round 2, applies to every round)

Claude Code's result JSON under `--resume` (with or without `--fork-session`) reports
`total_cost_usd` and `modelUsage` **cumulative over the conversation**, phase A included, while
`usage` covers only that invocation, and a `/compact` invocation reports `usage` all zero
although its summary call is in `modelUsage`. Checked on this run's saved files (`costs.py`):
on t01, native compaction's `total_cost_usd` 0.1553 = phase A 0.1319 + one summary call 0.0234;
arm A's `/compact` "cost" 0.1289 = its phase A 0.1289 exactly, with zero turns.

The earlier figures summed the three calls, counting phase A two or three times. The true cost
of one task in one arm is the last call's `total_cost_usd`; its input tokens are the last
call's `modelUsage` (this also counts the native summary call, which `usage` leaves out).
Round 1's phase-B token figures come from `usage` and stand. Amendment R3 registered the
corrected measure before round 3 ran; `costs.py` and `run_round2.py collect` use it.

## Round 2: the autopilot (A) against native `/compact` (N), tasks t01-t06

Registered as amendment R2 (`prereg.md`). Run by the coordinating agent with the owner's key;
`runs-r2.jsonl`, `analysis-r2.json`. N is round 1's N (its own phase A, forked compaction):
**not paired** with A, which ran its own phase A with the autopilot on.

**Two invalid pilot attempts** on t01 (`runs-r2-invalid.jsonl`, true cost 0.36 and 0.24 USD),
each from a product bug, both fixed in `src/` with tests before the valid pilot:

1. On Windows a hook command with backslash paths never ran (0 hook events in the attempt).
   `install.portable_command` now writes forward slashes.
2. `compact_hook.ts` read `$.session.usage` as a value; Claude Code's function-hook compiler
   refused the whole module and said so only in its debug log, so `/compact` fell to the native
   summary with no sign in the session.

| | A autopilot | N native (round 1) |
|---|---|---|
| success | **6/6** [61.0 %, 100 %] | **2/6** [9.7 %, 70.0 %] |
| Fisher exact on success | two-sided p = 0.061; one-sided (A > N) p = 0.030 | |
| fact `token` / `probe` / `window` | 6 / 6 / 6 | 5 / 3 / 3 |
| compaction | mask pruned 6/6 (freed 38-58 %), no model call, 6-7 s | summary 6/6, one model call, 31-44 s |
| what masking stubbed | 10-15 results (the `pkg/` reads, a Glob or Bash) | |
| kept verbatim | the last 5-8 acting turns' results (both one-shot outputs among them), all assistant text | |
| total input tokens, phase A + compaction + B (true) | 5,814,392 | 5,546,735 (**A +4.8 %**) |
| USD, whole task (true) | 1.58 (0.26 per task) | 1.42 (0.24 per task) (**A +11.5 %**) |
| re-reads of phase-A files in phase B, mean | **0** | 5 |
| archive reads in phase B | 0 | |
| arrival cuts | **0** (no result over 6,000 chars) | |
| recall on prompts | 6 injections, all on phase B's prompt, 749-1,373 chars each | |
| recall on tool calls | 26 injections; 143,621 chars injected in all (both kinds) | |
| Jev | 0.0054 USD | 0 |

Registered hypotheses, t01-t06:

- **HA1 holds**: 6 >= 2 - 1.
- **HA2 fails**: A used 4.8 % more input tokens. (The first collect said +12 % and 3.30 against
  3.15 USD; both summed cumulative totals.) What the mask saves in the compaction call and in
  phase B, recall spends in phases A and B: 32 injections, ~24k characters per task, kept in
  context.
- **HA3 holds**: token 6 vs 5, probe 6 vs 3.

How A got there, from the transcripts: the one-shot outputs were **kept by recency**, not
recovered. The token and probe results were among the last acting turns when `/compact` ran,
so the mask kept them verbatim; phase B read nothing from the archive; recall on phase B's
prompt injected about 1 KB. Masking keeps every assistant message, so what the agent wrote
while reading `pkg/` (the window constant and its module, the helper) was still there. Phase B
went straight to the three edits and the tests (0 re-reads; one `grep` in t01). In round 1 it
was the native summary that lost the probe code.

Caveats, as registered and as found:

- **n = 6, not paired**: A's and N's phase A are different sessions. Fisher's two-sided p is
  0.061.
- **The tasks favour this mechanism.** Both one-shot tools run at the end of phase A, where a
  last-10-turns mask keeps them. A fact produced early and needed late would reach phase B only
  through the archive and recall, and that path went untested.
- **The arrival gate never fired**: no tool result in these tasks exceeds 6,000 characters (as
  predicted in R2). So **whether Claude Code accepts `updatedToolOutput` for Read and Bash is
  still untested end to end.**
- Synthetic tasks, one agent model (Haiku 4.5), one Claude Code version.

Spend, round 2 (true cost): 1.58 USD valid + 0.60 USD invalid attempts = **2.18 USD**
(ceiling 6.00). Jev 0.0054 USD.

The free `dry` check and the keyed preflight worked as intended. The silent fail-open reported
while preparing round 2 is fixed: without a key the hook now writes `sanchopanza hook: passed
through unchanged (DeciderUnavailable: TYPESAFE_API_KEY is not set)` to stderr (checked with
`run_round2.py dry`). Earlier diagnosis, for the record: with the autopilot on,
`SANCHOPANZA_PROVIDER=jev` and no key, a 14,338-char Bash result above the arrival threshold
went through untouched with exit 0, nothing on stderr and no journal line
(`harness/claude_code.py:main` ended in `except Exception: return 0`); with a *wrong* key the
hook journaled the 401 but its stderr line read "the decider answered no block: passed whole".

## Round 3 (amendment R3): t07-t12, both arms, pooled n = 12

Registered before any t07-t12 session (`prereg.md`, hash on line 3 of `prereg.sha256`). N ran
fresh, as in round 1 (phase A, forked native `/compact`, phase B). A ran as in round 2, with
the round-2 product fixes and the keyed preflight. The budget for this round was 7.00 USD
(stop at 6.50), on true cost (`round3.py`).

### N, t07-t12

| task | success | token | probe | window | summary kept code | re-reads | USD whole (A / compact / B) |
|---|---|---|---|---|---|---|---|
| t07-payroll | yes | yes | yes | yes | yes | 7 | 0.229 (0.133 / 0.021 / 0.074) |
| t08-loans | yes | yes | yes | yes | **no** | 10 | 0.298 (0.136 / 0.022 / 0.140) |
| t09-fleet | yes | yes | yes | yes | yes | 5 | 0.233 (0.130 / 0.025 / 0.079) |
| t10-warehouse | yes | yes | yes | yes | yes | 8 | 0.269 (0.146 / 0.022 / 0.101) |
| t11-subscriptions | **no** | yes | **no** | yes | no (nor the tolerance) | 7 | 0.265 (0.132 / 0.025 / 0.108) |
| t12-meters | **no** | yes | yes | **no** (`GRACE_NOTICE_DAYS`) | yes | 5 | 0.243 (0.134 / 0.021 / 0.087) |

Every phase A was valid, and all 18 sessions ended `success` with none capped. Summaries lost
the probe code in 2 of the 6 compactions; in t08 the agent passed the probe test anyway.

### A, t07-t12

| task | success | re-reads | mask freed | recall (prompt / tool) | USD whole | input tokens (A / N) |
|---|---|---|---|---|---|---|
| t07-payroll | yes | 2 | 59.9 % | 1 / 6 | 0.374 | 1,839,142 / 862,334 |
| t08-loans | yes | 0 | 38.5 % | 1 / 4 | 0.275 | 1,011,158 / 1,260,578 |
| t09-fleet | yes | 0 | 39.6 % | 1 / 4 | 0.318 | 1,483,913 / 828,247 |
| t10-warehouse | yes | 1 | 48.0 % | 1 / 5 | 0.298 | 1,127,246 / 1,111,284 |
| t11-subscriptions | yes | 0 | 49.2 % | 0 / 4 | 0.267 | 1,069,799 / 1,054,696 |
| t12-meters | yes | 0 | 41.8 % | 1 / 4 | 0.242 | 807,417 / 931,888 |

All facts passed in all six tasks. The masking compaction pruned in 6 of 6, and the arrival gate
never cut anything.

### Pooled, t01-t12 (the registered primary analysis)

| | A autopilot | N native |
|---|---|---|
| success | **12/12** [75.8 %, 100 %] | **6/12** [25.4 %, 74.6 %] |
| Fisher exact on success | **two-sided p = 0.0137**; one-sided (A > N) p = 0.0069 | |
| fact `token` / `probe` / `window` | 12 / 12 / 12 | 11 / 8 / 8 |
| re-reads of phase-A files in phase B, mean | **0.25** | 6.0 |
| total input tokens (true) | 13,153,067 | 11,595,762 (**A +13.4 %**) |
| USD, all tasks (true) | 3.36 | 2.96 (**A +13.5 %**) |
| compaction | mask pruned 12/12, freed 38-60 %, no model call | summary 12/12, one model call each |
| arrival cuts | **0** (no tool result over 6,000 chars) | |
| recall injections | 11 on prompts, 53 on tool calls (297,710 chars) | |
| Jev | 0.0109 USD (0.3 % of A's cost) | 0 |

t07-t12 alone: A 6/6 against N 4/6 (Fisher two-sided p = 0.45); input tokens A +21.3 %. For
t01-t06, see round 2.

- **HA1 holds** (12 >= 6 - 1).
- **HA2 fails**: A used 13.4 % more input tokens.
- **HA3 holds**: token 12 against 11, probe 12 against 8.

Spend, round 3 (true cost): **3.31 USD** (N 1.54, A 1.77), within the 7.00 ceiling. Jev for
the round was 0.0056 USD, and 0.011 USD for the whole experiment.

## Files

| file | what |
|---|---|
| `prereg.md`, `prereg.sha256` | the registration |
| `tasks.py`, `tasks.sha256` | task generator, reference solution, test runner; fingerprint of the 16 repositories |
| `compact_wrapper.py` | the hook's command: `sanchopanza compact` for the arm, logged |
| `run_e2e.py` | driver (`estimate`, `run`, `recollect`) |
| `transcripts.py` | reads Claude Code's JSONL, the hook's marker and log, the journal |
| `analyze.py`, `analysis.json` | tables and hypotheses |
| `phase-a.jsonl`, `runs.jsonl` | one row of numbers per session (at most 600 characters of each final answer) |
| `costs.py` | true per-task cost and input tokens from the saved result JSON (cumulative under `--resume`) |
| `hook_wrapper.py`, `run_round2.py` | round 2 (and arm A of round 3): hooks with the key in their subprocess only; `dry`, `run` (with keyed preflight), `collect` |
| `round3.py` | amendment R3's tasks and its spend gate |
| `runs-r2.jsonl`, `runs-r2-invalid.jsonl`, `analysis-r2.json` | arm A rows, the two invalid pilot attempts, the pooled analysis |

Raw transcripts, hook logs and working copies: `~/.cache/sanchopanza/context-e2e/` and
`~/.claude/projects/` only.
