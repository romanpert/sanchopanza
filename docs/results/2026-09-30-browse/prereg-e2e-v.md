# Browse, Phase 3p: where the hook pays, on pages whose snapshot arrives inline

Written 2026-10-02 before any session of this phase ran. Runner: `benchmarks/browse/e2e_mcp.py
--v --live --warmup` (Playwright MCP only).

## Why

Read across Phases 3j, 3l and 3n (36 tasks, development, after the fact), the hook saved
0.047 USD a session on the six tasks where a large snapshot arrived inline (all six cheaper, 30-40
% of a session), nothing on the eight where the page was past Claude Code's limit (+0.001: Claude
Code saves the result, the agent `Grep`s it), and nothing to speak of where it had nothing to cut
(-0.005). A registered phase has only ever drawn a few inline pages, so this tests the claim on
tasks chosen for it, before anything is known of how the hook does on them: each page's snapshot
was measured with `playwright-cli snapshot` (free) at 11,000 to 75,000 characters, above the
hook's 6,000 and below the roughly 100,000 where Claude Code's MCP limit sets in.

It is also the first registered run of the hook asking Jev whether a request wants an element by
its place (`judged_position`, 7fd63c8 and 5dead40; 0.93 / 1.00 on sealed goals). V4 and V5 ask for
a place in words the old rule missed.

## Tasks

Answers checked by hand on 2026-10-02 from the pages' snapshots; graded by required substrings
(a list is met by any alternative), as before.

| id | start | question | required | snapshot chars |
|---|---|---|---|---|
| V1 | github.com/psf/requests | license and largest language | apache; python | 44,000 |
| V2 | en.wikipedia.org/wiki/Lake_Bled | surface area (km2) and max depth (m), infobox | 1.45; 29.5 | 71,000 |
| V3 | iana.org/domains/reserved | the RFC cited for special-use domain names | 6761 | 11,500 |
| V4 | docs.python.org/3/tutorial/index.html | the third chapter in the tutorial's contents | informal introduction | 40,000 |
| V5 | rust-lang.org | the link right after "Install" in the navigation menu | learn | 12,000 |
| V6 | nodejs.org/en/about/previous-releases | codename of Node.js 20 | iron | 31,000 |
| V7 | docs.python.org/3/library/os.path.html | version os.path.isjunction was added in | 3.12 | 75,000 |
| V8 | github.com/encode/httpx | license and largest language | bsd; python | 46,000 |
| V9 | postgresql.org/support/versioning | final release date of PostgreSQL 14 | November 12, 2026 (or 12 November 2026, 2026-11-12) | 15,000 |
| V10 | en.wikipedia.org/wiki/Bled | elevation in metres, infobox | 507.7 | 73,000 |
| V11 | en.wikipedia.org/wiki/Lake_Bohinj | max depth and surface elevation, infobox | 45 m; 526 | 36,000 |
| V12 | en.wikipedia.org/wiki/Lake_Jasna | region it lies in, infobox | upper carniola | 18,000 |

## Design

Phases 3l to 3n's, unchanged: three runs per task and arm, 72 counted sessions, one session at a
time, PLAIN then LEAN within a run, a warm-up session first (and again on a resume). The hook at
5dead40 with its defaults. playwright-cli is not run: its page content is about 16 % of a
session and it was never cheaper in four phases (`cli_cost.py`).

## Decision rule, fixed now

The claim holds if LEAN succeeds on at least as many runs as PLAIN minus two and its mean cost
per session (list USD plus Jev USD) is lower with the bootstrap interval of the per-task
difference (5,000 resamples over tasks, seed 2033) below zero.

Checks, fixed now, reported whatever the rule says:

1. **The tasks are what they were chosen to be.** The hook cuts in at least 20 of the 30 LEAN
   runs of the ten tasks other than V4 and V5. If it does not, the rule's verdict says little
   about inline pages and is reported as such.
2. **Position.** On V4 and V5 LEAN succeeds on at least as many of the 6 runs as PLAIN minus
   one, and the hook cuts none of those LEAN runs.
3. **Size.** The mean saving on the ten other tasks, reported per task, against the -0.047 USD
   read from 3j, 3l and 3n.

A session that returns the subscription's usage-limit notice is NOT RUN, left out of every count
and reported; past six, nothing is analysed until they are run again.

## Money

At most 20.00 USD at list price through the subscription (3n spent 8.53) and 1.00 USD of Jev,
within what is left of the 5 USD of Jev the owner approved (about 2.25 used); expected about 0.15.
The runner stops before passing either.

## What would make this wrong

Twelve tasks, an interval over twelve task means. The sizes are playwright-cli's; Playwright
MCP's snapshot of the same page can differ, and a page can change before it is visited (check 1
says whether the selection held). Pages chosen for size are not a sample of what users browse:
a pass says the hook pays on pages like these, not how often a user meets them.
