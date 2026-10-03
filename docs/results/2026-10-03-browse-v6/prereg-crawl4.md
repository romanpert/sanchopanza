# Pre-registration 4: Claude Code with the crawl hook as v7 left it, against Claude Code alone

Written 2026-10-03, after v7's development round (README of this folder) and before any session
of this phase. Sealed by `prereg-crawl4.sha256` (`nav_confirm4.py --record-hash`) and committed
with the code it names before the first session; `nav_confirm4.py --live` refuses to spend while
the two disagree. **Not launched**: launching is the owner's decision.

## What is being tested

The crawl hook (`sanchopanza.harness.crawl_hook`, `sanchopanza crawl-hook`) as
`sanchopanza install --crawl` writes it, switched to v7 the way a user would, through two
variables in the settings' `env`: `SANCHOPANZA_CRAWL_LINE_VERSION=6` and
`SANCHOPANZA_CRAWL_NOTES=1`. There is no model and no decision:

- `SessionStart` adds strategy line v6, verbatim (sha256 of the text
  `88212a15ab0f6ebd4cba111ec65d480b2b252adfdd67e9534f70220cc1cc1faa`).
- `PreToolUse` on `mcp__.*__browser_evaluate` returns only `updatedInput`. The function is
  raced against 120 s, and its result carries the crawl notes (`harness.crawl_notes`). These
  quote the size the open page states when the call fetched nothing, count failed fetches by
  status, and name pages served twice under different URLs. The wrapper is sealed by the sha256
  of `wrap("() => 1", 120, notes=True)`:
  `9ad6a00ef38827c3d304fdac7db813b602891770605a3f006ba1eebbe46e1b67`. Nothing is approved
  (`--preflight` checks this).

The bar is the owner's: **with sanchopanza, Claude Code has to beat Claude Code without it on
price and on answers at once, model by model, with no margin.**

## Arms (`nav_confirm4.ARMS`), Claude Code 2.1.287 with Playwright MCP

The same tools and permissions are used in every arm. `SendMessage`, `ListAgents`,
`ScheduleWakeup`, `CronCreate`, `RemoteTrigger`, `WebFetch`, `WebSearch` and `Bash` are denied,
and no Jev key is set.

- `HAIKU`, `SONNET`: `claude-haiku-4-5` and `claude-sonnet-5`, with no hook.
- `HAIKU-SP`, `SONNET-SP`: the same model, plus what `install._merge_crawl` writes and the two
  variables above. The hook imports this worktree's package.

A session counts as `not_run`, and runs again on resume, in these cases:

- an `-SP` session whose transcript lacks line v6;
- an `-SP` session that ran an evaluate without the notes;
- a plain session that shows either one.

`--preflight` runs before `--live` and checks three things: the pinned Claude Code; that the hook
command with the `-SP` env answers a session start with line v6; and that it wraps an evaluate
with the notes and the 120 s limit.

## Tasks (`nav_confirm4.CRAWLS`, `INTERACTIVE`): three runs per task and arm, 120 sessions

Eight crawls on pages no earlier phase used. On each, the first page states the size of the whole
and most of the whole lies beyond the open page. The answers come from `truth_confirm4.py`, and
each was checked by a second route:

| task | page | truth |
|---|---|---|
| G1 | dummyjson products (194, `skip`/`limit`; a guessed `?page=2` returns page 1) | 44 |
| G2 | swapi.dev people (82, `next` links): blue eyes (2 more have "blue-gray") | 19 |
| G3 | catfact.ninja facts (332, 34 pages, rate limit declared in headers) | 77 or 78 |
| G4 | pokeapi Pokemon (1,351, `next` links): names ending "-mega" (11 more contain "mega") | 88 |
| G5 | books.toscrape Fantasy (48 results, "Page 1 of 3"): four stars or more | 21 |
| G6 | LambdaTest table pagination demo (40 rows paged in the browser): last name M | 6 |
| G7 | books.toscrape Sequential Art (75 results, 4 pages): under 20.00 | 19 |
| G8 | swapi.dev planets (60, `next` links): population over one billion | 19 |

G3 takes either answer: the API's `length` field gives 77, while the facts' own text gives 78.

For no harm, the interactive tasks are confirmation 3's I1 (log in and out on the-internet) and
I2 (sort saucedemo by price, buy the first two, read the totals). Both were walked by hand in
`check_tasks3.py`, and neither notes nor line v6 has met them.

Crawls are graded on their ANSWER line only, with a number counted as a whole number.
Interactive tasks are graded on every required substring anywhere in the reply.

- A session the runner kills (30 min) is charged the session cap of 1.00 USD and counts as
  wrong.
- A reply refused by a content filter counts as wrong.
- A session refused by the subscription's usage limit is a pause, not a result. It is recorded
  as not run, the phase stops, and the session runs again on resume.

## Hypotheses (`nav_confirm3.verdicts`, unchanged), for each model m in {Haiku, Sonnet}, `m-SP` against `m`

- **Price.** The total charged USD on crawls for `m-SP` divided by that for `m` is **at most
  0.75**, and `m-SP` is cheaper by mean on **at least 6 of the 8** crawls.
- **Answers.** `m-SP` is right on **at least as many** of the 24 crawl sessions as `m`. There
  is no margin: one answer fewer fails it.
- **No harm.** On I1 and I2, `m-SP` is right on at least `m`'s count minus 1 (of 6), at a total
  cost ratio of at most 1.25.

**sanchopanza beats the harness on model m** if and only if all three hold for m. Results are
reported for each model and for both together. A result on one model is not claimed for the
other.

## Described, not tested

- Per arm: sessions killed by the runner, guard stops (counted as tool results that begin
  `### Error\nError: evaluate stopped after`), and median wall time.
- Per task: right answers, mean cost and turns.
- The cheap model with sanchopanza against the expensive one without it.

## Spend and stopping

This runs on the subscription through `claude -p`, at list prices, not on money. **The expected
cost is about 18 USD**, estimated from v7's development round and confirmation 3:

- Haiku unaided about 0.17 per session, Haiku with v7 about 0.07;
- Sonnet unaided about 0.20, Sonnet with the line about 0.14;
- that gives 30 sessions per arm at 5.1, 2.1, 6.0 and 4.2 USD.

The ceiling is 26 USD, enforced in code (`phase.Limits`, which counts the whole sessions file and
reserves one session before each). Every session must run on one Claude Code version, read from
its transcript, and the version is reported. At the first 429 the run is stopped by PID and
resumed when the limit clears.

## Whatever the outcome

The verdicts are published as computed, in the README of this folder. Every miss is read by hand
before it is described.
