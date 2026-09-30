# Browse, Phase 3d: the twice-fixed hook, on six tasks it was never fixed on

Written 2026-09-30 before any Phase 3d session ran. Runner: `benchmarks/browse/e2e_mcp.py --new`.

## Why

Phase 3c (`prereg-e2e-mcp-fixed.md`) made the hook 8.5 % cheaper with Playwright MCP, -0.0116 USD
a session [-0.0466, +0.0154], with no answer lost, and failed the rule only because the interval
crossed zero. Its transcripts showed two more faults, fixed in commit 0e8f5fd with tests: the hook
cut what the agent had narrowed itself (a `Read` with `limit`, a snapshot with `target`), and its
note sent the agent to read the whole archive where a `Grep` would do. Both fixes were designed on
Phase 3b and 3c's six tasks, so this phase uses **six new tasks**. The size threshold (6,000
characters) is not changed, though Phase 3c hinted at it: that would be fitting the six tasks.

## Tasks

New neutral public pages, answers checked by hand on 2026-09-30, graded by required substrings
(an item that is a list is met by any alternative):

| id | start | question | required |
|---|---|---|---|
| N1 | github.com/pallets/flask | its license and largest language | bsd; python |
| N2 | en.wikipedia.org/wiki/Eiffel_Tower | height to the tip in the infobox, metres | 330 |
| N3 | docs.python.org/3/library/json.html | default of json.dumps()'s indent | none |
| N4 | quotes.toscrape.com | author of the first quote | einstein |
| N5 | books.toscrape.com, Poetry category | title of the first book listed | a light in the attic |
| N6 | en.wikipedia.org/wiki/Guido_van_Rossum | year and city of birth, from the infobox | 1956; hague |

## Design and rule

Phase 3b and 3c's, unchanged: Playwright MCP 0.0.83, `Read`/`Grep`/`Glob`, no `WebFetch`,
`WebSearch` or `Bash`, the same system addition, four runs per task and arm (48 sessions), PLAIN
before LEAN in each run, `--max-budget-usd 1.50`, the hook's defaults and
`SANCHOPANZA_SESSION_MAX_USD=0.20`. The hook is recommended for Playwright MCP if LEAN succeeds on
at least as many runs as PLAIN minus one and its mean cost per session (list USD plus Jev USD) is
lower with the bootstrap interval of the per-task difference (5,000 resamples over tasks, seed
2033) below zero.

## Money

At most 20.00 USD at list price through the subscription (3b and 3c spent about 6 each) and 2.00
USD of Jev (3c spent 0.09); the runner stops before either could be passed.

## What would make this wrong

Six tasks, an interval over six task means, and pages that change. A saving that shows only on
pages whose snapshots are large will be diluted by tasks where the hook has nothing to cut; it is
reported by task either way.
