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

## Calibration for a "cut losses" lever (60 sessions, no hook)

The pilot suggested a lever: a failing free session spends its whole budget, so a cheap decision
mid-session that says "this is not converging" could replace turns that buy nothing. To place
such a cut it needs sessions that go both ways in the same arm. `free_calib.py` ran, interleaved
so a ceiling stop would cut every set alike: AssistantBench dev, all 25 short-answer tasks, on
Sonnet (cap 1.50 USD) and Haiku (cap 0.60); and ten BrowseComp tasks the pilot had not run, on
Haiku (cap 0.40). Same session as the pilot (the question, the ANSWER instruction, Claude Code's
own tools, no hook), Claude Code 2.1.287 in all 60, phase ceiling 40 USD, **23.14 USD** of
subscription at list price. Each row keeps the session's cost after every API call, rebuilt from
the transcripts (`free_trace.py`; it reproduces the pilot's Sonnet cost to the cent and spreads
the WebSearch/WebFetch reader, which no transcript shows, evenly over the web calls).

| arm, set | right (hand) | right (runner) | mean / median USD | at 90 % of cap | answered | WebSearch | WebFetch | opened browser |
|---|---|---|---|---|---|---|---|---|
| Sonnet, AssistantBench | **6/25** | 9/25 | 0.43 / 0.41 | 0 | 25 | 161 | 134 | 2 |
| Haiku, AssistantBench | **3/25** | 4/25 | 0.33 / 0.35 | 5 | 22 | 274 | 0 | 0 |
| Haiku, BrowseComp | **0/10** | 0/10 | 0.42 / 0.41 | 10 | 0 | 136 | 12 | 0 |

Every AssistantBench reply was read by hand. The runner's substring grade passed four Sonnet
replies and one Haiku reply that name the gold while answering something else ("None", a range of
savings that mentions the ticket price, a different series that lists the gold as unavailable,
four names of which three are wrong, and one that declines to give a figure), and failed one
Sonnet reply that is right but adds a second ticker. `free_cut.py` lists each (`HAND`) and runs
on the hand verdicts. Three wrong replies are plausibly right today (a 2025 film; an executive
team that has changed since the gold was written) and are flagged, not regraded. One Sonnet
session declined to use a figure because it recognised it as coming from "an AI-benchmark
dataset": the gold is on the web. BrowseComp is not printed or read here: all ten Haiku sessions
ran out of budget without an ANSWER line.

### Where a cut would have fired (offline)

`free_cut.py` replays rules on the 60 sessions plus the pilot's five (65 sessions, 9 right, 56
wrong, 27.1 USD spent on the wrong ones), at every API call, and counts what a stop would have
saved on wrong sessions against the right answers it would have thrown away. Jev was asked the
loop guard's own question (`points.loop` `goal_met`, on what the agent said and the result in
front of it, as `loop_hook.established` builds it) at every call with a tool result:
judgements (558 distinct states), 0.025 USD, cached by state hash in `calib-cut-jev.jsonl`.

| rule (pooled, 65 sessions) | wrong sessions cut | USD saved on wrong | right answers lost |
|---|---|---|---|
| spent 60 % of the cap | 26/56 | 5.45 (20 %) | 0/9 |
| spent 70 % of the cap | 24/56 | 3.82 (14 %) | 0/9 |
| spent 50 % of the cap | 30/56 | 7.54 (28 %) | 2/9 |
| 12 WebSearch in a row with nothing else between | 21/56 | 3.17 (12 %) | 0/9 |
| 10 WebSearch in a row | 27/56 | 6.36 (23 %) | 1/9 |
| 60 % of the cap and Jev `goal_met` never above 0.25 | 26/56 | 5.45 (20 %) | 0/9 |
| 12 WebSearch since Jev last judged >= 0.25 | 27/56 | 4.81 (18 %) | 0/9 |
| (not live) 60 % of the cap and the gold has not reached the agent | 19/56 | 4.42 (16 %) | 0/9 |

What it says, plainly:

- **The right sessions are the cheap ones.** All nine finished below 60 % of their cap (median
  0.29 USD); the gold reached the agent within its first two calls in eight of them. So the best
  rule found is not a decision at all: **stop at 60-70 % of the cap**, which saves 14-20 % of what
  the wrong sessions spent and loses no right answer here. That is the same as a lower
  `--max-budget-usd`, and needs no hook. The 60 % edge is fitted on the very sessions it is scored
  on (the costliest right session ended exactly at 0.60 of its cap); 70 % is the honest number.
- **Jev's `goal_met` does not separate right from wrong here.** Its highest judgement in a session
  has a median of 0.04 in both groups, so it almost never crosses a threshold and every Jev rule
  reduces to its counter: "60 % of the cap and Jev never above 0.25" is the 60 % rule, and "12
  searches since Jev last judged >= 0.25" is in effect "12 searches since the start". Sonnet narrates almost nothing between calls (the thinking is not in
  the transcript), so the judge sees little more than the last search result. Not a substitution
  that pays on this data.
- **Searching in circles is real but the counter is model-specific.** Haiku never called WebFetch
  on AssistantBench (274 searches, 0 fetches), so "N searches in a row" fires on Haiku and almost
  never on Sonnet, which reads pages (134 fetches). Below 12 in a row it starts cutting right
  answers.
- **On BrowseComp everything is a loss at these caps**: 0/15 right across both models, every
  session at its cap, and the gold never reached the agent in any of them. A cut there saves
  70-80 % (any rule fires), but only because nothing is ever right; it cannot be told apart from
  AssistantBench mid-session without knowing the set.
- **In 14 wrong AssistantBench sessions the gold name reached the agent and it chose something
  else** (another 4 numeric matches may be coincidence). Those are failures of selection or
  verification, not of search, and no cut recovers them.
- No session opened the browser except two Sonnet AssistantBench sessions.

Not shown: whether a cut that tells the agent to change strategy (rather than stop) would turn a
wrong session right; and anything held out - the 25 AssistantBench tasks with short answers are
all used, so a confirmation of the 70 % stop needs a new task set with mixed outcomes.
