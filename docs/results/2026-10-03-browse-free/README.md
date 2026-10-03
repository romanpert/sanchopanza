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
558 distinct states, 0.025 USD, cached by state hash in `calib-cut-jev.jsonl`.

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

## Selection: would a "another candidate fits" pushback have fixed a wrong answer? (offline)

The cut analysis left one place where a decision could raise answers instead of cutting spend:
wrong sessions in which the gold reached the agent in a tool result and the agent answered
something else. The bet: a Stop hook, before the final answer is accepted, collects the candidate
answers in the session's tool results, asks Jev which one the evidence supports, and if that is
not the agent's answer pushes back once ("candidate X, seen in <source>, also fits; check it
against every constraint before answering"). That is capability, not saving. `free_select.py`
tests it offline on the same 65 sessions, no Claude session, development, not a confirmation.

**Candidates, mechanically** (no model; `candidates`, tested in `tests/test_free_select.py`):
from all tool results of a session (main agent and subagents, URLs and the WebSearch trailer
removed), spans of the kind of the agent's own ANSWER - figures with their unit, or capitalised
names joined by connectors, colons and spaced dashes - minus the question's own words, ranked by
occurrences weighted by how many question words sit within 150 characters. The top 30 go to Jev,
plus the agent's own answer when it occurs in the results.

| sessions | gold reached the agent | gold in the candidate pool | gold in the top 30 | median pool |
|---|---|---|---|---|
| AssistantBench, right (9) | 8 | 8 | 6 | 110 |
| AssistantBench, wrong, gold reached (18) | 18 | 17 | **15** | 198 |
| AssistantBench, wrong, gold not reached (23) | 0 | 1 | 0 | 72 |
| BrowseComp (15) | 0 | 2 (loose partial matches) | 0 | 256 |

So the extraction is not the bottleneck: of the 14 wrong sessions whose gold is a name, 12 have
it in the top 30. Its blind spots: the agent's answer sets the kind, so a declined answer
("I could not verify...") makes a numeric gold invisible (one session), and a question that lists
its own options (VGT, MGK or VONG) has them filtered out as question words (only the agent's own
pick is scored then).

**Jev, reusing two points as they are** (cached by state hash in `calib-select-jev.jsonl` and
`calib-select-set-jev.jsonl`, numbers only; 1,886 + 64 decisions, **0.075 USD**):

- `claim`: `points.citation` per candidate, the claim "X is the answer to this question: ..."
  against three evidence windows around X; Jev's pick is the highest P(supports).
- `set`: `points.triage.set_questions`, one Choice over all candidates (the candidate as the page
  title, its evidence as the text); the pick is the largest share.

| | Jev's pick is the gold, wrong sessions with gold in top 30 | ... right sessions with gold in top 30 | right sessions where the pick is the agent's (right) answer |
|---|---|---|---|
| claim | 3/15 | 1/6 | 1/9 |
| set | 2/15 | 0/6 | - |

On the wrong sessions the gold's P(supports) has a median of 0.29 and the pick's 0.75: Jev gives
high support to things that are not answers at all. The pushback rule (the session gave an
ANSWER, Jev's pick differs from it, its probability >= t), all 65 sessions; the extra cost is one
call, or five, at each fired session's mean call cost (median 0.039 USD):

| shape, t | fires | on wrong | would fix (upper bound) | on right (risk) | extra USD, 1 / 5 calls |
|---|---|---|---|---|---|
| claim, 0.5 | 44 | 38 | 3 | 6 | 1.97 / 9.85 |
| claim, 0.7 | 34 | 31 | 3 | 3 | 1.54 / 7.71 |
| claim, 0.9 | 15 | 15 | 3 | **0** | 0.65 / 3.26 |
| set, 0.5 | 24 | 19 | 1 | 5 | 0.96 / 4.79 |
| set, 0.7 | 7 | 4 | 0 | 3 | 0.20 / 0.99 |
| set, 0.9 | 2 | 0 | 0 | 2 | 0.05 / 0.26 |

The lower bound of every row is zero fixes: the agent may not switch.

**The 15 fires of `claim` at 0.9, read by hand** (all AssistantBench; none on BrowseComp):

- Three picks are the gold, on two tasks. The martial-arts task (AB6e3be83d), on
  Sonnet and Haiku: the pick is Renzo Gracie Jiu-Jitsu Wall Street; Haiku had answered Equinox
  Wall Street, and Sonnet had seen Renzo Gracie and declined it because it could not confirm the
  five-minute walk, so a pushback asks it to reconsider what it already rejected. AB9baaa267 on
  Haiku: the pick, 31.67 %, comes from a WebSearch summary that repeats the question's own wording
  and states the figure - the gold leaking through the search reader, not evidence. Counted
  honestly, that is **one task, two sessions** that a pushback could plausibly fix.
- Twelve point at something that is not an answer, or a wrong one: names of sites or services
  (Realtor.com, "Visit Zillow.com", "Multiple Listing Service" twice, a USPS service name twice
  for a question that asks for sender and price), a time span ("Monday-Sunday", whose snippet
  happens to name the gold), and wrong answers of the right type (Trader Joe's, Delice, Sentir,
  Simone Nardi, 7 %). Each is a turn spent checking a bad lead.
- None fired on a right session at 0.9. With nine right sessions that bounds the risk loosely:
  0/9 is compatible with a true rate near 30 %.

BrowseComp, as ids and booleans: the ten Haiku sessions gave no ANSWER (all at their cap), so the
rule cannot fire; the five Sonnet pilot sessions fire at 0.5 (BC57, BC10, BC693, BC293, BC1248)
and at 0.7 (the first four), never at 0.9, and none can be a fix since the gold reached none of
them.

What it says, plainly:

- **The selection failure is real and the candidates are there, but Jev does not find the right
  one.** The citation question asks whether a snippet supports "X is the answer"; the AssistantBench
  questions are conjunctions (rated highest on IMDb, under 150 minutes, on Netflix US; within five
  minutes of the NYSE, open 7-9 pm). Whether one candidate meets every constraint is a composed
  judgement, and a typed head reads it as "the snippet is about this": site names and wrong
  answers of the right type score 0.9 and above, and the agent's own right answer scores low
  (picked in 1 of 9 right sessions). The one Choice over all candidates is worse, not better.
- **Not worth a registered live arm as it stands.** The upper bound is three fixes on two tasks,
  one of them a leaked gold; the realistic count is one task. A pushback adds turns, so on its own
  it cannot meet the owner's bar (cheaper and at least as many right); paired with the 70 %
  budget stop (14 % saved on wrong sessions) it might, but not on this evidence.
- **What would have to change first (tried in the second pass below; it does not separate either), offline and on these same sessions** (the extraction and its
  cache are free to re-run): type the candidates (a closed-vocabulary Choice - is X a bar, a film,
  a person, a site - is the kind of judgement a typed head does well), and split the question into
  its constraints so Jev answers one Truth per candidate and constraint, with the AND done in code.
  Only if that picks the gold in most of the 15 sessions where it is in the top 30, and the agent's
  answer in the right ones, is a live arm worth registering.
- **It needs fresh tasks with mixed outcomes**: the 25 AssistantBench dev tasks are burned. As far
  as we know AssistantBench's test answers are not public (leaderboard), so it cannot be graded
  here. GAIA validation (public answers; the text-only, web-reliant level 1-2 tasks) is the
  closest fit, with the same contamination risk seen twice here (a leaked gold in a search
  summary, a figure recognised as "an AI-benchmark dataset"). BrowseComp-Plus (BrowseComp queries
  over a fixed corpus with labelled evidence documents) would make "the gold reached the agent"
  controllable and remove web leaks, at the price of a local retriever instead of Claude Code's own
  WebSearch. Mind2Web-Live grades actions, not a final answer, so it does not fit this lever.

### Second pass: type the candidates, then one judgement per condition (offline)

The two changes the first pass pointed at, on the same 65 sessions and the same pool
(`free_select_typed.py`, tests in `tests/test_free_select_typed.py`):

1. **Type first.** Jev reads the question and names the expected answer type (a closed Choice,
   `points.entities.classification_questions`: person, place, organisation, title, number with
   unit, date, website, other). A question that asks for a figure gets figure candidates, whatever
   the agent answered (this closes the blind spot of the declined answer). Every name candidate is
   typed the same way from its evidence, and code drops it when both types are said at p >= 0.5
   and are incompatible (a venue may also be typed organisation, a platform website).
2. **One judgement per condition.** Each surviving candidate gets one `points.citation`
   judgement per condition ("X is within a five-minute walk of the New York Stock Exchange.",
   against the evidence windows sharing most words with that condition); code takes the product.
   **The AssistantBench conditions are written by hand**, two to four per task
   (`HAND_CONSTRAINTS`): an offline ceiling, not a live mechanism. BrowseComp's come from a
   mechanical clause split, in memory, never written.

Jev: 1,411 type Choices and 2,882 condition judgements, **0.124 USD** (0.199 USD for the whole
selection study), cached in `calib-select-type-jev.jsonl` and `calib-select-constraint-jev.jsonl`.

The type filter is the part that works: it drops 354 of 1,345 AssistantBench candidates and 296
of 450 BrowseComp ones, and keeps the gold in all 25 sessions where the gold is in the set (the
set now counts the agent's own answer, so right sessions are in it). Then the table, all 65
sessions ("gold picked" is over those 25), against two baselines with no model:

| method | t | fires | on wrong | would fix (upper bound) | on right (risk) | gold picked | extra USD, 1 / 5 calls |
|---|---|---|---|---|---|---|---|
| typed, product over conditions | 0.3 | 21 | 19 | 2 | 2 | 7/25 | 0.86 / 4.28 |
| | 0.5 | 13 | 12 | 2 | 1 | 7/25 | 0.52 / 2.58 |
| | 0.7 | 7 | 7 | 1 | 0 | 7/25 | 0.30 / 1.49 |
| | 0.9 | 3 | 3 | 1 | 0 | 7/25 | 0.14 / 0.71 |
| typed, comparisons left out | 0.5 | 22 | 17 | 2 | 5 | 6/25 | 0.84 / 4.17 |
| | 0.9 | 9 | 7 | 1 | 2 | 6/25 | 0.34 / 1.70 |
| baseline: top-ranked candidate | - | 48 | 40 | 1 | 8 | 5/25 | 2.11 / 10.52 |
| baseline: top-ranked after the type filter | - | 46 | 40 | 2 | 6 | **8/25** | 2.05 / 10.26 |
| baseline: most named in the agent's narration | - | 28 | 20 | 0 | 8 | 0/25 | 1.35 / 6.77 |

Read by hand, the 13 fires at 0.5 (all AssistantBench; BrowseComp never fires under the typed
rule): one plausible fix, Fubo's management team on Haiku (it answered four names, three of them
wrong; the pick is the gold alone); one leaked gold (31.67 % in a search summary, as before); one
"risk" that is an artifact (on the right Sonnet session the pick is the agent's own answer, which
`answer_head` failed to cut out of a sentence); and ten wrong leads - 7 % and 0.2 for a snow
percentage, a page heading for the shipping question (its expected type is "other", so nothing is
filtered), Knives Out for Glass Onion, 866 sq ft, 5.2 million USD for an apartment its own snippet
places outside Mission Bay, Casey George, one of the three gold names on its own, Red Bamboo. The
martial-arts gold of the first pass is lost: "has classes between 7 and 9 pm" scores 0.16 and 0.07.

What it says, plainly:

- **It still does not separate.** The typed per-condition shape picks the gold in 7 of 25
  sessions; ranking the type-filtered candidates by occurrences near the question's words picks it
  in 8. Jev's condition judgements add nothing over that baseline; the type Choice is the one Jev
  step that helps (5/25 to 8/25, no gold lost).
- **Why: what Jev cannot see from here.** Per condition, the gold's P(supports) is high on
  membership ("is a film starring Isabelle Adjani" 1.00, "is a bar" 0.99) and low on the rest:
  comparisons across candidates (highest rated among those, lowest rated among those: 0.00-0.18 for
  the gold in 12 of 14 sessions), because one snippet about one candidate cannot settle a comparison; and conditions whose
  fact lives on another page or nowhere (runtime, a catalogue, evening hours, a walking distance),
  because the evidence is the windows around the candidate's mentions, and an unstated fact reads
  as "says nothing". The product then sinks the gold with everything else. Leaving the comparisons
  out does not help: many candidates meet every membership condition (6/25, more risk). And six of
  the 25 tasks ask for a computed figure (a saving, a share of days) that no page states, so there
  is nothing to select.
- **What kind of decision would.** Comparisons and unstated facts need values, not verdicts: per
  candidate and attribute, the value a page gives (the runtime, the rating, the distance, the
  closing hour), from wherever it is stated, and then code applies the thresholds and the
  superlative. That is extraction, which a typed head does not do; it is a generative step (a small
  extractor) or, more simply, asking the agent itself at the Stop hook to list each condition with
  the source that meets it for its answer and for the leading alternative - a composed judgement
  made by the model that holds the evidence, with code only checking that every condition has a
  source. Neither is a substitution for Jev, and neither has been measured here.
- **Still not worth a registered live arm.** Best case at 0.5: one plausible fix and one leaked
  gold in 47 answered sessions, for 13 extra turns.
