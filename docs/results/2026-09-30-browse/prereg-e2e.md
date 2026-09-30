# Browse, Phase 3: a real Claude Code session browsing, with and without the hook

Written 2026-09-30 before any session ran. Not part of `prereg.md`; it runs whatever Phase 1
says, and its result stands on its own.

## Question

Claude Code browsing real pages with `playwright-cli` (the snapshot arrives on `Bash` stdout or
as a `.yml` file the agent `Read`s, measured 2026-09-30): does `sanchopanza.harness.browse_hook`
(PostToolUse on `Bash|Read`) lower what the session costs without losing the answer?

## Tasks

Six tasks on neutral public pages, each with an answer checked by hand on 2026-09-30 and graded
by required substrings (case-insensitive, spaces and thousands separators ignored):

| id | start | task | required |
|---|---|---|---|
| T1 | books.toscrape.com | In the Mystery category, the price and star rating of "Sharp Objects" | 47.82; four |
| T2 | books.toscrape.com | The UPC of "Tipping the Velvet" | 90fa61229261140a |
| T3 | quotes.toscrape.com | Jane Austen's birth date and place, from her author page | 1775; steventon |
| T4 | en.wikipedia.org/wiki/Python_(programming_language) | Who designed Python and the year it first appeared, from the infobox | guido van rossum; 1991 |
| T5 | en.wikipedia.org/wiki/Mount_Everest | The elevation in metres given in the infobox | 8848.86 |
| T6 | books.toscrape.com | The title of the first book on page 2 of the catalogue | in her wake |

## Arms

- **PLAIN**: `claude -p`, model `claude-sonnet-5`, tools `Bash` and `Read` only (`WebFetch` and
  `WebSearch` disallowed so both arms browse), user and project settings not loaded, the same
  appended system prompt naming `playwright-cli` and its commands, a fresh working directory and
  a `playwright-cli` session name per run.
- **LEAN**: the same, plus the hook in `--settings` with Jev (`jev-1.13.0`) ranking, defaults
  `BROWSE_CHARS=6000`, `BROWSE_KEEP=20`, `BROWSE_TEXT=3000`, and `browse.rank`'s defaults as of
  the commit that adds this file (`blend=0.5`, chosen on Phase 1's development set and not yet
  confirmed when this was written). A `Read` of the archived full snapshot is never pruned: that
  is the agent's way back to everything that was cut, and the note in each pruned snapshot says so.

A pilot first: T1 once per arm (run 0), to check that the hook fires inside Claude Code and the
grader reads the answer; excluded from every count, reported apart. Then three runs per task and
arm, 36 sessions, run in the order task, run, arm (PLAIN first), one at a
time. `--max-budget-usd 1.00` per session.

## Metrics

- Success: all required substrings in the final answer.
- Cost: `total_cost_usd` from `claude -p` (list price, our evaluation harness, not the API),
  plus the hook's Jev dollars from its journal; input tokens (fresh, cache read, cache write);
  turns.
- Paired per task: mean cost LEAN minus PLAIN with a bootstrap interval over tasks.

## Decision rule, fixed now

The hook is recommended in the docs if LEAN succeeds on at least as many runs as PLAIN minus one
(17 of 18 when PLAIN has 18) and its mean cost per session is lower with the bootstrap interval of
the difference below zero. If it saves but loses answers, or does not save, that is published and
the hook stays opt-in without a recommendation.

## Money

At most 20.00 USD at list price for the phase through the subscription; the runner stops before a
session that could pass it. Jev at most 0.50 USD. If the first two tasks (12 sessions) already
spend more than 8 USD, the runner stops and the result is reported as partial.

## What would make this wrong

Six tasks and three runs are a small sample: a difference in success of one or two runs is
noise. Pages change; the answers were checked the day this was written. The agent can choose
`playwright-cli find` or `eval` instead of reading snapshots, in which case the hook has nothing to
prune: that is part of what is measured, not a flaw.
