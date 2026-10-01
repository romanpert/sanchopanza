# Browse, Phases 3j and 3k: the hook after the saved-output and position fixes, twelve new tasks

Written 2026-10-01 before any session of these phases ran. Runners: `benchmarks/browse/e2e_mcp.py
--y --live --warmup` (3j, Playwright MCP) and `benchmarks/browse/e2e.py --y --live --warmup` (3k,
playwright-cli), each launched as its own command.

## Why

Two fixes since Phases 3h and 3i, each designed on their tasks, so both are measured on new ones:

- **A `Bash` output Claude Code saved to a file** (07f6a72). Past 30,000 characters Claude Code
  hands a `PostToolUse` hook only that prefix and shows the model the first 2,000 characters of the
  hook's reply. In 3i (X2, X4) the hook ranked the prefix and the model saw two kilobytes of the
  cut. The hook now ranks the whole saved output and replies with what fits. This touches
  playwright-cli on large pages (3k); Playwright MCP is unchanged by it.
- **Questions about position** (b16ce65): "the first quote", "the third book", "the last one" now
  pass through uncut. In 3h and 3i the cut cost three answers on such questions.

## Tasks

Answers checked by hand on 2026-10-01 from the pages' HTML (GitHub's language shares from its
API, as the page loads them by script); graded by required substrings (a list is met by any
alternative). Five ask for a position (Y5, Y8-Y11; `asks_for_position` holds for each and for no
other); several are pages whose playwright-cli snapshot passes 30,000 characters.

| id | start | question | required |
|---|---|---|---|
| Y1 | github.com/expressjs/express | license and largest language | mit; javascript |
| Y2 | github.com/rust-lang/rust | license and largest language | apache or mit; rust |
| Y3 | en.wikipedia.org/wiki/Germany | capital and currency, infobox | berlin; euro |
| Y4 | en.wikipedia.org/wiki/Danube | length in km and mouth, infobox | 2850; danube delta or black sea |
| Y5 | en.wikipedia.org/wiki/List_of_lakes_by_area | the lake listed first | caspian |
| Y6 | developer.mozilla.org, HTTP status 503 | the status code's name | service unavailable |
| Y7 | rfc-editor.org/rfc/rfc9111.html | title of section 5.2 | cache-control |
| Y8 | books.toscrape.com | Travel category: title of the third book | see america |
| Y9 | books.toscrape.com | History category: price of the last book | 43.70 |
| Y10 | quotes.toscrape.com | tag "life": author of the second quote | gide |
| Y11 | quotes.toscrape.com | page 3: author of the first quote | neruda |
| Y12 | books.toscrape.com | Philosophy category: price of "The Stranger" | 17.44 |

## Design

Phases 3h and 3i's, unchanged: three runs per task and arm, 72 counted sessions per tool, the two
tools at the same time, each process one session at a time, PLAIN then LEAN within a run. A
warm-up session (uncounted, run -9) before the first counted one; a process that resumes runs
another (run -10, ...) since its cache has gone cold. The hook at commit 07f6a72 with its
defaults.

## Decision rule, fixed now, for each tool apart

The hook is recommended with that tool if LEAN succeeds on at least as many runs as PLAIN minus
two and its mean cost per session (list USD plus Jev USD) is lower with the bootstrap interval of
the per-task difference (5,000 resamples over tasks, seed 2033) below zero.

Two checks, fixed now, reported whatever the rule says:

1. **Position.** On Y5 and Y8-Y11 the hook cuts nothing (zero cuts in LEAN), and LEAN succeeds on
   at least as many of those 15 runs as PLAIN minus one.
2. **Saved outputs (3k only).** The cuts the journal marks `preview` are counted by task; on the
   tasks where any LEAN run had one, LEAN minus PLAIN is reported by task, and every LEAN run with
   one is read.

## Money

At most 20.00 USD at list price per tool through the subscription (3h and 3i spent 8.77 and
8.84) and 1.00 USD of Jev per tool, within what is left of the 5 USD of Jev the owner approved
(about 1.57 used); expected well under 0.15. Each runner stops before passing either.

## What would make this wrong

Twelve tasks and an interval over twelve task means; five of them are positional and pass
through, so the hook can only save on seven, which makes a saving harder to show, not easier.
If the rule passes here and failed before, the difference can come from the fixes or the tasks;
the transcripts are read either way.
