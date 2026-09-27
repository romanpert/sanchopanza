# The tool window against a real MCP catalog: the platform's search wins here

Run of 2026-09-25, evening. Pre-registered in `PREREGISTRATION.md` (with an addendum written
before the first paid request). `claude-sonnet-5`, effort `medium`, AgentDojo v1.2.2 tasks,
catalog = AgentDojo's 69 tools + 329 real MCP tools from 10 public servers (`catalog.json`,
frozen by rule from `benchmarks/mcp_wide/catalog.json`), **398 tools, 167,937 tokens** of
definitions against 12,214 for AgentDojo alone. `tests/test_wide_catalog.py` recomputes every
count below from the rows in this directory.

## Two concurrent runs, one directory

This directory holds **two independent runs** of the same task order, made by two processes
that ran concurrently, both appending to `runs-5.jsonl`, each under its own spend cap. The
second process adds a field, calls to distractor tools, which is how the rows are told apart:

- **Run A**: rows **without** `wrong_calls`, plus `runs-5-first-four.jsonl` (its first four
  rows, kept in their own file).
- **Run B**: rows **with** `wrong_calls`.

Both stopped at their caps with only **travel and workspace** complete; one banking row
(`search`, run B) and no slack row. Four rows are rate-limit errors (429), a product of two
processes sending 168k-token requests at once; they are excluded. **Measured spend: 9.28 USD**
summed over the rows (the errored and stopped requests are not in it), against ~6 USD
estimated in the pre-registration.

**Cost is given two ways.** The tables below are as run. These runs did not share the
`tools` + `system` cache prefix between tasks, so every `full` and `search` task paid its
catalog as a cache write; a production harness with a fixed catalog shares it
(`../2026-09-25-cache/`). Re-priced from all rows of `runs-5.jsonl` with the prefix shared -
an estimate from recorded usage - `full` is 2.731 USD, `search` 0.938 and `sancho` 1.463:
**search 0.34x, sancho 0.54x** `full`. That is the comparable figure; the ordering is the same
as run.

## Result

Paired on the tasks where all three arms finished.

| run A, 9 tasks | success | USD as run | x `full`, as run | median s | mean turns |
|---|---|---|---|---|---|
| full | 7/9 | 4.581 | 1.00 | 43.6 | 3.22 |
| **search** (BM25, all deferred) | **8/9** | **0.575** | **0.13** | **14.1** | 4.11 |
| sancho (window) | 8/9 | 1.624 | 0.35 | 28.9 | 3.67 |

| run B, 5 tasks | success | USD as run | x `full`, as run | calls to a distractor |
|---|---|---|---|---|
| full | 4/5 | 0.714 | 1.00 | 0 |
| search | 4/5 | 0.207 | 0.29 | 0 |
| sancho | 4/5 | 0.165 | 0.23 | 0 |

Every row of both runs, not only the paired ones: `full` 16/19, `search` 17/19, `sancho` 15/17.

## Against the predictions

1. **Cost, sancho <= 0.35x `full` as run: met, barely** (0.35 in A, 0.23 in B; with the prefix
   shared, an estimated 0.54x over all rows). Either way the platform's search is cheaper
   still: **0.13x in A** as run, 0.34x shared.
2. **`full` makes wrong calls in >= 3 tasks: refuted.** Zero calls to a distractor in any arm
   of run B (n = 5; run A did not record them). With the near-duplicates in hand, the model
   called the task's own tools every time.
3. **MCP groups opened per task <= 2: met** (1.56 in A, 1.2 in B). But which group matters
   more than how many: the window opened `google_workspace` in **11 of 17** sancho tasks. It is
   the real near-duplicate of AgentDojo's workspace suite (Gmail, Calendar, Drive), 121 tools,
   about 50k tokens, and on Sonnet 5 an opened group is sent loaded.
4. **Success:** no detectable difference at this n.

**What would embarrass the window**, as written before the run: "`search` matching `sancho` on
success at lower cost". **That happened** (run A: 8/9 each, 0.13x against 0.35x as run, 0.34x
against 0.54x with the prefix shared, and faster).

## Reading

- **The window's cost is set by its coarsest group.** Grouping by MCP server made one
  server-sized group carry a quarter of the catalog, and the question "is this group needed?"
  is correctly answered yes for it on workspace tasks - Gmail really is relevant to "read my
  email". The per-group judgment was right; the unit of loading was wrong.
- **The platform's search loads by tool, not by group**, so its cost did not depend on
  server size. At this catalog shape, on a model without `tool_addition`, it is the better
  default.
- **The near-duplicates did not confuse the model** (0 wrong calls, n = 5). The feared
  failure of loading everything is cost, not accuracy, at least on these tasks.

## Claude Code (the same question inside a real harness)

`claude -p` headless, Sonnet 5, isolated (`--setting-sources project --strict-mcp-config`),
billed to a subscription, not the API key. Claude Code already defers MCP tools behind its own
`ToolSearch` and shows the model their names. The sanchopanza arm is a `UserPromptSubmit`
hook that opens a `ToolWindow` on the prompt and names what to load. Scripts are not in the
repo (they read a local key file); the rows are.

| setting | tasks | right tool/server, base / hook | ToolSearch calls | USD base / hook |
|---|---|---|---|---|
| built-in deferred tools (`claude-code-builtin.jsonl`) | 4 | 4/4 / 4/4 | 4 / 4 | 0.703 / 0.691 |
| 10 MCP servers, 329 tools (`claude-code-mcp.jsonl`) | 8 | 7/8 / 7/8 | 7 / 8 | 1.709 / 1.617 |

Null both times. The model selects exact names in one search without help. The one hook
failure (Jira) followed the hook's own server-scoped search hint (`+atlassian ...`) where the
base arm selected the exact name; the one base failure (PayPal) made no tool call at all.

## What changes, and what does not

- **No default changes.** Nothing here supports shipping the window as the default for large
  catalogs on Sonnet 5; the pre-registered criterion says the platform's search is preferred
  when it matches on success at lower cost, and it did.
- **The next design question is the unit, not the classifier:** split large servers into
  sub-groups (a server's own tool categories), or keep a window of groups but hand large
  groups to the platform's search instead of loading them. Measured neither.
- **On Opus 5** the window is delivered with `tool_addition` and never loads a group up front;
  this run says nothing about it.
- **Claude Code and Codex already have their own deferred search** (Codex CLI defers MCP tools
  behind a local BM25 search with a fixed tools array). A hook adds nothing measurable on top
  at this scale.
