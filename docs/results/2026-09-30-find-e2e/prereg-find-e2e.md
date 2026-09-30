# Pre-registration: find_in_repo end to end, with an agent

Written 2026-09-30, before any session of this run. `prereg-find-e2e.sha256` holds the hash of
this file with the code it names. The run starts only once its budget is approved.

## Why

The retrieval run (`../2026-09-29-find/`) measured `find_in_repo` alone, from the issue text:
a file the accepted fix edits comes first in 51 % of issues against 14 % for BM25. It said
what it does not show: whether an agent that already has `Grep`, `Glob` and `Read` localises
better, or cheaper, when the tool is offered. This runs the agent.

## Design (`benchmarks/find/e2e.py`)

- **Instances:** SWE-bench Verified, 4 per repository with seed 20260930, none from the 117 of
  the retrieval run or the 48 of its dev sample: 29 instances.
- **Sessions:** per instance and arm, a fresh git worktree at the base commit and one headless
  Claude Code session: Haiku 4.5, subscription, `--max-turns 25`, `--max-budget-usd 0.30`,
  `--setting-sources project --strict-mcp-config --permission-mode dontAsk`, the coordinating
  session's environment removed. The agent reads the issue, edits nothing, and ends with
  `FILES:` and up to five paths, most likely first.
- **Arms:**
  - `N`: `Read`, `Grep`, `Glob`;
  - `F`: the same, plus `find_in_repo` over the worktree (the BM25 shortlist judged by Jev
    `jev-1.13.0`). Offered, never imposed; the prompt does not mention it.
- **Label:** SWE-bench's, the files the accepted patch edits. A session with no `FILES` line
  is a miss and is reported apart.

## Hypotheses (`benchmarks/find/e2e_score.py`, paired by instance)

| | Hypothesis |
|---|---|
| E1 | F's any@1 is >= N's + 10 points. |
| E2 | F's median paired cost (list price, Jev not included) is <= N's: the tool does not make a session dearer. |
| E3 | F's median number of `Read` calls is <= N's. |

Also reported: any@5, how many F sessions called the tool at all, instances gained and lost,
Jev's cost, turns, tokens (input, cache read, cache write, output).

## Budget and caps (in code)

| | Cap | Expected |
|---|---|---|
| Subscription, sessions (list price) | 7.0 USD for the run, 0.30 per session | 4-7 |
| API, Jev inside the MCP server | 0.30 USD, summed from the journals between sessions | about 0.10 |

A session skipped by a ceiling is NOT RUN and reported as such.

## Threats, stated now

- **29 instances is small.** E1 asks for about three more first-file hits; a miss of E1 is not
  evidence of no effect, and a hit is not a precise estimate.
- **Adoption.** An agent may never call the tool. That is part of the answer, and reported.
- **Known repositories.** SWE-bench repositories are well known to generative models, which
  helps both arms alike.
- **Haiku only.** A stronger agent may search well enough that the tool adds nothing.
