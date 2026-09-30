# find_in_repo end to end: an agent localising SWE-bench issues with and without it

Registered in `prereg-find-e2e.md` (sealed before any session), amended twice before any verdict
was read (`amend-find-e2e-1.md`: the tool set; `amend-find-e2e-2.md`: Jev's accounting and three
sessions killed from outside). Run 2026-09-30.

**Question.** The retrieval run (`../2026-09-29-find/`) showed `find_in_repo` alone puts a file
of the accepted fix first in 51 % of issues, against 14 % for BM25. Does a Claude Code agent
that already has `Read`, `Grep` and `Glob` localise better, or cheaper, when the tool is
offered?

**Answer: not measurably, mostly because the agent rarely reached for it.** Offered the tool
without being told about it, Haiku 4.5 called it in 6 of 27 sessions. Over all 27 pairs the
first file was right in 17 against 16, the median session cost 0.006 USD more, and it read one
file fewer.

## Setup

- 29 SWE-bench Verified instances (4 per repository, seed 20260930, disjoint from the retrieval
  run and its dev sample), two arms, one headless Claude Code session per instance and arm in a
  fresh worktree at the base commit: Haiku 4.5, subscription, `--max-turns 25`,
  `--max-budget-usd 0.30`, `--tools Read,Grep,Glob`, `dontAsk`, nothing edited.
- `N`: `Read`, `Grep`, `Glob`. `F`: the same plus `mcp__sanchopanza__find_in_repo` (BM25
  shortlist judged by Jev `jev-1.13.0`), offered, never mentioned in the prompt.
- Label: the files the accepted patch edits. A session with no `FILES:` line is a miss.

## Verdicts (`summary.json`, 27 paired instances)

| | Hypothesis | Result | Verdict |
|---|---|---|---|
| E1 | F's any@1 >= N's + 10 points | F 17/27 (63 %, Wilson 95 % [44, 78]) vs N 16/27 (59 % [41, 75]): +3.7 points; 4 gained, 3 lost | **fails** |
| E2 | F's median paired cost <= N's | median paired delta +0.0058 USD (F 0.1092, N 0.1101 median per session) | **fails** |
| E3 | F's median `Read` calls <= N's | 6 against 7 | **holds** |

Also: any@5 17 vs 16; median turns 20 vs 23; sessions that hit the turn limit without a
`FILES` line 6 (F) vs 8 (N); total list cost 2.98 vs 2.95 USD; Jev 0.0132 USD.

**Adoption: 6 of 27 F sessions called `find_in_repo`, once each.** In those six (post hoc, not
registered, n = 6): F found the right first file in 3, N in 1; two instances gained
(astropy-8872, matplotlib-21568), none lost; F cost less in 3 of the 6.

## What it says

- A tool that is better than keyword search on its own does not show up in an agent's result
  when the agent seldom calls it. At 6 of 27 the run mostly measures two ways of using
  `Grep`. The honest reading of E1 is "no effect detectable at this adoption and this n",
  not "no effect". E1 asked for about three more hits; a stronger claim needs more instances
  or a prompt that names the tool, which is a different question (imposing it).
- It does not make a session dearer in any way that matters (0.6 cents at the median), and the
  sessions that used it read less and ended sooner.
- Where the agent did use it, the direction matches the retrieval run. Six sessions prove
  nothing; they are the reason to run adoption as its own question next.

## Budget and incidents

- **Ceiling 7.00 USD list (subscription), spent 6.73.** Three sessions NOT RUN by the ceiling:
  sympy-23413 F, sympy-24443 N and F (so 27 pairs, not 29).
- **Lost to incidents, still charged:** the pilot launched the whole run by a wrapper bug and
  ran with 36 tools (six sessions voided, amendment 1); a second launch was stopped because the
  tool running it would have killed it at ten minutes; three sessions were killed by another
  process (amendment 2). About 0.73 USD of the 6.73 went to voided sessions.
- **Jev's cap was not enforced during the run** (amendment 2); actual Jev spend 0.0132 USD
  against a 0.30 cap.

## Files

`summary.json` (the verdicts), `prereg-*` and `amend-*` (sealed). Per-session rows and streams
stay in `~/.cache/sanchopanza/find-e2e/` (they contain repository code).
