# Browse, Phase 3e: the fixed hook with playwright-cli, on the six new tasks

Written 2026-09-30 before any Phase 3e session ran. Runner: `benchmarks/browse/e2e.py --new`.

## Why

With Playwright MCP the fixed hook passed (Phase 3d: -0.0144 USD a session [-0.0270, -0.0025]).
With `playwright-cli`, the other browser tool built for agents, it was measured only before any
fix (Phase 3: +0.0095 [-0.006, +0.027]), on tasks that included a star rating no snapshot holds.
Two of the five fixes apply to it too: a `find` passes untouched, a `Read` of part of a file
passes, and the note points recovery at `Grep`; the goal is `browse_goal`.

## Design

Phase 3's setup (`prereg-e2e.md`), unchanged except the tasks and the runs: `claude -p`,
`claude-sonnet-5`, `Bash(playwright-cli:*)` and `Read`, `WebFetch` and `WebSearch` disallowed,
the same appended system prompt naming playwright-cli's commands, `@playwright/cli` 0.1.18 as
installed, the hook on `PostToolUse` for `Bash|Read` with its defaults and
`SANCHOPANZA_SESSION_MAX_USD=0.20`. Tasks: Phase 3d's six (N1-N6, `prereg-e2e-mcp-new.md`), four
runs per task and arm, 48 sessions, PLAIN before LEAN in each run, `--max-budget-usd 1.00`.

## Decision rule, fixed now

Phase 3's: the hook is recommended with playwright-cli if LEAN succeeds on at least as many runs
as PLAIN minus one and its mean cost per session (list USD plus Jev USD) is lower with the
bootstrap interval of the per-task difference (5,000 resamples over tasks, seed 2033) below zero.

## Money

At most 20.00 USD at list price through the subscription (Phase 3 spent 4.32 for 36 sessions) and
the hook's 0.20 USD of Jev a session at most; expected under 0.10 of Jev in all. The runner's
early stop (8 USD after the first two tasks) stays.

## What would make this wrong

Six tasks and an interval over six task means. playwright-cli's snapshots are moderate, so there
may be little to cut; that is part of what is measured.
