# What imposing `find_in_repo` on a frontier model could save at most (roadmap item A6)

**The result:** on clean Claude Code 2.1.287 with Sonnet 5.5, over 19 long-chain sessions and
1,046 bugs, the cost spent before the agent first reaches a file the fix changes, on the bugs
where `find_in_repo`'s top 5 holds that file, is **3.05 % of the model's cost, 95 % CI [2.36,
3.78]** (bootstrap over sessions; [2.00, 3.78] over the 5 chains). That is a ceiling: it assumes
find would replace all of that exploration and cost nothing itself. It is under 5 % with its
whole interval in the primary reading (any shell, Grep, Read or Edit call that names a fixed
file); with Read/Edit only, or with the re-read context, the upper bounds are 5.28 and 4.97 %
at points of 3.67 and 3.94 %. By the 5 % rule, **A6 is closed without spending**.

Free and offline: recorded streams and transcripts, local work copies, BM25 only. No Jev, no
Claude, no other paid API. Not pre-registered. The 5 % threshold is the plan's rule for every
bet replayed before a paid lot ([`PLAN-GANAR-H2H.md`](../../PLAN-GANAR-H2H.md), section 5, rule
2, 2026-10-07: only a bet whose realistic ceiling passes 5 % of the cost goes to a paid lot), the
one that archived bet A on long code.

## The question

Earlier lots offered `find_in_repo` to agents, which rarely called it: Haiku 4.5 in 6 of 27
sessions ([find-e2e](../2026-09-30-find-e2e/README.md)), and in 2 of 78 S sessions in phase D
([final scoreboard](../2026-10-13-final/README.md)). Getting an agent to use it (by a nudge, a
hook that runs it on the first prompt, or an instruction) costs Claude sessions to measure.
Before paying, this asks how much it could save if it worked perfectly. The saving is the
expensive model's cost spent finding the file the fix changes, on the bugs where find would
have pointed at it.

## Method

- **Sessions.** Every Sonnet 5.5 and Opus 5.5 long60 arm without sanchopanza (the smoke runs
  left out): clean Claude Code 2.1.287 with an empty `CLAUDE_CONFIG_DIR`, arms N (4 Sonnet
  sessions), Ne (N with the compact window, 9) and Nl (N with early compaction, 6). Five long60
  chains of SWE-smith bugs (conan ×2, moto ×2, pydantic), up to 60 bugs one after another in one
  session: **19 Sonnet sessions, 1,046 bug requests, 342.72 USD** (1,073 requests with the
  callbacks, which count only in the total).
- **Cost.** Each API request priced from the session transcript's final usage, matched by
  message id as the long runner meters its calls (the stream's usage carries only the output
  tokens at message start), at the API list rates (`benchmarks/meter.py`, `OWNER_RATES`).
  Subagent requests count under the request that spawned them. Only the expensive model counts;
  no other model ran in these sessions.
- **Gold files.** The files the bug's patch changes, tests left out (the chain manifests in
  `benchmarks/adopt/long60/`, else the patch's non-test files).
- **Reaching the gold.** The first main-thread request whose tool calls touch a gold file: a
  Read or an Edit (Write, MultiEdit) of it, or a shell or Grep call whose arguments name it (its
  last two path parts). The cost of the requests before it (0 to i−1) is what find could
  replace. A bug whose session never reaches a gold file counts in full. Two bugs whose call
  was cut (a `-dead` stream) count as whole bugs like the others.
- **Find.** `find_in_repo` with no key, `kind="code"`: the package's BM25 over code fragments
  (`context.repo.source_first(...).top(issue text, 5)`), on the chain's initial tree. A hit is a
  gold file in the top 5. It hits on **607 of 1,046 bugs (58.0 %)**.
- **Ceiling.** Sum of the cost before the gold on the bugs find hits, over the sessions' whole
  cost. 10,000 bootstrap draws (seed 20261015) over sessions; draws over chains and over
  requests are reported beside it.

## Result

| Reading, Sonnet 5.5, 19 sessions | Ceiling | 95 % CI | USD |
|---|---|---|---|
| **Primary: first Read, Edit or naming shell call, top 5** | **3.05 %** | **[2.36, 3.78]** | 10.47 of 342.72 |
| The same, bootstrap over the 5 chains | 3.05 % | [2.00, 3.78] | |
| The same, bootstrap over the 1,073 requests | 3.05 % | [2.33, 3.87] | |
| Bugs never reaching a gold file counted as 0 | 2.72 % | [2.15, 3.34] | 9.34 |

Why so little: Sonnet reaches the gold fast. A gold file is reached on 1,015 of the 1,046 bugs,
and the median number of requests before it is **0** (90th percentile 2): in most bugs the very
first request reads, greps or edits the right file. The cost before the gold over every bug that
reaches it, whether find hits or not, is 21.95 USD (6.4 %); the bugs find hits hold 9.34 of it,
and the 31 that never reach a gold file add 1.13 where find hits.

Per session the primary runs from 0.82 % to 6.70 %; 3 of the 19 reach 5 % (two Nl sessions and
one Ne, each on a different chain), and the pooled interval stays under 5.

## Sensitivities (Sonnet 5.5, 19 sessions)

| Change to the primary | Ceiling | 95 % CI |
|---|---|---|
| Requests 1 to i instead of 0 to i−1 (the session's first request, the system prompt's cache write, left out; the touching request counted) | 2.83 % | [2.17, 3.51] |
| Find's top 8 instead of top 5 (hits on 687 bugs; 8 is `find_in_repo`'s default k, 5 its hint's) | 3.72 % | [3.09, 4.36] |
| Plus the context the pre-gold exploration added, re-read at the cache-read rate by every later request until a compaction | 3.94 % | [2.99, 4.97] |
| Find always right (every bug counts) | 9.25 % | [7.85, 10.57] |
| Find always right, plus the re-read context | 11.44 % | [9.76, 13.00] |
| Find over every file kind instead of code (hits on 313) | 1.09 % | [0.72, 1.60] |
| Only a literal Read or Edit reaches the gold, bugs that never reach one counted as 0 | 3.67 % | [2.34, 5.28] |
| The same, requests 1 to i | 3.52 % | [2.24, 5.05] |
| Only a literal Read or Edit, bugs that never reach one counted in full | 43.43 % | [38.35, 47.81] |

- **Only with a perfect find does the ceiling pass 5 %.** BM25's top 5 is the find measured
  here; Jev's judged find was not replayed (see the limits).
- **The re-read rows can count twice.** The carry charges a bug with the re-reading its
  exploration causes in later requests, and those requests' cost can already count as a later
  bug's cost before its own gold. On the two phase-B chains the perfect-find row with the carry
  reaches 101.6 % of the sessions' cost under Read/Edit only. Read these rows as upper bounds.
- **The last row is not a ceiling.** In these chains Sonnet reads and edits mostly through the
  shell: a literal Read or Edit of a gold file happens on 284 of the 1,046 bugs, and 731 of the
  other 762 name the file in a shell or Grep call. Counting those 762 in full charges find with
  whole bugs whose file the agent reached through the shell.

## Other models and sets (reported)

| Set | Sessions | Bugs | Find top 5 hits | USD | Primary ceiling [95 % CI] | Requests 1 to i |
|---|---|---|---|---|---|---|
| Opus 5.5, clean Claude Code 2.1.287, long60 N (conan-1, pydantic-1) | 2 | 118 | 69 | 112.96 | 3.08 % [1.61, 4.32] | 2.96 % |
| Haiku 4.5, single SWE-bench Verified sessions (control arms of find_need's set) | 74 | 74 | 45 | 24.44 | 4.81 % [3.59, 6.21] | 1.76 % [1.09, 2.58] |
| Sonnet 5.5, two long chains with a user configuration loaded, Claude Code 2.1.285 | 2 | 50 | 32 | 14.57 | 3.33 % [1.07, 3.58] | 2.92 % |

- **Opus 5.5** comes out where Sonnet does. With 2 sessions the interval is the two sessions'
  values (conan-1 4.32 %, pydantic-1 1.61 %).
- **Haiku 4.5 on single issues reads 4.81 % [3.59, 6.21], but most of it is the session's first
  request** (the system prompt's cache write), which find cannot remove: counting requests 1 to
  i instead of 0 to i−1 gives 1.76 % [1.09, 2.58]. Its sessions come from earlier lots (phase A
  singles, two development probes, find-e2e) on the Claude Code builds of those lots, and Haiku
  is the mechanism model, not a frontier one. The 28 find-e2e sessions kept no transcript and are
  priced from their streams, 2.55 USD against the 3.03 Claude Code reported for them; with their
  costs scaled to the report, the ceiling would be about 4.9 %.
- The two chains with a user configuration loaded are not clean Claude Code and fill no cell;
  their interval is the two sessions' values (1.07 % and 3.58 %).

## Limits

- **No single-issue Sonnet 5.5 sessions.** Every Sonnet figure comes from long chains, where
  the agent has seen the repository by the time of the later bugs. A fresh repository, one issue
  per session, is the case where find should help most, and it is unmeasured on a frontier
  model. Haiku's single sessions are the only hint, and with the first request left out they read
  under 2 %.
- **Gold files are ambiguous.** A fix can be right in another file than the patch's, and an
  agent can reach a gold file early without knowing it is the one. Both make the ceiling a rough
  reading of "the cost of finding the file".
- **Shell detection is textual.** A shell call reaches a gold file when its arguments name the
  file's last two path parts; a glob, a directory listing or a grep over a folder that returns
  the file does not count, which pushes the reach later and the ceiling up.
- **No Jev judge in the replay.** Find with a key judges BM25's candidates in context (on 117
  Verified issues it put a file the fix edits first in 51 % and in the top 5 in 65 %,
  [find](../2026-09-29-find/README.md)). Its top 5 on these chains was not replayed, since that
  costs Jev. The perfect-find row bounds what any judge could add: 9.25 %.
- **The initial tree.** Find runs on the chain's tree before any bug; a later bug's code may
  have moved under the earlier fixes.
- **Compaction pushes the ceiling up.** The compacting arms read higher (N alone 2.63 %, Ne
  2.97 %, Nl 3.74 %), and the compaction calls' own cost (14.98 USD over the 19 sessions) is not
  in the transcripts, so not in the denominator. In the re-read rows it works the other way: the
  carry stops at a compaction and its cost is not charged to the exploration.
- **The ceiling assumes find is free and that the agent, told the file, goes straight to it.**
  Neither was measured; both lower the real saving.

**Against the long-compact lot's spend.** The 10 L-compact sessions cost 157.68 USD here, priced
from their transcripts, against the 173.11 the [long-compact](../2026-10-13-long-compact/README.md)
lot reports for them. The difference closes exactly: 11.28 USD of compaction calls the runner
metered from `modelUsage` and no transcript holds, and 4.15 USD for the one cut call (conan-2
Nl, request 40), which the runner charges at its cap.

## Files

- `a6-ceiling.json`: per set, the counts (`describe`), every ceiling above with its interval,
  the primary by arm, and per session the bugs, hits, USD, the primary ceiling and the
  Read/Edit-only one. No issue text, no file path, no message id.
- `benchmarks/find_need/a6_ceiling.py`: the analysis, with `benchmarks/find_need/test_a6_ceiling.py`
  (two synthetic sessions with known prices, stream against transcript). It needs the recorded
  long-chain runs and the local caches (SWE-smith rows, find_need's sessions, find_auto's
  recorded retrieval):

      python benchmarks/find_need/a6_ceiling.py retrieve --runs <runs root>   # BM25 top 8, cached
      python benchmarks/find_need/a6_ceiling.py report --runs <runs root>     # every table above
      python benchmarks/find_need/a6_ceiling.py summary                       # a6-ceiling.json

  `--runs` (or `SANCHOPANZA_A6_RUNS`) is the folder holding the long-chain run roots; the
  snapshots, the top-k cache and the full results with every unit stay in `--work` (default
  `~/.cache/sanchopanza/a6-ceiling`).
