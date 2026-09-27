# Pre-registration: the tool window against a real MCP catalog

Written 2026-09-25, **before** the catalog was harvested into its final form and before any
run. Nothing below is edited after the first paid request; later thoughts go in the report.

## Why

Every end-to-end number so far used AgentDojo's 74 tools in 16 groups
(`../2026-09-25-e2e/`). The only wide measurement (`benchmarks/agentdojo/tools_wide.py`, 250
groups) used invented, deliberately distinct distractors and measured selection alone: an
upper bound. Real catalogs carry near-duplicates. A Slack MCP server next to AgentDojo's
Slack tools, Gmail next to its email, a calendar server next to its calendar, Stripe next to
its bank. That is where a per-group judgment on the user's purpose can open the wrong group,
and where a model with everything loaded can call the wrong tool.

## Setup

- Same 40 AgentDojo v1.2.2 tasks (seed 5, 10 per suite), same model (`claude-sonnet-5`,
  effort `medium`), same turn cap, same system prompts as `e2e_window.py`.
- Catalog: AgentDojo's 74 tools plus every tool in `benchmarks/mcp_wide/catalog.json`
  (public MCP servers' published tool definitions, one window group per server).
- **The ground truth does not change.** No MCP tool can complete an AgentDojo task: every call
  to one returns "not available in this environment". So the MCP tools are pure distractors,
  and every call to one is a wrong call.
- Arms: `full` (everything loaded), `search` (the platform's BM25 tool search, everything
  deferred), `sancho` (`ToolWindow` + `WindowedTools`, `wait_on_deferred=False` on Sonnet 5 as
  shipped). Jev decisions recorded to `fixtures/e2e-wide.jsonl`.
- Spend cap `--max-usd` 7.

## Predictions (each can fail)

1. **Cost.** Sancho's cost as a fraction of `full` falls below the 0.45-0.60x of the 16-group
   run. Predicted <= 0.35x as run.
2. **Wrong calls.** `full` makes more calls to MCP tools than `sancho`, because it has the
   near-duplicates in hand. Predicted: `full` > 0 wrong calls in at least 3 tasks; `sancho`
   fewer than `full`.
3. **Window false positives.** The window opens at least one MCP group in some tasks (the
   near-duplicates are real), but the mean number of MCP groups opened per task stays <= 2.
   If it is higher, the "tope de altas por evento" in the handoff queue becomes necessary.
4. **Success.** Unchanged criteria from `e2e_window.py`: sancho is the default for large
   catalogs if its success is within 2 tasks of `full` on the paired set and it is cheaper;
   it beats `search` only on more success, or equal success and cheaper or faster.

## What would embarrass the window

`sancho` success more than 2 tasks below `full`, or a mean above 2 MCP groups opened per
task, or `search` matching `sancho` on success at lower cost. Any of these is reported as it is.

## Addendum, still before any paid request (2026-09-25)

The harvest came back at 857 tools from 40 servers, about 1.0M characters. Loaded whole, the
`full` arm alone would cost more than the spending rule allows without asking. So, fixed now
and not tuned on any result:

- **Catalog:** `catalog.json` in this directory, frozen by rule: every server overlapping
  AgentDojo's apps (slack, google_workspace, google_calendar, filesystem, stripe, paypal,
  google_maps, airbnb), then the others alphabetically until >= 300 tools: + airtable,
  atlassian. 329 MCP tools, 10 servers; with AgentDojo's, 398 tools in 26 groups,
  **167,937 tokens** of tool definitions (`count_tokens`, free) against 12,214 for AgentDojo
  alone.
- **Tasks:** `--per-suite 5`, 20 tasks, all three arms on the same tasks. Estimated ~6 USD,
  cap 7. At n = 20 the success comparison has little power; predictions 1-3 (cost, wrong
  calls, window false positives) are the ones this run can test. Prediction 4 is reported
  but cannot pass or fail convincingly at this size.
