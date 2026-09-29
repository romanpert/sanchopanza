# Pre-registration: compaction in the middle of a session, lean autopilot against native

Written 2026-09-29, before any paid session of the main run and before any Jev call of the
offline run, at commit `6058528` with this iteration's work uncommitted in the working tree
(`src/sanchopanza/context/index.py`, stub styles, free arrival, recall placement, the archive
MCP server, `install --lean`, the `handle` fix in `compact_hook.ts`). Its sha256 is in
`prereg.sha256`; `tests/test_context_lean_prereg.py` checks it. Everything is run through our
own evaluation harness; numbers are not directly comparable with numbers obtained through the
API.

## What happened before this registration (declared, not hidden)

1. **Exploratory, free** (`exploratory/`): re-reading the transcripts of
   `2026-09-28-context-e2e` showed that in every arm-A phase B the model received the
   **unmasked** history. Under `claude -p --resume`, Claude Code rebuilds the history along
   `parentUuid`; the entries written after our compaction chained to pre-compaction entries,
   so the chain skipped the boundary (0 stubs and no `compact_boundary` on it in 12/12 tasks;
   first phase-B context 55.3k tokens, as without compaction). The published 12/12 against
   6/12 therefore compared "no compaction, plus recall" against the native summary. It is
   corrected in that README with a dated amendment; it is not evidence for masking.
2. **Mechanics probes, paid, 2.14 USD in all** (`probe/`, `probe-results.jsonl`): a
   chained-read session with Claude Code's own auto-compaction forced low
   (`CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000` and `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE`) showed
   that (a) auto-compaction fires mid-turn in `-p` and runs the `session.compact` function
   hook with trigger `auto`; (b) masking reaches the model in a live session (57.4k to 46.7k
   tokens at the first compaction); (c) `--resume` brought the unmasked history back (85.8k);
   (d) with the plugin returning copies of the engine's messages **without** their `handle`
   (`detached()`), the resumed session starts masked (57.1k). The same held through the Agent
   SDK (42.6k to 14.7k). Anecdote, n = 1 each: with plain stubs the agent twice reported the
   code of the first *visible* file as the first file's (wrong, silently); with `index` stubs
   it reported the right one.
3. **Reading the Claude Code 2.1.282 binary** (no model call): its microcompaction never runs
   in `-p` (it is gated to the interactive main thread and a server flag), so no arm below
   can be "Claude Code's microcompaction"; arm K reproduces its effect (results outside the
   recent window replaced by `[Old tool result content cleared]`, nothing kept).
   `turn.complete` fires once per prompt, so the autopilot's between-turns trigger at 60 %
   cannot act inside a long task: this run uses Claude Code's own mid-turn auto-compaction as
   the trigger for every arm.
4. **Evidence against, collected before design** (literature): recoverable elision "adds
   machinery models rarely use and yields no accuracy gain" (arXiv 2609.20804, 176
   configurations; recall tool never called in 56 % of settings); head+tail keeps 0.05-0.14 of
   needed log lines against 0.86 for a task-conditioned extractor (Squeez); at 128k windows
   managed and unmanaged differ by 2.7 points. These set the arms and the predictions below.
5. A design decision made after seeing one generated build log, before any paid run of it:
   `index_of` puts error lines first (they were crowded out of the 240-character index by
   paths and hashes). Declared here.

## Part 1: offline (free, plus at most 0.30 USD of Jev)

Data: the 40 public trajectories, cut points and lexical "needed" labels of
`2026-09-28-context` (unchanged). Script `offline/run.py`.

- **O1, index stubs.** At the cut, mask M = 10: share of NEEDED masked results for which
  `index_of(result, 240)` holds at least one needed token (Wilson 95 %), and characters the
  index adds as a share of characters freed; also at limits 120 and 480, and against "first
  240 characters". **Holds if** the share is >= 50 % **and** the index adds <= 10 % of the
  characters freed.
- **O2, large outputs at arrival.** All history results of at least 6,000 characters (170).
  Needed lines labelled lexically. Arms: head+tail (20 + 20 lines), `free_cut`, BM25 lines only,
  and the current Jev tournament (`jev-1.13.0`, cap 0.30 USD, decisions recorded and
  replayable). Measure: share of results with needed lines whose needed lines are ALL kept;
  share of needed lines kept; characters kept. **Holds if** `free_cut` keeps all needed lines
  in at least as many results as head+tail **and** within 10 points of the Jev arm.
- **O3, the API's rival.** A replay of `clear_tool_uses_20250919` (keep 3 tool uses, trigger
  at T = 30k, 50k and 100k proxy tokens) against mask M = 10 and M = 3: retention of needed
  results at their freed characters. Descriptive (the modelling assumptions are listed in
  `offline/README.md`).

## Part 2: end to end in Claude Code (subscription)

### Tasks

10 generated Python mini-repositories (`tasks.py`, seed `context-lean-2026-09-29`, digest in
`tasks.sha256`), no private data; `python run.py check` (free) confirmed before registration
that on every task the hidden tests fail as generated and pass on the reference solution. Each
has ~24 modules under `pkg/`, a visible suite with one seeded bug, hidden tests outside the task
folder, and three facts:

| fact | where | can it be had again? |
|---|---|---|
| `token` (early) | only in the output of `tools/issue_token.py`, run in phase A; the tool deletes its seed | no |
| `check` (large, mid-session) | one line `CHECK <ID> failed: expected <v> got <v>` inside a 20-22 KB build log printed by `tools/build_report.py` at the start of phase B; position early in t01, t04, t07, t10, middle in t02, t05, t08, late in t03, t06, t09; the tool deletes its state | no |
| `limit` (control) | a constant in one named module, one decoy | yes |

### Flow

Claude Code 2.1.282, headless, one shared **phase A** per task and model (read the README and
the first modules, run `issue_token.py` once, run the tests, fix the bug, re-run, a short
status), forked into every arm with `--resume <A> --fork-session`, then **phase B** in the arm
(run `build_report.py` once; read, one per call, the remaining modules, which pushes the
context over the threshold so compaction fires mid-turn after at least 12 phase-B tool calls;
then set the token, implement `check_build()` raising `BuildError` with the check id and
expected value, implement the `limit` function, run the tests; never guess). Prompts are in
`tasks.py`/`run.py` as registered. Every session: `--setting-sources project
--strict-mcp-config --permission-mode dontAsk --output-format json`, tools Bash Read Write Edit
Glob Grep plus `mcp__sanchopanza_archive__search_archive`, environment without any inherited
`ANTHROPIC_*`, `TYPESAFE_*`, `SANCHOPANZA_*` or `CLAUDE_*` variable (a leak found while
building: the child sessions had inherited `CLAUDE_EFFORT=medium` and others from the
coordinating session), plus `CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000` and
`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=80` (threshold 64,000 tokens). The archive MCP server is
configured, under the same name, in phase A and in every arm, so the tool list is identical and
no arm pays a cache rewrite for it; in N and K its archive is empty.

### Arms

| arm | at the auto-compaction | during phase B |
|---|---|---|
| **N** | Claude Code's native summary | nothing |
| **K** | function hook, `sanchopanza compact --arm mask --mask-turns 10 --stub-style cleared`: results outside the last 10 acting turns become `[Old tool result content cleared]`, nothing archived (the effect of Claude Code's own microcompaction) | nothing |
| **L** (lean) | as K with `--stub-style index` (stub + archive path + `Holds: <index_of>`), archived | the hooks `sanchopanza install --autopilot --lean` writes: arrival cut in `free` mode (no decider) over 6,000 characters, recall pushed nowhere (`RECALL_ON=off`), the archive searchable through `search_archive` |

No decider is called in any arm (no Jev key in any session). A masking arm that exits non-zero
falls back to the native summary; a fallback is recorded and scored as it ran.

Models: **Haiku 4.5** (`claude-haiku-4-5-20251001`), tasks t01-t08, arms N, K, L; **Sonnet 5**
(`claude-sonnet-5`), tasks t01-t03, arms N, L, each model with its own phase A. (Tasks t09-t10
are generated and checked but not run, for budget; declared.)

### Measures

- **success**: all hidden and visible tests pass (primary); per fact `token`, `check`,
  `limit`, `visible`.
- **tokens**: phase-B input tokens (input + cache creation + cache read), per call from the
  transcript and as the difference of the cumulative totals; cache-read share; cost as the
  difference of `total_cost_usd` against phase A's (list price).
- **mechanism**: number of compactions, who did them (wrapper exit codes, marker), context of
  the last call before and the first after each compaction; arrival cuts and whether the
  failing line was kept; stubs holding the token or the check id.
- **retrieval**: `search_archive` calls, `Read`s of the archive, re-runs of one-shot tools,
  re-reads of phase-A files; where each fact's value came from (index in context, search,
  archive read, summary, kept result, none).

### Validity (checked before scoring)

A phase-B row is **INVALID** if the session did not end, if its phase-B prompt is missing, if
in K or L the plugin marker lacks `loaded` or no compaction ran through the wrapper, if in L the
classic hooks logged no event, or if no compaction happened at all in the session. An invalid
row is re-run once from the same phase A; the second result stands and both are reported.

### Hypotheses and decision rules (Haiku, t01-t08, paired by phase A)

- **H1 (primary, what survives)**: L successes >= N successes - 1 **and** L successes >= K
  successes + 3.
- **H2 (primary, cost)**: the sum over tasks of L's phase-B input tokens <= N's. The paired
  ratio with a bootstrap 95 % interval is printed next to it.
- **H3 (secondary)**: K against N, success and tokens, reported both ways (does the archive and
  index add anything over clearing, and does clearing beat the summary).
- **H4 (descriptive)**: the share of L sessions that call `search_archive` or read the archive
  when a needed fact is not in context; predicted **below 50 %** (the literature above).
- Sonnet 5 (t01-t03, N and L): descriptive, the same measures; n = 3 decides nothing.

Every number is reported whichever way it goes, with Wilson intervals; n = 8 reads only large
differences.

### What is expected, written so it can be wrong

- K loses `token` and `check` in most tasks: both are outside the last 10 acting turns when
  compaction fires, and clearing keeps nothing. Expected K successes: 0-2 of 8.
- N keeps `token` and `check` in most summaries (in 2026-09-28-context-e2e the summary carried
  the command-output facts in 9 of 12); expected 4-7 of 8.
- L: the index of the token report and of the build log should hold both facts (error lines
  first), so L should need no retrieval; expected 6-8 of 8.
- Tokens: after a summary N's context is smallest, but N re-reads files; masking keeps every
  assistant message and 10 recent results. Whether L's phase B costs less than N's is **a
  coin flip** before this run.

## Pilot

Before the main run: Sonnet phase A only for t01 (calibration: the compaction must fall in
phase B), then Haiku t01 with N, K, L. Each pilot transcript is inspected for: compaction in
phase B after >= 12 tool calls, the arm's stubs, the arrival cut in L, the hooks' logs. If the
mechanics need a change, only the harness or the sizes of the generated files change (never
prompts, arms or measures), the change is written as a dated amendment below the hash line of
this file, and the pilot is re-run with its spend counted. Otherwise the pilot rows count.

## Spend

Subscription, true cost at list price, for the whole iteration: **15.00 USD**, of which 2.14
are spent (probes). The driver refuses a session when its own spend plus the session cap
would pass: Haiku 7.60 USD, Sonnet 4.60 USD (per-session caps 0.80 and 2.00). Codex: one
check under the owner's ChatGPT login, reported separately. Jev: 0.30 USD for O2, 0 for the
end-to-end run.

## Files

`tasks.py`, `arms.py`, `evidence.py`, `run.py`, `dry.py`, `estimate.py`, `analyze.py` (end to
end); `offline/` (Part 1); `probe/` (mechanics, before this registration); `exploratory/`
(the attribution that found the invalid comparison); `codex/` (Codex CLI). Raw transcripts
stay under `~/.cache/sanchopanza/` and `~/.claude/projects/`; rows in the repo hold numbers,
never personal paths.

---

## Amendment A1 (2026-09-29, after the Haiku pilot, before any other task ran)

The Haiku pilot (t01, arms N, K, L; 0.46 USD for the three phase-B sessions plus 0.10 for
phase A) had **no compaction in any arm**: phase A ended at 37.9k tokens (not the ~47k the
character-based calibration assumed: the build log costs ~0.24 tokens per character, not 0.33)
and phase B peaked at 54.4k-60.4k, below the registered 64,000. The three rows test nothing and
are kept apart in `runs-pilot-invalid.jsonl`, reported, and not scored. The driver also marked
them valid, against the validity rules above; it now marks a row INVALID when no compaction
happened or when a masking arm's hook never ran at a compaction.

Harness change only (prompts, tasks, arms, measures and decision rules unchanged): the
threshold is set per model from the pilot's measured contexts, so that compaction fires after
at least 12 phase-B tool calls, with the build log outside the last 10 acting turns:

- Haiku 4.5: `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=63`, 50,400 tokens (phase B reaches 50.0k at
  its 13th call in the pilot).
- Sonnet 5: unchanged, 80, 64,000 tokens (its phase A for t01 ended at 48.3k: Sonnet counts
  about 27 % more tokens for the same text).

Haiku's phase A for t01 is reused: it reached neither threshold, so it is the same session it
would be under either. The pilot's spend counts against the Haiku stop (7.60 USD). The Haiku
t01 pilot is re-run under this amendment and its rows count if valid.
