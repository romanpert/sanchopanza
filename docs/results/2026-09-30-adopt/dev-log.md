# Adoption study: development log

Development runs only (Haiku 4.5, subscription, list price). The held-out tasks have not been
run. Every number here is from development and does not count toward any confirmation.

## Pilot and round 1 (2026-09-30)

| chain | arm | resolved | list cost | compactions | notes |
|---|---|---|---|---|---|
| pygments-1 | N | 3/5 | 2.70 USD | 0 | request 2 spawned a subagent and hit the call cap |
| pygments-1 | S | 3/5 | 2.08 USD | 1 (161.7k, guard block attached) | one false shell denial (`rm -f` of its own scratch files) |
| starlette-1 | N | 4/5 | 1.86 USD | 0 | |
| starlette-1 | S | 4/5 | 1.90 USD | 1 (160.6k, guard block attached) | |

| pygments-1 r2 | N | 4/5 | 1.99 USD | 0 | |
| pygments-1 r2 | S | 3/5 | 1.97 USD | 0 | S ran alone after its export failed (fixed); the difference is the noisy bug pr_2434 (6/9 tests; 7/9, 8/9, 9/9 in the other sessions); sanchopanza made no decision that changed anything |

Singles (SWE-bench Verified, development, official harness):

| instance | N resolved / cost | S resolved / cost |
|---|---|---|
| django-15315 | yes / 0.49 | yes / 0.59 |
| django-14752 | yes / 0.18 | yes / 0.16 |
| matplotlib-23412 | yes / 0.51 | yes / 0.64 |
| django-11206 | no / 0.71 | no / 0.51 |
| django-12708 (hard) | yes / 0.67 | yes / 0.49 |
| django-16631 (hard) | no / 0.51 | no / 0.39 |

4/6 in both arms; total 3.08 against 2.77 USD, paired median ratio S/N about 0.82: n = 6, noise.

Same bugs resolved in every chain pair but pygments r2. Neither arm ever called `find_in_repo` or the skill: these
issues name the module or the function, and `Grep` finds it (what the skill itself says).

## What the pilot found in the harness and in sanchopanza, all fixed

- A resumed `claude -p` reports the session's cumulative cost: the first ledger counted 6.21 USD
  for 3.29 spent. Per-call cost is now the difference.
- A Docker pytest run that returned nothing was graded as every test failing; it now raises.
  Also, xargs turns pytest's exit 1 into 123.
- `runtests` had no extension: PowerShell treated it as a document and Windows asked the person
  at the desk which program should open it. A `runtests.cmd` goes first on PATH now.
- The agents saw sanchopanza's venv `python` on PATH and ran tests locally against it.
- **The shell guard judged a coding session as a research sandbox**: see
  `../2026-09-30-guard-coding/`. The default install now writes a coding profile.
- **The PowerShell tool was not guarded at all** (found by the adversarial review of the fix).

Declared: the S arms of round 1 ran the guard code as it was edited during the round (the
package is installed editable); the profile fix landed while they ran.

## Where the context goes, and why Haiku cannot show the budget lever

- Base context about 29k tokens; one hard request can add 90k (starlette request 2: 82 calls,
  40k to 128k), and every later request re-reads it.
- The 160k budget fires near the end of a five-bug chain on Haiku, whose own compaction would
  fire at about 167k anyway. The saving measured in the owner's real sessions (context re-read
  cost at 42 % with a 160k budget) lives in 1M-window sessions of 300k-400k tokens.

## Compaction at request boundaries: not buildable headless today (negative)

Replayed on the owner's 153 long sessions, compacting when a new request arrives with more than
100k in context, under a 200k budget, keeps the cost at 46 % of what it was (budget alone, 160k:
42 %) and cuts mid-request compactions from 938 to 333: the same saving, taken where a summary
loses least. Built as the function-hook module's trigger at `turn.complete` and at `turn.start`
(`benchmarks/adopt/probe_boundary.py`, four live probes, 0.19 USD): the hook fires and sees the
tokens, but `$.session.compact()` never resolves in `claude -p` 2.1.285 and nothing is compacted.
Reverted; not measurable in this benchmark. Untested in an interactive session.

## Memory between requests and sessions (the owner's pivot, 2026-09-30 evening)

Built as `sanchopanza install --memory` (off by default until measured): `context/episodes.py`
records each finished request by code from the transcript (the request, the agent's final text
verbatim, files changed and read, the last test run, the one-shot output lines the compaction
guard's rule keeps), and `harness/memory_hook.py` gives a later request, in the same session
after a compaction or in a new one, the records outside its live context that BM25 proposes and
Jev keeps. Classic hooks only (`Stop`, `SessionEnd`, `UserPromptSubmit`), no model inside.

Free or nearly free measures, before any session with it:

- **Nothing to recall in the independent chains.** In the six development transcripts no request
  re-reads a file an earlier request read (1 of 85 distinct file reads), while 60-79 % of what enters
  requests 3-5 is context carried from earlier requests. There the lever is cost (a fresh
  session per request, or a short context), and memory can only be neutral or distracting.
- **BM25 alone always injects.** Replaying each request as a fresh session, BM25 proposes earlier
  records for 12 of 12 requests; a candidate shares a file with the request in 1 of 12.
- **Jev with the request as the purpose stays quiet.** Same replay with `triage_pages`
  (`jev-1.13.0`, 12 decisions, 0.0008 USD per pass): with the request alone as the purpose, no
  record kept for 10 of 12 requests, one for the other 2. Two earlier passes put a framing
  sentence in front of the request and scored every record 0.4-0.9: **`chunks.context_questions`
  keeps the first 400 characters of a purpose**, so the decider saw little of the request. The
  guard's `judge` and `decider` choosers (not the default `rule`, not `keep`) put a 301- and
  182-character framing in front of the requests in the same way: noted, not changed here.
- `SANCHOPANZA_SESSION_MAX_USD`, set by `hook_env.py` for every S arm, is read by the autopilot
  only: the guard and memory have no per-session cap (memory makes at most one call per prompt).
- `guard.is_test_run` does not know the benchmark's `runtests`, so the "last test run" of a
  record (and of the guard's trail) is empty in this benchmark. Left as is: fitting the product
  to the benchmark's command would not be fair.

An adversarial review of the first version found no critical issue and four high ones, all
fixed before any session: a request cut by an automatic compaction (always mid-request, 57 of
57 local transcripts) or written again after a boundary was offered back while still in context;
the same records came back on every prompt; and the planned arms could not attribute a
difference to memory, hence the controls `Sfn` (default install, fresh sessions) and `Sb` (100k
budget alone). The splitter ran on the 1,308 local transcripts without an error.

**Related chains** (`tasks-related.md`, sealed at 8b9f1c8 before any session on them): each later
bug touches a file an earlier one touched. Their first bake failed: SWE-smith's `pr_mirror`
patches take the final newline off every file they touch, so two bugs in one file cannot both be
undone; that hunk is dropped and hunks may not overlap. `encode__starlette-rel-1` (development)
validated with its five drawn bugs.

## Development batch 1: a new session per request, and memory v1 (2026-09-30 evening)

Haiku 4.5, subscription, list price. Arms of `run.py` `ARM_SPECS`: `N` one session (Claude Code
alone), `Nf` a new session per request (alone), `Sfn` a new session per request with the default
install, `Sf` the same plus `--memory`. One run each; `N` of `encode__starlette-1` is round 1's.

| chain | arm | resolved | list cost | tool calls | memory records injected |
|---|---|---|---|---|---|
| encode__starlette-rel-1 (related) | N | 4/5 | 1.35 USD | 90 | - |
| | Nf | 4/5 | 1.57 | 149 | - |
| | Sfn | 4/5 | 1.92 | 180 | - |
| | Sf (memory v1) | 3/5 | 2.43 | 175 | 0 of 5 prompts |
| encode__starlette-1 (independent) | N | 4/5 | 1.86 | 122 | - |
| | Nf | 4/5 | 2.13 | 167 | - |
| | Sfn | 4/5 | 1.94 | 164 | - |
| | Sf (memory v2) | 4/5 | 2.06 | 175 | 0 of 5 prompts |

- **A new session per request costs more than one session** on both chains (+16 % and +14 % for
  `Nf` against `N`) and makes 37-66 % more tool calls: each request explores the repository again.
  That re-exploration is what memory in a new session would have to save (H-new-session).
- **Memory v1 did nothing.** In the related chain Jev scored every earlier record 0.09-0.32 and
  kept none, so `Sf` and `Sfn` were in effect the same condition twice. Their difference (one
  bug, pr_2732, lost by `Sf` on its most expensive request, 1.36 USD) is a measure of run-to-run
  noise, not of memory. pr_2041 is lost by every arm.
- No shell denial in any arm. The ceiling in code (23.50 USD of chain spend) cut starlette-1's
  later requests; Roman raised it to 30 and they were finished with `--continue` in the same
  working copies (25.90 USD of chain spend at the end).

Found and fixed during the batch, each with a test:

- **Records of real `claude -p` sessions had lost every tool call.** In those transcripts every
  tool result carries its request's `promptId`, and the deduplication of prompts written again
  after a compaction took any user entry with that id for a copy of the prompt. Records kept the
  request and the report only (no files, tests or output). Found by the dry test of the recall
  question, whose labels came out all negative. Fixed in dad6c95 (identity by `promptId` for
  requests only).
- **The recall question.** Page triage asks whether a record holds "a fact the answer would
  use"; the fix of another bug in the same file holds none. Replaced by a typed question
  (`points.memory.related_questions`: one Truth per record, "is the new request about the same
  code as this record?", the request whole in its own field). Dry test on the development
  transcripts, labels by code (the agent changed a file the new bug's reference patch touches):
  related records 0.07-0.56, unrelated 0.02-0.09 (10 related, 60 unrelated, 0.0014 USD). Cut
  derived on these data: **0.2** (8 of 10 related kept, 0 of 60 unrelated; at 0.5, 4 of 10).
  Thin margin: the provider moves by up to 0.09 between runs. `Sf` of starlette-1 ran v2 with
  the 0.5 cut; batch 2 runs v2 at 0.2.
- **The shell guard read the hook event in the console code page on Windows** (found by another
  session): a command holding "Á" or "═" crashed `sanchopanza hook` before it judged anything,
  and Claude Code ran the command. A regression test feeds `rm -rf /` with accents through a
  cp1252 console and fails on the old code. Every hook now reads UTF-8 bytes (ec774fe).

Declared: during batch 1 another session edited `src/sanchopanza/cli.py`, `squire.py` and
`harness/mcp.py` (no hook behaviour changed; 377 hook events of the batch all exited 0), and one
line each of `benchmarks/adopt/runtests.py` and `docker_env.py` (a virtualenv activated only when
`/testbed/.venv` exists, absent in starlette's image). `Sf` of starlette-1 started after memory
v2 was in place (its first record already carries its files) and ran with the 0.5 cut.

## Development batch 2: memory v2 at the 0.2 cut, in one session and in new ones (2026-09-30 night)

Haiku 4.5, subscription, list price, `encode__starlette-rel-1` repetition 2 (`--rep 2`, its own
working copies). `Sm` one session with `--memory` and a 100k context budget, `Sb` the same budget
without memory (its control), `Sf` a new session per request with `--memory` (memory v2, the
typed "same code" question, cut 0.2). Batch ceiling in code 32.90 USD of chain spend. Round 1's
arms of the same chain are repeated for reference.

| chain | arm | resolved | list cost | tool calls | compactions | records injected |
|---|---|---|---|---|---|---|
| rel-1 (r1) | N | 4/5 | 1.35 USD | 90 | 0 | - |
| rel-1 (r1) | Nf | 4/5 | 1.57 | 149 | 0 | - |
| rel-1 (r1) | Sfn | 4/5 | 1.92 | 180 | 0 | - |
| rel-1 (r1) | Sf (memory v1) | 3/5 | 2.43 | 175 | 0 | 0 of 5 prompts |
| rel-1 (r2) | Sb | 4/5 | 1.31 | 105 | 1 (at 100.6k) | - |
| rel-1 (r2) | Sm | 4/5 | 1.80 | 159 | 2 (at 101.6k, 102.8k) | 0 of 5 prompts |
| rel-1 (r2) | Sf (memory v2) | 3/5 | 1.46 | 123 | 0 | 3 of 5 prompts |

Per request (list cost / tool calls):

| arm | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|
| N (r1) | 0.18 / 14 | 0.27 / 21 | 0.10 / 7 | 0.55 / 34 | 0.26 / 14 |
| Nf (r1) | 0.19 / 21 | 0.41 / 48 | 0.12 / 9 | 0.47 / 37 | 0.38 / 34 |
| Sfn (r1) | 0.23 / 19 | 0.36 / 41 | 0.14 / 15 | 0.63 / 53 | 0.55 / 52 |
| Sb (r2) | 0.23 / 17 | 0.29 / 23 | 0.14 / 11 | 0.51 / 45 | 0.14 / 9 |
| Sm (r2) | 0.27 / 24 | 0.31 / 28 | 0.21 / 16 | 0.73 / 67 | 0.29 / 24 |
| Sf (r2) | 0.24 / 18 | 0.30 / 26 | 0.06 / 4 | 0.49 / 43 | 0.37 / 32 |

What memory did, from each arm's `memory.jsonl`:

- **`Sf`: it injected the related record every time it injected.** Request 3 (pr_2341,
  websockets.py) got the record of request 2 (p 0.52; request 2 touched responses.py and
  websockets.py), request 4 the record of request 1 (p 0.64, responses.py), request 5 the record
  of request 4 (p 0.27; request 1 at 0.25 also passed the cut, one record is shown). Unrelated
  records scored 0.03-0.08. This is what the dry test predicted.
- **Request 3's "already fixed" was right.** With the record of request 2 in hand the agent made
  4 tool calls, changed nothing and said the bug was already fixed (0.059 USD, against 7-19 calls
  and 0.10-0.20 USD for the same request in every other arm, `N` included). Grading the tree
  after each request (`grade-steps.json`, the same Docker pytest as `grade`): after request 2,
  pr_2341 already passes; the fix for pr_2041 fixed it on the way. A legitimate saving, n=1.
- **`Sm`: memory never acted.** Recall runs after a compaction, on the records no longer in
  context. After the compaction in request 4, request 5 (pr_2761, responses.py) had three
  candidates and Jev scored them 0.16 (request 1, responses.py: related), 0.07 and 0.06: none
  passed 0.2. So `Sm` and `Sb` were the same condition twice, and their difference (1.80 against
  1.31 USD, a second compaction, request 4 at 0.73 against 0.51) is run-to-run noise. The
  recall of the 0.2 cut was 8 of 10 in development; this is one of the misses.
- **The 100k budget alone (`Sb`) cost what one session costs (`N`)**: 1.31 against 1.35 USD, with
  one compaction. Different repetitions, n=1 each: not a saving, not a loss.
- pr_2041 is lost by every arm in both repetitions.

What went wrong, declared:

- **`Sf` request 4 ran `git checkout .`** (after a `git stash` that did nothing). It reverted the
  earlier requests' change to websockets.py, so pr_2341, fixed since request 2, fails in `Sf`'s
  final patch: `Sf` resolves 3 of 5 where the tree after request 3 held pr_2576 and pr_2341.
  It also emptied the files `sanchopanza install` wrote (`.claude/settings.json`, `.mcp.json`,
  the skill): the runner stages them as intent-to-add, and `git checkout .` restores them from
  the index as empty files. No `Stop` event was logged for request 4 (its record was written on
  the next prompt by the hook's catch-up of earlier transcripts), and request 5 could not start
  (`claude -p`: "MCP config is not a valid JSON"). The same command would empty a real user's
  untracked install; in a repository that commits its `.claude/` it would not. No other run of
  this study ran `git checkout .`, `reset --hard`, `restore .` or `clean` (grep of every
  stream). Seven streams ran `git stash`, some without a `pop`; in `Sf`'s copy it left no stash
  (the intent-to-add entries seem to make it fail), and no arm lost a bug grading would show
  other than as said here.
- **Request 5 of `Sf` was run again, declared.** First failure at 19:30 (exit 1 in 1.3 s, empty
  stream; the runner of that moment dropped stderr), recorded `NOT RUN (harness exit 1, rerun
  declared)`; the rerun with the new runner failed the same way and kept its stderr (the reason
  above). The three install files were then copied back from the arm's evidence (`settings.json`,
  `mcp.json`) and from `Sm`'s identical install (the skill), the agent's code left as it was, and
  request 5 ran (0.37 USD). Every failed attempt is kept (`stream-5.harness-failed*.jsonl`,
  `.err`, `row.before-rerun.json`).
- **Request 5 of `Sb` was cut by the ceiling** (`NOT RUN (cap)`: three arms each holding a 1.50
  USD call reservation against 32.90) and run with `--continue` in the same session (0.14 USD).
- A fresh session's first prompt logs a `record_error` (its own transcript does not exist yet
  when `UserPromptSubmit` fires). Harmless, noisy; not changed while arms were running.
- indagis-e0 committed af3e55a at 19:34, during this batch. It changed `harness/mcp.py`, but the
  arms' MCP server serves the `find` tool set only, which it did not touch.

Reading, honestly: n=1 per arm and repetition, and one bug of difference between two runs of the
same condition is noise (`Sm` against `Sb` here, `Sf` v1 against `Sfn` in batch 1). What this
batch shows is mechanism, not an effect: in new sessions the typed question picks the related
record, and once it saved a request that was already done; in one session with compaction the
0.2 cut missed the one related record it was offered. `Sf` v2 is the cheapest fresh-session arm
so far (1.46 USD, 123 calls, against 1.57-2.43 and 149-180), with the `git checkout .` costing
it a bug; that is a hint for H-new-session, not a result. Chain spend at the end: 30.47 USD
(development total with singles, probes and Jev: ~36.6 of 42 USD).

## Phase B, the long-session pilot on Sonnet 5.5 (indagis-45, 2026-09-30 evening)

Development, approved as part of the three-phase plan (B 25-30 USD, C 55-60 USD, A ~105 USD).
Written by the session that ran it; the pre-registration draft is `prereg-confirm.md`.

**The task.** `encode__starlette-long-1r1`: starlette-1 then starlette-rel-1 asked in ONE
session, one working copy, ten requests, graded per chain (`benchmarks/adopt/combined.py`). The
two chains did not fit in one image as drawn: pr_2141 (starlette-1) and pr_2041 (rel-1) change
the same lines of `websockets.py` (61-75) and share their six FAIL_TO_PASS. The combining rule,
written in `combined.py` before any session and agreed with indagis-6b: the first chain as it
is; a bug of the second that conflicts is replaced by that chain's first spare that conflicts
with nothing and shares a code file. pr_2041 -> pr_2443. Validated in Docker, 10 of 10 (171 s).

**Harness changes before B** (all tested; none changes a run already made):
- `run.py`: `--call-cap` and `--chain-cap`; combined chains run only when named and with
  `--model`; a timeout is charged its cap once (a resumed call after it no longer charges the
  cut part again); all or nothing per chain for held-out and combined tasks (every arm's chain
  cap held before any arm starts); held-out tasks refuse to run before the seal holds; each
  call's stderr kept in `stream-<k>.err`, and a call that never opened a session is recorded
  `NOT RUN (harness)` with the arm stopped there for `--continue`; install files snapshot after
  `install` and restored (and named in the row) if an agent changed them.
- `docker_env.py`: the install files stay out of the index (`git add -N` excluded them from the
  diff but not from the index: that is what emptied `Sf`'s install in batch 2); bake with
  `--no-verify`, `/testbed/.venv` where an image has one, grading with `-p no:pretty` (all three
  found validating pydantic; inert for pygments and starlette, checked).
- `confirm.py`, the verdict code the prereg will seal, reviewed adversarially before B (a
  code-reviewer subagent: two ways to read held-out runs before the seal, incomplete arms
  entering the cost ratio as zero, subagent calls counted as exploration; all fixed).

**Run** (`--model sonnet --call-cap 4.5 --chain-cap 15 --ceiling 60.5`, arms `N`, `Sm`):

| arm | resolved (starlette-1 + rel-1) | list cost | peak context | compactions | tool calls | wall |
|---|---|---|---|---|---|---|
| N | 9/10 (4 + 5) | 0.972 USD | 80.3k | 0 | 44 | 715 s |
| Sm | 9/10 (4 + 5) | 0.931 USD | 77.5k | 0 | 43 | 965 s |

Spent 1.90 USD (runs total 30.47 -> 32.37). The same bug unresolved in both arms. Memory offered
nothing on any of the ten prompts (no candidate: records are offered only once they leave the
live context, and nothing was compacted); hooks took 123 s of `Sm`'s wall time.

**The rule to run C** (fixed in the draft before B): `Sm` <= 0.90 of `N` and resolved >= N - 1.
Cost ratio 0.958: **not met, C is not run.**

**What B shows, plainly.** Not the lever: the premise was wrong. Sonnet 5.5 solved ten real bugs
in 44 tool calls and ended at 80k tokens of context, not the 300k-400k the plan expected from
Haiku's ~160k per five bugs. With a 100k budget nothing compacts below 80k, so `Sm` behaved as
the default install that never acts, and the 4 % difference is noise. These SWE-smith chains
do not produce the long sessions where the owner's spend sits (median context 308k-419k in 160
sessions of 100+ calls); a test of the budget lever needs tasks that do, which this benchmark
does not have. On Haiku (phase A), five bugs reach ~160k and a 100k budget does compact, so A
still tests `Sm` where it can act.

## Memory v3, measured on real sessions, and its smoke test here (indagis-72, 2026-10-01)

Batch 2 showed memory v2 picking the related record in these chains, but a chain of SWE-smith
issues is not how people ask. Measured on real people's Claude Code sessions (SWE-chat, 60 groups
of one person on one public repository, sealed; `docs/results/2026-10-01-memory-real`), v2
(recall at every prompt, decider at 0.2) gave something to 26-39 % of the requests that had
nothing related, at 3-7 % precision: only 2 % of BM25's candidates are related there, and a short
prompt ("fix it") is judged below chance. The Sm "miss" of batch 2 was a label artifact too: the
record Jev scored 0.16 was a different feature of the same file, which our own criteria call
unrelated.

v3 (in main, d5f8a25): when the agent opens or changes a file, the records of earlier requests
that changed it (the two newest, once per session, code only; `PostToolUse` on the file tools),
and recall at a prompt only at a session's first live request with the decider at 0.7.
Confirmed on the held-out half of SWE-chat: recall 0.950, precision 0.559, noise 0.034 (v2:
0.622 / 0.066 / 0.263). An adversarial review found 3 high and 7 medium issues first; all fixed
with tests (subagents, a lock on the index, stale records, compaction, paths after `cd`).

Smoke test on `encode__starlette-rel-1` repetition 3 (Haiku, n=1, to see the hooks work in
`claude -p`, not to measure an effect):

| arm | resolved | list cost | tool calls | records given by the touch |
|---|---|---|---|---|
| Sf (v3, new session per request) | 4/5 | 2.35 USD | 180 | 7 (29,302 characters) |
| Sm (v3, one session, 100k budget) | 4/5 | 1.35 USD | 115 | 1, after its compaction |

- No hook error in either arm; both lose only pr_2041, as every arm has.
- Sf's cost is its request 4 (pr_2732, 1.43 USD, 97 calls), the same bug that cost Sf v1 1.36
  USD in batch 1. In request 3 the decider scored the related record 0.49 (under 0.7, not given
  at the prompt) and the touch gave it when the agent opened websockets.py.
- **Found and fixed:** after Sm's compaction, `SessionStart: compact` read no boundary and every
  request live. Claude Code writes the `compact_boundary` entry after the SessionStart hooks
  (summary 19:18:57.389, hooks 57.960, boundary 58.021). Here it cost nothing (request 5's
  prompt read the boundary and the touch gave record 1), but the rest of a compacted request
  went without memory. Fixed in d5f8a25.
- Both request 5s were first cut by the ceiling (36.90, after Sf's 1.43 USD request 4) and run
  with `--continue` (ceiling 38.60). Chain spend: 32.37 to 36.08 USD (3.71 for this test).
