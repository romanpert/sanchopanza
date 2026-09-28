# What it costs and when it pays

Every number in the **Measured** sections comes from the recorded public bench in this
repository and replays with `sanchopanza bench --provider recorded`. Token counts are exact,
from Anthropic's token counter, not chars divided by four. Model prices are Anthropic's
list prices as of 2026-06-24 and are the only inputs that are not measured here.

**Read this first.** Most of what follows is what the layer costs, what it keeps out, and the
arithmetic that says when the second exceeds the first. The end-to-end measurements come at
the bottom, and none of them is a saving figure for keeping pages out of a context: in an
agent loop that saving did not appear, and on a fixed fetch sequence it was paid for in
answers. The end-to-end percentages quoted here belong to wiring: narrowing a tool catalog
once, and the estimated cost of a tool window.

| Model | Input $/MTok | Output $/MTok |
|---|---|---|
| Claude Opus 5 | 5.00 | 25.00 |
| Claude Sonnet 5 | 2.00 | 10.00 |
| Claude Haiku 4.5 | 1.00 | 5.00 |
| Jev 1.13 (the decision model) | 0.042 | free |

## Measured: what the decision layer costs

The public bench is 227 decisions over 154,886 input tokens (the plan's 56 pairwise calls are
counted apart),
and it cost **0.0065 USD**. That is **28.7 millionths of a
dollar per decision**, output included, because this model's output is free.

The same input tokens, priced as input alone and ignoring any output the model would have
had to write:

| Priced as | Cost | Multiple |
|---|---|---|
| claude-opus-5 | 0.7744 USD | 119x |
| claude-sonnet-5 | 0.3098 USD | 48x |
| claude-haiku-4-5 | 0.1549 USD | 24x |
| Jev 1.13 | 0.0065 USD | 1x |

Those multiples are a floor in one direction and a ceiling in another.

They are a floor because a generative model also pays for the tokens it writes: a measured
comparison on 156 of these cases against Claude Haiku 4.5 with tool-forced output came out
at **49x** (0.0048 against 0.2337 USD) with three times the latency (paper, Section 5.6).

They are a ceiling because inside a warm agent loop the tokens being compared are not priced
at the list rate. A cached read costs **0.1x** base input, a five-minute cache write 1.25x
([Anthropic, prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)).
So the honest competitor to this decider, for tokens that are already in a cached prefix, is:

| Priced as a cache read | USD/MTok | Multiple over the decider |
|---|---|---|
| claude-opus-5 | 0.50 | 11.9x |
| claude-sonnet-5 | 0.20 | 4.8x |
| claude-haiku-4-5 | 0.10 | 2.4x |

**Which multiple applies depends on what the decision is for.** If it *replaces* a call the
big model was going to make, that call pays list price for its own output and a cache write
for its own prefix, and the 48x-to-119x column is the right one. If it *keeps tokens out of
a prefix that is already warm*, the 4.8x-to-11.9x column is. Most of the disappointment in
the end-to-end A/B lives in that distinction; `docs/where-it-pays.md` is the argument in
full.

## Measured: what page triage keeps out

On the 16 triage cases, the squire dropped 7.
That is **898 tokens that never entered the context** against
1,517 that did, so 37% of the text was kept out.
Deciding it cost 0.000712 USD.

| Priced as | Value of what was dropped | Times the cost of deciding |
|---|---|---|
| claude-opus-5 | 0.00449 USD | 6.3x |
| claude-sonnet-5 | 0.00180 USD | 2.5x |
| claude-haiku-4-5 | 0.00090 USD | 1.3x |

**Be careful with that table, and do not quote it as a saving.** The bench pages are
excerpts, averaging 151 tokens. At that size the lever barely pays for itself:
2.5x at Sonnet 5 prices, 1.3x at Haiku prices. A real fetched page is one to two orders of
magnitude larger, which is the whole point of the next section.

## The number that travels: break-even page size

One triage decision costs 44.5 millionths of a dollar. At the measured
drop rate of 37%, the expected tokens kept out of a page of T tokens is
0.37 x T. Triage pays for itself when that is worth more than the decision:

| The large model is | A page pays for its own triage above |
|---|---|
| claude-opus-5 | **24 tokens** |
| claude-sonnet-5 | **60 tokens** |
| claude-haiku-4-5 | **120 tokens** |

So on a Sonnet-class orchestrator, any page over about 60 tokens is worth triaging. Below
is what the same arithmetic gives for pages of a realistic size, per page:

| Page | Tokens | Expected tokens kept out | Value at Sonnet 5 | Cost of deciding | Net |
|---|---|---|---|---|---|
| news snippet | 500 | 186 | 0.00037 USD | 0.000044 USD | **8x** |
| full article | 2,000 | 744 | 0.00149 USD | 0.000044 USD | **33x** |
| official PDF | 10,000 | 3,720 | 0.00744 USD | 0.000044 USD | **167x** |

The same shape applies to a job. A round that fetches 40 pages of 2,000 tokens spends
0.0018 USD on triage and keeps about 29,760 tokens out of the context, worth 0.0595 USD at Sonnet 5 input prices. Whether those
tokens would have changed the deliverable is exactly what the end-to-end experiment has to
answer, and it is not answered here.

## Measured: model routing and search routing

On 20 delegation cases the squire chose 7 light, 9 default and 4 deep, and 7 of the light choices carried confidence 0.75 or above,
which is the threshold at which the policy acts. Deciding all twenty cost 0.000527 USD, that is 26.4 millionths per task.

Claude Haiku 4.5 costs half of Claude Sonnet 5 per token, input and output alike. So a
subtask moved down one tier costs half of what it would have. With 35 % of tasks moving
down, routing pays for itself once a subtask is larger than:

| The default tier is | A subtask pays for its own routing above |
|---|---|
| claude-opus-5 | **30 tokens** |
| claude-sonnet-5 | **75 tokens** |

Any real subtask is thousands of tokens, so this lever is effectively free to run. What it
is not is free of risk: the risk is quality, not money, which is why the policy only acts
above 0.75 confidence and never sends a task about an identifiable person to the light tier.

On 18 search cases it sent 11 to a free engine, cut
3 as repeats and left 4 for the paid search,
for 0.000792 USD. The saving there is whatever your search
provider charges per query, which we cannot measure for you.

## End to end: the agent loop, and a fixed fetch sequence

Everything above is arithmetic about tokens. It does not say the deliverable gets cheaper or
better. That question needed its own experiment, and `benchmarks/ab/` is it: the same agent,
the same eight tasks, the same prompts, tools, model, thinking and effort, one arm with page
triage and one without, over a fixed corpus, with each squire run paired against the run of
the same task and repetition without it.

**In the agent loop no cost saving is measurable, in either condition.** Claude Sonnet 5, 64
paired runs:

| Condition | Pairs | Input tokens | Total cost | Wall time | Correct |
|---|---|---|---|---|---|
| Page-sized documents | 40 | -3.3 % [-13.6, +11.2] | -1.3 % [-11.2, +12.6] | **+16.4 %** [+4.2, +30.5] | 38/40 to 39/40 |
| Large documents | 24 | +0.3 % [-6.2, +11.6] | -0.2 % [-6.2, +10.5] | **+11.6 %** [+4.1, +18.9] | 21/24 to 21/24 |

Every cost interval spans zero. Both latency intervals exclude it. Quality held: the squire
lost no answers and gained one in the first condition.

**Why, and it is visible in the runs.** The lever needs the agent to fetch several documents
of which several are useless. It fetched 1.8 per task in the first condition and 1.0 in the
second, and triage dropped 0.45 and 0.17 of them. Making the documents larger did not help,
because in this corpus size and retrieval difficulty are coupled: larger documents means
fewer of them, each holding more, so the first one the agent opens usually has the answer.
Nothing was left for triage to keep out.

**With the fetch sequence held fixed.** An avoidance lever can only act on what the agent
fetches, so both arms have to read the same documents for the lever to be the only difference.
`benchmarks/ab/fixed.py` drives both arms through an identical 20-document sequence per task
and answers from what survives (10 tasks, Claude Sonnet 5, 2.92 USD):

| Lever | Documents dropped | Input tokens | Cost | Correct |
|---|---|---|---|---|
| Page triage | 170/193 | **-75.2 %** [-86.8, -63.9] | -72.8 % | **10/10 to 6/10** |
| Source redundancy | 4/193 | -3.5 % [-12.1, +0.0] | -2.0 % | 9/10 to 9/10 |

Page triage saves three quarters of the input and the saving is the cost of not answering: in
all four failures the answer document was among those dropped, and in none of the six
successes was it. The two halves are one result, and neither is quoted without the other
(`docs/results/2026-09-24-fixed-sequence/`, paper Section 5.15). Judging passages with the
others in view instead (`triage_many`), the same design answered 9/9 against 9/9 at -79.5 %
input tokens, pre-registered, one answering call (`docs/results/2026-09-28-fixed-pages/`).

**What to quote, then.** The cost per decision and the break-even, which are measured. The
safety and quality numbers in the paper, which are measured. Not a saving percentage for
keeping pages out: in the agent loop there was none to measure, and on a fixed sequence it
came at the price of answers.

## The percentages that belong to wiring

The end-to-end percentages this repository quotes are about where a decision acts, not about
page triage. Narrowing a 58-tool catalog to 28 tools **once, before the first request of a
session**, cost 0.07916 USD against 0.13873 for the full catalog over 8 turns on
claude-sonnet-5: **43 % cheaper**, measured, `benchmarks/cache/`.

The same narrowing applied on alternate turns costs 0.15770, which is 14 % *more* than never
narrowing, and applied afresh every turn it costs 0.32864, which is 4.15x the arm that
decided once and reads **zero** tokens from cache across the entire conversation. Tool
definitions are the front of the prompt prefix; rewriting them invalidates the tools, system
and message caches together.

So the percentage belongs to the wiring, not to the model: the same decision, taken at the
right moment, saves 43 %, and taken every turn, costs three times what it saves.

The tool window is the same kind of result, and it is an estimate from recorded usage with the
`tools` + `system` prefix shared between tasks, as a production harness shares it. On a
74-tool AgentDojo catalog, Claude Sonnet 5, 40 tasks: the window cost an estimated 0.77-0.88x
of loading everything and the platform's tool search 1.48x, with no detectable difference in
success. On a real MCP catalog of 398 tools the platform's search was the cheaper, an estimated
0.34x against the window's 0.54x (`docs/results/2026-09-25-e2e/`,
`docs/results/2026-09-25-cache/`, `docs/results/2026-09-25-wide/`).

**Why triage reads more than the head of a long document.** Judged on its first 1,500
characters, a 10,000-character document whose preamble does not address the purpose is
dropped even when it holds the answer; in the agent loop the agent then re-fetches it, hits
its turn cap and returns nothing at twice the cost. `sanchopanza.text.excerpt` sends the head
plus the window that best matches the purpose. Documents that already fit are unchanged, so
no decision-level number depends on it. A defect of this kind lives in the wiring, not in the
decision, and only an end-to-end run shows it.
