# Browse on free tasks: a calibration pilot (development)

The owner's point (2026-10-03): the lever phases gave the agent a URL, a question shaped for one
mechanism and only the browser; a harness should also be measured the way people use it. So
`benchmarks/browse/free_e2e.py` gives Claude Code only the question and its normal tools
(WebSearch, WebFetch, Playwright MCP, files, subagents; Bash off on this machine), on tasks from
two public sets with checkable answers: AssistantBench (dev) and BrowseComp (test, decrypted to
the local cache only; no answer is written here).

## Pilot: Sonnet, no hook, BrowseComp (5 tasks; AssistantBench not reached)

Claude Code 2.1.287, `claude-sonnet-5`, one run, session cap 1.50 USD, phase ceiling 8 USD:

| | sessions | right | mean list USD | median wall | WebSearch | WebFetch | sessions that opened the browser |
|---|---|---|---|---|---|---|---|
| BrowseComp | 5 | **0** | **1.43** (1.36-1.49) | 353 s | 98 | 19 | **0** |

Read by hand (the final text of each, not the answer): four of the five say in their own words
that they could not verify the answer, and all five stopped within 0.14 USD of the cap. One gave
a confident wrong answer.

What it says, plainly:

- **On free research tasks Claude Code does not open the browser.** It searches and fetches.
  Every browse lever of this line (crawl line, evaluate limit, snapshot pruning) has nothing to
  act on there; their value is where an agent drives a page.
- **A failing free session spends its whole budget, and the agent knows before the end that it
  has not found the answer.** That is a place a cheap decision could pay by substitution: say
  early that the search is not converging, and stop or change strategy, instead of 1.4 USD of
  searching in circles. It needs tasks with mixed outcomes to calibrate on; BrowseComp gave
  Sonnet none at this budget.
- The task order put all of BrowseComp before AssistantBench, so the ceiling stopped the pilot
  before any AssistantBench task: a design slip of the pilot, recorded here because it limits
  what the pilot says.

7.14 USD of subscription at list price. One session called `ScheduleWakeup`; the runner now
denies it, with `CronCreate` and `RemoteTrigger`.
