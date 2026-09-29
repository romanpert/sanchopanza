# Compaction in the middle of a session: native summary against lean masking

## Summary

Run through our own evaluation harness, inside Claude Code 2.1.282 (headless). Numbers are not
directly comparable with numbers obtained through the API. Pre-registered in `prereg.md` (hash
in `prereg.sha256`, pinned by `tests/test_context_lean_prereg.py`) before any paid session of
the main run; one amendment (A1, after the pilot) is below its hash line.

**The negative first.** When Claude Code's own auto-compaction fires in the middle of a task,
its native summary did better than our masking on these tasks:

| Haiku 4.5, 7 tasks | N: native summary | K: clear old results (no archive) | L: lean masking (index stubs, archive, arrival cut, pull search) |
|---|---|---|---|
| tasks finished (all hidden tests) | **5/7** [35.9 %, 91.8 %] | **0/6** [0 %, 39.0 %] (one row invalid) | **3/7** [15.8 %, 74.9 %] |
| early one-shot fact (`token`) kept | 7/7 | 1/6 | 5/7 |
| mid-session log fact (`check`) kept | 5/7 | 3/6 | 5/7 |
| phase-B input tokens, sum | 8.73M | 8.56M (6 tasks) | 10.46M |
| phase-B cost, sum (list price) | 2.03 USD | 1.68 USD (6 tasks) | 1.99 USD |

- **H1 fails**: L finished 3, N 5 (the rule needed L >= N - 1). Its second part holds: L >= K + 3.
  Paired: N alone 2, L alone 0 (McNemar exact p = 0.5).
- **H2 fails**: L used more input tokens than N (paired mean +248k per task, 95 % bootstrap
  [-13k, +604k]); in dollars the two are the same (L - N mean -0.005 USD, [-0.11, +0.08]),
  because more of L's tokens are cache reads (96.6 % against 95.4 %).
- **H3**: clearing old results without an archive (the effect of Claude Code's own
  microcompaction, which never runs in `-p`) finished nothing: it lost the early fact in 5 of 6.
- **H4 held as predicted**: the agent never called `search_archive` (0 calls in 7 L sessions). It
  did read archive files 13 times, and it tried to re-run the one-shot tools 39 times in L and
  28 in K (they fail by design). Pull recall as a tool is not what an agent reaches for.

**Why the index stubs did not save L.** An index is written when a result is archived, before
anyone knows which of its tokens will matter. In t03 and t06 the token report's 240-character
index was filled by the inventory's other codes (`SKU-34169; bin=F04; ...`) and the release
token sat past it; the agent guessed from the index instead of reading the archive. Offline, on
40 public trajectories, the same index holds a needed token for only **12.0 %** of the needed
masked results [7.2 %, 19.5 %]; the first 240 characters of the result do as well (15.7 %).
O1's bar was 50 %: it fails.

**What did work, and is kept.** Two defects found and fixed, each with a test:

- **The compaction hook returned the engine's `handle`**, so under `--resume` Claude Code rebuilt
  the unmasked history. That invalidated the published 12/12 against 6/12
  (`../2026-09-28-context-e2e/`, corrected there). With the fix a resumed session starts masked
  (57.1k tokens against 85.8k before), live and through the Agent SDK (`probe/`).
- **The child sessions inherited the coordinating session's `CLAUDE_*` variables**
  (`CLAUDE_EFFORT=medium` and others). The runners now drop them.

And the mechanics are now known exactly (read from the 2.1.282 binary and checked in `probe/`):
auto-compaction fires before each API call, mid-turn, when context passes
`min(effective x CLAUDE_AUTOCOMPACT_PCT_OVERRIDE %, effective - 13k)` with effective = window -
20k (`CLAUDE_CODE_AUTO_COMPACT_WINDOW`, floor 100k), and it runs the `session.compact` function
hook with trigger `auto`; `turn.complete` fires once per prompt, so a between-turns trigger
never acts inside a long task.

## Offline (Part 1)

Same 40 public trajectories, cuts and lexical labels as `2026-09-28-context`; test split (25
units) below, dev split in `offline/results.json`.

| measure | result | registered bar | verdict |
|---|---|---|---|
| O1: needed masked results whose index (240 chars) holds a needed token | 13/108 = **12.0 %** [7.2, 19.5]; adds 5.3 % of freed chars. First 240 chars: 15.7 %; index 480: 13.9 %; first 480: 31.5 % | >= 50 % and <= 10 % of freed | **fails** |
| O2: large results (>= 6,000 chars) with ALL needed lines kept | head+tail 12/42, `free_cut` 11/42, BM25 lines 10/42; Jev tournament 66/69 (both splits) but keeps 95.9 % of the characters and cut only 15 of 170 | `free_cut` >= head+tail and within 10 points of Jev | **fails** |
| O3: `clear_tool_uses` (keep 3) against masking | API rule at 30k: frees 82.1 %, keeps 9.0 % of needed results; mask M = 3 the same; mask M = 10: frees 69.3 %, keeps 18.8 % | descriptive | - |

O2 in one line: on real trajectories every free cut at arrival loses the needed lines in three
of four large outputs, and the decider avoids losing them by hardly cutting. Jev spent 0.081 USD
(236 decisions, 0 errors, recorded and replayable).

## End to end (Part 2)

### Per task, Haiku 4.5 (success, facts missed, phase-B input tokens, compactions @ phase-B call of the first)

| task | N | K | L |
|---|---|---|---|
| t01-orders | yes, 1.13M, 1@14 | no (token, check, limit), 0.82M, 1@13 | yes, 1.19M, 1@13 |
| t02-shipments | no (check), 1.00M, 4@2 | no (check), 1.64M, 3@2 | no (check), 0.97M, 1@2 |
| t03-invoices | yes, 1.18M, 1@14 | no (token, check, limit), 1.60M, 2@14 | no (token), 1.43M, 1@14 |
| t04-sensors | yes, 1.00M, 1@12 | no (token), 1.21M, 1@12 | yes, 1.19M, 1@12 |
| t05-tickets | no (check), 1.54M, 3@3 | INVALID: no compaction | no (check), 2.80M, 3@10 |
| t06-bookings | yes, 1.13M, 1@15 | no (token), 1.50M, 1@15 | no (token), 1.46M, 2@15 |
| t07-payroll | yes, 1.08M, 1@12 | no (token), 1.69M, 2@12 | yes, 1.32M, 2@12 |

- **Compaction reached the model in every masking session**: the first call after each
  compaction was 31.6k-45.3k tokens against 49.9k-51.1k before.
- **Timing was not always as designed.** In t02 (all arms) and t05 (N) compaction fired within
  the first 3 phase-B calls, because those phase As ended higher than the pilot's; the build
  log then came after the compaction and the `check` fact was lost in every arm of both tasks.
  Scored as registered. Exploratory, restricted to the five tasks where it fired after >= 12
  calls: N 5/5, L 3/5, K 0/5.
- **t05-K is invalid** (the session ended before any compaction). The registered re-run did not
  fit under the Haiku stop and was not made; t08 was not run for the same reason.
- The arrival cut fired 5 times in L; the failing build line was kept each time.

### Sonnet 5 (descriptive, stopped by the spend gate)

| task | N | L |
|---|---|---|
| t01-orders | yes, 1.25M, 1@14, 0.67 USD | yes, 1.34M, 1@14, 0.56 USD |
| t02-shipments | not run (the Sonnet stop, 4.60 USD, was reached) | no (token, check, limit), 3.06M, **5 compactions** @8, 21, 28, 47, 54, 2.04 USD |

One pair and one unpaired row decide nothing. What t02-L shows is a failure mode the native
summary does not have: **masking thrashes**. It keeps every assistant message and the last 10
acting turns, so the context after a compaction sits close enough to the threshold (64k) to
fire again a few calls later; each compaction rewrites the prefix and pays cache writes again.
Five compactions and 2.04 USD for one task, against 0.67 USD for native on t01. Sonnet also
repeated the release token in its own phase-A status (2 of 2), against the prompt, so on Sonnet
the token survives any masking through the assistant text. As with Haiku, `search_archive` was
never called (0), the archive was read 15 times, and one-shot tools were re-run 15 times.

## Integration: what plugs in where

| harness | what works today | measured here |
|---|---|---|
| Claude Code, function hooks (early access) | `session.compact` replaces the message list on manual, auto and plugin compaction, mid-turn; must return messages without `handle` | yes: live, `--resume`, 7 tasks |
| Claude Code, classic hooks | `PostToolUse` `updatedToolOutput` (arrival cut) and `additionalContext`; `UserPromptSubmit` `additionalContext`; `PreCompact` cannot replace the summary | arrival cut applied 5 times in L |
| Claude Agent SDK (Python) | the same plugin through `ClaudeAgentOptions(plugins=[...])`; auto-compaction through the session's env | yes: `probe/sdk_probe.py`, 42.6k to 14.7k |
| Messages API / own harness | `compact.plan` / `apply` over the message list; the rival is `clear_tool_uses_20250919` | offline only (O3); no API key used |
| Codex CLI 0.158.0 | hooks are stable; no hook can edit earlier history or replace a built-in tool's output; compaction on OpenAI models is server-side and encrypted; `PostToolUse` + an MCP `search_archive` is the least fragile plug | **not verified**: in four `codex exec` attempts under the owner's ChatGPT login our trusted hooks never ran (not one journal line); inside Codex's Windows sandbox a venv's Python cannot start. See `codex/README.md` |

## Spend

Subscription, true cost at list price: probes 2.14 USD; Haiku 6.93 USD (pilot included);
Sonnet 3.75 USD; **12.82 USD in all** (ceiling 15.00).
Jev: 0.081 USD (O2). Codex: four checks against the owner's ChatGPT plan
(34k-60k input tokens each), not billed per token. No Anthropic or OpenAI API key was used.

## Files

`prereg.md`, `prereg.sha256`, `tasks.py`, `tasks.sha256`, `arms.py`, `evidence.py`, `run.py`,
`dry.py`, `estimate.py`, `analyze.py`, `analysis.json`, `phase-a.jsonl`, `runs.jsonl`,
`runs-pilot-invalid.jsonl`; `offline/` (Part 1); `probe/` (mechanics, before registration);
`exploratory/` (the attribution that found the invalid comparison); `codex/`.
