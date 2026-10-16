# What imposing `find_in_repo` on a frontier model could save at most (A6)

**The result:** on clean Claude Code 2.1.287 with Sonnet 5.5, over 19 long-chain sessions and
1,046 bugs, the cost spent before the agent first reaches a file the fix changes, on the bugs
where `find_in_repo`'s top 5 holds that file, is **3.20 % of the model's cost, 95 % CI [2.50,
3.94]** (bootstrap over sessions). That is a ceiling: it assumes find would replace all of that
exploration and cost nothing itself. The rule for this analysis was to pay for a lot that makes
an agent use find only if the ceiling reached 5 %. It is under 5 % with its whole interval, so
**A6 is closed without spending**.

Free and offline: recorded streams, local work copies, BM25 only. No Jev, no Claude, no other
paid API. Not pre-registered: the 5 % threshold is the script's `THRESHOLD`, fixed before the
report was run.

## The question

Earlier lots offered `find_in_repo` to agents, which rarely called it: Haiku 4.5 in 6 of 27
sessions ([find-e2e](../2026-09-30-find-e2e/README.md)), and in 2 of 78 S sessions in phase D
([final scoreboard](../2026-10-13-final/README.md)). Getting an agent to use it (by a nudge, a
hook that runs it on the first prompt, or an instruction) costs Claude sessions to measure.
Before paying, this asks how much it could save if it worked perfectly. The saving is the
expensive model's cost spent finding the file the fix changes, on the bugs where find would
have pointed at it.

## Method

- **Sessions.** Every recorded long-chain arm without sanchopanza: clean Claude Code 2.1.287
  with an empty `CLAUDE_CONFIG_DIR`, Sonnet 5.5, arms N (4 sessions), Ne (N with the compact
  window, 9) and Nl (N with early compaction, 6). Five long60 chains of SWE-smith bugs (conan
  ×2, moto ×2, pydantic), up to 60 bugs one after another in one session: **19 sessions,
  1,046 bug requests, 301.66 USD** of Sonnet 5.5 (1,073 requests with the callbacks, which count
  only in the total).
- **Cost.** Each API request priced from its own tokens at the API list rates
  (`benchmarks/meter.py`, `OWNER_RATES`), subagent requests included under the request that
  spawned them. Only the expensive model counts; no other model ran in these sessions.
- **Gold files.** The files the bug's patch changes, tests left out (the chain manifests in
  `benchmarks/adopt/long60/`, else the patch's non-test files).
- **Reaching the gold.** The first main-thread request whose tool calls touch a gold file: a
  Read or an Edit (Write, MultiEdit) of it, or a shell or Grep call whose arguments name it (its
  last two path parts). The cost before that request is what find could replace. A bug whose
  session never reaches a gold file counts in full.
- **Find.** `find_in_repo` with no key, `kind="code"`: the package's BM25 over code fragments
  (`context.repo.source_first(...).top(issue text, 5)`), on the chain's initial tree. A hit is a
  gold file in the top 5. It hits on **607 of 1,046 bugs (58.0 %)**.
- **Ceiling.** Sum of the cost before the gold on the bugs find hits, over the sessions' whole
  cost. 10,000 bootstrap draws over sessions (seed 20261015); a draw over requests is reported
  beside it.

## Result

| Reading, Sonnet 5.5, 19 sessions | Ceiling | 95 % CI | USD |
|---|---|---|---|
| **Primary: first Read, Edit or naming shell call, top 5** | **3.20 %** | **[2.50, 3.94]** | 9.65 of 301.66 |
| The same, bootstrap over the 1,073 requests | 3.20 % | [2.46, 4.04] | |
| Bugs never reaching a gold file counted as 0 | 2.89 % | [2.28, 3.53] | 8.71 |

Why so little: Sonnet reaches the gold fast. A gold file is reached on 1,015 of the 1,046 bugs,
and the median number of requests before it is **0** (90th percentile 2): in most bugs the very
first request reads, greps or edits the right file. The cost before the gold over every bug that
reaches it, whether find hits or not, is 20.33 USD (6.7 %); the bugs find hits hold 8.71 of it,
and the 31 that never reach a gold file add 0.94 where find hits.

Per session the primary runs from 0.89 % to 6.89 %; 3 of the 19 reach 5 % (two Nl sessions and
one Ne, each on a different chain), and the pooled interval stays under 5.

## Sensitivities (Sonnet 5.5, 19 sessions)

| Change to the primary | Ceiling | 95 % CI |
|---|---|---|
| Find's top 8 instead of top 5 (hits on 687 bugs) | 3.88 % | [3.24, 4.53] |
| Plus the context the pre-gold exploration added, re-read at the cache-read rate by every later request until a compaction | 4.21 % | [3.21, 5.29] |
| Find always right (every bug counts) | 9.58 % | [8.17, 10.90] |
| Find always right, plus the re-read context | 12.08 % | [10.38, 13.63] |
| Find over every file kind instead of code (hits on 313) | 1.14 % | [0.76, 1.66] |
| Only a literal Read or Edit reaches the gold, bugs that never reach one counted as 0 | 3.71 % | [2.35, 5.39] |
| Only a literal Read or Edit, bugs that never reach one counted in full | 44.19 % | [39.17, 48.46] |

- **Only with a perfect find does the ceiling pass 5 %.** BM25's top 5 is the find measured
  here; Jev's judged find was not replayed (see the limits).
- **The re-read context** takes the upper bound to 5.29 %, with the point at 4.21 %.
- **The last row is not a ceiling.** In these chains Sonnet reads and edits mostly through the
  shell: a literal Read or Edit of a gold file happens on 284 of the 1,046 bugs. Counting the
  762 others in full charges find with whole bugs whose file the agent reached through the shell.
  Read/Edit-only with those bugs at 0 gives 3.71 % [2.35, 5.39].

## Other models and sets (reported)

| Set | Sessions | Bugs | Find top 5 hits | USD | Primary ceiling [95 % CI] |
|---|---|---|---|---|---|
| Opus 5.5, clean Claude Code 2.1.287, long60 N (conan-1, pydantic-1) | 2 | 118 | 69 | 105.50 | 3.15 % [1.67, 4.36] |
| Haiku 4.5, single SWE-bench Verified sessions (control arms of find_need's set) | 74 | 74 | 45 | 20.75 | 5.29 % [3.96, 6.79] |
| Sonnet 5.5, two long chains with a user configuration loaded, Claude Code 2.1.285 | 2 | 50 | 32 | 13.26 | 3.39 % [1.08, 3.63] |

- **Opus 5.5** comes out where Sonnet does, on 2 sessions; its interval is two clusters wide.
- **Haiku 4.5 on single issues** is the only set over 5 %: a weaker model starting cold on a
  repository explores more before it finds the file (median 2 requests). Its sessions come from
  earlier lots (phase A singles, two development probes, find-e2e) on the Claude Code builds of
  those lots, and Haiku is the mechanism model, not a frontier one.
- The two chains with a user configuration loaded are not clean Claude Code and fill no cell.

## Limits

- **No single-issue Sonnet 5.5 sessions.** Every Sonnet figure comes from long chains, where
  the agent has seen the repository by the time of the later bugs. A fresh repository, one issue
  per session, is the case where find should help most, and it is unmeasured on a frontier
  model; Haiku's 5.29 % is the only hint.
- **Gold files are ambiguous.** A fix can be right in another file than the patch's, and an
  agent can reach a gold file early without knowing it is the one. Both make the ceiling a rough
  reading of "the cost of finding the file".
- **Shell detection is textual.** A shell call reaches a gold file when its arguments name the
  file's last two path parts; a glob, a directory listing or a grep over a folder that returns
  the file does not count, which pushes the reach later and the ceiling up.
- **No Jev judge in the replay.** Find with a key judges BM25's candidates in context (on 117
  Verified issues it put a file the fix edits first in 51 % and in the top 5 in 65 %,
  [find](../2026-09-29-find/README.md)). Its top 5 on these chains was not replayed, since that
  costs Jev. The perfect-find row bounds what any judge could add: 9.58 %.
- **The initial tree.** Find runs on the chain's tree before any bug; a later bug's code may
  have moved under the earlier fixes.
- **Compaction is left out** of the re-read context: a compaction ends the carry, and its own
  cost is not attributed to the exploration that filled the context.
- **The ceiling assumes find is free and that the agent, told the file, goes straight to it.**
  Neither was measured; both lower the real saving.

## Files

- `a6-ceiling.json`: per set, the counts (`describe`), every ceiling above with its interval,
  and per session the bugs, hits, USD, the primary ceiling and the Read/Edit-only one. No issue
  text, no file path, no message id.
- `benchmarks/find_need/a6_ceiling.py`: the analysis. It needs the recorded long-chain runs and
  the local caches (SWE-smith rows, find_need's sessions, find_auto's recorded retrieval):

      python benchmarks/find_need/a6_ceiling.py retrieve --runs <runs root>   # BM25 top 8, cached
      python benchmarks/find_need/a6_ceiling.py report --runs <runs root>     # every table above
      python benchmarks/find_need/a6_ceiling.py summary                       # a6-ceiling.json

  `--runs` (or `SANCHOPANZA_A6_RUNS`) is the folder holding the long-chain run roots; the
  snapshots, the top-k cache and the full results with every unit stay in `--work` (default
  `~/.cache/sanchopanza/a6-ceiling`).
