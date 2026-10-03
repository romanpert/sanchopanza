# Browse, line v6: development on eight new crawls (2026-10-03)

**This is development, not a confirmation.** Nothing here was registered or sealed. The tasks were
chosen after confirmation 3's misses had been read, and half of them were built to look like
those misses. What this round can show is whether v6 fixes the kinds of miss it was written for,
and what kind of miss is left.

## What was run

- **Line v6** (`crawl_hook.STRATEGY_LINE_V6`, chosen with `SANCHOPANZA_CRAWL_LINE_VERSION=6`; v5
  stays the default) is v5 with four clauses added, one for each miss read in confirmation 3:
  follow pages through the site's own links or data and never a guessed URL pattern; the page and
  item counts must be computed by the code and checked against what the site states; match the
  field the request names, not a word anywhere in the item's text; count each item once by URL or
  id, never by name. It is 223 words, where v5 is 156.
- **Eight new crawls** (`benchmarks/browse/truth_v6.py`). None of their URLs appears anywhere else
  in `benchmarks/`, and a test checks this. Each answer was computed by two routes, recomputed
  after the phase, and was unchanged (`truth-v6.json`). Five of the eight are shaped like a miss:

| task | site, mechanism | truth | trap it was built around |
|---|---|---|---|
| F1 | scrapeme.live, WooCommerce, 48 pages | 218 | the Store API gives prices in pence |
| F2 | scrapingcourse.com/pagination, 13 pages at `/pagination/N` | 96 | a guessed `?page=N` returns 200 with page 1 every time |
| F3 | LambdaTest OpenCart, Tablets, 5 pages | 30 | 75 products share 18 names |
| F4 | Toolshop (Angular over a JSON API) | 5 | 4 products have "Pliers" in their name; 5 are in the Pliers category |
| F5 | DataTables, all 57 rows in the HTML, 10 drawn at a time | 11 | (plain) |
| F6 | DataTables, rows served by Ajax | 4 | 8 job titles contain "Developer" |
| F7 | LambdaTest, Cameras, brand only on each product's page | 22 | the same 18 names; the filter says "Apple 42" |
| F8 | Rick and Morty API, 42 JSON pages | 366 | `?species=human` matches Humanoid too (434); the API answers 429 after about 30 requests |

- **Arms**: Haiku with `install --crawl` and v5; the same with v6; Haiku with no hook, as a
  reference. Three runs each, 72 sessions. Claude Code 2.1.287 in every session. Session cap
  1.00 USD, phase ceiling 12. SendMessage, ListAgents, ScheduleWakeup, CronCreate and
  RemoteTrigger were denied (`benchmarks/browse/nav_v6.py`). No session was `not_run`: every
  treated transcript showed its own version of the line and not the other one, which also
  confirms that the settings' `env` reaches the hook. There were no hangs.
- **Spend**: 8.16 USD at list price for the phase and 0.16 for the smoke session, 8.32 in total,
  through the subscription.

## Result

| arm | right | mean / median USD | worst | mean turns |
|---|---|---|---|---|
| Haiku, no hook | **15/24** | 0.181 / 0.147 | 0.572 | 16.6 |
| Haiku + crawl, v5 | 8/24 | **0.079** / 0.058 | 0.265 | 10.6 |
| Haiku + crawl, v6 | 12/24 | **0.080** / 0.063 | 0.277 | 10.4 |

| task | v5 | v6 | no hook |
|---|---|---|---|
| F1 | 0/3 | 1/3 | 2/3 |
| F2 | 0/3 | 2/3 | 3/3 |
| F3 | 1/3 | 1/3 | 3/3 |
| F4 | 3/3 | 3/3 | 2/3 |
| F5 | 0/3 | 0/3 | 3/3 |
| F6 | 1/3 | 3/3 | 1/3 |
| F7 | 0/3 | 1/3 | 0/3 |
| F8 | 3/3 | 1/3 | 1/3 |

**v6 does better than v5 and costs the same, but it is still below Haiku with no hook on answers
(12 against 15).** So on these tasks it does not meet the owner's bar of being cheaper and at
least as often right. The price advantage holds at 2.3 times cheaper.

## Every miss, read by hand

All 37 misses were read in their transcripts (the code of each evaluate, its result, and the
reply). Each miss has one class:

| class | v5 | v6 | no hook | what happened |
|---|---|---|---|---|
| **read only the open page** | 6 | 6 | 1 | no fetch at all: the DOM of the page that was open was taken as the whole. F5's 10 rows of 57 (always "3"), F3's 15 of 75, F1's 16 of 755. Each of these pages states its size ("Showing 1 to 10 of 57 entries", "(5 Pages)", "of 755 results") |
| guessed URL, repeated page | 5 | **1** | 0 | `?page=N` on F1 and F2: the site served page 1 again and again, giving answers of 100, 250, 400 and 1,000 |
| request errors swallowed | 0 | 2 | 1 | F8: the 429s after about 30 requests came back as HTML, `JSON.parse` threw, the code skipped those pages, and it still reported "42 pages processed" |
| ran past the end | 0 | 1 | 0 | F1: 404 pages beyond page 48 hold a product widget, which made 1,067 products where the page says 755 |
| field, not the word | 2 | **0** | 3 | "Developer" as a substring (8 for 4); products in the Pliers category counted by name (4 for 5) |
| merged by name or price | 3 | 2 | 4 | F7: distinct names (6) out of 42 Apple products; once, distinct prices (F1, 50) |

What this says, plainly:

- **v6 fixed the two kinds of miss its clauses describe most concretely.** Guessed URLs fell from
  5 to 1 and field matching from 2 to 0. The clause about merging by name did not take: it went
  from 3 to 2, and v6's F7 run 1 collected all 42 Apple products and then wrote "count the
  unique".
- **The largest kind of miss is caused by the line itself, and neither version fixes it.** The
  line says to do it in one call. Haiku's one call reads the open page and stops there, and the
  account the line asks for ("check them against what the site states") is not made, even when
  the statement is on the screen. Haiku with no hook walked F3 and F5 and got 6/6. This is the
  same partial result, believed, that sections 15-18 of `2026-10-02-browse-nav` describe. A
  clause has now failed to fix it in v2, v5 and v6.
- **F8 against v5 is not a regression of the wording.** v6's two misses are 429s that the code
  swallowed. v5 met the same limit (it ran first and in the same windows) and handled it 3/3.
  How often a session runs into the rate limit depends on timing, and three runs cannot separate
  that from the line.

## Where the fix belongs: in the result, not in the line

Every coverage miss above (15 of the 28 misses with the line) has a cause that the harness can see
without a model, at the point where the result arrives. The guard already wraps every
`browser_evaluate` (`crawl_hook.wrap`), so the same wrapper could add a short note to the result:

- **the call fetched nothing and the open page states a size**: quote the statement ("Showing 1
  to 10 of 57 entries"). This targets the 12 "read only the open page" misses.
- **the call's fetches returned errors**: count them by status ("12 fetches answered 429, 3
  answered 404"). This targets F8 and F1's past-the-end pages.
- **fetched bodies identical to an earlier one**: this catches F2's guessed `?page=N` (the bodies
  are byte-identical) and pages past the end on LambdaTest and quotes. It does not catch
  scrapeme's `?page=N`. Checked offline, at no cost, with a stand-in for `textContent`
  (`benchmarks/browse/repeat_fingerprint.py`, `repeat-fingerprint.txt`): visible text is identical for those three and different
  for every real next page tried, the hockey table included. A link-set fingerprint fails, since
  the hockey table's pages have identical link sets.

This is the conclusion section 17 reached about the hang, applied to the partial result: a check
the model is asked to make belongs in the harness, delivered where the result lands. Section 18
measured a model deciding when to warn, and its precision was poor. This proposal does not decide
anything. It quotes what the page and the network said, and the agent decides. The open question
is whether Haiku acts on a note inside the tool result where it ignored the line. That needs a
live development round. The F tasks are suitable for it, because their misses repeat, but it
still has to be measured.

## Is v6 worth a sealed confirmation?

**Not as it stands.** It loses to Haiku with no hook by three answers on tasks shaped for it, and
confirmation 3's bar requires at least as many. The order I would follow:

1. v7 = v6 plus the result notes above, as an opt-in in `crawl_hook`. Measure it in development
   on F1, F2, F3, F5 and F8, which hold 15 of the 28 line misses. Three runs and one arm, about
   1 USD.
2. If it closes the open-page gap without giving back the price, register a confirmation on new
   tasks. At least half should declare their size on the first page and put more than a page
   beyond the DOM: client-side paginated tables, WooCommerce or OpenCart listings, a rate-limited
   JSON API. Add two interactive tasks for no-harm, against both Haiku and Sonnet with no hook,
   under confirmation 3's rules.

## A fault found in confirmation 3's runner

`nav_confirm3.one_session` counts `guard_stops` as occurrences of "evaluate stopped after"
anywhere in the transcript. The wrapper's own code contains that sentence, and Playwright MCP
echoes the code it ran, so every wrapped evaluate counts several times. In this round the runner
reported 398 and 372 stops for v5 and v6. In fact there was 1 stop, in a v5 session (a tool
result that begins `### Error\nError: evaluate stopped after`). This runner records the same
inflated field, and this README gives the counted figure. Confirmation 3's `described` field
`guard_stops` should be recounted the same way before it is cited. Its verdicts do not use that
field.

## v7: the check moved into the result (development, same day)

**v7 is line v6 plus the crawl notes** (`harness/crawl_notes.py`, `SANCHOPANZA_CRAWL_NOTES=1`,
off by default). They come from the evaluate guard: no model, and still a rewrite of the call's
input that approves nothing. PreToolUse can change a call's input but not its result, so the
wrapper computes the notes itself. While the function runs, `window.fetch` is replaced by a
counting copy, and the original goes back in `finally`. If there is something to say, the value
comes back as `{result, sanchopanza}`; otherwise it comes back unchanged. If the function throws,
the notes are added to its error message. No PostToolUse hook is needed, so nothing collides
with memory's or prune's hooks. The notes say:

- **when the call fetched nothing**, what the open page states about its size: the first of a
  "Showing x to y of N" line, "Page n of N" or "N results/entries/records"; JSON counts
  (`count`, `total`, `pages`, ...); numbered pagination links; and the `rel=next` link;
- failed fetches by status, network errors included;
- fetched pages whose visible text equals that of an earlier, different URL.

The wrapper grows to about 3,300 characters, and Playwright MCP echoes it in every evaluate's
result. The cost figures below already include that.

Round (`nav_v7.py`): F1, F2, F3, F5 and F8, which held 15 of the 28 line misses above. Three
runs, 45 sessions, Claude Code 2.1.287, ceiling 6 USD. It cost 4.50 USD, plus 0.19 for a smoke
session (F5, right; the note quoted "Showing 1 to 10 of 57 entries" and the agent went on to all
57 rows). The fresh Haiku arm ran at the same hour as v7.

| arm (F1 F2 F3 F5 F8) | right | mean / median USD | mean turns |
|---|---|---|---|
| Haiku, no hook | 11/15 | 0.177 / 0.196 | 20.1 |
| **Haiku + v7** | **11/15** | **0.066** / 0.055 | 7.7 |
| Haiku + v6 (no notes) | 3/15 | 0.058 / 0.046 | 7.4 |

Per task, v7 / alone / v6: F1 2/2/1, F2 2/2/0, F3 1/3/1, F5 **3**/3/0, F8 **3**/1/1. In the
morning round, Haiku alone scored 12/15 on the same five tasks.

**The notes close the gap that line v6 left, and v7 keeps the price**: as many right answers as
Haiku with no hook, at 0.37 of its cost. Without the notes, the same line scored 3/15. Reading
only the open page fell from 6 of 6 (F5 under v5 and v6) to none: F5 went 3/3 and F8 3/3. All
four v7 misses were read by hand, and they are of another kind. The data was all fetched, the
count was wrong, and the code never compared it with the total the page stated:

- F3 runs 1 and 2: every card counted twice by a nested selector (155 and 150 of 75 products)
  → **structure**.
- F2 run 2: the note named 99 repeated pages; the agent then followed the real links and
  double-counted 454 cards → **structure**.
- F1 run 3: 767 products where the page says 755, because the 404 page past the end shows a
  product widget, and the note's 404 count was not acted on → **ran past the end**.

That suggests the next note: quote the stated size on calls that do fetch, too, so that "155"
appears beside "of 75". It is not part of what is registered below. The confirmation tests v7
exactly as it was measured here.

This is development on tasks seen before, with three runs: an 11 against 11 is a tie, not a win.
Because it meets the bar on these tasks, a confirmation on new tasks is registered in
`prereg-crawl4.md` (`nav_confirm4.py`, `truth_confirm4.py`). It is sealed and **not launched**,
and its expected cost is about 18 USD.

## Files

- `nav-v6-sessions.jsonl` / `.log`, `nav-v6.json`: the phase. `nav-v6-smoke-sessions.jsonl`: the
  smoke session (F4, v6, right, 0.16 USD).
- `nav-v7-sessions.jsonl` / `.log`, `nav-v7.json`, `nav-v7-smoke-sessions.jsonl`: the v7 round.
- `truth-v6.json`: the answers recomputed after the phase.
- `prereg-crawl4.md` / `.sha256`: confirmation 4, sealed, not run.
- `benchmarks/browse/nav_v6.py`, `nav_v7.py`, `nav_confirm4.py`, `truth_v6.py`,
  `truth_confirm4.py`, `repeat_fingerprint.py`; `tests/test_nav_v6.py`, `test_nav_v7.py`,
  `test_nav_confirm4.py`, `test_crawl_notes.py`.
