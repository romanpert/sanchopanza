# Pre-registration: compaction inside Claude Code, native summary against pruning

Written 2026-09-28, before any paid call of this run, at commit `02111ea` with the context
work (`src/sanchopanza/context/`, `points/context.py`, `harness/compact_hook.ts`,
`sanchopanza compact`, `install --compact`) uncommitted in the working tree. Its sha256 is in
`prereg.sha256`; `tests/test_context_e2e.py` checks it.

## Question

After a compaction in the middle of a task, does the agent finish the task as well when the
compaction is sanchopanza's pruning as when it is Claude Code's own summary, and at what
token and dollar cost?

## Tasks

16 generated Python mini-repositories (`tasks.py`, seed `context-e2e-2026-09-28`; fingerprint
of the repositories in `tasks.sha256`, hidden tests `92b0a667...`). No private data. Each has
16 modules under `pkg/` (~23 KB), a visible suite with one seeded bug it catches, and two
one-shot tools. Four facts are planted for the second half of the task:

| fact | where it is | can it be had again after compaction? |
|---|---|---|
| `token` | only in the output of `tools/issue_token.py` (~2 KB report), which deletes its seed | no: a second run prints an error |
| `probe` (tolerance and error code) | only in the failing output of `tools/probe.py` (exit 1), which deletes its state | no |
| `window` | a constant `GRACE_WINDOW_DAYS` in one of four modules, among decoys | yes, by reading the file again |
| `helper` | name and keyword-only parameter of the working-day helper in `pkg/scheduler.py`, next to a calendar-day decoy | yes |

`python tasks.py check` (free) confirmed before registration that, on every task, the hidden
tests fail as generated and pass on the reference solution.

## Session flow

Claude Code 2.1.282, headless, agent `claude-haiku-4-5-20251001` (the cheapest agent model;
the question is about what survives compaction, which a smaller model is if anything more
sensitive to). Every call: `claude -p <prompt> --model claude-haiku-4-5-20251001
--max-budget-usd 0.40 --output-format json --setting-sources project --strict-mcp-config
--permission-mode dontAsk --allowedTools Bash Read Write Edit Glob Grep`, cwd the task's
working copy under `~/.cache/sanchopanza/context-e2e/work/`, environment without
`ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` (billed to the
subscription) and without `TYPESAFE_API_KEY`.

1. **Phase A, once per task** (prompt `PROMPT_A` in `run_e2e.py`): read every file in `pkg/`,
   run `issue_token.py` once, run the tests, fix the bug, re-run the tests, run `probe.py`
   once, end with a status report of at most three lines. The working copy is then
   snapshotted.
2. **Per arm**: restore the snapshot; `claude -p "/compact" --resume <A> --fork-session`
   with the arm's configuration; then `claude -p <PROMPT_B> --resume <forked>` with the same
   configuration; then the hidden tests and the visible suite.

Every arm forks **the same** phase A session. The arms therefore differ only from the
compaction on: this is a paired design, and it removes phase-A variance from the comparison.
(The brief asked for a fresh phase A per arm; one shared phase A is the stricter comparison
and costs less. Declared here as a deviation.)

`PROMPT_B` asks for three changes: set `RELEASE_TOKEN` to the token issued earlier; set
`DRIFT_TOLERANCE` to the tolerance the probe reported and implement `check_drift` raising
`GuardError` with the probe's code; implement `grace_deadline` with the package's grace window
and working-day helper. It says not to guess a value it cannot find.

## Arms

| arm | compaction | how |
|---|---|---|
| **N** | native `/compact` (the model's summary) | no plugin |
| **R** | sanchopanza, rules only, no decider | `--plugin-dir <plugin>` written by `sanchopanza install --compact --plugin-dir`, `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`, hook command `compact_wrapper.py R` = `sanchopanza compact --stdin --arm rules --provider null` |
| **S** | sanchopanza, rules then Jev (`jev-1.13.0`) | as R, `--arm sanchopanza --provider jev` |
| **F** | fast-jev replica | as R, `--arm fastjev --provider jev` |

All four use the command's defaults: `--keep-recent 6`, `--small 400`, `--min-reduction 0.25`,
`context_keep` 0.5. A pruning arm that exits 3 (below the minimum reduction) or fails in any
other way makes the hook fall back to the native summary. **A fallback is recorded as such,
counted, reported per arm, and the session is scored as it ran** (it is what a user of that
arm gets). The plugin and hook environment are the same in phase B, so an automatic
compaction there would also go through the arm.

For S and F the TypeSafe key is read by the runner from its own environment, written to a
file readable by the hook's wrapper, and passed only to the `sanchopanza compact` child; the
Claude Code session does not carry it. Jev spend: at most 0.05 USD per compaction (the
squire's `max_usd`), and no S/F session is launched once the run's journals total 0.45 USD
(ceiling 0.50).

**Change of instructions before any paid call**: the owner's permission system does not allow
this agent to obtain the Jev key. **Arms S and F are prepared, not run in this sitting**:
`TYPESAFE_API_KEY=... python run_e2e.py run --arms S,F` runs them later against the same
phase A sessions and snapshots, with no other change. Everything registered about S and F
below applies to that later run.

## Measures (per task and arm)

- **success**: every hidden test and every visible test passes (primary outcome).
- per fact: `token`, `probe`, `window` (the window test also needs the helper), `visible`.
- **tokens after compaction**: phase B's input tokens, input + cache creation + cache read,
  summed over its API calls (the `usage` of the result JSON); phase B output tokens; the
  context of phase B's first call (from the transcript).
- **cost**: `total_cost_usd` of the compaction call and of phase B, Claude list price; phase A
  reported once per task; Jev USD from the hook's journal.
- **re-reads**: phase B `Read` calls on a file already read in phase A; reads of the archive
  (`.sanchopanza/`); `Grep`/`Glob` calls; re-runs of a one-shot tool.
- wall time of each call; what the compaction left (`summary`, `pruned` stubs, or neither);
  the hook's exit codes, reduction and reasons.

## Hypotheses and decision rules

Over the tasks with a valid phase A, paired:

- **H1 (primary, S against N)**: holds if S successes >= N successes - 1 **and** the sum of
  phase B input tokens of S <= that of N.
- **H2 (secondary)**: S against F, same two parts, reported both ways.
- **H3 (secondary)**: R against N, same form as H1.
- **H4 (secondary)**: re-reads after compaction, S and R against N, per task (descriptive:
  mean and paired differences).

Every number is reported, whichever way it goes. With 16 tasks a difference of one or two
successes is noise; the rules above are the registered reading, and the Wilson intervals are
printed next to them.

**What is expected, written down so it can be wrong**: the rules arm stubs only superseded
reads (the file fixed in phase A), repeated commands (the second pytest) and retried errors,
so on this phase A it will often free less than 25 % and fall back; where it prunes, it keeps
every message and most results, so its phase B input is likely **larger** than after a native
summary. The token half of H3 (and likely of H1) is expected to fail; the success half is
expected to hold, with the one-shot facts the place where a native summary can lose
something.

## Exclusions and failures

- A task whose phase A is not valid (result not `success`, or either one-shot tool not
  consumed) is excluded from every arm and reported with its reason. Decided before any arm
  runs, so it cannot favour one.
- An arm session that errors, times out (900 s) or hits its 0.40 USD cap counts as a failure
  of that arm on that task, not as an exclusion.
- A compaction that leaves neither a summary nor stubs is reported as a harness failure and
  scored as it ran.

## Pilot

Task `t01-orders`, arms N and R (S and F when they are run), before the rest. The transcripts
are inspected to confirm that compaction happened in each arm: a summary for N; stubs for R,
or a fallback with its reason and then a summary. If the mechanics need a fix, only the
harness changes (never tasks, prompts, arms or measures), the change is written as an
amendment below the hash line in the README, and the pilot task is run again from phase A
with its spend counted. Otherwise the pilot rows count.

## Spend

Claude Code, list price through the subscription: ceiling 12.00 USD for every session of this
run, **no new session once spent + 0.40 x sessions in flight would pass 11.00**. At most 4
tasks in parallel, arms of one task one after the other. The estimate is printed before the
full run from the pilot's costs. Jev: ceiling 0.50 USD (S and F only).

## Files

`tasks.py` (generator, reference solution, test runner), `compact_wrapper.py` (the hook's
command), `run_e2e.py` (driver), `transcripts.py` (reading evidence), `analyze.py` (tables,
`analysis.json`), `phase-a.jsonl` and `runs.jsonl` (one row of numbers per session). Raw
transcripts stay under `~/.cache/sanchopanza/context-e2e/` and `~/.claude/projects/`.

---

## Amendment R2 (2026-09-28, written before any paid call of round 2)

Everything above this line is the round-1 registration; its sha256 stays the first line of
`prereg.sha256`, computed over the text up to (not including) the `---` above. The whole file,
with this amendment, hashes to the second line.

### Question

Does the autopilot (`sanchopanza install --autopilot`: PostToolUse arrival gate, recall on
prompts and on tool calls, compaction by the plugin's free `mask` arm) finish the tasks as well
as native `/compact`, for fewer input tokens over the whole session, and does it keep the
one-shot facts the native summary lost (the probe code: missing from 3 of 12 summaries in
round 1)?

### Arms and flow

- **A (autopilot)**, tasks t01-t06: fresh repository, phase A **with the autopilot installed**
  (the arrival gate acts during phase A, so A cannot fork round 1's phase A), then `claude -p
  "/compact" --resume <A>` (the plugin's `mask` arm), then phase B on the same session, then the
  hidden tests. Settings: exactly what `sanchopanza install --autopilot --provider jev` writes,
  into a file in the run's evidence folder passed with `--settings`, with three edits: the
  marketplace and `enabledPlugins` entries are dropped (the plugin comes through `--plugin-dir`,
  so nothing is registered under `~/.claude`), each hook command is `hook_wrapper.py` around
  `sanchopanza hook`, and the compaction command is `compact_wrapper.py M` around
  `sanchopanza compact --stdin --arm mask --provider null`. Defaults otherwise (arrival over
  6,000 characters, minimum saving 0.2, recall k 5, compaction at 60 %).
- **N (native)**: round 1's six N rows are reused, with round 1's phase A for those tasks. This
  is no longer the paired fork design: A has its own phase A, so A and N are two independent
  sessions per task (paired by task only). Reusing N is the same process (same prompts, model,
  Claude Code version, flags, no hooks), run the same day; re-running it would add a second
  sample of the same thing for about 3 USD. Declared as the reason, not hidden.
- Same model, flags and per-session cap as round 1 (`--max-budget-usd 0.40`, no
  `ANTHROPIC_API_KEY`).

### Jev

`jev-1.13.0` (the provider's pinned default). The key reaches only the hook subprocesses,
through a file the wrappers read, deleted at the end of the run; the Claude Code session does
not carry it and it is never printed. `SANCHOPANZA_SESSION_MAX_USD=0.08` per session, and no
new session once the Jev spent by the whole experiment passes 0.45 USD (ceiling 0.50).

### Hypotheses (A against N, tasks with a valid phase A in both)

- **HA1**: A successes >= N successes - 1.
- **HA2**: A total input tokens (phase A + compaction + phase B: input + cache creation +
  cache read) < N's.
- **HA3**: the one-shot facts: A passes the `token` test and the `probe` tests at least as
  often as N (N: 5/6 and 3/6).

Recorded and reported whatever they show: arrival cuts (count, tools, characters saved),
tool results over the 6,000 threshold, recall injections (on prompts, on tool calls, characters
injected), whether Claude Code applied `updatedToolOutput` (the cut header visible in the stored
tool result, per tool, Read and Bash in particular), whether the mask compaction pruned or fell
back (exit 3), re-reads in phase B, Jev USD, Claude USD, wall time.

**Expected, written down so it can be wrong**: no single tool result in these tasks reaches
6,000 characters (source files ~1.5 KB, the one-shot outputs ~2-2.7 KB), so **the arrival gate
is expected to cut nothing**, and whether `updatedToolOutput` is accepted will then stay
untested here. Masking should free well over 25 % (phase A has ~23 calls, most outside the last
ten turns), so compaction is expected to prune without a model call; recall on phase B's prompt
is where the one-shot outputs can come back from the archive.

### Pilot and spend

Pilot: t01-orders, arm A (N already exists), transcripts inspected for arrival headers, mask
stubs and recall `additionalContext` before t02-t06. Claude: 6.00 USD ceiling for round 2, no
new session once round-2 spend + 0.40 x sessions in flight would pass 5.50. Jev as above.

---

## Amendment R3 (2026-09-28, written before any run of t07-t12)

Rounds 1 and 2 above are unchanged (their hashes: lines 1 and 2 of `prereg.sha256`, over the
text before each `---`). This file with R3 hashes to line 3.

### Extension

Tasks **t07-t12** (already generated with the others; fingerprint unchanged in `tasks.sha256`),
**both arms**:

- **N**, fresh: phase A, then `claude -p "/compact" --resume <A> --fork-session`, then phase B
  on the fork, exactly as round 1 (`run_e2e.py run --arms N --tasks t07-...,t12-...`).
- **A**, exactly as round 2 (`run_round2.py run --tasks t07-...,t12-...`), with the two product
  fixes made during round 2's pilot (forward-slash hook commands; `compact_hook.ts` no longer
  reading `$.session.usage` as a value) and the keyed preflight.

Same model, flags, per-session cap, Jev pin and caps as round 2.

### Primary analysis: pooled, n = 12

Tasks t01-t12. **The pooled N includes round 1's N rows for t01-t06** (phase A shared with arm
R, compaction on a fork), and the pooled A includes round 2's rows for t01-t06. A and N are
independent sessions per task (paired by task only). Success is compared with **Fisher's exact
test** (two-sided, and one-sided for A > N), 95 % Wilson intervals beside it. HA1, HA2 and HA3
are read as registered in R2, on the pooled twelve; t07-t12 alone are reported too.

### Correction of the cost measure (harness, found before this round)

Claude Code's result JSON under `--resume` (with or without `--fork-session`) reports
`total_cost_usd` and `modelUsage` **cumulative over the conversation**, phase A included, while
`usage` covers only that invocation, and a `/compact` invocation reports `usage` all zero
although its summary call is in `modelUsage` (checked on the saved files of rounds 1 and 2,
`costs.py`). Rounds 1 and 2 summed the three calls' `total_cost_usd`, counting phase A two or
three times. From now on, and restated for rounds 1 and 2:

- USD of one task in one arm = the last call's `total_cost_usd`;
- **HA2's input tokens** = the last call's `modelUsage` input + cache creation + cache read
  (this also counts the native summary call, which `usage` leaves out).

The spend gates use the same measure. Round 1's phase-B token figures (from `usage`) are
unaffected.

### Budget

Claude, this round (N and A for t07-t12, true cost as above): ceiling 7.00 USD, no new session
once this round's spend + 0.40 x sessions in flight would pass 6.50. Jev: the whole
experiment's 0.50 ceiling (0.45 stop) still holds.

Open question noted, not tested: whether `--max-budget-usd` is compared with the cumulative
cost in a resumed session. If it is, phase B had an effective cap of about 0.40 minus phase A's
cost (~0.27 USD); no phase B session has hit it so far.
