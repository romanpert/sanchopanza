# Browse, Phase 3q: a row of a data table, on pages whose snapshot arrives inline

Written 2026-10-02 before any session of this phase ran. Runner: `benchmarks/browse/e2e_mcp.py
--t --live --warmup` (Playwright MCP only).

## Why

Phase 3p passed (17 % cheaper on inline pages) and showed one way the hook still costs: V9 cut
PostgreSQL's version table and kept the cell "14" without "November 12, 2026" beside it in the
same row, so the agent searched the archive. Since 890d3f1 a cell the cut keeps in a data table
brings its whole row and the table's column headers (up to six rows a table). In development
(`visible.py`, BM25, 372 snapshots of earlier phases, V9 among them) the answer became visible
in 275 against 271, four gained, none lost. This phase measures it on new pages that are data
tables, chosen, like 3p's, by measured snapshot size so that they arrive inline.

## Tasks

Answers checked by hand on 2026-10-02 from the pages' snapshots. Each asks for one cell of one
row. Graded by required substrings; a date is met by its usual spellings (31 Oct 2028, 31
October 2028, October 31, 2028, 2028-10-31).

| id | start | question | required | snapshot chars |
|---|---|---|---|---|
| T1 | endoflife.date/python | end of security support for Python 3.12 | 31 Oct 2028 | 17,700 |
| T2 | endoflife.date/nodejs | end of security support for Node.js 20 | 30 Apr 2026 | 34,500 |
| T3 | endoflife.date/ubuntu | end of Expanded Security Maintenance for Ubuntu 22.04 | 21 Apr 2032 | 47,700 |
| T4 | endoflife.date/django | end of security support for Django 5.2 | 30 Apr 2028 | 22,900 |
| T5 | endoflife.date/debian | end of Debian LTS for Debian 12 | 30 Jun 2028 | 25,700 |
| T6 | endoflife.date/ruby | end of support for Ruby 3.2 | 31 Mar 2026 | 15,300 |
| T7 | endoflife.date/go | release date of Go 1.25 | 12 Aug 2025 | 14,900 |
| T8 | endoflife.date/mysql | end of Extended Support for MySQL 8.4 | 30 Apr 2032 | 25,100 |
| T9 | iana.org HTTP status code registry | the description of code 418 | unused | 29,800 |
| T10 | devguide.python.org/versions | release manager of Python 3.11 | galindo | 32,800 |
| T11 | php.net/supported-versions.php | end of security support for PHP 8.2 | 31 Dec 2026 | 7,900 |

Eight come from one site (endoflife.date); T9-T11 are three others, one (T10) with each cell's
value inside a paragraph.

## Design

Phase 3p's: three runs per task and arm (66 counted sessions), one session at a time, PLAIN then
LEAN within a run, a warm-up session first (and again on a resume). The hook at 890d3f1 with its
defaults. Playwright MCP only.

## Decision rule, fixed now

The hook is cheaper on these pages if LEAN succeeds on at least as many runs as PLAIN minus two
and its mean cost per session (list USD plus Jev USD) is lower with the bootstrap interval of
the per-task difference (5,000 resamples over tasks, seed 2033) below zero.

Checks, fixed now, reported whatever the rule says:

1. **The tasks are what they were chosen to be.** The hook cuts in at least 22 of the 33 LEAN
   runs.
2. **The row comes with the cut.** LEAN runs that use `Grep` or `Read` number at most PLAIN's
   plus three (in 3p, V9's LEAN runs went to the archive for the row; PLAIN's never did).
3. **Answers.** LEAN succeeds on at least as many runs as PLAIN minus one.

A session that returns the subscription's usage-limit notice is NOT RUN, left out of every count
and reported; past six, nothing is analysed until they are run again.

## Money

At most 20.00 USD at list price through the subscription (3p spent 8.54) and 1.00 USD of Jev,
within what is left of the 5 USD of Jev the owner approved (about 2.35 used); expected under 0.10.
The runner stops before passing either.

## What would make this wrong

Eleven tasks, eight from one site; an interval over eleven task means. Relative dates on
endoflife.date ("Ends in 2 years") change daily; the questions ask for the absolute dates beside
them, which do not. Pages chosen for size are not a sample of what users browse.
