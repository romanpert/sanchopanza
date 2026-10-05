# Pre-registration 3: Claude Code with sanchopanza's crawl against Claude Code alone

Written 2026-10-03, before any session of this phase. Sealed by `prereg-crawl3.sha256`
(`nav_confirm3.py --record-hash`) and committed with the code it names before the first session;
`nav_confirm3.py --live` refuses to spend while the two disagree.

## What is being tested

Not a sentence in a system prompt, as in the first two confirmations, but the package as a user
installs it. `sanchopanza install --crawl` writes two classic Claude Code hooks
(`sanchopanza.harness.crawl_hook`, `sanchopanza crawl-hook`), no model and no decision:

- `SessionStart` (every source) adds the strategy line v5, verbatim
  (sha256 of the text `06990ee0f4e0afff811a4f6638ce66c256a797bf98fccee5d19f37620df420ca`):
  extract a multi-page crawl in one `browser_evaluate` that fetches and parses each page, cap
  every loop far above the site, account for what was read, fix the code rather than walk.
- `PreToolUse` on `mcp__.*__browser_evaluate` races the function against 120 s and returns
  only `updatedInput`: a loop that cannot end becomes an error the agent reads. It approves
  nothing (`crawl_hook_probe.py`, measured live).

The bar is the owner's (2026-10-03): **with sanchopanza, Claude Code has to beat Claude Code
without it on price and on answers at once**, model by model.

## Arms (`nav_confirm3.ARMS`), Claude Code with Playwright MCP

Same tools and permissions in every arm (`nav_e2e.one_session`: `SendMessage` and `ListAgents`
denied, no Jev key, the shared system-prompt line only):

- `HAIKU`, `SONNET`: `claude-haiku-4-5`, `claude-sonnet-5`, no hook.
- `HAIKU-SP`, `SONNET-SP`: the same model plus exactly what `install --crawl` writes, built by
  `install._merge_crawl`, the hook importing this worktree's package (`PYTHONPATH=src`).

An `-SP` session whose transcript does not show the line had no treatment: it is `not_run` and
runs again on resume. `--preflight` (run before `--live`) checks that the hook command answers a
session start with the line and wraps an evaluate without approving it.

## Tasks (`nav_confirm3.CRAWLS`, `INTERACTIVE`), three runs per task and arm, 120 sessions

Eight crawls on pages no line, arm or check has met, answers from `truth_confirm3.py`, each
checked by a second route: E1 a 5-page listing (10), E2 testimonials htmx loads on scroll (36),
E3 reviews behind a GraphQL cursor and a Load More button (51), E4 a 12-page WooCommerce shop
(55), E5 products an AJAX offset loads on scroll (27), E6 a 94-page Next.js catalogue (208), E7 a
list in an iframe whose answer sits on each family's page (7), E8 nineteen detail pages behind
one category (235). Two interactive tasks walked by hand (`check_tasks3.py`): I1 log in and out
(the-internet), I2 sort by price, buy the first two, read the totals (saucedemo).

Crawls are graded on their ANSWER line only, a number as a whole number; interactive tasks on
every required substring anywhere in the reply. A session the runner kills (30 min) is charged
the session cap, 1.00 USD, and counts as wrong. A reply refused by a content filter counts as
wrong. A session the subscription's usage limit refuses is a pause, not a result: it is recorded as
not run, the phase stops, and the session runs again on resume.

## Hypotheses (`nav_confirm3.verdicts`), for each model m in {Haiku, Sonnet}, `m-SP` against `m`

- **Price.** Crawl total charged USD of `m-SP` / `m` **at most 0.75**, and `m-SP` cheaper by
  mean on **at least 6 of the 8** crawls.
- **Answers.** `m-SP` right on **at least as many** of the 24 crawl sessions as `m`. No margin:
  one answer fewer fails it.
- **No harm.** On I1 and I2, `m-SP` right on at least `m`'s count minus 1 (of 6), at a total cost
  ratio of at most 1.25.

**sanchopanza beats the harness on model m** if and only if all three hold for m. Reported for
each model and for both together; a result on one model is not claimed for the other.

## Described, not tested

Sessions killed by the runner and guard stops per arm; median wall time per arm; per task right,
mean cost and turns; and the cheap model with sanchopanza against the dear one without it
(`HAIKU-SP` against `SONNET`: crawl cost ratio and right answers).

## Spend and stopping

Subscription through `claude -p`, list prices, not money. Expected about 25 USD (Haiku about
0.13 a session unaided and 0.10 with the line in confirmation 2; Sonnet about 0.22 and 0.12 in
development; E6's 94 pages can push a walking session to its 1.00 cap). Ceiling 34 USD in code
(`phase.Limits`, which counts the whole sessions file and reserves one session before each).
One Claude Code version for every session, read from each transcript; the version is reported.
At the first 429 the run is stopped by PID and resumed when the limit clears.

## Whatever the outcome

The verdicts are published as computed, with every miss read by hand before it is described,
in `README.md` of this folder.
