# Browse, Phase 3c: Phase 3b again, with the hook's three faults fixed

Written 2026-09-30 before any Phase 3c session ran. Runner: `benchmarks/browse/e2e_mcp.py
--fixed`.

## Why

Phase 3b (`prereg-e2e-mcp.md`, registered) found no saving: -0.0009 USD a session [-0.0185,
+0.0126]. Its transcripts showed three faults of the hook, none of the ranking:

1. Claude Code replaces an MCP result past its token limit with a notice before `PostToolUse`
   runs, so the hook never saw a large `browser_snapshot`.
2. The hook pruned the agent's own `browser_find` results, and the agent then read the whole
   archive (3 of 4).
3. The hook's goal kept the first 130 characters of the request and lost its question.

Fixed in commit a17dc5b, each with a test: the hook reads the saved result behind the notice
(only from its own session's `tool-results` folder) and returns it pruned in its place, which a
live probe confirmed Claude Code accepts; searches pass untouched; the goal is `browse_goal`.
Nothing else about the hook changed (6,000 characters to act, 20 elements, 3,000 characters of
text, Jev `jev-1.13.0`, `blend=0.5`).

## Design

Phase 3b's, unchanged: the same six tasks and graders, Playwright MCP 0.0.83, `Read`/`Grep`/
`Glob`, `WebFetch`/`WebSearch`/`Bash` disallowed, the same one-line system addition and prompts,
four runs per task and arm (48 sessions), PLAIN before LEAN within each run, one at a time,
`--max-budget-usd 1.50`, `SANCHOPANZA_SESSION_MAX_USD=0.20`. PLAIN is run again, not reused
from 3b, so both arms share the day and the pages.

## Decision rule, fixed now

Phase 3b's rule: the hook is recommended for Playwright MCP if LEAN succeeds on at least as many
runs as PLAIN minus one and its mean cost per session (list USD plus Jev USD) is lower with the
bootstrap interval of the per-task difference (5,000 resamples over tasks, seed 2033) below
zero. Reported besides: every cut, which tools each session called, and on which tasks the hook
acted on a replaced notice.

## Money

At most 20.00 USD at list price through the subscription (Phase 3b spent 6.06) and 2.00 USD of
Jev for the phase; the runner stops before a session that could pass either. Jev is estimated at
under 1 USD: the largest snapshot seen (860,106 characters, 2,672 elements) is about 91 calls,
0.03 USD.

## What would make this wrong

Six tasks and an interval over six task means. The fixes were designed on Phase 3b's
transcripts, so the tasks are not new; what is new is every session. If the hook now helps only
where snapshots pass Claude Code's limit (M1, M2, M4), the saving concentrates there and the
mean over six tasks may still include zero: reported by task either way.
