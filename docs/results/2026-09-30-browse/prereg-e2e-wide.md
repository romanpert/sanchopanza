# Browse, Phases 3f and 3g: the hook on twelve more tasks, with Playwright MCP and playwright-cli

Written 2026-10-01 before any session of these phases ran. Runners: `benchmarks/browse/e2e_mcp.py
--wide` (3f) and `benchmarks/browse/e2e.py --wide` (3g).

## Why

Phases 3d (Playwright MCP, -12.9 %) and 3e (playwright-cli, -8.6 %, partly session noise) each
rest on six tasks, mostly reading one page. This widens the sample to twelve new tasks, five of
them several steps long (open a category, open a book, page through, follow a tag), on ordinary
public pages, and runs both tools on the same tasks.

The hook is the one of commit 1476d12: Phase 3d's, plus the fixes of a code review on
2026-10-01 (goal parts sized so none falls off; no goal, no cut; Claude Code's notice read only
for MCP results; a return cap of 60,000 characters; a CLI `find` only as the subcommand). None of
them was designed on these tasks.

## Tasks

Answers checked by hand on 2026-10-01 (docs.python.org was down, 503, so none of its pages is
used; gnu.org refused scripted requests and was dropped):

| id | start | question | required |
|---|---|---|---|
| W1 | github.com/psf/requests | license and largest language | apache; python |
| W2 | github.com/microsoft/vscode | license and largest language | mit; typescript |
| W3 | en.wikipedia.org/wiki/Mount_Kilimanjaro | elevation in metres, infobox | 5895 |
| W4 | en.wikipedia.org/wiki/Spain | capital and currency, infobox | madrid; euro |
| W5 | rfc-editor.org/rfc/rfc9110.html | title of section 15.5.5 | not found |
| W6 | developer.mozilla.org, HTTP status 418 | the status code's name | teapot |
| W7 | en.wikipedia.org/wiki/List_of_tallest_buildings | the tallest building | burj khalifa |
| W8 | books.toscrape.com | Travel category: price of the third book | 48.87 |
| W9 | books.toscrape.com | Mystery category: UPC of the second book | 19ed25f4641d5efd |
| W10 | quotes.toscrape.com | page 3: author of the first quote | neruda |
| W11 | quotes.toscrape.com | tag "love": author of the first quote | gide |
| W12 | books.toscrape.com | catalogue page 3: title of the first book | slow states of collapse |

## Arms and design

3f is Phase 3d's design (Playwright MCP 0.0.83, `Read`/`Grep`/`Glob`, no `WebFetch`/`WebSearch`/
`Bash`, `--max-budget-usd 1.50`); 3g is Phase 3e's (playwright-cli 0.1.18 in `Bash`, `Read`,
`--max-budget-usd 1.00`) with one change, made because Phases 3 and 3e lost runs in both arms to
a final message of "Done - browser closed.": the system addition now asks the agent to close the
browser first and give the answer as its final message. Three runs per task and arm, 72 sessions
per tool, PLAIN before LEAN in each run, the two tools run at the same time in two processes,
each process one session at a time. The hook's defaults, `SANCHOPANZA_SESSION_MAX_USD=0.20`.

## Decision rule, fixed now, for each tool apart

Phase 3's: the hook is recommended with that tool if LEAN succeeds on at least as many runs as
PLAIN minus one (here, minus two, since the runs are twice as many: 36 per arm) and its mean
cost per session (list USD plus Jev USD) is lower with the bootstrap interval of the per-task
difference (5,000 resamples over tasks, seed 2033) below zero. Reported besides, by task: the
cuts, and the difference on tasks where the hook cut against tasks where it did not (the second
measures noise between sessions, as Phase 3e showed).

## Money

At most 20.00 USD at list price per tool through the subscription (expected about 8 each) and
2.00 USD of Jev per tool (expected well under 0.20); each runner stops before passing either.

## What would make this wrong

Twelve tasks, three runs each: an interval over twelve task means. Pages change; the answers were
checked today. Running the two tools at once shares the subscription's rate, not the sessions.
