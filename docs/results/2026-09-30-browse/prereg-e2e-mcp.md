# Browse, Phase 3b: an ordinary Claude Code session with Playwright MCP, with and without the hook

Written 2026-09-30 after a four-session pilot and before any counted session. Runner:
`benchmarks/browse/e2e_mcp.py`.

## Why

Phase 3 (`prereg-e2e.md`) found no saving, but measured where the hook could not win:
`playwright-cli` serves snapshots of 7,000-29,000 characters against about 45,000 tokens of fixed
context a turn, three runs a task left one extra turn of noise in tasks the hook never touched
(T2-T4), and T1's star rating lives in a CSS class that no snapshot holds. What most people
install is Playwright MCP. In 0.0.83 (probed with no model, 2026-09-30) `browser_navigate` writes
the snapshot to a `.yml` file and returns its link, and `browser_snapshot` returns it inline:
50,157 characters for a GitHub repository page, 860,106 for Wikipedia's Mount Everest.

## Pilot (run 0, excluded from every count)

M1 and M2 once per arm. All four answered right. M1 (GitHub): PLAIN called `browser_snapshot`
twice, 0.257 USD, 44,535 tokens written to cache; LEAN read the `.yml` file, the hook cut it from
48,653 to 11,171 characters, 0.168 USD, 19,826 written. M2 (Everest): neither arm read the
860,000-character snapshot; PLAIN used `browser_find`, LEAN `Read` and `Grep` on the file, 0.117
and 0.096 USD. After the pilot M3's grader was tightened (a bare "0" matched almost anything)
and the ceiling lowered to 20 USD; nothing else changed.

## Tasks

Neutral public pages, answers checked by hand on 2026-09-30, graded by required substrings
(case-insensitive; an item that is a list is met by any alternative):

| id | start | question | required |
|---|---|---|---|
| M1 | github.com/microsoft/playwright | its license and its largest language | apache; typescript |
| M2 | en.wikipedia.org/wiki/Mount_Everest | elevation in metres in the infobox | 8848.86 |
| M3 | docs.python.org/3/library/functions.html | default of sum()'s start | start=0 / `0` / is 0 / zero ... |
| M4 | en.wikipedia.org/wiki/Python_(programming_language) | designer and first year | guido van rossum; 1991 |
| M5 | npmjs.com/package/react | its license | mit |
| M6 | books.toscrape.com | first title on catalogue page 2 | in her wake |

## Arms

Both: `claude -p`, `claude-sonnet-5`, Playwright MCP 0.0.83 as its README installs it
(`npx @playwright/mcp`, plus `--headless --isolated` to run unattended), tools the Playwright
server, `Read`, `Grep` and `Glob` (`WebFetch`, `WebSearch` and `Bash` disallowed so the browser
is used), user and project settings off, a one-line system addition ("Answer the user's question
briefly with the facts found on the page."), a fresh directory per session. The prompt says only
which page to open and the question: nothing about which tool to use.

- **PLAIN**: nothing else.
- **LEAN**: `sanchopanza.harness.browse_hook` on `PostToolUse` for `Read|mcp__playwright__.*`,
  Jev `jev-1.13.0` ranking, the hook's defaults (6,000 characters to act, 20 elements, 3,000
  characters of text), `SANCHOPANZA_SESSION_MAX_USD=0.20`.

Four runs per task and arm, 48 sessions, in the order task, run, arm (PLAIN first), one at a
time, `--max-budget-usd 1.50` each.

## Metrics and decision rule, fixed now

Phase 3's rule, unchanged: the hook is recommended for Playwright MCP if LEAN succeeds on at
least as many runs as PLAIN minus one and its mean cost per session (list USD plus Jev USD) is
lower with the bootstrap interval of the per-task difference (5,000 resamples over tasks, seed
2033) below zero. Also reported: turns, cache read and write, which tools each session called,
and every cut the hook made.

## Money

At most 20.00 USD at list price through the subscription (the pilot suggests 6-10); the runner
stops before a session that could pass it. Jev at most 0.20 USD a session.

## What would make this wrong

Six tasks is a small sample, and the interval is over six task means. Pages change; the answers
were checked today. The agent may avoid snapshots (`browser_find`, `Grep`), in which case the hook
has nothing to cut: that is part of what is measured.
