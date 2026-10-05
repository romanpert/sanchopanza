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
`prereg-crawl4.md` (`nav_confirm4.py`, `truth_confirm4.py`). It is sealed, and its expected cost
was about 18 USD. Its result is in the next section.

## Confirmation 4: v7 against Claude Code alone, Haiku and Sonnet (registered, 2026-10-03)

Run as `prereg-crawl4.md` registered it (`nav_confirm4.py --live`). There were 120 sessions, every
one on Claude Code 2.1.287, and no session was `not_run`: each `-SP` transcript showed line v6 and
the notes, and no plain one did. The runner killed no session, and the guard stopped no evaluate
(0 tool results that begin `### Error\nError: evaluate stopped after`, in every arm). It cost
**11.14 USD** at list price through the subscription, against the 18 expected. The difference is
the plain arms: Haiku alone averaged 0.085 a crawl here, where the estimate assumed 0.17.

### Verdicts, as computed (`nav-confirm4.json`)

| | Haiku | Sonnet |
|---|---|---|
| price: total crawl ratio (at most 0.75) | **0.602** (1.23 / 2.04 USD) | 0.872 (2.09 / 2.39 USD) |
| price: crawls cheaper by mean (at least 6/8) | **7/8** | 4/8 |
| answers: right on 24 crawls (at least the plain arm) | **21** against 18 | **23** against 20 |
| no harm: right on I1, I2 (plain minus 1) | 5/6 against 6/6 (holds) | 6/6 against 6/6 |
| no harm: cost ratio (at most 1.25) | 1.394 | 1.038 |
| **beats the harness** | **no** (no harm, on cost) | **no** (price) |

**Not confirmed, on either model.** The prereg asks for all three hypotheses on a model, and each
model fails one.

- **Haiku fails only no harm, and only on cost.** Price and answers hold with room: 0.60 of the
  cost, cheaper on 7 of 8 crawls (G4 is the exception, 0.040 against 0.035), and 3 more right
  answers. The 5/6 on the interactive tasks is inside the prereg's margin. The cost of the
  interactive tasks is not: 0.668 against 0.479 USD, a ratio of 1.39.
- **Sonnet fails price.** It is more often right (23 against 20) and costs the same on I1 and I2
  (1.04), but the crawls cost 0.87 of the plain arm's, and it is cheaper on only 4 of 8 crawls
  (G1, G5, G6 and G7). The four where it costs more are the JSON APIs, G2, G3, G4 and G8. There
  Sonnet alone already writes one evaluate and is done in 4 turns, so the line has no walk to
  remove. Its fixed cost remains: a few thousand more tokens written to cache per session (the
  line, and the wrapper Playwright MCP echoes back) and longer output.

Per task, right answers (plain / `-SP`) and mean USD:

| task | Haiku | Haiku-SP | Sonnet | Sonnet-SP |
|---|---|---|---|---|
| G1 | 1/3, 0.047 | **3/3**, 0.040 | 3/3, 0.084 | 3/3, 0.081 |
| G2 | 2/3, 0.046 | 3/3, 0.033 | 3/3, 0.077 | 2/3, 0.079 |
| G3 | 3/3, 0.048 | 2/3, 0.046 | 0/3, 0.072 | **3/3**, 0.096 |
| G4 | 1/3, 0.035 | **3/3**, 0.040 | 2/3, 0.072 | 3/3, 0.086 |
| G5 | 2/3, 0.100 | 3/3, 0.042 | 3/3, 0.115 | 3/3, 0.089 |
| G6 | 3/3, 0.155 | 1/3, 0.128 | 3/3, 0.132 | 3/3, 0.098 |
| G7 | 3/3, 0.154 | 3/3, 0.045 | 3/3, 0.174 | 3/3, 0.085 |
| G8 | 3/3, 0.096 | 3/3, 0.036 | 3/3, 0.072 | 3/3, 0.083 |
| I1 | 3/3, 0.051 | 2/3, 0.044 | 3/3, 0.113 | 3/3, 0.116 |
| I2 | 3/3, 0.109 | 3/3, 0.178 | 3/3, 0.254 | 3/3, 0.264 |

Described, not tested: median wall time 24 s against 38 s (Haiku) and 25 s against 40 s
(Sonnet), and mean turns on crawls 5.8 against 8.7 and 4.2 against 5.4. Haiku with sanchopanza
against Sonnet alone: 21 right against 20, at 0.51 of the crawl cost.

### Every miss, read by hand

The 15 misses (out of 120) were read in their transcripts:

| session | answer | what happened |
|---|---|---|
| G1 r1, r3 Haiku | 6 | read only the open page: 30 products of the 194 the JSON states |
| G4 r2, r3 Haiku; G4 r2 Sonnet | 0 | read only the open page: 20 names of 1,351 |
| G3 r1, r2, r3 Sonnet | 1 | read only the open page: 10 facts of 332, and said so in the reply |
| G2 r1 Haiku | 21 | `eye_color` matched as a substring, so "blue-gray" and "red, blue" counted |
| G5 r2 Haiku | 22 | counted by eye from three snapshots and miscounted |
| G3 r2 Haiku-SP | 52 | invented `?limit=100&page=N`: the pages overlapped, giving 332 rows of which 298 were distinct, and the code never deduplicated |
| G6 r1, r2 Haiku-SP | 48, 30 | the 40 rows were already in the DOM and paged by CSS. The code called `click()` on the pager inside the evaluate and read the same rows after every click (6 per page, 8 and 5 pages, against 6) |
| G2 r1 Sonnet-SP | 21 | `includes('blue')`, the same substring as G2 r1 Haiku |
| I1 r1 Haiku-SP | none | the-internet.herokuapp.com answered 503 for the whole session; the agent reported the outage and did not log in |

What this says:

- **The notes did what v7's round said they would.** All 8 "read only the open page" misses are
  in the plain arms; none is in an `-SP` arm. The "fetched nothing" note fired in 15 Haiku-SP
  sessions, and 14 of them ended right. Sonnet-SP never needed it (0 notes): line v6 alone sent
  it past page 1 of G3 and G4, where Sonnet alone stopped 4 times.
- **The misses left with sanchopanza are of another kind.** All the data was reached, and it was
  read more than once (G3, G6) or matched by the wrong rule (G2). No current note sees either:
  the G3 overlap is not a byte-identical page, and G6 made no fetch at all.
- **The interactive cost is the wrapper and longer walks, not the line.** On I2, Haiku-SP took
  25 to 37 turns against 20. Of its extra 0.21 USD, about 30 % is the wrapper's echo: Playwright
  MCP returns the code it ran under `### Ran Playwright code`, and the wrapped function is 3,313
  characters with the notes, against 450 for the guard alone. That block is then re-read at cache
  price on every later turn. About 4 % is the line. The rest is turns: extra screenshots,
  repeating the checkout flow, and in r3 evaluates where a snapshot would have done.

**An error in the prereg, which does not change the verdict.** Its task table says that 2 more
people in G2 have "blue-gray" eyes. In the data, 1 has "blue-gray" and 1 has "red, blue". The
truth (19, exactly "blue") stands. Sonnet's G2 r2 and r3 answered "19 (21 if including
blue-gray and red, blue)". The registered grading reads the first whole number on the ANSWER line
and counts both as right. A stricter reading would make Sonnet alone 18/24 and leave every
verdict as it is.

### What v8 should be, from these misses

Development, not registered. Each item is opt-in and leaves v7 as it is:

1. **Cut the echo.** A `PostToolUse` hook on `browser_evaluate` replaces the echoed wrapper with
   one short line, and leaves the result and the notes intact. That is 30 % of I2's extra cost.
2. **Two more neutral notes**, each from a miss above: clicks that did not change the page's text
   (G6), and JSON rows fetched against distinct rows (G3 r2). They give numbers and no advice.
3. **The line only on crawl requests**, so that I1 and I2 never carry it. The guard and the notes
   stay on for every request.

## v8 development (2026-10-05)

Development, not a confirmation: the tasks are confirmation 4's own. v8 is three switches
(`harness/crawl_hook.py`, all off by default): `SANCHOPANZA_CRAWL_NOTES=2` (v7's notes plus clicks
that never changed the page text and fetched JSON rows against distinct rows),
`SANCHOPANZA_CRAWL_ECHO=short` (a PostToolUse hook replaces the wrapper Playwright MCP echoes with
one line) and `SANCHOPANZA_CRAWL_LINE_AT=prompt` (the line moves to UserPromptSubmit, and only on
prompts that gather and do not act). The `-V8` arms get `install --crawl`'s hooks, the two events
in `crawl_hook.V8_HOOKS`, and line v6. `-V7` is confirmation 4's `-SP`.

Round (`nav_v8.py`): G3, G6, I2 (the misses and the cost), G4, G8 (where Sonnet with v7 cost
more) and G1 (no regression); five arms, two runs, 60 sessions, Claude Code 2.1.287, ceiling 12
USD. It cost **5.87 USD** at list price, smoke included. Every transcript was checked: each `-V8`
session on a G task carried the line, neither `-V8` session on I2 did, and no `-V8` result echoed
the wrapper. The `-V8` transcripts hold 110 cut echoes and none left whole; the `-V7` transcripts
hold the whole wrapper 62 times. The guard stopped nothing.

| task | Haiku | Haiku-V7 | Haiku-V8 | Sonnet | Sonnet-V8 |
|---|---|---|---|---|---|
| G3 | 2/2, 0.051 | 2/2, 0.070 | 2/2, 0.038 | 0/2, 0.094 | **2/2**, 0.078 |
| G6 | 2/2, 0.169 | 2/2, 0.084 | 1/2, 0.079 | 2/2, 0.178 | 2/2, 0.084 |
| G4 | 0/2, 0.033 | 2/2, 0.040 | **2/2**, 0.037 | 1/2, 0.074 | 2/2, 0.081 |
| G8 | 2/2, 0.094 | 2/2, 0.036 | 2/2, 0.032 | 2/2, 0.079 | 2/2, 0.078 |
| G1 | 0/2, 0.030 | 2/2, 0.043 | 1/2, 0.035 | 2/2, 0.068 | 2/2, 0.072 |
| I2 | 2/2, 0.131 | 2/2, 0.140 | 2/2, 0.183 | 2/2, 0.257 | 2/2, 0.265 |
| crawls right / sum of means | 6/10, 0.378 | **10/10**, 0.272 | 8/10, **0.221** | 7/10, 0.493 | **10/10**, 0.392 |

Mean USD per session. The ratios v8 was for:

- **Sonnet on the JSON APIs (G4 + G8): 1.034** (G4 1.093, G8 0.978). The echo cut closed the
  cache-write gap: Sonnet-V8 now writes 12,224 to 12,703 tokens to cache against 11,967 to
  12,825 for Sonnet alone. What is left is output: 980 to 1,258 tokens against 708 to 1,660,
  because the line asks for code that also returns pages read and the stated total. On G4 that
  code is the right answer (2/2 against 1/2). There is no walk to remove on these tasks. Plain
  Sonnet writes one evaluate in 4 turns, and so does Sonnet-V8. So **v8 brings the JSON APIs to
  parity, not below it**. Over the five crawls Sonnet-V8 costs 0.795 of Sonnet alone and is
  cheaper on G3, G6 and G8. G3's plain mean includes the round's first Sonnet session, which paid
  a cold cache (25,220 tokens written against about 11,300 in run 2).
- **Haiku on I2: 1.394**, and v8 is not in those sessions. On I2, no `-V8` session ran an
  evaluate, so no hook returned anything: no line, no wrapper, no echo. The session is Claude
  Code alone. The cost follows the path Haiku takes. When it checks each step with
  `browser_take_screenshot`, the session runs 26 to 37 turns and 0.149 to 0.217 USD. When it
  checks with `browser_snapshot`, it runs 19 to 20 turns and 0.104 to 0.124. Both `-V8` sessions
  took the screenshot path, and so did one of the two plain ones (0.158). **v8 removes what v7
  added to the interactive tasks.** The remaining cost difference is the model's own choice
  between these two paths, and two runs cannot measure it.
- Haiku-V8 against Haiku-V7 on the crawls: **0.81**, cheaper on 5 of 5. That is the echo cut.
  Against Haiku alone: 0.585 with 8 right against 6.

Every miss, read in its transcript:

| session | answer | what happened |
|---|---|---|
| G4 r1, r2 Haiku; G4 r1 Sonnet | 0 | read only the open page: 20 names of 1,351 |
| G1 r1, r2 Haiku | 6 | read only the open page: 30 products of 194 |
| G3 r1, r2 Sonnet | 1 | read only the open page: 10 facts of 332 |
| G6 r2 Haiku-V8 | 8 | read the first-name column (`cells[1]`, "Maddie") and clicked the 8 pager buttons inside one evaluate, reading the same 40 rows each time (320). The click note fired: "8 clicks did not change the page text: the rows were already loaded". The agent answered without acting on it |
| G1 r1 Haiku-V8 | 6 | the note fired ("read only the open page, which says: "total":194") but the agent never saw it. The evaluate returned all 30 products, 64,577 characters. Claude Code saved that result to a file and showed a 2 KB preview, and the note sat at character 64,295 |

What this says:

- **As in confirmation 4, every "read only the open page" miss is in a plain arm.** None of
  them happened with v7 or v8.
- **The two v8 misses are of new kinds, and neither has a counter-note.** In G6, a note that is
  right is ignored, and the column is the wrong one. In G1, a note is lost because a result over
  Claude Code's size limit is persisted and only its head is shown. The notes go after the
  value, so a large value hides them. **The next fix is placement**: put the notes before the
  value. The PostToolUse hook that already rewrites the result could do this, or the wrapper
  could return `{sanchopanza, result}` in that order.
- **The rows note had a bug, now fixed.** On catfact.ninja each page holds 10 facts under `data`
  and 15 pagination links under `links`. The note took the largest array of objects and counted
  the links: "fetched JSON rows 510, distinct 137" for 34 pages of 332 facts. No answer was hurt,
  and G3 was 4/4 right with v8. `crawl_notes._V2` now skips a `links`/`_links` key
  (`test_a_paginators_links_are_not_taken_for_the_rows`). The round ran before the fix. On G1,
  G4 and G8 the rows note was right (194/194, 1,351/1,351, 60/60).

## v8.1 development (2026-10-05)

Development, not a confirmation: the tasks are confirmation 4's own. v8.1 is v8 plus two switches
(`harness/crawl_hook.py`, both off by default), one for each finding of v8's round:

- `SANCHOPANZA_CRAWL_NOTES_AT=front`: the PostToolUse hook that cuts the echo also moves the notes
  from the end of the evaluate's result to its head, under `### sanchopanza note`. The note is
  taken from the last key of the returned value, or from the tail of an error message, and is
  moved, not copied. A test builds a 60,000-character result and finds the note in its first 500
  characters.
- `SANCHOPANZA_CRAWL_SHOT=snapshot-first`: a PreToolUse hook denies the session's first
  `browser_take_screenshot`, with the reason "browser_snapshot gives the page text and element
  refs for clicks at a fraction of the tokens; call browser_take_screenshot again if you need to
  see the visual layout." Every later screenshot passes, so a task that has to see the page
  still can. There is no model in it. There is one mark per `session_id`, and with no session or
  no writable mark the call passes. `crawl_hook.V81_HOOKS` widens the PreToolUse matcher to
  `mcp__.*__browser_(evaluate|take_screenshot)`.

Round (`nav_v8.py --round v81`): Claude Code alone against `-V81` (v8's hooks and env plus these
two), Haiku and Sonnet, on G1, G3, G6 and G5 with two runs each, and on I1 and I2 with four. That
makes 64 sessions on Claude Code 2.1.287, with a ceiling of 10 USD. It cost **7.29 USD** at list
price, plus 0.23 for two smoke sessions. In the smoke, G1 got the note at the head of both results
and I2's first screenshot was denied. No session was `not_run`, no 429 came back, and the guard
stopped nothing. Every `-V81` transcript had the line on the crawls and none on I1 and I2. None
echoed the wrapper. The notes came first in all 18 noted results (12 Haiku, 6 Sonnet), and none
was left at the end.

| task | Haiku | Haiku-V81 | Sonnet | Sonnet-V81 |
|---|---|---|---|---|
| G1 | 1/2, 0.076 | 2/2, 0.033 | 2/2, 0.067 | 2/2, 0.072 |
| G3 | 1/2, 0.056 | 2/2, 0.039 | 0/2, 0.067 | **2/2**, 0.092 |
| G6 | 2/2, 0.181 | 2/2, 0.089 | 2/2, 0.192 | 2/2, 0.082 |
| G5 | 0/2, 0.109 | **2/2**, 0.038 | 2/2, 0.168 | 2/2, 0.077 |
| crawls right / sum of means | 4/8, 0.422 | **8/8**, 0.200 | 6/8, 0.493 | **8/8**, 0.323 |
| I1 | 4/4, 0.049 | 3/4, 0.044 | 4/4, 0.112 | 4/4, 0.112 |
| I2 | 4/4, 0.157 | 4/4, 0.111 | 4/4, 0.256 | 4/4, 0.263 |

Mean USD per session. Ratios (sum of means, treated over plain): crawls **0.473** Haiku and
**0.655** Sonnet; I1+I2 **0.749** Haiku and 1.020 Sonnet; I2 alone 0.703 Haiku.

**The screenshot rule, read in the transcripts.** It fired in 3 of the 16 Haiku-V81 sessions (I1
r4, I2 r1, I2 r2) and in no Sonnet session: Sonnet never asks for a screenshot on these tasks.
After each denial the agent switched to snapshots, or to reading the snapshot file Playwright MCP
had already saved. It never asked for the screenshot again. The I2 sessions the rule touched ran 22
and 20 turns, at 0.121 and 0.109 USD. All four Haiku-V81 I2 sessions ran 19-22 turns, at
0.104-0.121. Plain Haiku took screenshots in 2 of its 4 I2 sessions: 26 turns at 0.141, and 40
turns at 0.248. Its two snapshot sessions ran 20 and 27 turns, at 0.113 and 0.127. So the I2 ratio
rests mostly on plain Haiku's r4. Without it, plain Haiku's I2 mean is 0.127 and the ratio 0.871.
Four runs per arm still cannot separate the rule from the path Haiku happens to choose. What they
show is that every Haiku-V81 I2 session stayed on the cheap path, and that the rule never cost a
right answer.

**G5 is not broken.** Neither Haiku-V81 G5 session asked for a screenshot. The line sent both
into one evaluate that read the star classes (2/2, 5 turns, 0.038). The two plain Haiku misses on
G5 were the screenshot path itself: three full-page screenshots, stars counted by eye, and 31 and
36 books where the truth is 21. So the rule has not yet met a task that needs to see the page.
That case, the second call passing, is covered by tests and the preflight only.

**The notes at the head, read in the transcripts.** In both Haiku-V81 G1 sessions the first
evaluate parsed the open page, and the result began "this call fetched nothing, so it read only the
open page, which says: "total":194". The next evaluate fetched `?limit=200`, and the note read
"fetched JSON rows 194, distinct 194" (44, right). No result in this round was large enough for
Claude Code to persist it (0 of 64 sessions). So the case that caused v8's G1 miss, a note behind a
2 KB preview, has not been seen live with the move. What was seen live is that the hook's rewritten
text is the text the agent reads.

Every miss, read in its transcript:

| session | answer | what happened |
|---|---|---|
| G1 r1 Haiku | 6 | read only the open page: 30 products of 194 |
| G3 r2 Haiku; G3 r1, r2 Sonnet | 1 | read only the open page: 10 facts of 332 (Sonnet's replies say "default page size") |
| G5 r1, r2 Haiku | 31, 36 | counted stars by eye in full-page screenshots of the three pages |
| I1 r3 Haiku-V81 | none | the-internet.herokuapp.com answered 503 ("Application Error"); the agent reported the outage, 4 turns. The other three Haiku-V81 I1 sessions averaged 0.049, the same as plain Haiku |

As in confirmation 4 and v8, every "read only the open page" miss is in a plain arm. The one
`-V81` miss is the site being down, the same outage that cost confirmation 4's I1 r1 Haiku-SP.

**What v8.1 does not fix: Sonnet on the JSON APIs.** These four crawls include one JSON API (G3),
and there Sonnet-V81 costs more than Sonnet alone (0.092 against 0.067). It is right 2/2 where
Sonnet alone is 0/2, and the extra cost is the second, paginating evaluate. v8's round measured
G4+G8 at 1.034. Confirmation 4's Sonnet price criterion counts crawls cheaper by mean (at least
6/8), and on a mix with four JSON APIs that count is still at risk.

## Confirmation 5: v8.1 against Claude Code alone, Haiku and Sonnet (registered, 2026-10-05)

This was run as `prereg-crawl5.md` registered it (`nav_confirm5.py --live`), with confirmation 4's
criteria. There were eight new crawls (H1-H8) on hosts no earlier phase used, three runs each,
and four interactive tasks (I1-I4), four runs each. That makes 160 counted sessions, every one on
Claude Code 2.1.287. One more session ran because of the site-down rule. I1 run 2 of plain Haiku
got a 503 from the-internet on both of its page loads. It was repeated at the end and was right.

No session was `not_run` for its treatment. Every `-SP` transcript had line v6 on all 24 crawls
and on none of the 32 interactive sessions, no echoed wrapper was left whole, and no note was left
at the end of a result. No plain transcript showed any of it. The runner killed nothing, and the
guard stopped nothing. The phase cost **18.38 USD** at list price through the subscription,
against 18 expected and a ceiling of 25. The answers, recomputed after the phase by both routes,
were unchanged (`truth-confirm5.json`).

### Verdicts, as computed (`nav-confirm5.json`)

| | Haiku | Sonnet |
|---|---|---|
| price: total crawl ratio (at most 0.75) | 0.802 (1.54 / 1.92 USD) | 1.055 (2.43 / 2.30 USD) |
| price: crawls cheaper by mean (at least 6/8) | 5/8 | 4/8 |
| answers: right on 24 crawls (at least the plain arm) | **19** against 12 | **24** against 23 |
| no harm: right on I1-I4 (plain minus 1) | 16/16 against 16/16 | 16/16 against 16/16 |
| no harm: cost ratio (at most 1.25) | **0.917** | 1.006 |
| **beats the harness** | **no** (price) | **no** (price) |

**Not confirmed, on either model.** Both models fail price and hold answers and no harm. This is
the first confirmation in which Haiku holds no harm on cost: 0.917, where confirmation 4 gave
1.394.

Per task, right answers and mean USD:

| task | Haiku | Haiku-SP | Sonnet | Sonnet-SP |
|---|---|---|---|---|
| H1 | 1/3, 0.042 | 2/3, 0.035 | 3/3, 0.103 | 3/3, 0.077 |
| H2 | 1/3, 0.041 | **3/3**, 0.034 | 3/3, 0.070 | 3/3, 0.075 |
| H3 | 3/3, 0.073 | 3/3, 0.056 | 3/3, 0.087 | 3/3, 0.084 |
| H4 | 0/3, 0.029 | 1/3, 0.040 | 3/3, 0.070 | 3/3, 0.084 |
| H5 | 0/3, 0.049 | 2/3, 0.050 | 2/3, 0.083 | 3/3, 0.088 |
| H6 | 1/3, 0.119 | **3/3**, 0.041 | 3/3, 0.095 | 3/3, 0.076 |
| H7 | 3/3, 0.158 | 2/3, 0.127 | 3/3, 0.114 | 3/3, 0.212 |
| H8 | 3/3, 0.131 | 3/3, 0.132 | 3/3, 0.146 | 3/3, 0.112 |
| I1 | 4/4, 0.050 | 4/4, 0.048 | 4/4, 0.117 | 4/4, 0.115 |
| I2 | 4/4, 0.110 | 4/4, 0.118 | 4/4, 0.258 | 4/4, 0.257 |
| I3 | 4/4, 0.150 | 4/4, 0.107 | 4/4, 0.211 | 4/4, 0.213 |
| I4 | 4/4, 0.131 | 4/4, 0.131 | 4/4, 0.259 | 4/4, 0.265 |

Described, not tested:

- **Haiku with sanchopanza against Sonnet alone:** 19 right against 23, at 0.671 of the crawl
  cost.
- **Median wall time:** 48.5 s against 51.8 s (Haiku) and 41.8 s against 49.2 s (Sonnet).
- **Mean turns on crawls:** 9.5 against 9.2 (Haiku) and 5.8 against 5.9 (Sonnet).
- **What the hooks did in Haiku-SP:** 345 echo cuts, 63 notes at the head of a result, and 12
  screenshots asked for and 12 denied, each the first of its session. No session asked again,
  and every one of those 12 sessions was right.
- **What the hooks did in Sonnet-SP:** 153 echo cuts and 35 notes at the head. It asked for no
  screenshot.
- **The preview case was not met live again.** No result in the 160 sessions was large enough
  for Claude Code to save it behind its preview. H4's open page is 785 KB, but every session
  parsed it in the page and returned only counts.

Every right crawl answer was checked by hand: in each one, the first number on the ANSWER line is
the truth.

### Every miss, read by hand

| session | answer | what happened |
|---|---|---|
| H1 r1, r2 Haiku; H1 r3 Haiku-SP | 3 | read only the open page: 10 houses of 444. The next page is named only in the `Link` header, and the page states no size, so the Haiku-SP session got no note |
| H2 r1, r2 Haiku | 18 | read only the open page: 50 of the 295 the JSON states. No Haiku-SP session missed it: the note quoted `"pages":6, "total":295` |
| H4 r1, r2, r3 Haiku; H4 r2, r3 Haiku-SP | 126 | read only the open page: 1,000 rows of 3,023. Socrata states no total and gives no link, so the two Haiku-SP sessions got no note. The Haiku-SP session that paged on its own (r1) was right |
| H5 r1, r2, r3 Haiku; H5 r1 Haiku-SP | 2 | read only the open page: 100 characters of 5,410. The page states `"last":55, "records":5410` under `meta.pagination`, and neither key is among those the note reads (`count`, `total`, `pages`, `last_page`, ...), so it stayed silent |
| H5 r2 Sonnet | 64 | paged with its own cap of 20 pages and stopped at 2,000 of 5,410 |
| H6 r2, r3 Haiku | 30, 32 | counted prices by eye in snapshots of the three pages |
| H7 r3 Haiku-SP | 100 | clicked Next inside one evaluate up to 50 times. On the last page the button reloads items, so the code read 303 cards. Its own result listed 4 distinct products under $500, but the reply answered 100. No note: demoblaze loads its list by XHR, which the notes do not count, and the clicks did change the page text |
| I1 r2 Haiku (first try) | none | the-internet answered 503 on both loads (`site_down`). The repeat at the end was right |

What this says:

- **The notes and the line still remove "read only the open page" when the page says how big it
  is.** On H2 and H6, Haiku went from 1/3 to 3/3. There were 14 open-page misses. The 2 on a
  page whose size the note can read (H2) are both in the plain arm. The other 12 are on pages that
  state no size the note can read: a `Link` header (H1), no total at all (H4), or keys the note
  does not know (H5). There the note is silent by construction, and 4 of those 12 misses are in
  Haiku-SP.
- **Haiku fails price because a wrong answer from the open page is cheap.** Haiku-SP is cheaper on
  H1, H2, H3, H6 and H7, ties H8 (0.1315 against 0.1314), and costs a little more on H4 and H5. On
  those two, plain Haiku read one page and was wrong 6 times out of 6. The criterion compares cost
  whatever the answer.
- **Sonnet fails price on the JSON APIs and on H7.** On H2, H4 and H5 both arms mostly write one
  evaluate in 4 or 5 turns, and the treated arm's output is longer: +0.005 to +0.014 USD per
  session by mean, as in v8 and v8.1. H7 is new. Line v6 says to fetch the data the page loads, and on a 15-product list
  with one Next button, Sonnet-SP went looking for the API with `browser_network_requests` and
  replayed it: 22 and 16 turns in r2 and r3, against 6 to 9 for Sonnet alone, which clicked Next.
  Without H7 the Sonnet ratio, as a sum of means, would be 0.915.

## v9 development (2026-10-05)

Development, not a confirmation: the tasks are confirmation 5's own. v9 is v8.1 plus one switch,
`SANCHOPANZA_CRAWL_NOTES=3` (`harness/crawl_notes._V3`, off by default; v8.1's wrapper is
unchanged and its sha256 is tested). It answers the four kinds of confirmation 5 miss that the
notes could not see:

- **H1, the `Link` header.** When the call fetched nothing, the wrapper asks for the open page's
  URL again with the original `fetch` (HEAD, or GET when HEAD answers 405 or 501, aborted once
  the headers arrive, 3 s at most) and quotes its `next` and `last` links. That request is not
  counted as the agent's.
- **H5, size keys the note did not read.** The open page's JSON is walked outside its rows, and
  `records`, `last`, `next`, `total_results` and similar keys are quoted with their path
  (`meta.pagination.records: 5410`). Keys the v7 text match already quotes are not repeated.
- **H4, no size at all.** A JSON array of a round size (10, 20, 25, 50, 100 or 1,000) on a page
  that states no size key and no `Link` is named: "a JSON array of exactly 1000 items and no
  total". So is a single fetched response like it.
- **H7, XMLHttpRequest.** `open` and `send` are observed like `fetch`: an XHR counts as a fetch,
  its failures by status, and its JSON rows with the fetched rows. Both are put back afterwards.

The notes stay neutral, with numbers, at the head of the result (`NOTES_AT=front`).

Before any session, the wrapper ran in Chrome against the real pages, at no cost. H1 said "Link
header: next ...page=2&pageSize=10, last ...page=45&pageSize=10". H4 said "a JSON array of exactly
1000 items and no total". H5 quoted `meta.pagination.next: 2, ... last: 55, ... records: 5410`
and the two `links`. Three clicks on H7's Next gave "fetched JSON rows 18, distinct 6". H2's note
was the same as before.

Round (`benchmarks/browse/nav_v9.py`): H1, H4, H5 and H7, the misses, plus H2 and H8 for no
regression, with two runs each. There were five arms: Claude Code alone (`HAIKU`, `SONNET`),
v8.1's hooks with notes v3 (`HAIKU-V9`, `SONNET-V9`), and `SONNET-NOTES`, which is the same
without the line (`SANCHOPANZA_CRAWL_LINE=0`). That last arm was added because on H7 line v6 sent
Sonnet hunting the list's API. All 60 sessions ran on Claude Code 2.1.287, with a ceiling of 10
USD. The round cost **5.37 USD** at list price, plus 0.09 for two smoke sessions. In the smoke,
HAIKU-V9 was right on H1 and H5, and the `Link` and `meta.pagination` notes came first.

All 24 `-V9` transcripts held the line, and the 12 `-NOTES` transcripts did not. No wrapper was
echoed in an agent-visible result, the guard stopped nothing, the subscription refused nothing
and no site was down. One session was `not_run` and ran again: H8 run 1 of HAIKU-V9, whose note stayed at the end
of a result (see below).

| task | Haiku | Haiku-V9 | Sonnet | Sonnet-V9 | Sonnet-notes |
|---|---|---|---|---|---|
| H1 | 1/2, 0.053 | **2/2**, 0.040 | 2/2, 0.078 | 2/2, 0.075 | 2/2, 0.088 |
| H4 | 0/2, 0.028 | **2/2**, 0.035 | 2/2, 0.069 | 2/2, 0.076 | 2/2, 0.069 |
| H5 | 0/2, 0.055 | **2/2**, 0.054 | 2/2, 0.080 | 2/2, 0.073 | 2/2, 0.097 |
| H7 | 2/2, 0.126 | 1/2, 0.156 | 2/2, 0.131 | 2/2, 0.195 | 2/2, 0.136 |
| H2 | 1/2, 0.045 | 2/2, 0.038 | 2/2, 0.073 | 2/2, 0.080 | 2/2, 0.074 |
| H8 | 2/2, 0.135 | 1/2, 0.059 | 2/2, 0.124 | 2/2, 0.131 | 2/2, 0.167 |
| right / sum of means | 6/12, 0.441 | **10/12**, 0.382 | 12/12, 0.554 | 12/12, 0.629 | 12/12, 0.631 |

Mean USD per session. Confirmation 4's price and answers, computed the same way over these six
crawls. This is not a verdict, because the tasks were seen:

| | total crawl ratio | crawls cheaper by mean | right | cost per right answer, ratio |
|---|---|---|---|---|
| Haiku-V9 / Haiku | 0.864 | 4/6 | 10 vs 6 | 0.519 |
| Sonnet-V9 / Sonnet | 1.136 | 2/6 | 12 vs 12 | 1.136 |
| Sonnet-notes / Sonnet | 1.140 | 0/6 | 12 vs 12 | 1.140 |
| Sonnet-notes / Sonnet-V9 | 1.003 | 3/6 | 12 vs 12 | 1.003 |

By task group: the misses (H1 H4 H5 H7) give 1.085 for Haiku, 1.173 for Sonnet-V9 and 1.092 for
Sonnet-notes. H2+H8 give 0.543, 1.069 and 1.227. Haiku-V9's H8 counts its repeat (0.065). With
the first attempt counted instead (0.093, right), the Haiku crawl ratio is 0.896.

**What the v3 notes did, read in the transcripts.** The round note fired in both HAIKU-V9 H4
sessions. Each time the agent fetched `?$limit=50000` next and answered 392. The size-key note
fired in HAIKU-V9 H5 run 1, as in the smoke, and the agent paged the 55 pages. The other H5
session and both H1 sessions fetched from their first evaluate, so no open-page note was
needed. The `Link` note fired twice, in SONNET-NOTES H1 run 2. That session opened the API filtered
by region, and the note gave it the next page and then the last. The XHR rows note fired on H7 (below).
**No `-V9` or `-NOTES` session read only the open page.** In confirmation 5, 4 of the 9 HAIKU-SP
sessions on H1, H4 and H5 did.

Every miss, read in its transcript:

| session | answer | what happened |
|---|---|---|
| H1 r2, H4 r1, r2, H5 r1, r2, H2 r2 Haiku | 3, 126, 126, 2, 2, 18 | read only the open page, as in confirmation 5. In H5 r2 and H2 r2 it did so through `browser_run_code_unsafe`, a tool no hook watches |
| H7 r1 Haiku-V9 | 200 | clicked Next inside one evaluate up to 100 times and read 603 cards. The note at the head said "fetched JSON rows 600, distinct 6", and the agent answered from the 603 without acting on it. This is the same kind as v8's G6: a note that is right, ignored |
| H8 r2 Haiku-V9 | 26 | counted `table tbody tr` over every table on the page, not the product table, while clicking the four page links. No note speaks to it. The note it got, "this call fetched nothing, so it read only the open page ... pagination links up to page 4", was wrong, because the call had clicked through the pages |

Neither Haiku-V9 miss is an open-page miss, and both are cheap (0.048, 0.053).

What this says:

- **The four new notes do what they were built for.** On the three pages whose size v8.1 could
  not read, they fired when the agent read only the open page, and the agent then fetched the
  rest every time. Haiku-V9 was right on H1, H4 and H5 6/6, where plain Haiku was 1/6.
- **Haiku's price is still the open-page miss's price.** On H1, H4 and H5, plain Haiku read one
  page in 4 turns, at 0.028 to 0.055, and was wrong. Haiku-V9 paid 0.035 to 0.054 to be right.
  Over the six crawls that gives 0.864 and 4 of 6 cheaper. Per right answer it is 0.519.
  Confirmation 5's crawls give 0.507 on the same measure.
- **Removing the line does not make Sonnet cheaper.** Sonnet-notes against Sonnet-V9 is 1.003 on
  the crawls. The line's cost on H7 is real: Sonnet-V9 went to the API (POSTs answered 405, then
  `network_requests`, then the site's `index.js`) at 0.195, against 0.136 for Sonnet-notes, which
  clicked Next. But without the line Sonnet costs more on H8 (0.167 against 0.131) and on H5
  (0.097 against 0.073). On H8 the open-page note is said again on every evaluate of a table
  paged in the browser ("fetched nothing ... pagination links up to page 4"), six times in run 1,
  and Sonnet-notes walked the four pages by clicks in 13 turns. **Sonnet's price is not a line
  problem.** Sonnet alone reads these JSON APIs in 4 or 5 turns, and every arm with hooks adds
  output to that.
- **The open-page note is wrong on a page paged in the browser.** It fires whenever the call made
  no request, including when the call clicked through the pages and the text changed (H8). That
  makes it noise on H8 for every arm. A fix would leave it out when the call's clicks changed the
  page, and say it once per page rather than on every evaluate. It is not in v9.
- **A result too large for Claude Code bypasses the hook that moves the notes.** In H1 run 2 of
  HAIKU-V9, the evaluate returned all 444 houses, 380 KB. Claude Code answered "exceeds maximum
  allowed tokens" and saved the output to a file. That file is the raw output: the wrapper is
  echoed whole, and the note sits on line 10,830 of 10,835. The `PostToolUse` rewrite never
  reached it. The agent grepped the file and was right. This is a second form of v8's G1 case
  (v8 saw a 2 KB preview, and this time there was no preview). `nav_v8.v81_counts` does not count
  it, so `persisted` reads 0. The fix that survives both forms is for the wrapper to return the
  notes as the first key of its value, `{sanchopanza, result}`, so any reader of the file or
  preview meets them first. It is not in v9.
- **A note that is the whole value was not moved.** A function that returns nothing comes back
  as `{"sanchopanza": ...}`, with no comma before the key, so `NOTES_KEY` missed it. That
  happened in H8 run 1 of HAIKU-V9, which the treatment check marked `not_run`. After the round,
  `notes_first` moves such a note and leaves `undefined` in its place, but only with
  `NOTES=3`; v8.1 is left as it was measured (`test_a_note_that_is_the_whole_value_comes_first_with_v9`).

### Confirmation 6: DRAFT, not sealed

Not registered, not sealed and not launched. Roman has to decide the price criterion first
(note below). The text follows confirmation 5's prereg. Only what is listed changes.

- **What is tested.** The crawl hook as v9 left it, `install --crawl` plus `V8_HOOKS` and
  `V81_HOOKS` with the same command, and seven variables in the session's own `--settings` only:
  `CRAWL_LINE_VERSION=6`, `CRAWL_NOTES=3`, `CRAWL_ECHO=short`, `CRAWL_LINE_AT=prompt`,
  `CRAWL_NOTES_AT=front`, `CRAWL_SHOT=snapshot-first` (each with the `SANCHOPANZA_` prefix). The
  wrapper is sealed by the sha256 of `wrap("() => 1", 120, notes=3)`, and the texts as in
  confirmation 5. Line v6 stays on both models. v9's round gives no reason to drop it for
  Sonnet.
- **Arms.** `HAIKU`, `HAIKU-SP`, `SONNET`, `SONNET-SP`, on Claude Code 2.1.287 with Playwright MCP,
  with the same tools and denials as confirmation 5. `not_run` follows `nav_v8.treatment`, as in
  confirmation 5. A session refused by the subscription stops the phase only on Anthropic's 429
  or a usage limit (`nav_v9.api_limit_hit`). A site's 429 is the agent's to handle.
- **Tasks.** These are to be chosen and walked by hand before sealing: eight new crawls (J1-J8)
  on hosts no earlier phase used, with confirmation 4's mix (five JSON APIs, one server-paged
  listing with a stated total, one list paged by a Next button over an API, one table paged in
  the browser). Each truth is checked by a second route. At least one API states its size only in
  a `Link` header, and one states none. There are also four interactive tasks for no harm: I1-I4
  again, or four new ones walked by hand. Crawls run three times per arm and interactive tasks
  four times, for 160 sessions.
- **Hypotheses.** Confirmation 4's criteria, word for word: price (total crawl ratio at most 0.75
  and cheaper by mean on at least 6 of 8), answers (at least as many right of 24) and no harm (of
  16, minus 1, at a cost ratio of at most 1.25). They are computed by `nav_confirm3._compare`.
- **Rules carried over.** The site-down rule (a), the spend about 18 USD expected with the ceiling
  at 25 USD in code, the 30-minute kill charged at the cap, and every miss read by hand.
- **What development predicts, said before sealing.** Under these criteria both models are
  expected to fail price again. Haiku-V9 was at 0.864 with 4 of 6 cheaper on seen tasks, and
  Sonnet-V9 at 1.136 with 2 of 6. Answers and no harm are expected to hold.

**Note for Roman: the price criterion punishes being right more often.** It compares cost
whatever the answer. Where plain Haiku reads one page, it is cheap and wrong: in confirmation 5,
H4 and H5 were 6 of 6 wrong, at 0.029 and 0.049. Getting those right costs a second evaluate, so
an arm that fixes Haiku's misses looks more expensive on exactly the tasks it fixes. A proposal,
**not applied**: price on **cost per right crawl answer**, (total crawl USD of `m-SP` / its right
crawl answers) divided by (the same for `m`), at most 0.75, with the answers criterion unchanged.
On that measure, confirmation 5 gives Haiku 0.507 and Sonnet 1.011. v9's round gives Haiku 0.519,
Sonnet-V9 1.136 and Sonnet-notes 1.140. So Haiku would pass and Sonnet would not, either way. Its
own weakness is that an arm that costs more in dollars passes if it is right often enough: 1.3
times the cost with twice the right answers gives 0.65. Charging every wrong answer at the
session cap (1.00 USD) is a stricter alternative. Either must be chosen and written before the
seal, not after the results.

## Files

- `nav-v6-sessions.jsonl` / `.log`, `nav-v6.json`: the phase. `nav-v6-smoke-sessions.jsonl`: the
  smoke session (F4, v6, right, 0.16 USD).
- `nav-v7-sessions.jsonl` / `.log`, `nav-v7.json`, `nav-v7-smoke-sessions.jsonl`: the v7 round.
- `nav-v8-sessions.jsonl` / `.log`, `nav-v8.json`, `nav-v8-smoke-sessions.jsonl`: the v8 round
  (`benchmarks/browse/nav_v8.py`, `tests/test_nav_v8.py`).
- `nav-v81-sessions.jsonl` / `.log`, `nav-v81.json`, `nav-v81-smoke-sessions.jsonl`: the v8.1
  round (`nav_v8.py --round v81`, `tests/test_crawl_v81.py`).
- `truth-v6.json`: the answers recomputed after the phase.
- `prereg-crawl4.md` / `.sha256`: confirmation 4, sealed before it ran.
- `nav-confirm4-sessions.jsonl`, `nav-confirm4.json`: confirmation 4's 120 sessions and its
  verdicts.
- `prereg-crawl5.md` / `.sha256`: confirmation 5, sealed before it ran.
- `nav-confirm5-sessions.jsonl` / `.log`, `nav-confirm5.json`: confirmation 5's 161 sessions
  (160 counted) and its verdicts; `truth-confirm5.json`: its answers recomputed after the phase.
  Code: `benchmarks/browse/nav_confirm5.py`, `truth_confirm5.py`, `check_tasks5.py`,
  `tests/test_nav_confirm5.py`.
- `nav-v9-sessions.jsonl` / `.log`, `nav-v9.json`, `nav-v9-smoke-sessions.jsonl`: the v9 round
  (`benchmarks/browse/nav_v9.py`, `tests/test_nav_v9.py`, `tests/test_crawl_v9.py`).
- `benchmarks/browse/nav_v6.py`, `nav_v7.py`, `nav_confirm4.py`, `truth_v6.py`,
  `truth_confirm4.py`, `repeat_fingerprint.py`; `tests/test_nav_v6.py`, `test_nav_v7.py`,
  `test_nav_confirm4.py`, `test_crawl_notes.py`.
