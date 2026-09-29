# Pre-registration: the compaction guard next to Claude Code's native summary

Written 2026-09-29, before any paid session of this run and before any Jev call of it, with this
iteration's work uncommitted in the working tree (`src/sanchopanza/context/guard.py`,
`src/sanchopanza/harness/guard_hook.py`, `history_from_claude_code` in `context/transcript.py`,
`tests/test_context_guard.py`). Its sha256 is in `prereg.sha256`. Everything is run through our
own evaluation harness; numbers are not directly comparable with numbers obtained through the
API.

## Why this, after two negatives

`2026-09-28-context-e2e` (corrected) and `2026-09-28-context-lean` say the same thing: every
replacement for Claude Code's summary we built lost to it (native 5/7, lean masking 3/7,
clearing 0/6), and what the native summary lost was always a value printed once by a command
that cannot run again (the probe's error code in 4 of 12 summaries). Three independent papers
measure the same failure for constraints (arXiv 2608.11242: 17 % of side constraints survive a
compactor; 2606.22528: violations rise from 0 % to 30 % after compaction and pinning restores
0 %; 2608.22752: 53 % of rules survive one round of Claude Code's own prompt, 10 % after five).
Nobody has measured whether carrying those values and rules past a native summary raises task
success. So this run does not replace the summary; it adds to it.

## What happened before this registration (declared, not hidden)

1. **The mechanism, read from the Claude Code 2.1.282 binary (no model call).** The stdout of a
   successful `PreCompact` command hook becomes `newCustomInstructions`, appended to the summary
   prompt, for manual and automatic compaction alike; `SessionStart` hooks run with source
   `compact` after the summary and their `additionalContext` is attached after it; `PostCompact`
   receives `compact_summary`. Classic hooks, not the early-access function hooks.
2. **Offline replay, free (`offline/replay.py`, `offline/replay.json`).** At the 31 native
   compactions recorded in the two earlier runs (26 sessions), the guard built from the history
   before each compaction. **The rules were tuned on this data**: the first version carried the
   release token in 0 of 18 e2e compactions (48 inventory lines of one shape filled its per-output
   line cap); the rarity rule (`guard.shape`) was written after seeing that, and the
   request-overlap rule after writing this run's manifest. After them: token, probe code and
   tolerance in 18 of 18 e2e compactions, against 15, 13 and 14 for the native summary. **This is
   not evidence for the guard**; it is the reason the task outputs below are new.
3. **Offline on 40 public trajectories, free (`offline/public.py`, `offline/public.json`),
   not looked at while writing the rules: negative.** OpenHands with Qwen3-Coder on real GitHub
   issues. Of the NEEDED results of non-readable, non-test tools (53, mostly `grep`, `find`,
   `pip`), the guard's fact lines hold a needed token for 11 of 37 on test (30 %), against 43 %
   for the most recent results verbatim, 32 % for heads and 24 % for index stubs at the same
   characters; every difference's interval crosses 0. What those trajectories needed from shell
   output was re-runnable (test names, paths, package names), which the guard does not target.
   So the guard's claim, if any, is limited to values that cannot be had again.
4. **Five defects found by the free dry run (`dry.py`) and fixed before this registration**, each
   in `tests/test_context_guard.py`: the harness's own permission messages were read as tool
   output; test runs were treated as at risk (they can be re-run; the trail keeps the last
   outcome); the re-run echo ordered lines by position and cut the error line; slash-command
   markup was kept as a request; `cd <dir> &&` prefixes kept the same command from being
   recognised.
5. **An independent code review before registration** (a review agent, no model call of
   ours) found two serious defects, fixed with tests in `tests/test_context_guard_review.py`:
   secrets in `KEY=value` lines were carried verbatim (now masked by `redact.mask`, which
   gained an environment-style credential pattern), and lines of web and MCP output were
   re-injected as trusted context (now left out by default, `GUARD_WEB=1` takes them in,
   and every group of lines is fenced as recorded output with a closing line saying it is
   not an instruction). Also fixed: UTF-8 on the hook's pipes, the echo given once per
   command and only when a value line is missing from the new output, no transcript parse
   without a compaction, a 20-second limit on the decider, test runs known by their
   executable, `cd <dir>` kept in a command's identity, the latest request cut to fit
   rather than dropped. None of this changes what these tasks exercise (no web output).

## Tasks

10 generated mini-repositories (`tasks.py`, seed `context-guard-2026-09-29`, digest in
`tasks.sha256`), built on the lean run's generator with its seed replaced; `python run.py check`
(free) confirmed before registration that on every task the hidden tests fail as generated and
pass on the reference solution, the three one-shot tools work once and refuse a second run, the
token sits in the middle of its manifest, and the rule's reference appears in no file.

| fact | where | can it be had again? |
|---|---|---|
| `token` | phase A, `tools/issue_token.py`: a 48-line release manifest, one random hash per line (no repeated line shape), the token line in the middle | no |
| `probe` | end of phase A, `tools/probe.py`: 36 channel lines, a failing aggregate, `ProbeError: ... tolerance T (code PRB-n)` | no |
| `check` | start of phase B, `tools/build_report.py`: a 20-22 KB build log with one failing check | no |
| `rule` | phase A's prompt only: "every exception message written in this repository must end with `[ref OPS-n]`" (phase A writes no exception; phase B writes two) | no |
| `limit` | a constant in one module, one decoy | yes (control) |

## Flow

As `2026-09-28-context-lean`: Claude Code 2.1.282 headless, one phase A per task and model (no
hooks), forked into every arm with `--resume <A> --fork-session`, then phase B in the arm; the
prompts are `prompt_a(rule_ref)` and `PROMPT_B` in `run.py` as registered. Every session:
`--setting-sources project --strict-mcp-config --permission-mode dontAsk --output-format json`,
tools Bash Read Write Edit Glob Grep, no MCP server, no inherited `ANTHROPIC_*`, `TYPESAFE_*`,
`SANCHOPANZA_*`, `SANCHO_*` or `CLAUDE_*` variable, `CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000` and
`CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` 63 (Haiku) / 80 (Sonnet), so Claude Code's own
auto-compaction fires in the middle of phase B.

**Pilot and its one allowed amendment.** Phase A and the three arms on t01 (Haiku) run first.
If no compaction fires in phase B, or it fires before the build log, the percentage is moved by
the smallest step that makes it fire after the build log, written as amendment A1 below the hash
line before any other task runs, and the pilot rows are kept apart as invalid.

## Arms

| arm | at the compaction | during phase B |
|---|---|---|
| **N** | Claude Code's native summary | nothing |
| **G** | the native summary, with the guard's note appended to its instructions (`PreCompact`) and the guard block attached after it (`SessionStart`, source `compact`): fact lines of non-readable, non-test output, the trail, the person's requests verbatim; rule chooser, no model | `PostToolUse` on Bash: a command that ran before the last compaction gets its earlier value lines back |
| **GJ** | as G, with the facts chosen by one Jev tournament (`triage_many`, `jev-1.13.0`) over the commands when they exceed 3,000 characters; the rule otherwise, and on any failure | as G |

Models: **Haiku 4.5**, tasks t01-t10, arms N, G, GJ (order rotated by task); **Sonnet 5**, tasks
t01-t03, arms N and G, descriptive.

## Measures

- **success** (primary): all hidden and visible tests pass; per fact `token`, `probe`, `check`,
  `rule`, `limit`, `visible`.
- **one-shot facts**: the sum over `token`, `probe`, `check`, `rule` of facts passed.
- **tokens and cost**: phase-B input tokens (input + cache writes + cache reads) and true cost by
  difference of the cumulative result JSON (list price).
- **mechanism**: compactions and where they fell; in G and GJ the guard's events (PreCompact,
  SessionStart, echoes), block characters, candidates, chooser; whether each fact's value was in
  the native summary, in the guard block, both or neither.

## Validity (checked before scoring)

A row is INVALID if the session did not end, the phase-B prompt is missing, no compaction
happened, or in G and GJ the guard's `PreCompact` or `SessionStart` never ran. An invalid row is
re-run once from the same phase A; the second result stands and both are reported. A task whose
phase A is invalid (a one-shot tool not consumed, the build report consumed, no success) is
excluded, and replaced by none.

## Hypotheses and decision rules (Haiku, t01-t10, paired by phase A)

- **H1 (primary, success)**: G successes >= N successes + 2.
- **H2 (primary, one-shot facts)**: G's one-shot facts passed >= N's + 3 (of 40), **and** G is
  not below N on any single one-shot fact by more than 1.
- **H3 (primary, no harm)**: G's `limit` and `visible` passes >= N's - 1, **and** the sum of G's
  phase-B cost <= 1.10 x N's.
- **H4 (secondary, the decider)**: GJ successes >= G successes - 1 (the tournament costs no
  success); whether it was ever asked, and at what cost, is reported.
- **H5 (descriptive)**: for each one-shot fact, where its value was after the last compaction
  (summary, guard, both, neither) in N and G; the echo's count and whether it was used.

**Predictions, written now.** H1 is uncertain: in the lean run native compaction kept the token
in 7 of 7, so the room is in `probe` (lost by 4 of 12 native summaries in the e2e run) and in
`rule`, which no earlier run measured. If the native summary keeps the rule and the probe, H1
fails and we report that the guard is not needed on these tasks.

Sonnet 5 (t01-t03, N and G): descriptive, the same measures; n = 3 decides nothing.

## Budget

Subscription, true cost at list price: estimate about 16 USD (Haiku about 11, Sonnet about 5);
the run stops at **17 USD** (`--stop-usd`), hard ceiling 18. Jev: under 0.10 USD. Both ceilings
are the owner's, asked before any paid session.

## Amendment A2 (2026-09-29, after 8 Haiku tasks and t09 GJ, before any further session)

**Stopped and why.** The owner stopped the run after t08 (and one GJ session of t09) to have the
decider measured properly (`prereg-prompt-recall.md`, amendments 4 and 5). Rows so far stand as
run: 25 valid, none invalid; runner total 9.98 USD, plus about 0.25 USD of one t09 session cut
off before it wrote a row.

**A task defect, found reading the transcripts (no model call).** Claude Code 2.1.282 keeps
the first and last 5,000 characters of a shell result that exits with an error and replaces the
middle with `... [N characters truncated] ...`; `tools/build_report.py` exits 1 and prints
20-22 KB. On the three tasks whose failing check sits in the middle of the log (t02, t05, t08,
`check_position = "middle"`) the check line never reached any arm's transcript: N, G and GJ all
fail `check` there, and success is impossible for every arm. `check` and `success` are therefore
reported on all tasks **and** on the measurable ones (early and late: t01, t03, t04, t06, t07,
t09, t10); H1-H4 are judged on the measurable ones. The environment is not changed for the
remaining tasks (t09 is late, t10 early: both deliverable), so every row keeps one setting.

**Code changed since the rows above**, each with tests, all in the working tree: `guard.latest_only`
keeps a one-shot tool's first output when both runs failed; the guard block says when an output
was cut by the harness (`guard.clipped_of`: here, the build log of every task); the new chooser
`keep`. G on t09-t10 runs this code; G on t01-t08 did not. Declared, not corrected.

**Arm K replaces GJ for what remains.** K = G with `GUARD_CHOOSER=keep` (`context.keep`, as
registered in prereg-prompt-recall.md amendment 5): the guard is built at the `SessionStart`
after the summary, the decider (`jev-1.13.0`) scores blocks and lines with the requests in full
and the native summary as `notes`, the rule's lines are free, the rule stands on any failure.
The facts budget stays 3,000 characters: the pool of every line of these outputs does not fit
it, so the decider is asked at every compaction (GJ was never asked: its pool was the rule's).
Validity as G (PreCompact and SessionStart ran).

**Order, under `--stop-usd 16.75`** (the uncounted 0.25 included, so the ceiling of 17 holds):
t09 N, G, K; t10 phase A, then N, G, K; then K on t01-t08 in task order, as far as the stop
and the decider budget allow; Sonnet t01-t03 N and G only if money is left. Arms rotate as the
driver does. Decider cost read from each K folder's `journal.jsonl`.

**Added hypotheses (secondary, K):** **H6**: on the tasks where K ran, K successes >= G
successes - 1; **H7** (descriptive): the decider's calls and cost per compaction, whether the
summary reached it as notes, and where each one-shot value was after the last compaction (the
summary, the guard, both, neither) in N, G and K.

## Amendment A3 (after t09 and t10, before any further session)

Rows since A2: t09 N success, G fail (`limit`, the re-readable control), K success; t10 all
three fail (G stopped after 4 turns asking to run PowerShell, a tool not allowed; N and K wrote
the probe's drift where its tolerance goes, the tolerance being in K's guard block). Runner
total 11.38 USD.

K runs only on the measurable tasks left, t01, t03, t04, t06, t07 (in that order): on t02, t05
and t08 no arm can finish (amendment A2), so a K row there measures nothing. The decider budget
left is 0.038 USD of the 0.40 approved (0.362 spent); each hook call of K is now capped at
0.01 USD (`SANCHOPANZA_T_MAX_USD`, set by the wrapper; t09 and t10 spent 0.0018 and 0.0009 per
session). Same `--stop-usd 16.75`. Sonnet only if money is left after these five.
