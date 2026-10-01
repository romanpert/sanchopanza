# Phases 3f and 3g, amendment 1: the cache-warming first session

Written 2026-10-01 while both phases were running, after looking at their first two sessions
each (to check the setup: every one answered right; W1 run 1 PLAIN cost 0.253 USD with Playwright
MCP and 0.240 with playwright-cli, against 0.092-0.148 for the next three) and before any
analysis of either phase.

## Why

The first session of a phase writes the prompt-cache prefix the later sessions read, and it is
always PLAIN (PLAIN runs first in each run). Re-reading the earlier phases (`warmup.py`,
`warmup.json`): in Phase 3e that first session wrote 49,489 cache tokens against about 13,800 for
the same task's other sessions, and dropping run 1 of the first task (both arms) moves 3e from
-0.0094 USD [-0.0184, -0.0036] to -0.0037 [-0.0066, -0.0004]. Phase 3d does not move (-0.0144 to
-0.0143, interval still below zero). The registered results stand as published; this is about
3f and 3g.

## Change to the decision rule

For each tool, the registered statistic is computed twice: on every session, and without run 1
of W1 in both arms (paired). The hook is recommended with that tool only if the registered rule
holds on **both**. Everything else in `prereg-e2e-wide.md` is unchanged.

Future phases will run one uncounted warm-up session before the first counted one.
