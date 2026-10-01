# Browse, Phases 3n and 3o: the hook after the card, nearest-row and position-word fixes

Written 2026-10-01 before any session of these phases ran. Runners: `benchmarks/browse/e2e_mcp.py
--u --live --warmup` (3n, Playwright MCP) and `benchmarks/browse/e2e.py --u --live --warmup` (3o,
playwright-cli), each launched as its own command, once the other session sharing the
subscription has finished its run.

## Why

Changes since Phases 3l and 3m, each designed on recorded snapshots or hand-written goals, so
they are measured on new tasks:

- **Infobox rows nearest the kept one first** (4416aa4): the Danube's "Length" was the 23rd of 52
  rows and the budget ran out in page order.
- **A kept element brings the facts of its card** (4416aa4): Y12's price sat beside the kept link
  in its product card.
- **Which questions ask for a position** (d2a6fda, da4711d): the request only, a word of listing
  beside the ordinal, and "final", "top", "at the top/bottom"; on two sealed sets of hand-labelled
  goals, precision 0.50 -> 0.86 and recall 0.25 -> 0.92.

In development (`visible.py`, the 239 large snapshots PLAIN sessions received): the answer is in
what the model sees in 177 against 173 before these changes (BM25), none lost. That is the data
they were designed on.

## Tasks

Answers checked by hand on 2026-10-01 from the pages' HTML (GitHub's language shares from its
API); graded by required substrings (a list is met by any alternative). `asks_for_position`
holds for U7, U8 and U9 only; U2 ("the first ascent") is the kind of goal it used to misread.

| id | start | question | required |
|---|---|---|---|
| U1 | en.wikipedia.org/wiki/Rhine | length in km and mouth, infobox | 1230; north sea |
| U2 | en.wikipedia.org/wiki/Matterhorn | year of the first ascent, infobox | 1865 |
| U3 | en.wikipedia.org/wiki/Austria | capital and currency, infobox | vienna; euro |
| U4 | en.wikipedia.org/wiki/Mississippi_River | length in km and mouth, infobox | 3766; gulf of mexico |
| U5 | books.toscrape.com | Science Fiction: price of "The Project" | 10.65 |
| U6 | books.toscrape.com | Horror: price of "Pet Sematary" | 10.56 |
| U7 | quotes.toscrape.com | tag "friendship": author of the final quote | tennyson |
| U8 | books.toscrape.com | Classics: the book at the bottom of its first page | alice |
| U9 | en.wikipedia.org/wiki/List_of_countries_and_dependencies_by_area | the country listed first | russia |
| U10 | github.com/pallets/jinja | license and largest language | bsd; python |
| U11 | developer.mozilla.org, HTTP status 429 | the status code's name | too many requests |
| U12 | rfc-editor.org/rfc/rfc9113.html | title of section 6.5 | settings |

## Design

Phases 3l and 3m's, unchanged: three runs per task and arm, 72 counted sessions per tool, the two
tools at the same time, each process one session at a time, PLAIN then LEAN within a run, a
warm-up session first (and again on a resume). The hook at commit 4416aa4 with its defaults.

## Decision rule, fixed now, for each tool apart

The hook is recommended with that tool if LEAN succeeds on at least as many runs as PLAIN minus
two and its mean cost per session (list USD plus Jev USD) is lower with the bootstrap interval of
the per-task difference (5,000 resamples over tasks, seed 2033) below zero.

Checks, fixed now, reported whatever the rule says:

1. **Infobox and cards (U1-U6).** LEAN succeeds on at least as many of those 18 runs as PLAIN
   minus one; LEAN minus PLAIN reported for each task.
2. **Position (U7-U9).** LEAN succeeds on at least as many of those 9 runs as PLAIN minus one.
3. **U2.** The hook cuts or previews in at least one LEAN run (it no longer reads "the first
   ascent" as a position).

A session that returns the subscription's usage-limit notice instead of running is NOT RUN, is
left out of every count and is reported (3m lost three that way); if more than six do, the phase
is not analysed until they are run again.

## Money

At most 20.00 USD at list price per tool through the subscription (3l and 3m spent 8.71 and
7.65) and 1.00 USD of Jev per tool, within what is left of the 5 USD of Jev the owner approved
(about 2.17 used); expected well under 0.15. Each runner stops before passing either.

## What would make this wrong

Twelve tasks and an interval over twelve task means. With playwright-cli the agent may narrow
with `find` and leave the cut little to do (3k, 3m); that is reported as such.
