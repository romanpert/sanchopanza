# Browse, Phase 3r: rows that say which header each cell is under

Written 2026-10-02 before any session of this phase ran. Runner: `benchmarks/browse/e2e_mcp.py
--r --live --warmup` (Playwright MCP only).

## Why

Phase 3q was 16 % cheaper on data tables but did not meet its rule: on T4 (Django 5.2) all three
LEAN runs, shown the header row and the whole row, slid one column (an unnamed header; five
names for six cells) and gave the end of Active Support for Security Support. Since 2dd0bc8 a row
the cut brings whole carries one YAML comment pairing each cell with its header (`_row_label`).
In development (`visible.py`, 372 snapshots) it changed no answer's visibility and added 52
characters on average; it has not run in a session.

## Tasks

New pages, answers checked by hand on 2026-10-02 from the pages' snapshots. Each asks for the
cell of one row in a column with a neighbour of the same kind (two support end dates side by
side, a date beside a version), the slip T4 made. Graded by required substrings; a date is met by
its usual spellings.

| id | start | question | required | snapshot chars |
|---|---|---|---|---|
| R1 | endoflife.date/laravel | end of security support for Laravel 11 | 12 Mar 2026 | 22,500 |
| R2 | endoflife.date/rails | end of security support for Rails 7.2 | 09 Aug 2026 | 20,900 |
| R3 | endoflife.date/symfony | end of security support for Symfony 6.4 | 30 Nov 2027 | 31,100 |
| R4 | endoflife.date/spring-boot | end of commercial support for Spring Boot 3.4 | 31 Dec 2026 | 29,500 |
| R5 | endoflife.date/angular | end of active support for Angular 19 | 28 May 2025 | 31,800 |
| R6 | endoflife.date/nginx | release date of nginx 1.29 | 24 Jun 2025 | 34,500 |
| R7 | endoflife.date/redis | end of security support for Redis 7.4 | 01 Dec 2029 | 22,900 |
| R8 | endoflife.date/mongodb | end of security support for MongoDB 7.0 | 31 Aug 2027 | 20,200 |
| R9 | endoflife.date/electron | the Chrome version of Electron 43 | 150 | 24,200 |
| R10 | endoflife.date/dotnet | end of support for .NET 9 | 10 Nov 2026 | 20,700 |
| R11 | endoflife.date/kubernetes | end of maintenance support for Kubernetes 1.33 | 28 Jun 2026 | 38,400 |
| R12 | endoflife.date/elasticsearch | end of support for Elasticsearch 8.19 | 15 Jul 2027 | 18,600 |

All twelve from one site, chosen for its tables of near-identical columns; that is a limit,
stated below.

**R0, reported apart:** 3q's T4 again (same page, question and answer). It is the task the fix
was written on, so it counts in no rule; it says whether the fix does what it was built to.

## Design

Phase 3q's: three runs per task and arm, one session at a time, PLAIN then LEAN within a run, a
warm-up session first (and again on a resume). The hook at 2dd0bc8 with its defaults.
Playwright MCP only.

## Decision rule, fixed now, on R1-R12 only

Computed by the runner's own `analyze` on the R1-R12 sessions: the hook is cheaper on these
pages if LEAN succeeds on at least as many runs as PLAIN minus two and its mean cost per session
(list USD plus Jev USD) is lower with the bootstrap interval of the per-task difference (5,000
resamples over tasks, seed 2033) below zero.

Checks, fixed now, reported whatever the rule says:

1. **The tasks are what they were chosen to be.** The hook cuts in at least 24 of the 36 LEAN
   runs of R1-R12.
2. **Answers.** On R1-R12 LEAN succeeds on at least as many runs as PLAIN minus one.
3. **R0.** LEAN answers T4 right in at least two of its three runs (it answered none in 3q).

A session that returns the subscription's usage-limit notice is NOT RUN, left out of every count
and reported; past six, nothing is analysed until they are run again.

## Money

At most 20.00 USD at list price through the subscription (3q spent 7.21) and 1.00 USD of Jev,
within what is left of the 5 USD of Jev the owner approved (about 2.40 used); expected under 0.10.
The runner stops before passing either.

## What would make this wrong

Twelve tasks from one site; an interval over twelve task means. Columns that look alike are
what the label is for, so a pass here says it holds on such tables, not on every table.
