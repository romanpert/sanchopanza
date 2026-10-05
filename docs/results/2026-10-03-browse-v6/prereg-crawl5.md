# Pre-registration 5: Claude Code with the crawl hook as v8.1 left it, against Claude Code alone

Written 2026-10-05, after v8.1's development round (README of this folder) and before any session
of this phase. Sealed by `prereg-crawl5.sha256` (`nav_confirm5.py --record-hash`) and committed
with the code it names before the first session; `nav_confirm5.py --live` refuses to spend while
the two disagree.

## What is being tested

The crawl hook (`sanchopanza.harness.crawl_hook`, `sanchopanza crawl-hook`) as v8.1's development
round ran it. That is what `sanchopanza install --crawl` writes, plus the events of
`crawl_hook.V8_HOOKS` and `crawl_hook.V81_HOOKS` with the same command, switched on through six
variables in the settings' `env`:

- `SANCHOPANZA_CRAWL_LINE_VERSION=6`
- `SANCHOPANZA_CRAWL_NOTES=2`
- `SANCHOPANZA_CRAWL_ECHO=short`
- `SANCHOPANZA_CRAWL_LINE_AT=prompt`
- `SANCHOPANZA_CRAWL_NOTES_AT=front`
- `SANCHOPANZA_CRAWL_SHOT=snapshot-first`

These go only in each session's own `--settings` file, never in `~/.claude/settings.json`, and
every session runs with `--setting-sources ""`. There is no model and no decision:

- `UserPromptSubmit` adds strategy line v6, verbatim (sha256 of the text
  `88212a15ab0f6ebd4cba111ec65d480b2b252adfdd67e9534f70220cc1cc1faa`), on a prompt that gathers
  and does not act (`crawl_hook.gathers`). `SessionStart` adds nothing.
- `PreToolUse` on `mcp__.*__browser_evaluate` returns only `updatedInput`. The function is raced
  against 120 s, and its result carries v8's notes (`harness.crawl_notes`, version 2). The wrapper
  is sealed by the sha256 of `wrap("() => 1", 120, notes=2)`:
  `a53df5997236e594a0e0a17d19264307df6d6de439c38470cadb86e6215c6e1e`.
- `PreToolUse` on `mcp__.*__browser_take_screenshot` denies the session's first screenshot with
  `SHOT_REASON` and lets every later one pass.
- `PostToolUse` on `mcp__.*__browser_evaluate` replaces the wrapper Playwright MCP echoes with
  `ECHO_LINE` and moves the notes to the head of the result under `NOTES_HEAD`. The three texts are
  sealed by the sha256 of `ECHO_LINE`, `NOTES_HEAD` and `SHOT_REASON` joined by newlines:
  `e72ec9f631fe19b44d5225793296834706232ea14bfa9bda8cbcfffca43e1b3a`.

The bar is the owner's: **with sanchopanza, Claude Code has to beat Claude Code without it on
price and on answers at once, model by model, with no margin.**

## Arms (`nav_confirm5.ARMS`), Claude Code 2.1.287 with Playwright MCP

The same tools and permissions are used in every arm. `SendMessage`, `ListAgents`,
`ScheduleWakeup`, `CronCreate`, `RemoteTrigger`, `WebFetch`, `WebSearch` and `Bash` are denied,
and no Jev key is set.

- `HAIKU`, `SONNET`: `claude-haiku-4-5` and `claude-sonnet-5`, with no hook.
- `HAIKU-SP`, `SONNET-SP`: the same model, plus the settings above (`nav_v8.settings_for` for
  its `-V81` arms, unchanged). The hook imports this worktree's package.

A session counts as `not_run`, and runs again on resume, in these cases (`nav_v8.treatment`):

- an `-SP` session on a crawl whose transcript lacks line v6, or one on an interactive task whose
  transcript shows it;
- an `-SP` session in which a wrapper was echoed whole, or an evaluate with a function ran
  without the notes, or the first screenshot passed, or a note was left at the end of a result;
- a plain session that shows the line, the notes or the echo cut;
- a session refused by the subscription (a 429 or a usage limit). This is a pause, not a result:
  the phase stops (`STOP-LIMIT` in its log), the run is stopped by PID, and the session runs
  again on resume.

`--preflight` runs before `--live`. It checks v8.1's preflight: the pinned Claude Code, and the
hook command answering line v6, the notes, the echo cut, the notes at the head and the denied
first screenshot. Then it checks this phase's own conditions: the line answers the prompt of
every crawl below and of no interactive task, and no sanchopanza hook is in
`~/.claude/settings.json`.

## Tasks (`nav_confirm5.CRAWLS`, `INTERACTIVE`): 160 sessions

Crawls run three times per arm, and interactive tasks four times per arm: 4 x (8 x 3 + 4 x 4) =
160 sessions.

The eight crawls are on hosts no earlier phase used. H6 is the exception: it is a books.toscrape
category never used before, as G5 and G7 were. The mix is confirmation 4's: five JSON APIs, one
listing paginated on the server with a stated total, one list paged by a Next button over an
API, and one table paged in the browser. Two open pages are over 50 KB (H4 about 785 KB, H5 about
74 KB), so a result that returns either one whole is saved by Claude Code behind its 2 KB preview.
That is the case v8.1 moved the notes for. The answers come from `truth_confirm5.py`, and each
was checked by a second route:

| task | page | truth |
|---|---|---|
| H1 | anapioficeandfire houses (444; next page only in the `Link` header): region The Reach | 72 |
| H2 | World Bank countries (295 stated, 6 pages by `page`, 78 aggregates): income level High income | 86 |
| H3 | dnd5eapi monsters (334 listed whole; the rating only on each monster's page): challenge rating 10 or more | 55 |
| H4 | NYC Central Park squirrel census (3,023 rows, 1,000 on the open page, no total, no link): primary fur Cinnamon | 392 |
| H5 | potterdb characters (5,410 stated, 55 pages by `next`): house exactly Ravenclaw (21 more contain the word) | 203 |
| H6 | books.toscrape Young Adult (54 results, 3 pages): over 35.00 | 29 |
| H7 | demoblaze (15 products, 9 then a Next button; 2 of the 4 on the first nine): under $500 | 4 |
| H8 | testautomationpractice Pagination Web Table (20 rows, 5 drawn at a time by JS): over $15.00 | 10 |

The second routes: H1 by the API's region filter, H2 by the income-level endpoint, H3 by the
challenge-rating filter, H4 by a SoQL count, H5 by the API's house filter, H6 on each book's page,
H7 by category, and H8 by the table as the browser draws it, page by page (`check_tasks5.py`).
H4's data holds 5 duplicated sighting ids. All of them are Gray, so a deduplicated count of
Cinnamon is also 392.

For no harm, the interactive tasks are confirmation 3's I1 (log in and out on the-internet) and
I2 (sort saucedemo by price, buy the first two, read the totals), plus two new ones walked by hand
in `check_tasks5.py`:

- I3: log in to the XYZ Bank demo (globalsqa) as Hermoine Granger, choose account 1001
  (balance 5096), deposit 1500 and withdraw 400. Required: `6196` and `transaction successful`.
- I4: fill and submit testpages.eviltester's HTML form as stated. Required: `first program`,
  `cb1`, `rd3` and `dd5`, the values its results page shows.

Crawls are graded on their ANSWER line only, with a number counted as a whole number.
Interactive tasks are graded on every required substring anywhere in the reply.

- A session the runner kills (30 min) is charged the session cap of 1.00 USD and counts as
  wrong.
- A reply refused by a content filter counts as wrong.

## Hypotheses (`nav_confirm3._compare`, unchanged), for each model m in {Haiku, Sonnet}, `m-SP` against `m`

These are confirmation 4's criteria, word for word, and computed by the same code. The task set
is the one the owner set for this phase, so "of 6" on no harm becomes "of 16".

- **Price.** The total charged USD on crawls for `m-SP` divided by that for `m` is **at most
  0.75**, and `m-SP` is cheaper by mean on **at least 6 of the 8** crawls.
- **Answers.** `m-SP` is right on **at least as many** of the 24 crawl sessions as `m`. There
  is no margin: one answer fewer fails it.
- **No harm.** On I1, I2, I3 and I4, `m-SP` is right on at least `m`'s count minus 1 (of 16), at
  a total cost ratio of at most 1.25.

**sanchopanza beats the harness on model m** if and only if all three hold for m. Results are
reported for each model and for both together. A result on one model is not claimed for the
other.

## Added before the first session, and nothing else

**(a) A site that is down.** A page load is a tool result in which Playwright MCP reports
`- Page URL:`. It adds `- HTTP status: NNN` when the server did not answer 2xx. A session that is
graded wrong, and in which every page load reports a 5xx, is `site_down`. It is recorded as
`not_run` and runs again once, after every other planned session. If the repeat is `site_down`
again, it counts as a wrong answer for its arm, at its own cost. A session with a right answer is
never `site_down`, and the same rule applies to every arm.

**(b) Confirmation 4's erratum on G2 does not apply.** G2 is not in this phase.

**(c) Spend.** This runs on the subscription through `claude -p`, at list prices, not on money.
**The expected cost is about 18 USD**, from the per-session means measured in confirmation 4 and
in v8.1's round, for crawls and interactive tasks respectively:

| arm | crawl | interactive | sessions | expected |
|---|---|---|---|---|
| Haiku | 0.10 | 0.10 | 24 + 16 | 4.0 |
| Haiku-SP | 0.06 | 0.08 | 24 + 16 | 2.7 |
| Sonnet | 0.115 | 0.185 | 24 + 16 | 5.7 |
| Sonnet-SP | 0.085 | 0.19 | 24 + 16 | 5.1 |

The crawl means are raised a little over the measured ones for H4 and H5, whose open pages are
large. **The ceiling is 25 USD**, enforced in code (`phase.Limits`, which counts the whole
sessions file, the site-down repeats included, and reserves the 1.00 session cap before each
session). That is 1.4 times the expected cost, the same headroom as confirmation 4 (26 against
18). The most expensive session of those two rounds cost 0.28. Every session must run on one
Claude Code version, read from its transcript, and the version is reported.

## Amended before the first session

The first seal (264b843) asked H7 for the products over $700 (truth 6). An independent check of
the sealed text, before any session, found that demoblaze's product names hold the digit 6
("Nexus 6", "Iphone 6 32gb", "Samsung galaxy s6"). The registered grading counts a whole number
anywhere on the ANSWER line, so a wrong count that named one of those products would have passed.
The grading is left as registered. H7's question changed to the products under $500 (truth 4, by
both routes). No product name holds a whole 4. Nothing else changed, and the amended text is
sealed again before the first session.

## Described, not tested

- Per arm: sessions killed by the runner, guard stops (tool results that begin
  `### Error\nError: evaluate stopped after`), median wall time, and what v8.1's hooks did:
  sessions with the line, echo cuts, click and rows notes, notes at the head, results saved
  behind the preview and with the notes at their head, and screenshots asked for and denied.
- Per task: right answers, mean cost and turns.
- The cheap model with sanchopanza against the expensive one without it.
- Every site-down session and its repeat.

## Whatever the outcome

The verdicts are published as computed, in the README of this folder. Every miss is read by hand
before it is described.
