# Browse, Phases 3l and 3m: the hook after the infobox and page-order fixes, twelve new tasks

Written 2026-10-01 before any session of these phases ran. Runners: `benchmarks/browse/e2e_mcp.py
--z --live --warmup` (3l, Playwright MCP) and `benchmarks/browse/e2e.py --z --live --warmup` (3m,
playwright-cli), each launched as its own command.

## Why

Three changes since Phases 3j and 3k (0138a2d), each designed on their sessions or on the
recorded snapshots of earlier phases, so they are measured on new tasks:

- **An infobox the cut touches keeps its keys and values.** 3j's Y4: the cut kept the Danube's
  "Mouth" row and dropped "Length 2,850 km", plain text the ranking never sees.
- **A question about position, or the agent's own `find`, on a `Bash` output Claude Code saved,
  comes back as the page's content in page order** (from the end for "the last", from the table
  or list the question names). Passing it through had shown the model the output's first 2,000
  characters, the banner and the navigation.
- **Lines that say nothing** (rows of star icons) leave the 2,000-character preview.

In development (`benchmarks/browse/visible.py`, the 239 large snapshots PLAIN sessions of earlier
phases received, BM25, no Jev) the answer is in what the model sees in 173 snapshots against 152
for the hook at a31edd3 and 143 with no hook, none lost; on saved `Bash` outputs 15 of 20 against
1. That is the data the changes were designed on and claims nothing.

## Tasks

Answers checked by hand on 2026-10-01 from the pages' HTML (GitHub's language shares from its
API); graded by required substrings (a list is met by any alternative). `asks_for_position`
holds for Z2, Z5, Z6, Z9 and Z10. Z2 ("the first ascent") is a false positive of that rule, kept
as asked: the hook passes it through uncut unless the output is saved.

| id | start | question | required |
|---|---|---|---|
| Z1 | en.wikipedia.org/wiki/Nile | length in km and mouth, infobox | 7088; mediterranean |
| Z2 | en.wikipedia.org/wiki/Mont_Blanc | year of the first ascent, infobox | 1786 |
| Z3 | en.wikipedia.org/wiki/Italy | capital and currency, infobox | rome; euro |
| Z4 | en.wikipedia.org/wiki/Amazon_River | length in km, infobox | 6575 or 6400 |
| Z5 | en.wikipedia.org/wiki/List_of_largest_cities | the city listed first | jakarta |
| Z6 | en.wikipedia.org/wiki/List_of_river_systems_by_length | the river ranked first | nile |
| Z7 | github.com/django/django | license and largest language | bsd; python |
| Z8 | github.com/vuejs/core | license and largest language | mit; typescript |
| Z9 | books.toscrape.com | Fantasy category: title of the last book on its first page | folly |
| Z10 | quotes.toscrape.com | tag "inspirational": author of the third quote | edison |
| Z11 | developer.mozilla.org, HTTP status 301 | the status code's name | moved permanently |
| Z12 | rfc-editor.org/rfc/rfc9112.html | title of section 3.2 | request target |

## Design

Phases 3j and 3k's, unchanged: three runs per task and arm, 72 counted sessions per tool, the two
tools at the same time, each process one session at a time, PLAIN then LEAN within a run, a
warm-up session first (and again on a resume). The hook at commit 0138a2d with its defaults.

## Decision rule, fixed now, for each tool apart

The hook is recommended with that tool if LEAN succeeds on at least as many runs as PLAIN minus
two and its mean cost per session (list USD plus Jev USD) is lower with the bootstrap interval of
the per-task difference (5,000 resamples over tasks, seed 2033) below zero.

Checks, fixed now, reported whatever the rule says:

1. **Infobox (Z1-Z4).** LEAN succeeds on at least as many of those 12 runs as PLAIN minus one;
   LEAN minus PLAIN reported for each.
2. **Position (Z5, Z6, Z9, Z10).** LEAN succeeds on at least as many of those 12 runs as PLAIN
   minus one; cuts there are only page-order previews of saved outputs.
3. **Saved outputs (3m).** Every LEAN run whose journal marks a `preview` is listed and read.

## Money

At most 20.00 USD at list price per tool through the subscription (3j and 3k spent 9.25 and
7.81) and 1.00 USD of Jev per tool, within what is left of the 5 USD of Jev the owner approved
(about 1.62 used); expected well under 0.15. Each runner stops before passing either.

## What would make this wrong

Twelve tasks, an interval over twelve task means, and five tasks the hook mostly leaves alone.
With playwright-cli the agent may again take few snapshots (3k: none outside positional tasks),
which would leave the cli fixes unexercised; that is reported as such, not as a result.
