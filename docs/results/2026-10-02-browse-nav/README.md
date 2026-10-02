# Navigating by substitution: what the arithmetic allows before anything is spent

**Development only. Nothing here is a confirmed result.** Every number below comes from
rankings and sessions already paid for and recorded (`fixtures/browse-jev.jsonl`,
`fixtures/browse-jev-confirm.jsonl`, `docs/results/2026-09-30-browse/e2e-mcp-*-sessions.jsonl`)
replayed at no cost, or from prices. Two of these readings are on steps already used once for
the published recalls, so they claim nothing on their own; what they decide is the design of
the live phase, and whether it is worth running at all.

The design handed over (`docs/where-it-pays.md`, section 6, item 12) was: Jev ranks each step's
elements, a small model acts on the top ones, and the large model is called only when the
ranking is unsure. Three of its pieces were checked for free first. **Two of them do not
exist**, and the third is smaller than it looked.

## 1. There is no cut at which the ranking can act on its own

`benchmarks/browse/calib.py` replays both sets and asks: among the steps whose best element
scores at least `c`, how often is that element the one the step needed?

| `p1` cut | development (169 steps) | | confirmation (142 steps, used once) | |
|---|---|---|---|---|
| | coverage | top-1 right [95 %] | coverage | top-1 right [95 %] |
| 0.70 | 72.8 % | 50.4 % [41.7, 59.1] | 74.7 % | 50.0 % [40.7, 59.4] |
| 0.80 | 42.0 % | 63.4 % [51.8, 73.6] | 45.1 % | 57.8 % [45.6, 69.1] |
| 0.85 | 18.9 % | 71.9 % [54.6, 84.4] | 26.1 % | 67.6 % [51.5, 80.4] |
| 0.90 | 7.7 % | 69.2 % [42.4, 87.3] | 9.9 % | 92.9 % [68.5, 98.7] |

The two sets agree everywhere except the last row, where each holds 13 or 14 steps: 69.2 %
against 92.9 % is the warning this project has written down twice (a perfect-looking cell has a
wide interval, and 11/11 is compatible with 27 % error). Read together, the strictest cut worth
a tenth of the steps buys about **70 %**. A navigation loop that clicks on its own at 70 % will
be wrong on a third of the steps it takes alone, and it is the only arm with no model to notice.

## 2. The probability does not say whether the shortlist holds the answer

The design escalated to the large model with the whole page when the ranking was "unsure". That
assumes `p1` tells you when the target is missing from the top 20. It does not:

| `p1` cut | target in top 20, steps **below** the cut | **above** it |
|---|---|---|
| 0.75 | 85.96 % | 91.76 % |
| 0.80 | 87.18 % | 92.19 % |
| 0.85 | **89.52 %** | **89.19 %** |
| 0.90 | 88.28 % | 100 % (14 steps) |

(confirmation set; the development set has the same shape, 78-87 % below against 85-94 % above for the
same cuts.)
At the cut where coverage is reasonable the two are the same number. **`escalate_below=p1` is
not a lever**, and the loop keeps the knob only because it is also how "no decider at all"
escalates, which is a different and honest use of it.

What would be the right question is the one this project has already learnt twice (page triage,
`triage_many`, and `where-it-pays` section 6 item 1): not the score of each candidate but the
**sufficiency of the set** - given the goal and the twenty elements shown, does one of them do
what this step needs? That is one Truth call per step and it is not recorded, so it is the
first thing the live phase has to buy. One Jev call costs 0.000337 USD here (0.006544 USD
over 19.43 calls a step, Phase 1), so asking it once on each of the 311 recorded steps is
about 0.11 USD.

## 3. The margin is a signal, and it is the same signal on both sets

`p1 - p2` predicts top-1 correctness better than `p1`, and - unlike `p1` - the two sets agree:

| margin cut | development: coverage / top-1 right | confirmation: coverage / top-1 right |
|---|---|---|
| 0.10 | 45.0 % / 57.9 % [46.7, 68.4] | 39.4 % / 67.9 % [54.8, 78.6] |
| 0.15 | 31.4 % / 69.8 % [56.5, 80.5] | 28.9 % / 78.1 % [63.3, 88.0] |
| 0.20 | 20.7 % / 77.1 % [61.0, 87.9] | 19.7 % / 82.1 % [64.4, 92.1] |
| 0.30 | 7.7 % / 84.6 % [57.8, 95.7] | 11.3 % / 87.5 % [64.0, 96.5] |

At the same coverage (about a fifth of the steps) the margin gives 77-82 % where `p1` gave
68-72 %. It is the better knob. Whether it is worth having at all is section 4.

## 4. The number that decides the phase: what a turn of the baseline actually costs

344 recorded baseline sessions (Claude Code, `claude-sonnet-5`, Playwright MCP, no hook, 3-12
turns):

    list USD = 0.0532 + 0.0143 x turns          (n = 344)
    cache reads = -37,352 + 44,881 tokens x turn

44,881 tokens read from cache at Sonnet's 0.30 USD/MTok is **0.0135 USD**, which is 94 % of the
0.0143 USD a turn costs. **A turn of a browsing session is, to within a rounding error, the
price of re-reading its own fixed context.** The page is not where the money is; this is the
75 % prefix of `docs/results/2026-09-30-browse/` restated as a price per turn.

Against that, the ranking costs **0.0065 USD a step** (full tournament, pages of 552 elements)
or **0.0014 USD** with a BM25 shortlist of 90, which keeps 66.9 % of targets in the top 20
instead of 81.1 % (Phase 1, `analysis.json`).

So, plainly: **the ranking cannot pay by replacing a turn.** Full, it eats 45 % of the turn it
would have to replace; shortlisted, 10 %, and it gives up 14 points of recall. And Phase 2d's
eighth-of-the-cost is not a per-step saving inside a session: it compared two *stateless*
sessions, one reading the whole page at list price (0.097 USD) and one reading twenty elements
(0.012 USD). A warm session pays for that page once and then at the cache-read rate, which is
reason 1 of avoidance in `where-it-pays` and it applies to us.

**What is left is the price of the model that takes the turn.** The same 44,881 tokens a turn:

| Who takes the navigation turn | cache read / turn | + cheap ranking | against a Sonnet turn |
|---|---|---|---|
| `claude-sonnet-5` (the baseline) | 0.0135 | - | 1.0x |
| `claude-haiku-4-5` | 0.0045 | 0.0059 | **2.4x cheaper** |
| `claude-opus-5` as the main model | 0.0673 | - | 4.7x **dearer** |

That last row is the real prize and it is not about pruning: if the navigation happens in a
small-context Haiku subagent and the main session only receives the answer and its evidence,
the expensive model does not take the fifteen turns at all. The ranking's job in that design is
not to save tokens. It is to make the cheap model **able** to do the job - which is what Phase
2d measured for Sonnet (choosing from the top 20 in page order is as good as from the whole
page) and what nobody has measured for Haiku.

## 5. What the live phase has to be, then, and the control that can kill it

(Sections 6 and 7 are what running it found; read them with this one.)

Arms, on multi-step tasks (10-30 steps) on stable sites, graded by required substrings:

1. **Baseline**: a `claude-sonnet-5` Claude Code session with Playwright MCP (the harness
   already runs this: `benchmarks/browse/e2e_mcp.py`).
2. **Haiku alone**: the same session with `claude-haiku-4-5` and nothing of ours. **This is the
   control that can kill the idea**: if Haiku navigates as well unaided, the ranking adds
   nothing and the phase ends there. It was not in the handed-over design, and it is the first
   thing to run.
3. **Haiku + the ranking**: the same, with the shortlist in front of it.
4. (If 3 beats 2) **Haiku + ranking + the set-sufficiency question**, escalating to Sonnet only
   when the twenty shown do not hold what the step needs.

Two things to measure besides cost, because they are where Haiku can fail in a way the price
list does not show: how often it answers right, and how often a page simply does not fit it (a
Wikipedia snapshot of 860,106 characters is about 215,000 tokens, more than Haiku's window;
measured on 2026-09-30, no model). If the ranking's only real contribution turns out to be
"the page now fits", that is worth saying as plainly as a saving.

Estimated spend of the phase: Jev under 0.20 USD (shortlisted ranking, about 25 steps a task);
the sessions go through the subscription at list price, 7-9 USD a phase, which is not money.

## Files

- `calib.py` (`benchmarks/browse/`): the free replay of sections 1-3. `calib.json`,
  `calib-rows.jsonl` here.
- `src/sanchopanza/navigate.py`: the loop. The browser and the model are **injected**: the
  package has no LLM client and no browser dependency, and does not grow one for this. In the
  live phase the small model is Claude Code's own subagent and the browser is Playwright MCP.
- `tests/test_navigate.py`: 15 tests, no model and no browser.

## 6. The pilot: on tasks a cheap model can already do, there is nothing to add

Two of the six tasks, one run each, both arms, 2026-10-02, Claude Code 2.1.287 throughout
(`nav-pilot.json`). A smoke run: one session per cell, so it settles direction and not size.

| Arm | Success | Median turns | Mean list USD |
|---|---|---|---|
| SONNET (`claude-sonnet-5`) | 2/2 | 18 | 0.4454 |
| HAIKU (`claude-haiku-4-5`) | 2/2 | 18 | 0.1864 |

**Haiku answered both, in the same number of turns, for 2.4 times less, with nothing of ours in
the session.** The tasks are in the regime this phase went looking for (17 and 18 turns, against
the four turns of everything in `2026-09-30-browse`), and the cheap model needed no help in it.
So the honest reading of the pilot is the one that costs us the claim: on tasks like these the
ranking has nothing to add, and the advice is "use the cheap model".

Two things the pilot found that no cost table shows:

- **Haiku navigated A1 by screenshots**: six `browser_take_screenshot` and no
  `browser_snapshot`. Our ranking and our hook read the accessibility snapshot. A model that
  looks at pixels never reaches the lever, whatever the lever is worth. Where a cut or a ranking
  attaches is not a detail of the design; on that task it decided whether it ran at all.
- A session at 17-18 turns costs 0.36-0.53 USD, above the 0.30 the 3-12 turn curve predicts:
  the growth is slightly superlinear, as a history that is re-read should be.

## 7. Why the stateless loop cannot be one Claude Code session per step

Measured, and it changes the shape of the thing: a `claude -p` session on `claude-haiku-4-5`
with **no tools and the prompt "Reply with the number 7 and nothing else"** costs **0.0196 USD**
(26,523 tokens read from cache, 7,865 written, 48 out). That is the floor of a session, before
any page.

A warm turn of a browsing session costs 0.0143 USD (section 4). **So a loop that spends one
isolated session per step pays more per step than the agent turn it is replacing**, on the
cheapest model there is, with an empty prompt. The stateless loop is still the right idea - a
step whose price does not grow with the step number - but it can only be paid for inside one
long-lived cheap context: a subagent of the host harness, whose turns are the small model's and
whose history never enters the main model's. That is item 3 of the handover, and it turns out to
be the only shape of the four that the arithmetic allows.

It also means the per-step costs in `pick.json` are this floor plus a prompt, and are **not**
comparable with Phase 2d's 0.012-0.097 USD a step through our evaluation harness (which is not
installed on this machine). Only the accuracies there are read.

## 8. And the cheap model does not need the ranking to pick well either

The pilot's tasks were easy, so the claim was taken to where picking is hard: the 82 Mind2Web
steps of Phase 2d, real pages of 552 elements with the needed action known. `pick.py`, first 24
of them, development, `claude -p` with no tools, the rankings replayed free:

| Arm | Accuracy [95 %] | Right element shown | List USD / step |
|---|---|---|---|
| HAIKU-FULL (every element) | 54.2 % [35.1, 72.1] | 100 % | 0.0767 |
| HAIKU20 (Jev's top 20, page order) | 50.0 % [31.4, 68.6] | 91.7 % | 0.0174 |
| HAIKU20 - HAIKU-FULL | **-4.2 points [-25.0, +16.7]** | | |
| *Sonnet, Phase 2d, other elicitation* | *FULL 51.2 %, PAGE20 52.4 %* | | |

**Haiku picks as well as Sonnet, from the whole page or from the top twenty, and the ranking
does not make it better.** 24 steps cannot confirm an equality - the interval is 41 points wide -
but there is no sign of the effect the claim needs, and the four numbers sit within three points
of each other. Both models at about 50 % also looks like this benchmark's own ceiling, which
Phase 2c noted: several elements can be right and one is labelled.

So the capability argument of section 4 does not hold where it was supposed to hold. What the
ranking still does, measured here, is make the prompt **4.4 times cheaper** at no accuracy cost
that 24 steps can see, with the right element in view in 91.7 % of them. That is avoidance
again, with the ceiling avoidance has.

## 9. Where this leaves browsing, said plainly

Three claims of the handed-over design were tested against data that already existed or cost
little, and three failed:

1. The ranking cannot act alone (no cut, section 1).
2. The probability cannot say when to escalate (section 2; the margin can, section 3, and the
   loop now uses the margin).
3. The ranking does not make a cheap model able - not on multi-step tasks it can already do
   (section 6), and not on hard pages where it picks as well as the expensive one (section 8).

What stands from the whole line is what `2026-09-30-browse/` already published: the ranking is a
good tool on its own terms (the step's element in its top 20 in 89.4 % of new steps, 0.0065 USD),
and the hook makes a session 17-22 % cheaper where a large snapshot arrives inline. Both are
avoidance, and avoidance is the lever that pays least.

**The number nobody has measured is not ours.** A navigation turn costs what the model taking it
costs: 0.0045 USD on Haiku, 0.0135 on Sonnet, 0.0673 on Opus, for the same 44,881 tokens. A
17-turn task inside the main session therefore costs an Opus user about 1.14 USD and a Haiku
subagent about 0.08. That is 15x, it comes from the price list rather than from any decision of
ours, and the pilot says the cheap model does the task. If that is the finding, it belongs in
`where-it-pays` as a limit on our own claims: **in browsing, choosing who takes the turn beats
anything we do to what they read.**

## 10. Loop waste in a browsing session: an upper bound, and two traps that nobody falls into

The owner's choice after section 9 was to stop optimising the pick and look at the loop: what
breaks a long navigation is not which element you click, it is repeating yourself, losing a
sub-goal and not knowing you are done. `points/loop.py` has existed for weeks with `goal_met`
and `repeats_check`, measured on a single-author bench, and **wired to nothing**.

**First, free: is there any waste to supervise?** `waste.py` reads the transcript of every
recorded browsing session (1,124 of them with a transcript still on disk, 4,536 tool calls) and
counts what a cheap check could have caught:

| | calls | share | sessions with any | worst |
|---|---|---|---|---|
| a read of a page nothing had changed | 450 | 9.9 % | 250/1124 | 8 |
| reading past the first read after the last action | 622 | 13.7 % | 311/1124 | 13 |
| navigating to a URL already asked for | 20 | 0.4 % | 17/1124 | 2 |
| the same action with identical input, twice | 0 | 0 % | 0/1124 | 0 |
| any of the four | | | **346/1124 (31 %)** | |

**That is an upper bound and not waste**: no counter can tell a redundant read from a necessary
second one, and Claude Code saves a large result to a file the agent then has to `Grep` and
`Read`, which is three legitimate reads of one page. The first version of this script also
counted the first read after the last action and reported 28.9 % of all calls as "tail"; that
is reading, and the number was wrong rather than large.

**Second: two traps built to make an agent flounder.** saucedemo ships accounts that misbehave
the same way every run, so a failure is reproducible rather than lucky. Both walked by hand:

- **B1, `problem_user`**: typing into *Last Name* writes into *First Name*. The field cannot be
  filled from the keyboard at all, so the agent either reports the fault or loops on it.
- **B2, `error_user`**: *Remove* on the inventory page silently does nothing (the cart keeps the
  item); on the cart page it works. An agent that trusts the first one reports the totals for
  two items (39.98 / 3.20 / 43.18) rather than one (9.99 / 0.80 / 10.79) - a wrong answer, not
  a wasted turn.

One run of each, both arms, no hooks: **all four succeeded.** Sonnet's own answer to B2 says it
"had to remove it a second time directly from the cart", so it hit the trap, saw it and
recovered. What the traps cost is turns, not answers:

| Task | SONNET | HAIKU |
|---|---|---|
| B1 (impossible field) | ok, 17 turns, 0.2628 USD | ok, **26 turns**, 0.1676 USD |
| B2 (silent no-op) | ok, 21 turns, 0.3250 USD | ok, 20 turns, 0.1266 USD |

So a deterministic trap does not break a model of this class; it makes the cheap one spend nine
extra turns getting out. **That is the only live signal left in this line**, and it is what the
loop guard is now wired to attack (`harness/loop_hook.py`, a `PostToolUse` hook that advises and
never denies). Whether it cuts those turns is the next measurement; the arms are HAIKU and
HAIKU-LOOP on B1 and B2.

## 11. The loop guard, run: it never spoke, and that is the result

Arms HAIKU and HAIKU-LOOP on the two trap tasks, three runs each, 12 sessions, Claude Code
2.1.287 throughout, 1.61 USD of subscription at list price and 0.00238 USD of Jev
(`nav-loop.json`). Every session answered correctly in both arms, 12/12.

| Task | HAIKU turns | HAIKU-LOOP turns | HAIKU USD | HAIKU-LOOP USD |
|---|---|---|---|---|
| B1 | 14, 17, 17 (16.0) | 18, 18, 18 (18.0) | 0.1123 | 0.1206 |
| B2 | 37, 20, 19 (25.3) | 19, 21, 21 (20.3) | 0.1701 | 0.1340 |

**The phase cannot inform on the hook, and saying so is the result.** The guard asked its two
questions 12 to 14 times a session and `goal_met` came back 0.01-0.03 **every single time**,
with `repeats_check` never over 0.35: across all 65 decisions of the five sessions where the hook
ran, **none** was above the 0.70 the advice speaks over. (The sixth HAIKU-LOOP session, B2 run 2,
has no journal: the hook never ran in it at all - see the commit, it is a runner fault - so that
row is an untreated session under a treated label.) A guard that
stays silent is the same treatment as no guard, so the two arms differ only by noise - and the
difference flips sign between the tasks, which is what noise does. The 10 % lower mean cost of
the LOOP arm rests entirely on one 37-turn HAIKU run on B2; drop it and the arms are the same.

What the phase does establish, and it is worth having:

- **The variance is enormous.** The same arm on the same task took 19, 20 and 37 turns. Three
  runs is nowhere near enough for a turn-count comparison here; a future phase needs many more
  runs, or pairing, or a measure less noisy than turns.
- **The hook is cheap and harmless.** 12-14 decisions a session at 0.000037 USD each, 0.00045 to
  0.00051 USD a session, which is 0.35 % of a 0.13 USD session, and it never changed an answer.
- **Why it was silent is a diagnosis, not a tie**, and it had a fix within the hour: `done` held
  the agent's narration, and a small model narrates intent rather than findings. With what the
  page says added, the same question on the last step of four sessions that all ended with the
  answer goes from a mean 0.19 to 0.50, and on the two whose answer was a figure on screen from
  0.04 and 0.05 to **0.83 and 0.58** (`loop-probe.json`, 0.00033 USD of Jev). One of four crosses
  the shipped threshold. That is a development read on four sessions; nothing is confirmed, and
  the threshold has not been moved - this is the sample it was examined on.

The fix ships unmeasured end to end, which is stated here rather than implied. What it needs is
the thing this whole line now lacks, and section 9's conclusion stands: **no task set in which a
Claude model of this class actually fails.** Both traps were solved first time by both models;
all 20 sessions over the pilot, the mining run and this phase answered correctly. Every lever
measures zero where nothing goes wrong.

## 12. The guard again, improved, and measured offline instead of by noise

A live smoke run of the improved guard (B2, one run each arm, `nav-smoke.json`) showed it had
page text in front of it at all 18 decisions and still never spoke. Reading what it was given
found why: anything that was not a snapshot went in whole, cut at 600 characters - a
screenshot's Playwright code and image path, or ten levels of `generic [ref=...]:` from a
`browser_find` before the line with the total. `loop_hook.page_line` now reduces every result to
the lines that say something, and a result with nothing to say is recorded as blind. It also
found that in Playwright MCP 0.0.83 **an action's result carries no page text**: a click saves
its snapshot to a file, and only `browser_snapshot` and `browser_find` return what the page
says.

Rather than another live phase whose arms differ by noise, `loop_replay.py` asks the guard's
question at every step of the 20 recorded sessions whose answer sits on one page, labelled with
no model - is the answer already in what the agent has in front of it? (B1's label is the
field's value, not its "First Name" label, which is on the form before anything is typed.)
383 steps, 0.0148 USD of Jev (`loop-replay.json`):

| | |
|---|---|
| AUC of `goal_met` against "the answer is visible" | **0.999** |
| Early "you already have it" at the shipped 0.70 | **0 of 372** |
| Spoke when the answer was visible | 2 of 11 |
| Mean `goal_met`, visible / not yet | 0.55 / 0.016 |
| Steps with nothing readable (screenshots, actions) | 69 of 383 |

The guard is near perfect and safe; its threshold is strict, and stays where it is (11 positives
is under the 16 this repo requires for an 80 % precision target, and this is the sample it was
examined on). **And it has almost nothing to cut**: after the answer was first visible, agents
made 0, 0, 0, 0, 0, 1, 2, 0 and 0 more calls. They already stop. The error note is no better
placed: 17 of 415 recorded calls failed (4.1 %), and 2 of 22 sessions had a streak of two or
more (`streaks.json`).

## 13. Aggregation over many pages: no failures either, and the cheap model is not cheaper

Five tasks counted or summed over many pages, every answer computed from the sites' HTML by
`truth_hard.py`, one run each on both models (`nav-hard.json`, Claude Code 2.1.287, 1.22 USD of
subscription at list price):

| | right | mean turns | mean list USD |
|---|---|---|---|
| `claude-sonnet-5` | 5/5 | **4.8** | 0.1288 |
| `claude-haiku-4-5` | 5/5 | 11.4 | 0.1148 |

Both models answered all five. What differs is **how**: on the counts Sonnet wrote one
`browser_evaluate` that fetched and parsed every page in a single call (four turns, 0.09 USD for
ten pages of quotes), while Haiku walked the pages with snapshots and clicks (23 turns, 0.20 USD
for the same task). On H1 the expensive model was **2.2x cheaper** than the cheap one, and
across the five Haiku saved 11 %, against the 2.4x of section 6. Where a task is a crawl, the
lever is the strategy - one extraction instead of a walk - and neither a model's price nor a
cut to what it reads reaches it.

Two faults of the grader, found by reading the two "failures" rather than reporting them: it
required the literal `answer: 10` and failed Sonnet's right "ANSWER: There are 10 quotes by
Albert Einstein"; and the runner kept 800 characters of a reply whose ANSWER line comes last.
`grade` now reads the last ANSWER line, numbers as whole numbers, and `--regrade` grades a round
again from each session's whole final answer in its transcript, keeping the first grade beside
the new one. Both fixed before a number was written down.

Across the day, 32 sessions on 9 tasks (A1, A4, B1, B2, H1-H5) - easy, trapped and aggregating - and every one answered
correctly once graded correctly. The blocker of section 9 is now measured three ways.

## 14. The strategy lever: one fixed line halves a crawl, and it is not a decision

Section 13 left one live lever: on H1 Sonnet wrote one `browser_evaluate` that fetched and
parsed every page and Haiku walked them. Before buying a decision that says "this is a crawl,
extract it in one call", the cheaper control was run first: **the same advice as one fixed line
in the system prompt, for every request, with no decider at all**. A gate earns its place only
where the line does harm.

Five new crawls of 20 to 50 pages (`truth_strategy.py`: answers from the sites, each checked by
a second route), Claude Code 2.1.287 throughout, development, three runs on Haiku
(`nav-strategy.json`; Sonnet one run, for reference):

| arm (S1-S5) | right | mean / median list USD | mean turns |
|---|---|---|---|
| `claude-sonnet-5`, unaided (1 run) | 5/5 | 0.232 / 0.094 | 14.2 |
| `claude-haiku-4-5`, unaided | 11/15 | 0.265 / 0.261 | 23.2 |
| Haiku + line v1 | 12/15 | 0.130 / 0.101 | 17.3 |
| Haiku + line v2 | **13/15** | **0.136 / 0.105** | 19.2 |

**The line halves what a long crawl costs the cheap model, and it does not cost answers.** Every
failure was read by hand before being counted; they are of two kinds, and they say what each
strategy risks:

- **Walking fails by arithmetic.** Unaided Haiku's four misses: a tag `live-death-love` counted
  as `love` (twice), a running total that dropped one page (60 for 65), one row in 582 missed (33
  for 34). Counting in code removes exactly this.
- **One call fails in silence.** Line v1 on S5, the infinite-scroll page: **0/3**, against 3/3
  unaided. The code was no worse - both arms wrote scroll loops - but with the line Haiku took
  its single call's answer as final (8 authors of 50), where unaided it saw a short result and
  tried again. "Do it in one call" had switched off the check. And on H1 one call never returned:
  it read Next from the open page rather than the fetched one, looped on page 2, and **Playwright
  MCP never stops an evaluate**; the session hung for 30 minutes until the runner killed it.

Line v2 answers both: the extraction must return how many pages and items it read and whether
more remained, the agent must hold that against the site before answering, and every loop gets a
cap. S5 went from 0/3 to 2/3 and H1 from one hang in three to 3/3 (4, 24 and 6 turns, against 23
unaided). The line is taken up unevenly: on S4 both versions extracted in one call once in three
and walked the other two.

**No harm where it does not apply**: line v1 on two interactive tasks, a cart (A1) and the
silent-failure trap (B2), three runs each: 6/6 right, 13-27 turns, 0.09-0.18 USD, as unaided.

So, plainly, against where this line set out: **the strategy lever is substitution - one call
for twenty turns - but what pulls it is a sentence, not a decision of ours.** With no harm on the
tasks where it does not apply, a gate in front of the line would only add cost. This is
development on the tasks the line was written on; the confirmation is registered in
`prereg-strategy.md` and runs on eight crawls and two interactive tasks it has never seen.

## 15. Why the line was not taken up, and the version that is: v5

Section 14 left the line taken up unevenly: on S4 both versions walked two runs in three. Every
hint session that walked was read to see why, rather than counted (`strategy_lines.py` holds each
version and its reason). In 9 of 13 the agent **had** followed the line: its first extraction
clicked Next or set `location` inside the `browser_evaluate`, which destroys the call
("Execution context was destroyed"), and it then fell back to walking instead of fixing the
code. In the other four the first call errored or read nothing, with the same fallback. The line
was not ignored; the cheap model wrote the one-call extraction the wrong way and gave up on it.

So v3 says how: never click or change location inside the call; `fetch()` each page and parse it
with `DOMParser`, or fetch the data the page loads; if it errors or falls short, fix the code
rather than walking. Its one miss was its own cap - "a cap on every loop" became 10 pages on a site
of 20, and the half was taken for the whole. v4 fixed that in more words and was taken up worse
(3 walks in 12 against v3's 0); **v5 is v3 with only the cap clause changed** ("far above the
site's size; a loop that reaches its cap fell short"). Development, Claude Code 2.1.287:

| S1-S5, 3 runs (Sonnet: 3 on S3/S4, 1 elsewhere) | right | mean list USD | worst session |
|---|---|---|---|
| `claude-haiku-4-5`, unaided | 11/15 | 0.265 | 0.889 |
| Haiku + v2 (in the first confirmation) | 13/15 | 0.136 | 0.374 |
| **Haiku + v5** | **14/15** | **0.066** | 0.118 |
| `claude-sonnet-5`, unaided | 9/9 | 0.222 | 0.522 |
| **Sonnet + v5** | 9/9 | **0.123** | 0.210 |

With H1 added, Haiku + v5 is 17/18 and **no session walked**. The one miss read by hand: it fetched
all 20 pages and its first count was right (65), then "refined" it with a pattern that wanted
cents, lost every round price ($1,399) and answered 44 over 81 laptops of 117 - the account the line
asks for would have caught it, and the agent did not check.

What this says, plainly:

- **One sentence makes the cheap model 3.4 times cheaper than the expensive one unaided**, on
  these crawls, and more often right than either unaided Haiku or v2.
- **The same sentence halves Sonnet** where Sonnet walked (S3, S4: 0.36-0.52 USD a session down to
  0.10-0.21) and changes nothing where it already extracted (S1, S2, S5). It is not a crutch for
  a weak model; it is the strategy, said.
- The page-walking misses are arithmetic and the extraction's misses are parsing; the line moves
  failures from the first kind to the second, and the second is rarer.

Still development, on the tasks v3-v5 were written on. v5 has its own registered confirmation on
eight crawls over mechanisms no line has met (`prereg-strategy2.md`, `nav_confirm2.py`).

## 16. Confirmation 1 (line v2): NOT confirmed

Registered in `prereg-strategy.md` (sealed d5f42ad) before any session; 60 sessions, all on Claude
Code 2.1.287, 8.46 USD of subscription at list price; verdicts computed by the registered
`nav_confirm.verdicts` (`nav-confirm.json`):

| hypothesis | result | holds |
|---|---|---|
| H1 cost: total ratio <= 0.75 **and** cheaper on >= 6 of 8 crawls | ratio **0.546**, cheaper on **5 of 8** | **no** |
| H2 answers: v2 >= unaided - 2, of 24 | v2 **15/24**, unaided **22/24** | **no** |
| H3 no harm on A2, A3 | 6/6 and 6/6, cost ratio 1.06 | yes |

**Line v2 is not confirmed, and the reason is not cost: it lost answers.** Every one of the eleven
misses was read by hand; none is a grader fault (each ANSWER line is a wrong number). The nine of
v2 are one kind - **an extraction whose result was implausible on its face, and believed**:

- C4 (year tabs filled by AJAX), 0/3: it clicked the tabs inside the call and read the table before
  each request returned, so the years shifted by one and the totals mixed.
- C5 (pagination done in the browser): it fetched the "pages", got the same six tablets four times,
  and answered 6 x 4 = 24.
- C7: "60 pages of 22 quotes, 180 tagged humor" on a 10-page site; and 14 for 12.
- C2: "40 books across 3 pages" of a 1,000-book catalogue. C6: 108 of 117 laptops. C1: 22 for 23.

The line asked for exactly the check that would have caught each of these (how much it read,
against what the site shows), and the cheap model did not make it. Unaided Haiku missed twice (one
page read as the whole table, one country dropped). So on mechanisms the line was not written on,
v2 trades answers for cost; development had not shown it, because S1-S5 are plain paginations.

What changed since v2 is the question confirmation 2 answers: v5 forbids clicking or navigating
inside the call and says to fetch the data the page loads, which is C4's and C5's failure exactly
(found in development on S3/S4 before these results were seen, `strategy_lines.py`). Whether that
is enough on new mechanisms, and whether Haiku then checks its account, is `prereg-strategy2.md`.

## 17. Confirmation 2 (line v5): NOT confirmed - answers held, and one hang decided the cost

Registered in `prereg-strategy2.md` (sealed 5e03627) before any session; 60 sessions, Claude Code
2.1.287 throughout, 7.01 USD of subscription at list price; the verdicts are the first
confirmation's registered function over v5's arms (`nav-confirm2.json`):

| hypothesis | result | holds |
|---|---|---|
| H1 cost: total ratio <= 0.75 **and** cheaper on >= 6 of 8 crawls | ratio **1.027**, cheaper on **5 of 8** | **no** |
| H2 answers: v5 >= unaided - 2, of 24 | v5 **20/24** (21 as first graded, see below), unaided **22/24** | yes |
| H3 no harm on A2, B2 | 6/6 and 6/6, cost ratio 0.79 | yes |

**v5 is not confirmed.** What it did fix is what sank v2: on new mechanisms it lost no answers
that matter (20 against 22; v2 had 15 against 22). What it did not fix is the cost, and the
reason is one session. The misses, read by hand:

- **D5 run 3, v5: a hang.** `while (true)` with no cap, a selector that found nothing, and an exit
  condition that needed more than zero items; Playwright MCP never stops an evaluate, so the
  runner killed it at 30 minutes and the registered rule charged it the 1.00 USD session cap.
- D5 run 1, v5: a scroll that stopped at 82 of 117 laptops, believed. D3 run 1, v5: read each
  delayed page before its ten seconds were up, so pages 2-10 held nothing.
- Unaided: `better-life-empathy` counted as `life` (14 for 13), and one session ended on "API
  Error: Output blocked by content filtering policy", which the registered rules count as wrong.
- **A sixth miss, found after this section was first written**: D5 run 2, v5, answered
  `ANSWER: 36` (truth 38, over "121 laptops") and was graded right, because the grader read only
  the ANSWER line for task ids starting H, S or C and the D tasks fell through to a match
  anywhere in the reply. Graded by its ANSWER line, as the C tasks were, v5 is 20/24; no other
  session of the phase changes. H2 holds at its threshold either way (20 >= 22 - 2).

Described, not tested: without that one hang the crawl ratio would be 0.73 and v5 cheaper on 6 of
8, so H1 would have held. That is reported because it is true, not to soften the verdict: a
hang is a real cost of the one-call strategy (a user waits forever), and the rule charging it was
registered for exactly that reason after H1 of development hung.

What the two confirmations say together, plainly:

- **The line is not a free lunch on any crawl.** Where unaided Haiku walks a long pagination it
  is a large saving (development, S1-S5: 0.265 to 0.066 USD); on these sixteen new tasks unaided
  Haiku often extracted on its own already (most D tasks at three navigations or fewer), and the
  line had less to save than its failure modes cost.
- **Its failure modes are of the strategy, not of the wording**: a silent partial result, and a
  loop that never returns. v5 named both (account for what you read; cap every loop) and the
  cheap model still wrote `while (true)` and believed 82 of 117. **Clauses the model must obey
  are the wrong place for a safety property.**
- So the next step is not v6 of the sentence. The hang can be removed by the harness rather than
  asked for: a `PreToolUse` hook that wraps every `browser_evaluate` in a time limit (Claude Code
  hooks can rewrite a tool's input), turning a hang into an error the agent sees and fixes. The
  partial result is where a check belongs, and section 15's offline probe says what it needs: the
  site's own size beside the result.

## 18. A Jev check of the extraction's result: it ranks, and it cannot warn

Section 17 left the partial result as the failure mode that needs judgment: "82 of 117" and
"3 pages" of 50, believed. The candidate is a substitution: the question the agent should have
asked of a tool result it already holds, asked by Jev where the result lands. Offline, on every
recorded session that answered from one extraction (at most three navigations), exploratory and
post hoc (confirmation sessions included, read after their verdicts):

| version (`benchmarks/browse/`) | cases | AUC right vs wrong | at the cut 0.5: wrong caught / right flagged |
|---|---|---|---|
| request, code and result (`extract_replay.py`) | 125 | 0.602 | 10/17 / 70/108 |
| **plus what the site's first page declares** (`extract_replay2.py`) | 155 | **0.727** (0.82 where the site declares a size) | 15/19 / **79/136** |
| no model: the site declares a size and no number in the result equals it | 155 | - | 8/19 / 40/136 |

The second version's filter was committed before its first Jev call (f08a9fe): AUC >= 0.80, half
the wrong caught, at most 10 % of the right flagged. **It does not pass**, and no cut would: at 0.1
it catches 10 of 19 and flags 21 of 136. 0.0074 USD of Jev.

Why, read case by case:

- **The site's size answers a different question from the request's.** "Page 1 of 50" is the
  catalogue; a request over one category reads 8 pages and is right. "25 items" on the hockey
  table is one page's worth. The rule with no model fails on exactly this; Jev sorts much of it
  out, which is where the AUC gain comes from.
- **A third of the right extractions return only the figure** ("42"), with no account of what was
  read. Jev rightly cannot trust them, so its median on right results is 0.43 (wrong: 0.08): it
  ranks, but every cut that catches the wrong ones flags many right ones.
- **The four wrong results it misses are the infinite scroll** (S5), whose first page declares
  nothing.

So the check stays out of the "with sanchopanza" arm of the next confirmation, as the filter
said it would. What would change that is not a better question but a better result: an
extraction that says how much it read, which the line asks for and the cheap model does not
always give.
