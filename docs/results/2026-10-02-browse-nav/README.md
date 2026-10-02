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
