# Browse, Phases 3h and 3i: the hook after Phase 3f's fixes, on twelve tasks it has not seen

Written 2026-10-01 before any session of these phases ran. Runners: `benchmarks/browse/e2e_mcp.py
--x --warmup` (3h, Playwright MCP) and `benchmarks/browse/e2e.py --x --warmup` (3i,
playwright-cli).

## Why

Phase 3f (Playwright MCP, twelve tasks) did not pass: -0.0061 USD a session [-0.0257, +0.0101]
without the warm-up run. Its transcripts showed two fixable causes, fixed in commit fccc06a with
tests: Jev ranking 2,000-3,000 elements of a huge page cost more than the cut saved (now BM25
shortlists 600 before Jev), and a section the question pointed at lost its body (a heading that
shares a word with the goal now brings up to 12 lines). Both were designed on 3f's tasks, so they
are measured on twelve new ones, chosen to include what they touch: huge Wikipedia pages,
GitHub's "Languages" section, and the several-step tasks. Phase 3g (playwright-cli) passed; 3i
checks it holds with the fixed hook.

## Tasks

Answers checked by hand on 2026-10-01; graded by required substrings (a list is met by any
alternative):

| id | start | question | required |
|---|---|---|---|
| X1 | github.com/pallets/click | license and largest language | bsd; python |
| X2 | github.com/facebook/react | license and largest language | mit; javascript |
| X3 | github.com/golang/go | license | bsd |
| X4 | en.wikipedia.org/wiki/France | capital and currency, infobox | paris; euro |
| X5 | en.wikipedia.org/wiki/Mount_Fuji | height of its highest point, infobox | 3776 |
| X6 | en.wikipedia.org/wiki/List_of_highest_mountains_on_Earth | the highest mountain | everest |
| X7 | developer.mozilla.org, HTTP status 404 | the status code's name | not found |
| X8 | rfc-editor.org/rfc/rfc9110.html | title of section 15.3.1 | 200 ok |
| X9 | books.toscrape.com | Science category: price of the first book | 42.96 |
| X10 | books.toscrape.com | Poetry category: UPC of the second book | 1dfe412b8ac00530 |
| X11 | quotes.toscrape.com | page 2: author of the first quote | monroe |
| X12 | quotes.toscrape.com | tag "humor": author of the first quote | austen |

## Design

Phases 3f and 3g's, unchanged, with the warm-up the amendment to them introduced: one uncounted
PLAIN session (run -9) before the first counted one, in each process. Three runs per task and arm,
72 counted sessions per tool, the two tools at the same time, each process one session at a time.
The hook at commit fccc06a with its defaults.

## Decision rule, fixed now, for each tool apart

The hook is recommended with that tool if LEAN succeeds on at least as many runs as PLAIN minus
two and its mean cost per session (list USD plus Jev USD) is lower with the bootstrap interval of
the per-task difference (5,000 resamples over tasks, seed 2033) below zero. Reported besides: the
cuts by task, the Jev dollars of LEAN, and how many snapshots were shortlisted.

## Money

At most 20.00 USD at list price per tool through the subscription (3f and 3g spent 8.52 and 7.87)
and 2.00 USD of Jev per tool (expected well under 0.10 now that huge pages are shortlisted); each
runner stops before passing either.

## What would make this wrong

Twelve tasks and an interval over twelve task means. If 3h passes and 3f did not, the difference
can come from the fixes or from the tasks; the transcripts are read either way.
