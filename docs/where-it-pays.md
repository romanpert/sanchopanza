# Where a decision layer pays, where it does not, and how to tell before you build it

`docs/savings.md` answers "what does one decision cost". This document answers the harder
question: **which decisions are worth taking at all**, and how to tell a saving from the cost
of not delivering.

The short version, and everything below is the argument for it:

> A cheap calibrated decision pays reliably when it **replaces a call to a bigger model that
> was going to happen anyway**. It pays unreliably when it tries to **keep tokens out of a
> big model's context**, because that saving depends on the shape of the workload, is
> mostly cache-priced, and is easily bought with lost answers. It pays in a third way that is
> not a saving at all: it makes quality checks cheap enough to run always instead of never.
> And it can **cost** money, badly, if it is wired to a point where acting mutates a cached
> prefix.

Every figure marked **[M]** is measured in this repository and reproducible from it.
**[P]** is a primary published source with a URL. **[D]** is derived arithmetic from those.
Where a cost is re-priced from recorded usage rather than run, the text says so and calls it
an estimate.

---

## 1. The three economies, and the anti-economy

### Substitution: the decision replaces an LLM call

Somewhere in the pipeline a model is already being asked a yes/no or a pick-one: is this
citation supported, are these two mentions the same company, does this chunk contain an
entity, is this comment worth showing, does this fact contradict the stored one. The answer
is consumed by code, and nothing about it has to be written as prose.

The saving is a price ratio, it is bounded below by that ratio, and it does not depend on
the workload's shape. This is the only economy where the arithmetic is safe.

| Replacing | Price of the thing replaced | Ratio to 29 millionths a decision |
|---|---|---|
| **Claude Opus 5, the same 211 judgments, measured both ways** | **0.7884 against 0.0060 USD [M]** | **131x, and 10.9x faster, for 2 decisions of accuracy** |
| Claude Opus 5, input only | 5.00 USD/MTok **[P]** | 119x **[D]** |
| Claude Sonnet 5, input only | 2.00 USD/MTok **[P]** | 48x **[D]** |
| Claude Haiku 4.5, tool-forced, same 156 cases | 0.2337 against 0.0048 USD **[M]** | **49x, and 3x faster** |
| Bedrock Guardrails content filter, ~0.60 USD/MTok | 0.15 USD per 1k text units **[P]** | 14x **[D]** |
| Azure AI evaluations meter / Vertex legacy model-based metrics | 20 USD/MTok in + 60 out **[P]** | **~1,450x per 1,000 judgments** **[D]** |

**The first row is the one to quote.** Every other row compares a measured price against a
published one. That row is the same 211 judgments answered twice, independently: once by the
evaluator and once by a frontier generative model given the same questions, the same criteria
and the same state, neither of them having seen the labels. It came out of building the second
annotator for the bench, so the generative arm was not constructed to lose.

| | Evaluator, shipped policy | Evaluator, plain 0.5 cut | Claude Opus 5 |
|---|---|---|---|
| Agreement with the labels | 200/211 = 95 % | 202/211 = 96 % | 204/211 = 97 % |
| Cost per judgment | 28.4 millionths | same | 3,719 millionths |
| Median latency | 250 ms | same | 2,731 ms |

**It is not a tie, and saying so is the point.** The frontier model is the better judge. But
two of the four decisions between them are the model and two are our own thresholds,
so the honest claim is: *a small amount of accuracy, bought back at 131x the price and 10.9x
the latency.* Whether that trade is worth taking is a property of the decision, not of the
models - clearly yes for a gate in front of a generative pass, clearly no for a judgment that
is itself the deliverable. Reproduce with `benchmarks/substitution.py`; full account under
the shipped policy in `docs/results/2026-09-27-memory-write-cut/fifty/substitution.md`.

The Haiku row holds the comparison against the cheapest generative option: a small model
forced into a tool call, on the same 156 cases, is 49x the price and about 3x the latency
(827 ms median against 266 ms), and it over-rates task complexity systematically, 13 of 20
one level too high **[M]**.

Two things push the Opus ratio *towards* the generative model rather than away: it was run at
`low` effort answering in a single word, about the cheapest a frontier model can be asked to
do this; and neither side caches, because a per-decision prompt of a few hundred tokens is
below the minimum cacheable prefix. That second fact is worth keeping: the prompt cache, which
dominates the economics of a long agent conversation, does nothing at all at the granularity
of one decision.

The Azure row is not a typo either, and it is the most under-appreciated number in this
document. At 1,500 input and 200 output tokens per judgment, a hosted evaluation meter bills
about 42 USD per thousand judgments; the same thousand judgments here cost 0.029 USD. The
judge model is not where the money goes. The meter is.

### Avoidance: the decision keeps tokens out of the big model

Page triage, redundancy, context pruning, a window over the tool catalog. The saving is
`dropped tokens x price`, and there are four reasons it disappoints:

1. **It is priced at the cache-read rate, not the list rate.** A page that enters the context
   is paid once at full price and then, on every later turn, at 0.1x **[P]**. So the honest
   competitor to a 0.042 USD/MTok decider inside a warm loop is 0.20 USD/MTok on Sonnet 5 and
   0.50 on Opus 5: the multiple is 4.8x and 11.9x **[D]**, not 48x and 119x.
2. **Fewer input tokens is not proportionally fewer dollars.** AgentDiet cut input tokens by
   39.9-59.7 % and total cost by only 21.1-35.9 % at equal performance **[P]**. That gap is
   the honest ceiling for any context-pruning classifier.
3. **It needs the workload to be fetch-heavy and the fetches to be mostly useless.** In a
   free agent loop over our corpus the agent fetched 1.8 documents per task, and there was
   nothing to avoid **[M]**.
4. **What it drops can be the answer.** Held to a fixed 20-document sequence, where there is
   plenty to drop, page triage cut input tokens by **75.2 % [-86.8 %, -63.9 %]** and took
   correctness from **10/10 to 6/10**, and in every failure the answer document was among
   those dropped **[M]**. That is one result, not a saving with a footnote (section 3).
   Asked instead of each passage, with the others in view, whether it holds a fact the
   answer needs (`triage_many`), the same design answered 9/9 against 9/9 at **-79.5 %**
   input tokens [-86.5 %, -72.9 %], pre-registered, the tenth task stopped by the cost
   cap **[M]** (`docs/results/2026-09-28-fixed-pages/`). That is one answering call:
   reason 1 still applies in a loop.

### Affordability: the decision makes a quality check cheap enough to always run

This one is not a saving, and it is the one that survives every null result on avoidance.
Some checks are not skipped because they are hard; they are skipped because running them on
everything is unaffordable. Verify every extracted triple. Verify every citation. Resolve
every candidate entity pair after blocking. Test every retrieved chunk for relevance rather
than trusting the top-k.

LazyGraphRAG makes the point by construction: its relevance-test budget is the single
parameter that controls the whole cost/quality curve, evaluated at 100, 500 and 1,500 binary
judgments **per query** **[P]**. At 29 millionths a judgment, 1,500 of them cost 0.043 USD.
The lever stops being "how do we afford more checks" and becomes "how many do we want".

The output here is not a smaller bill. It is a check that used to be sampled and can now be
exhaustive. Report it as quality, not as savings, or you are lying with a true number.

### The anti-economy: acting where acting invalidates a cache

The prefix hierarchy is `tools -> system -> messages`, and a change at any level invalidates
that level and everything after it **[P]**. So a decision that rewrites the tool array, edits
the system prompt or rewrites history does not merely fail to save: it converts every cached
read in the rest of that turn into a fresh write at 1.25x.

We measured it (`benchmarks/cache/`, 8 turns, claude-sonnet-5, 4 isolated arms) **[M]**:

| Arm | Cached reads | Cache writes | Cost | vs deciding once |
|---|---|---|---|---|
| full catalog, fixed | 201,957 | 28,851 | 0.13873 USD | 1.75x |
| narrowed once, then fixed | 98,567 | 14,081 | **0.07916 USD** | 1.00x |
| narrowed, alternating two stable subsets | 129,312 | 43,104 | 0.15770 USD | 1.99x |
| a different subset every turn | **0** | 117,148 | 0.32864 USD | **4.15x** |

Narrowing the catalog **once** is worth 43 %. Narrowing it on alternate turns costs 14 %
*more* than never narrowing. Narrowing it differently every turn reads **nothing** from cache
across eight turns and costs 4.15x the arm that took the same decision once. Same decision,
same tools, different moment, opposite sign.

**The corresponding good news comes from a real job rather than a benchmark.** The same
investigation was run twice in the deploying harness, identical in brief, profile and model,
differing only in whether the layer was attached. With the layer on, **90.8 %** of input
tokens came from cache; with it off, **89.5 %** **[M]**. Deciding through hooks that rewrite
a tool's *input* or deny the call never touches `tools`, `system` or the history, so the
prefix survives - which is what the invariant says, measured. The layer cost 0.0007 USD on a
0.86 USD job, **0.08 %**.

What that run does **not** show: the decider returned the default route on all 13 of its
decisions, so this is "harmless to the cache", not "harmless under load". And the same job
run twice with the layer off *both* times differed by 18 % in cost, a variance floor wider
than any effect one pair could resolve, so the cost comparison from it is null and only the
cache result is claimed.

---

## 2. The rule that generalises all of it: *when* beats *how good*

The clearest evidence for this is not ours. Meta deployed Infer in batch, assigning 20-30
issues to developers: the fix rate was near zero. They switched the same analysis, with the
same false-positive rate, to run at diff time: the fix rate went **over 70 %** **[P]**.

> "The same program analysis, with same false positive rate, had much greater impact when
> deployed at diff time." - Distefano, Fahndrich, Logozzo, O'Hearn, CACM 62(8), 2019.

A decision layer is subject to the same law, in both directions. Our cache result is the cost
side of it: the same selection is worth -43 % or +315 % depending on which turn it lands on.
Meta's is the value side: the same finding is worth nothing or everything depending on when
it is shown. **Choose the attachment point before you tune the model.**

Four corollaries the package follows:

- **Decide where there is no prefix to invalidate.** Before the first request of a session; on
  content that is about to be appended (a fetched page, a subagent's prompt); inside a tool
  the agent called anyway. Never by rewriting `tools`, `system` or history mid-session. The
  tool window obeys this by appending groups and never swapping them out.
- **Routing a subagent is cache-safe; routing the main loop is not.** A subagent does not read
  the parent's cache in any case, so choosing its model costs nothing extra; switching the
  model of a running conversation re-reads the whole thing uncached **[P]**.
- **Ask about what the request names, and widen when an unnamed need appears.** Selecting
  tool groups once from the request keeps every needed group on 91 of 97 AgentDojo tasks, and
  BM25 at the same budget on 38 **[M]**. Every miss is a group the request does **not** name: a
  clock behind "next", a channel list behind "the channel starting with External", a web
  fetch behind a link inside a message. Parts and groups themselves cost nothing: varying them
  apart on requests of one to three parts and one to three groups, the selector kept **300 of
  300** needed groups whenever each part names its domain **[M]**. Multi-group tasks miss more
  because they carry more unnamed needs, not because they are composite. So a pointwise gate
  per group is the right procedure for tool selection, and the fix for its misses is to widen
  when the unnamed need becomes visible - which is what the tool window does.
- **A purpose with parts may still defeat a pointwise gate on pages.** Page triage over a
  fixed 20-document sequence lost **4 of 4** and **3 of 3** answer documents on its two
  compound tasks, and every one of its four failures dropped the answer while none of its six
  successes did **[M]**. The reading that a per-item relevance question cannot express a
  covering constraint - every page individually insufficient while the set is jointly
  required - does not hold for tools, and it **may hold for pages**: "does this page satisfy
  the purpose?" can fail on a composite purpose in a way that "would the agent call this
  group?" does not. It is unmeasured. The experiment that settles it varies the parts of the
  purpose while holding the required documents fixed. Either way the fix is not a threshold:
  in both points the model answers the question it is asked.
- **Predict behaviour, not truth, when you have the choice.** Atlassian ran both filters over
  the same pipeline: an encoder classifier predicting *will an engineer act on this* added
  20 points of human alignment, and an LLM-as-judge predicting *is this claim correct* had
  "minimal impact" **[P]**. Meta's result explains why.

---

## 3. What the measurements taught

Negative results first, because they are the ones that change what you build.

**An avoidance lever needs the fetch sequence out of the agent's hands to be measured at
all.** In a free agent loop, page triage was null: 64 paired runs, two retrieval conditions,
two document sizes, every cost interval spanning zero, both latency intervals excluding it,
quality unmoved **[M]**, `docs/savings.md`. The agent fetched 1.8 documents per task and
triage dropped 0.45 of them. Larger documents did not change that: in that corpus size and
retrieval difficulty are coupled, so bigger documents means fewer of them and the first one
opened usually holds the answer **[M]**.

Scattering the answers across sources does not fix the design either, because **an avoidance
lever can only act on what the agent fetches, and the run that fetches many redundant sources
is the run that was already going badly.** The lever's opportunity is correlated with the arm
having a bad draw, so pairing on (task, repetition) does not isolate it. A pilot with the
redundancy point on shows the size of that effect: the point dropped **nothing** - six calls,
all `adds_nothing` at 0.03 to 0.16, correctly, since every document carried a pin the agent
still needed - so both arms handed the model the same bytes, and the paired total-cost
difference still came out at -47.8 % [-58.9 %, -1.0 %] **[M]**. One task had identical
fetches and an effect of exactly zero; the whole difference was the other task, where the bare
arm wandered through eight documents and nine turns against four and five. That interval
measures the agent's search-path variance. Two rules follow and are in the harness: a run
reports the drops of every lever separately, and a run in which the lever drops nothing says
in its summary that it is uninformative.

**With the sequence fixed, page triage is large and costs answers, as one result.** Both arms
walk the identical 20 documents per task and one call answers from the survivors
(`docs/results/2026-09-24-fixed-sequence/`, 2.92 USD). Triage drops 170 of 193 documents:
input tokens **-75.2 % [-86.8 %, -63.9 %]**, cost -72.8 % [-84.1 %, -61.6 %], correctness
**10/10 -> 6/10** **[M]**. The attribution is case by case: the answer document was among the
dropped in all four failures and in none of the six successes. The prediction written before
the run - a real effect on tokens, a smaller one on cost, quality holding - is right on the
first two and wrong on the third, and the third is the one that matters. A 73 % cost reduction
that loses four answers in ten is the cost of not answering. Source redundancy on the same
design drops **4 of 193** documents, -3.5 % input tokens [-12.1 %, +0.0 %], quality untouched:
it does not fire even on a corpus built to make it fire.

**Asked the right question, the same lever keeps the answers.** Rerun on the same design
with `triage_many` over passages of at most 900 characters, the others in view, at the
shipped cuts, both arms rerun through our own evaluation harness on a pinned corpus: **9/9**
correct in both arms, input tokens **-79.5 % [-86.5 %, -72.9 %]**, 81 of 173 documents
withheld whole and 2,042 passages cut from the rest, and no passage holding an answer pin
withheld in any of the ten tasks, the two compound ones included **[M]**. Pre-registered at
>= 9 of 10 and >= 50 % fewer tokens; the tenth task was stopped by the 3 USD cap, and it
cannot overturn either bar (`docs/results/2026-09-28-fixed-pages/`). Both failure shapes of
the first run, a compound purpose and a long document judged by its head, are addressed by
the question and the unit, not by a threshold.

**End-to-end runs see what decision-level benches cannot: document length.** A 10,000-character
document judged on its first 1,500 characters loses the page that holds the answer, and the
agent re-fetches it until it hits its turn cap. `sanchopanza.text.excerpt` therefore sends the
head plus the window that matches the purpose; documents that already fit are unchanged, so no
bench number moves **[M]**.

**A cost benchmark must isolate its arms' caches from each other and share the prefix that
production would share.** Both mistakes favour whichever arm varies its prefix. Arms that share
one catalog read caches earlier arms wrote, and the naive per-turn wiring comes out cheapest;
the cache benchmark therefore carries a per-arm tag in every tool description and a `churn`
arm, because the risk is not narrowing but *instability* (`benchmarks/cache/results/summary.md`)
**[M]**. In the other direction, a harness that caches only at the last message never lets one
task read the `tools` + `system` prefix another task wrote: on a 74-tool catalog, a second task
with a different first message writes 12,296 tokens and reads none without a breakpoint on
`system`, and writes 86 and reads 12,211 with one **[M]**. Without it, every arm with a fixed
catalog pays that catalog as a write on every task, while an arm whose prefix depends on the
request barely notices. The end-to-end harness puts a breakpoint on `system` for every arm and
pre-warms the shared prefixes before launching tasks in parallel
(`docs/results/2026-09-25-cache/`). **If a result favours you, find whose cache it inherited.**

**Check whether your two signals are one signal.** For a Truth answer from this model class,
`confidence` is exactly `|2p - 1|` - verified on 651 recorded answers across three independent
runs, with zero deviation **[M]**. Probability and confidence are the same number. So a policy
asking for both `p >= 0.70` and `confidence >= 0.60` is asking for `p >= 0.80`: a
`memory_write` configured at 0.70 with both gates enforces 0.80 and rejects facts that score
0.75 and 0.76. **Two gates on one number is one gate at the stricter value.** The shipped
policy puts one gate on each Truth point, and on the 124 cases of the new points the six binary
points score **82 of 88** under it against 85 of 88 at a plain 0.5 cut, with **AUC 1.00 on all
six** and every policy error a refusal to act **[M]**. A confidence gate earns its place where
it is the only gate and the point wants an abstention band - the citation verdict, the entity
band, the edge check - and nowhere else.

The same holds for a Choice, rescaled: across 11,595 recorded Choice answers,
`confidence = (p_top - 1/k) / (1 - 1/k)` to within 0.022, the rounding of the reported
probabilities **[M]** (`docs/results/2026-09-27-edge-facts/`). So a confidence gate on a
Choice is a cut on the top probability that depends on the number of options, and it is one
cut for every option: `relate_facts` needs the same confidence to say `unrelated`, which
triggers nothing, as to say `conflict`. Accepting `unrelated` at a plain majority gains right
answers on each of six recordings and never adds a costly error; it is one set of cases, read
before the rule was written, so a candidate and not a result, and nothing in code changed.

**Score a bench at the threshold the policy applies.** A bench scored at a cut the policy
never applies reports a policy that does not exist. `check_loop` acts only from 0.70: under
that, `goal_met` scores 12/14 on the first batch and 46/50 on both, `repeats_check` 12/12 and
50/50, with zero false alarms; scored at a 0.5 cut, the same recordings put `goal_met` at 14/14
and 49/50 (`docs/results/2026-09-25-pending/`) **[M]**. The recall at 0.70 is the fragile
figure - seven true `goal_met` cases sit within 0.09 of the cut - and the precision is the
robust one: no false case is near it. Benches are scored with the thresholds the shipped
policy applies, and `tests/test_policy_in_force.py` holds them to it.

**Check whether one threshold is serving two questions.** `memory_collision` looks like a
4-way classification and is not one. The model answers two independent Truth questions,
`contradicts` and `adds_nothing`; the four actions are those two plus `newer`, which the
harness answers from its own timestamps and never asks. Scored as two binary truths recovered
from the labels - the inverse of `decide_collision` - both questions reach **AUC 1.00**
**[M]**. Both are gated on the same `t.act = 0.75`. On a bench of 52 cases built toward the
acting branch - 18 genuine fact-level restatements against 24 near-misses - that cut catches
**16/18 duplicates with zero false positives, precision 100 %, 95 % lower bound 81 %**: the
first acting branch in this package to clear an 80 % target on its lower bound **[M]**. 0.0016
USD, `benches/memory-collision-toward-branch.jsonl`. The threshold does not move because it is already at 100 %
precision. The method point is the size of the evidence: a branch that never fires on a bench
with two positives says something about those two cases, not about the threshold, and
`benchmarks/thresholds.py` exists so that no threshold moves on two cases in either direction.

What stays open is worth more than a fix would be: **does a threshold derived for a predicate
at one granularity transfer to the same predicate at another?** `redundant_page` asks the same
`adds_nothing` predicate about a page and has its own derived cut of 0.59; the collision point
keeps the generic 0.75. On facts, 0.59 buys two cases of recall and loses nothing - defensible,
unnecessary, and still only one dataset. `docs/results/2026-09-24-collision/`.

The general lesson: **check whether your two signals are one signal** before concluding that a
model is under-confident, and check whether your one threshold is serving two questions before
concluding that a branch is broken. Thresholds should be derived rather than picked, and
Google's deployed equivalent shows how - a probability threshold chosen per language to hit a
*target precision*, reported as recall@X, lowered from 70 % to 50 % and then to 40 % once a
human preview step existed **[P]**.

**Labels move on the question's criteria, never toward the model.** Three labels were revised
on the question's own criteria; both sets of numbers are published, with the reason recorded
in the bench header. Two other disagreements stand: the model missed them at low confidence,
and a bench that moves its labels to match the model measures nothing.

**A question about the future is not a closed question.** At compaction, "will the rest of
this session use this tool result?" reads like a yes/no a decider could answer. It is not
one: the answer depends on work that has not happened, and nothing in the state says what
the agent will do next. On 40 public OpenHands trajectories our prune question ranked needed
against unneeded results at AUC 0.57 on test and 0.61 on dev, with 98 % of its probabilities
below 0.25; the question of a replica of the fast-jev-compaction plugin scored 0.56 and 0.53
**[M]**. The replica freed 81 % and kept 9 % of what the future used, exactly what clearing
all but the last three results keeps (`docs/results/2026-09-28-context/`) **[M]**. So the
autopilot asks no decider at compaction. A calibrated model is calibrated about what is in
front of it; a prediction about the rest of the session is not in front of it.

**Decisions pay where the purpose is known, and even there a lexical ranker is the bar.**
The same autopilot asks the decider two questions whose purpose is in hand: which blocks of
an arriving result bear on the current task, and which archived entries bear on the current
prompt. Neither beat a free baseline offline. The arrival cut saved 3.7 % of long results
and kept every used token of 95.2 % of needed results, against 97.6 % for a head-and-tail cut
of the same size; recall found 70.4 % of masked needed results against BM25 top 3's 68.5 %,
at 7.8 % less text, not a detectable difference **[M]**. On LongMemEval a gate over memory
files injected half of BM25 top 3's text or less at 0.93-0.97 precision and missed its
registered recall (0.73 against 0.85); at equal text its evidence was not distinguishable
from BM25 over sentences (`docs/results/2026-09-28-memory-gate/`) **[M]**. Where the decider
did beat lexical ranking in this package (the tournament over 100 pages, `select_passages`),
the purpose was stated as the question and the unit was a page or a paragraph, not a line of
someone else's session.

**Masking did not beat Claude Code's own compaction, and the earlier result that said so is
retracted.** A first run inside Claude Code reported that the autopilot finished 12 of 12
synthetic coding tasks against 6 of 12 for the built-in `/compact` (p = 0.014). That comparison
did not measure masking. Its second phase ran as `claude -p --resume`, and our compaction hook
returned the engine's own message objects with their `handle`, so Claude Code rebuilt the
unmasked history on resume: phase B never saw the masked context. The run compared "no
compaction, plus recall" against the native summary, and its +13 % input tokens came mostly
from run-to-run variance in the first phase, not from recall
(`docs/results/2026-09-28-context-e2e/`, correction at the top) **[M]**. The bug is fixed and
checked: a resumed session now starts masked (57.1k tokens against 85.8k before).

Measured again, pre-registered, with compaction fired by Claude Code's own auto-compaction in
the middle of a task (Haiku 4.5, 7 tasks, run through our own evaluation harness), the native
summary finished **5 of 7**, lean masking (index stubs, an archive, a free arrival cut and a
`search_archive` tool to pull from it) **3 of 7**, and clearing old results without an archive,
the effect of Claude Code's microcompaction, **0 of 6** (`docs/results/2026-09-28-context-lean/`)
**[M]**. Both registered hypotheses failed. Lean masking used more input tokens (10.46M
against 8.73M) for the same dollars (1.99 against 2.03 USD at list price), because more of its
tokens were cache reads. The agent never called `search_archive` (0 of 7 sessions); it tried to
re-run one-shot tools 39 times instead. Offline, on 40 public trajectories, the index a stub
carries held a later-needed token for **12.0 %** of needed masked results (the registered bar
was 50 %); a free cut at arrival kept all needed lines in about 1 of 4 large outputs; Jev kept
them by hardly cutting (95.9 % of the characters). The API's `clear_tool_uses` rule, keeping
the last 3 results, behaves like masking with M = 3 **[M]**. The lesson: an index written when
a result is archived cannot know which of its tokens will matter, and an agent does not reach
for a pull-recall tool on its own. Keep the harness's native compaction as the default; our
masking is experimental and opt-in.

**Running it for real found silent product bugs that no test caught.** Each looked like
a working install: no error, the session ran, and the result was Claude Code's own
behaviour. On Windows, a hook command written with backslash paths never ran (0 hook events
in the attempt); `install` now writes forward slashes. And the compaction plugin read
`$.session.usage` as a value; Claude Code's function-hook compiler refused the whole module
and said so only in its debug log, so `/compact` fell back to the native summary with no sign
in the session. Both pilot attempts are published as invalid, and both fixes carry tests. The third is
the `handle` above: any plugin that replaces a session's messages must not return the
engine's `handle`, or a resumed session rebuilds the history from before the compaction. It
too looked like success, and it inflated a published result until the transcripts were
re-read.
This is section 5's failure from the other side: fail-open hides a layer that never ran as
well as a layer that failed. **Count the hook's own events before scoring an arm.**

---

## 4. The catalog: every lever we can argue about, ranked by how sure we are

Ranking is by *confidence that the saving is real*, not by size. "In the package" means it is
implemented with a bench; "designed" means the arithmetic is here and the code is not.

### Tier 1 - substitution, measured, safe to quote

| Lever | Replaces | Calls scale with | Status | Evidence |
|---|---|---|---|---|
| **Citation verification** | the big model re-reading each cited source | citations per report | in the package | 19/20, 23/24 with numbers, 100 % when it emits a verdict **[M]** |
| **Entity resolution after blocking** | an LLM judging each candidate pair | **pairs**, i.e. quadratically before blocking | in the package | 24/24, AUC 1.00 on hard pairs **[M]** |
| **Triple verification before commit** | an LLM re-reading the chunk per proposed edge | triples extracted | in the package | **17 committed and 1 of them backwards** on 50 cases, eleven of them `reversed`: `ed-26` is committed against a text that states the opposite **[M]**. A backwards edge is the one error here nothing downstream catches |
| **Injection screening on fetched content** | a hosted guardrail at ~0.60 USD/MTok | pages fetched | in the package | Public bench: 27/28 under the policy (flags above 0.70), AUC 1.00, against a regex at 23/28. AgentDojo: 101/124 attacks at 0.70, 120/124 with the regex alongside, **0/149** false alarms on real tool outputs **[M]**. End to end on AgentDojo's `slack` suite the undefended Sonnet 5 was compromised **0 times in 105**, so the scan bought nothing there, and it is off by default **[M]** |
| **Closed-vocabulary classification** | a small LLM doing extraction-by-prompt | records | in the package | 80-85 % against independent labels, majority baseline 43-62 % **[M]** |
| **Extraction gating before a generative pass** | the generative extractor, on chunks with nothing in them | chunks in the corpus | in the package | 15/16, AUC 1.00 **[M]**; LazyGraphRAG makes this budget the whole cost curve **[P]** |

### Tier 2 - substitution, argued, not yet measured end to end

| Lever | Replaces | Calls scale with | Status | The number that motivates it |
|---|---|---|---|---|
| **The loop guard** (goal met, repeated check) | nothing today; the agent simply keeps going | turns | in the package | redundant verification at its extreme cost **18x** the clean-run median, 2.5x the tool calls, 3x the wall time, **no success improvement**, preregistered over 4,644 runs **[P]**. Ours, under the policy (which speaks only from 0.70): 12/14 and 12/12, AUC 1.00; 46/50 and 50/50 with the second batch, zero false alarms **[M]** (`docs/results/2026-09-25-pending/`) |
| **The compaction guard** (`sanchopanza install --guard`; the cascade with `SANCHOPANZA_GUARD_CHOOSER=keep`) | nothing: it adds, after Claude Code's own summary, the lines of one-shot output the summary drops | compactions | in the package | Quality, not saving, and measured end to end: inside Claude Code 2.1.282 with Haiku 4.5, pre-registered, on the 7 tasks whose facts could reach the model, **2/7 finished with the native summary alone, 5/7 with the free rule, 6/7 with the cascade** (n = 7, McNemar p = 0.375), and the guard's sessions cost 0.66x (the summary lost the probe's value in 6 of 7 and the agent spent turns looking). The rule's arm lost the re-readable control twice more than native (a registered no-harm criterion that failed) **[M]**. Offline, choosing 400 characters of one-shot output with the next prompt as the question, the cascade kept every needed value in 28/28 on each of four conditions, where BM25 fell to 0/28 and the rule to 0-7/28 once the values were reworded or the prompt named nothing **[M]**; the decider's first questions reached 54/56 on the new conditions once they read the whole request (they had been reading about 95 characters of it). One family of generated tasks, and criteria written after seeing the failures (`docs/results/2026-09-29-context-guard/`) |
| **Memory write gate** | the extraction call a memory pipeline makes on every turn | turns | in the package | Mem0 runs extraction unconditionally per message pair; nobody gates it **[P]**. Ours, one cut of 0.54 on the weakest margin, derived on half of 100 cases to an 80 % precision target and pre-registered: **39/49 with 1 costly store** on the held-out half (the three-question conjunction it replaced: 37/49 with 2), and **74 of 108 with 1** on cases never used for any threshold (conjunction: 60 with 4) **[M]** (`docs/results/2026-09-27-memory-write-cut/`). It stores 4 of 36 standing instructions; the opt-in `common` question scores 45/48 on a batch written before it was measured, where the shipped cut scores 37/48 **[M]** (`docs/results/2026-09-25-window/memory.md`) |
| **Memory collision** (contradicts / adds nothing) | the ADD/UPDATE/DELETE/NOOP call, 1 of 2 LLM calls per message pair in Mem0 **[P]** | candidate facts x similar stored facts | in the package | **50/52 on a bench built toward the acting branch**, both questions at AUC 1.00, and `duplicate` at **16/18 with zero false positives, precision lower bound 81 %** - the first branch here to clear an 80 % target **[M]**. It is two binary questions, not four labels (section 3) |
| **Recall gating** | a memory lookup per turn; Anthropic's memory tool prompt is literally "always view your memory directory before doing anything else" **[P]** | turns | in the package | 14/14, AUC 1.00, ECE 0.049 **[M]** |
| **Model per subtask** | nothing; it changes which model runs | delegations | in the package | 17/20 raw, 11/11 above 0.75 confidence, against a small LLM at 8/20 **[M]**. Cache-safe **only** because it routes subagents |
| **First stage of a permission gate** (`CascadeDecider` + `points.actions`) | the frontier model judging every agent action | actions | in the package, no default threshold | On R-Judge's held-out half the Jev-then-Opus 5 cascade reached Opus's accuracy (93.2 %) at **57 %** of Opus's cost, over the registered 50 %: **fails**, and the verdict stands **[M]** (`docs/results/2026-09-25-cascade/`). Post hoc, on the same cases, and not a result: tau 0.35 reaches 93.2 % at 25.2 % of the cost; prompt caching moves the ratio by at most 0.7 points, because it cheapens an escalation and an Opus-alone call alike; escalating on one side only does not help **[M]**. **Confirmed on ATBench-Codex**, pre-registered, tau 0.45 fixed on R-Judge, Opus never shown the set: held-out half 80.3 % against Opus 79.9 % at **38.8 %** of its cost; the other half and all 500 replicate (79.1 % against 77.8 %, 38.5 %) **[M]** (`docs/results/2026-09-27-cascade-frontier/`). There Jev alone matches Opus (78.2 %) with fewer false allows (14.9 % against 25.7 %): which model is the strong one depends on the set. Pass tau 0.45. Against Sonnet 5 the original registration's verdict is **partial**: R-Judge fails on cost (57.7 %, median 47.7 % over re-splits), the register and Codex hold **[M]** (`docs/results/2026-09-28-cascade-sonnet/`) |

### Tier 3 - avoidance, workload-dependent, prove it on your own traffic

| Lever | Why it is here and not in tier 1 |
|---|---|
| **Page triage by relevance, one page at a time** | **A large saving that costs answers, and it is one result.** With the fetch sequence held fixed in both arms, it drops 170 of 193 documents for **-75.2 % input tokens [-86.8 %, -63.9 %]** and takes correctness from **10/10 to 6/10** **[M]**. In all four failures the answer document was among those dropped; in none of the six successes. Worst on compound purposes, where it dropped 4 of 4 and 3 of 3 answer documents. Keep `triage_page` for its injection and source-kind answers; to keep documents out, use the row below. |
| **In-context page triage (`triage_many` over passages)** | **The recommended way to keep documents out of a call.** Same fixed design: **9/9 against 9/9** correct at **-79.5 %** input tokens [-86.5 %, -72.9 %], pre-registered, the tenth task stopped by the cost cap and unable to overturn the bar **[M]** (`docs/results/2026-09-28-fixed-pages/`). Tier 3 still: one answering call over a sequence built to be mostly useless, 9 tasks, and unmeasured inside a warm loop, where reason 1 of section 1 applies. |
| **Page and sentence selection that asks for a contribution** | **What it keeps is measured, and on HotpotQA with short answers the kept text answers as well as all of it.** On multi-part HotpotQA questions, labels by construction: asking of each page alone whether it contributes a fact the answer needs (`triage_part`) keeps both supporting paragraphs in 93.3 % of 300 held-out questions at 52 % of the text, BM25 80.3 % with more **[M]** (`docs/results/2026-09-25-triage/`). Asking all ten pages in one call, each with the others in view (`triage_pages`), keeps every supporting page in **98.3 %** of 300 new questions at 34 % of the text, against 94.3 % at 53 % page by page in ten calls; sentences inside the kept pages (`select_sentences`) keep every supporting sentence in **90.3 %** at 22 % **[M]** (`docs/results/2026-09-27-chunks/`). Past one call (30 pages), a tournament (`triage_many`) over 100 pages per question keeps both supporting pages in **96.5 %** of 200 held-out questions at **3.1 %** of the text in 5 calls; the groups alone 94.0 % at 4.3 %; BM25 at the same page count 50.5 %; the 90 added pages are off-topic **[M]** (`docs/results/2026-09-27-hierarchy/`, after LATTICE, arXiv:2510.13217). Answering from the in-context sets, with the reply forced into one short field (pre-registered, Haiku 4.5 through our own evaluation harness): all pages 70.0 %, kept pages **71.0 %**, kept sentences **70.7 %**, all three criteria holding; the claim is equality, not gain **[M]**. The first run, with free-length replies, was negative as registered (81.0 % against 76.7 % and 76.0 %): its score counts a reply correct when the gold answer is contained in it, and replies grew with the context (median 30, 9 and 4 words) (`docs/results/2026-09-27-answers/`). On whole documents the compression does not transfer: on 300 QASPER papers the tournament kept all evidence in 94.7 % but 48.9 % of the text, against a criterion of 25 %, from the tournament before a fix and not yet replayable **[M]** (`docs/results/2026-09-27-longdocs/`). |
| **Redundancy between sources** | **It does not fire.** Handed **193 documents** drawn from a handful of source files, on a fixed sequence, it dropped **4**: -3.5 % input tokens [-12.1 %, +0.0 %], quality untouched **[M]**. Decision-level accuracy is real (AUC 1.00, 15/16 at a 0.5 cut), but **it is not a cost lever**: it does not appear under conditions built to produce it. |
| **Tool window** (which tool groups the application loads) | **Correct and safe; its cost case is weak where the platform offers tool search.** Offline, on 97 AgentDojo trajectories and 40 three-task sessions, it misses 0 and 0 needed groups, against 6 and 124 when selecting once from the request, and 3 and 13 with prerequisites added and the selection repeated on every user turn - in-sample, so a statement that the mechanism covers the known failure families, not a success rate **[M]**. Its injection scan stops the window from handing the attacker a capability: without it 24 of 56 payloads got the window to add the attacker's group, with it 0 of 56, and 0 of 26 clean texts blocked **[M]**. End to end with Sonnet 5 on a 74-tool catalog, success shows no detectable difference - loading everything 70/80 pooled over two runs, the window 100/120 over three, the platform's BM25 search 31/40 - and the window runs at 0.91x the time of loading everything **[M]**. Cost, re-priced from the recorded usage with the `tools` + `system` prefix shared between tasks as production shares it (an estimate): the window **0.77-0.88x** of loading everything, the search **1.48x** **[M]**. On a real 398-tool MCP catalog (167,937 tokens of definitions, near-duplicates of the AgentDojo apps included) success is 7/9 loading everything and 8/9 for both the search and the window, no arm calls a distractor tool (n = 5), and the estimated cost with a shared prefix is **0.34x** for the search against **0.54x** for the window **[M]**. The window's cost is set by its coarsest group: it opened the 121-tool `google_workspace` server in 11 of 17 tasks, correctly, and loaded all of it. **Server-sized groups are the open problem.** `docs/results/2026-09-25-window/`, `-e2e/`, `-wide/`, `-cache/`. |
| **Search tier routing** | 17/18 **[M]**, and the saving is whatever your search provider charges, which we cannot measure for you. **Read the warning in section 5 before wiring it.** |

### Tier 4 - do not use a decision model for this

| Not this | Because |
|---|---|
| **Tool selection, per turn, by rewriting `tools`** | Measured at 1.99x to 4.15x the cost of deciding once **[M]**. Decide once per session, or use the channels that append instead of swapping. |
| **Tool selection on top of a harness that already defers tools behind its own search** | Inside Claude Code, which defers tools behind its own `ToolSearch` and shows the model their names, a `UserPromptSubmit` hook that opens a window on the prompt changed nothing measurable: 4/4 against 4/4 with the built-in tools, 7/8 against 7/8 with 329 MCP tools from 10 servers **[M]** (`docs/results/2026-09-25-wide/`). The model selects exact names in one search without help. Codex CLI likewise defers MCP tools behind a local BM25 search. |
| **Predicting which context the rest of a session will need** | At chance: AUC 0.53-0.61 on 40 public coding trajectories, and a replica of an existing compaction plugin kept what clearing all but the last three results keeps **[M]** (`docs/results/2026-09-28-context/`). Observation masking into an archive asks nothing and did the work end to end (section 3). |
| **Replacing the harness's own compaction with masking** | Not a decision, but measured here: inside Claude Code the native summary finished 5 of 7 tasks, lean masking 3 of 7, clearing without an archive 0 of 6, at more input tokens for masking and the same dollars (`docs/results/2026-09-28-context-lean/`) **[M]**; read on the tasks whose facts could reach the model, 5/5, 3/5 and 0/5 (a task defect, corrected there). The earlier 12 of 12 against 6 of 12 is retracted. Adding to the summary instead of replacing it is Tier 2 (the compaction guard) |
| **Deduplicating fetches by URL** | A dict does it. Keep the model for semantic redundancy, which a dict cannot see. |
| **Reranking retrieved documents** | A dedicated reranker is better and cheaper, and it is steerable too. See the section below: this one is worth spelling out, because the opposite is being marketed. |
| **Anything arithmetic, or any comparison of dates** | The model class reads numbers and dates as text, and its own card says so. Our memory collision point never asks which fact is newer; the harness's timestamps answer that in code. |
| **Being the only barrier before an action** | The decider is itself vulnerable to instructions injected into its state. It adds denials; it never grants permission. |

---

## 4b. Reranking: the pitch we were being handed, and why we are not taking it

A vendor's post frames the top-100-to-top-5 step as a choice between a cross-encoder that
"cannot be steered", an LLM reranker at "27x cost", and a decision model that is "steerable
and cheap". It flatters us, so we checked it.

**"Cross-encoders cannot be steered" is false in 2026.** Instruction-following is a shipped,
priced feature: Voyage sells `rerank-2.5` and `rerank-2.5-lite` as instruction-following,
with the instruction appended to the query in natural language, and their own worked example
is our pitch nearly word for word ("retrieve regulatory documents and legal statutes, not
court cases") **[P]**. ZeroEntropy's `zerank-2` takes instructions and business context.
Contextual AI shipped one in March 2025 for recency, document type and source priority. Four
benchmarks exist to measure the capability: MAIR, IFIR, FollowIR, InstructIR.

**The price argument inverts.** Verified on vendor pages, 2026-09-24: Voyage
`rerank-2.5-lite` at 0.02 USD/MTok and ZeroEntropy `zerank-2` at 0.025 are **below** our
0.042, and a self-hosted Qwen3-Reranker is lower still **[P]**. The "27x" in the post
compares an LLM reranker against a reranker, and then recommends the option that costs about
twice the steerable cross-encoder.

**Someone published our differentiation first, cheaper.** ZeroEntropy's "zerank-2 as a
calibrated classifier" (2026-04-02) argues the score is an absolute probability, gives
thresholds, and replaces top-K with a threshold: 85 % context compression at 90 % recall on
150-page clinical documents **[P]**. That is the calibrated-gate story, owned by a reranker
vendor at 60 % of our price.

**And pointwise scoring is the known-worst architecture for ranking.** Aggregate quality runs
pointwise LLM below cross-encoder below listwise, and N documents means N calls against one
listwise pass at about 300 ms for a top-100 **[P]**.

So: **we do not compete on reranking.** What survives is narrower and worth stating exactly.
Our difference is not one calibrated score per document; it is **several independent typed
questions about one state in a single pass** - is it an official source, does it state a
figure, is it an opinion piece, is it in range - where a reranker takes one blended
instruction or runs once per criterion. The open door in the literature is **exclusion**:
models solve at most one ExcluIR query in eight and negation is where instruction-following
degrades **[P]**.

Our own first measurement of that, deliberately small: 14 flipped pairs where only the
criterion changes, **11 of 14 both sides right**, with five exclusion criteria of which four
passed **[M]** (`docs/results/2026-09-24-steerability/`). No baseline was run, so it says
what we do and not what we do better. The three-arm experiment that would settle it is at the
end of that file.

That measurement fixed one design rule: a provenance criterion written into the purpose prose
fails while the answer sits unused in the same decision (`source_kind`: `news`, confidence
1.00). `triage.decide` takes `allowed_kinds` / `denied_kinds` and filters in code. **A
criterion that a Choice question already answers does not belong in free-text prose.**

## 5. Two ways to lose money with a layer that "fails open"

Fail-open protects you from the decider being unavailable. It does not protect you from these.

**The alternative that does not exist.** A routing policy chooses between options the harness
claims to offer. If one of them is not actually deployed, the policy will route work into a
hole, confidently and cheaply, and the fail-open invariant will never fire because nothing
failed. We have seen this in production: a search router asked whether a cheap engine was
"available", was handed a function that answered *is there quota left* rather than *does this
service exist*, routed every query to a stub and produced a report beginning "this research
could not be carried out". The arm was 75 % cheaper. The 75 % was the cost of not delivering.
Page triage on a fixed sequence is the same shape from the other side: 73 % cheaper, four
answers in ten lost.

The package's README shows a probe, never `cheap_search_available=lambda: True`, because a
flag that is always true is the same bug waiting in example code. **A capability must be
probed, not declared.**

**The gate with nothing to gate.** Below roughly 17 % precision in whatever generates the
candidates, filtering them adds nothing: ByteDance measured an off-the-shelf LLM reviewer at
10.1 % precision and their trained filter moved it to 10.6 % **[P]**. A filter needs a signal
to separate. Measure the thing you are filtering before you build the filter.

---

## 6. The experiments that would move these claims

Each of these is specified enough that a disagreement becomes a measurement.

1. **Page triage on a purpose with parts.** The fixed-sequence A/B
   (`docs/results/2026-09-24-fixed-sequence/`) settles the size of the avoidance effect and
   its price: -75.2 % input tokens and four answers in ten. Judging passages with the others
   in view answered all nine tasks it reached, one compound task among them, and served every
   answer pin of the other (`docs/results/2026-09-28-fixed-pages/`); what is left is the same
   lever inside a warm agent loop, and more tasks. The older design below is kept for the
   record: what it does not settle is why relevance triage fails compound purposes. The
   experiment varies the number of parts in the purpose while
   holding the required documents fixed, and tests the two candidate fixes against plain
   triage: splitting the purpose into its parts, and gating on the *sufficiency of the set*
   rather than the relevance of each page. Moving the threshold is not a candidate: it buys
   answers back by dropping less, which is turning the lever off slowly.
2. **The unit of the tool window.** On a 398-tool catalog the window's cost is set by one
   121-tool server-sized group. Three designs, none measured: split large servers into
   sub-groups (a server's own tool categories); run the page tournament (`triage_many`) over
   those sub-groups, so a large server is judged among its own parts rather than loaded
   whole; or keep a window of groups and hand large groups to the platform's search instead
   of loading them. Any new end-to-end cost figure
   comes from a run of the fixed harness (breakpoint on `system`, pre-warmed prefixes); the
   shared-prefix figures in tier 3 are estimates from recorded usage. On Opus 5 the window is
   delivered with `tool_addition` and never loads a group up front; that end-to-end run has
   not been done.
3. **Thresholds at a target precision need more cases than a bench usually has.** For the six
   binary points, 212 harder cases take them to 50 each; a blind second annotator agrees with
   the author on 97 %, kappa 0.96, and the evaluator is as close to the blind annotator as to
   the author (93 % with each). Requiring the precision *lower bound* to clear the target,
   which is what makes a target falsifiable, imposes a sample-size floor of 16 acted cases for
   80 %, 35 for 90 % and 73 for 95 %. **Fifty cases per point buys an 80 % target and nothing
   above it.** Three of six points reach it. For `repeats_check` and `recall` the derived
   threshold scores out of sample what the shipped one scores. For `goal_met` the derived 0.34
   scores 14/14 against 12/14 for the shipped 0.70, and the threshold stays: 80 % is the only
   target reachable at n = 36, 0.34 is the costly direction (declaring a goal met sooner), and
   a threshold is not moved on the sample that was used to examine it. `memory_write`, which
   carried most of the gap, reached its target by pooling its 100 cases, deriving one cut on
   half and judging it on the other half and on 108 cases never used
   (`docs/results/2026-09-27-memory-write-cut/`). On the cases written to be hard, the gap the
   thresholds cost is 200 of 212 against 202 at a plain 0.5 cut, every loss in the safe
   direction; on the original cases it is three decisions, 82 against 85, one of them a store
   the derived cut refuses at margin 0.51. Closing the gap on hard cases is about 70 cases per
   point for a 90 % target and 146 for 95 % at a balanced label mix.
   `docs/results/2026-09-24-fifty/`.
4. **Deferred labelling in production.** Sample a fraction of *confident* decisions and
   re-label them. AWS's shipped pattern for exactly this is to review everything below
   threshold **and** randomly sample 5 % above it, as a continuing audit of the threshold
   **[P]**. The label must be behavioural (did the harness act, was it reverted), not
   heuristic: heuristic labels cap an actionability classifier at AUC 0.59-0.68, and the label
   definition dominates the model **[P]**.
5. **The memory pipeline, end to end.** Mem0-shaped write path with and without the write gate
   and the collision point, measured on calls, tokens and retrieval quality. Nobody has
   published this: only 2 of 9 memory systems surveyed in 2026 report any efficiency metric at
   all **[P]**.
6. **A within-family control.** Every comparison here is against an LLM of another family. An
   open-weight classifier behind the same contract would separate "non-generative" from "this
   particular vendor".
7. **Whole documents** (`docs/results/2026-09-27-longdocs/`). The tournament with the
   shipped cuts on 300 QASPER papers kept all evidence in 94.7 % and 48.9 % of the text, over
   the 25 % criterion: not confirmed (replayed with the fixed tournament, unchanged). With
   `select_sentences` inside the kept paragraphs: every answer sentence in 83.1 % at 31.5 %,
   31 points over BM25 with the same text, again short of 85 % and 25 %. **Confirmed** with
   the compression moved to the paragraph (`select_passages`: gate 0.75, window 2): 87.2 % of
   219 new questions at 21.0 % of the text, and an answering model as good from it as from
   the whole paper (`docs/results/2026-09-28-lateral-wholedocs/`). Open: Spanish documents and
   documents that are not papers.
8. **Long documents, by descent.** The in-context judgment reads an excerpt of 900 characters
   of each page, and sentence selection judges the first 40 sentences of a page. A long document would be judged as document, then sections, then
   sentences, each step among its siblings, the tournament's shape. Unmeasured.
9. **A cascade rule that does not overpay where the second stage is clearly stronger.** On
   R-Judge the registered rule failed on cost against Opus and against Sonnet; "within half a
   point", fixed in advance, is untested against Sonnet on unseen data.
10. **`relate_facts` on new cases.** On the fifth batch neither `unrelated` at a plain majority
    nor examples on `unrelated` beat the shipped question (25 right answers each). The `direction`
    question by roles did, and ships.
11. **Masking with an archive, where recall is the only path.** Measured and negative
    (`docs/results/2026-09-28-context-lean/`): with facts made early and needed late, the
    agent guessed from the stub's index or re-ran tools instead of searching the archive. What
    would move the claim: a stub that says what a result will be needed for (not knowable at
    archive time, see above), or an agent model that uses a search tool unprompted; Sonnet 5
    is in the same results folder. The Codex CLI integration is written but not verified end
    to end.

---

## Sources

Measured **[M]** figures come from this repository: `docs/results/2026-09-21-public/` (the
paper's public run), `docs/results/2026-09-24-new-points/` and `docs/results/2026-09-25-pending/`
(the new points, scored under the policy in force), `docs/results/2026-09-24-fifty/` (fifty
cases per point, the second annotator and the substitution run),
`docs/results/2026-09-24-fixed-sequence/` (the avoidance A/B on a fixed sequence),
`docs/results/2026-09-24-collision/` and `docs/results/2026-09-24-fourth-batch/` (collision and
edges), `docs/results/2026-09-24-agentdojo/` and `docs/results/2026-09-24-agentdojo-e2e/`
(injection on AgentDojo, by decision and end to end), `docs/results/2026-09-24-third-batch/`
(`memory_write` on 100 cases),
`docs/results/2026-09-24-tools/`, `docs/results/2026-09-25-window/`,
`docs/results/2026-09-25-e2e/`, `docs/results/2026-09-25-wide/` and
`docs/results/2026-09-25-cache/` (tool selection, the window and its cost),
`docs/results/2026-09-25-triage/`, `docs/results/2026-09-27-chunks/`,
`docs/results/2026-09-27-hierarchy/`, `docs/results/2026-09-27-longdocs/` and `docs/results/2026-09-27-answers/` (page and sentence
selection, and answering from what it keeps), `docs/results/2026-09-27-memory-write-cut/`
(the derived `memory_write` cut and the substitution table under it),
`docs/results/2026-09-25-cascade/` and `docs/results/2026-09-27-cascade-frontier/` (the
permission cascade), `docs/results/2026-09-27-edge-facts/` (the Choice confidence identity),
`benchmarks/ab/results/` (the free-loop A/B) and `benchmarks/cache/results/` (the cache arms).
All replay or reproduce from the files in the repository.

Published **[P]** sources, all accessed 2026-09-24:

- Anthropic, *Advanced tool use* (2025-11-24). 58 tools ~55k tokens; a 134k peak; tool search
  77k -> 8.7k, 85 %; programmatic tool calling 43,588 -> 27,297 tokens.
  https://www.anthropic.com/engineering/advanced-tool-use
- Anthropic, *Prompt caching* docs. Cache read 0.1x, 5-minute write 1.25x, 1-hour write 2x;
  the `tools -> system -> messages` invalidation hierarchy.
  https://platform.claude.com/docs/en/build-with-claude/prompt-caching
- Anthropic, *How we built our multi-agent research system* (2025-06-13). Agents ~4x the
  tokens of chat, multi-agent ~15x; token usage explains 80 % of performance variance.
  https://www.anthropic.com/engineering/multi-agent-research-system
- Weinberger, S., Hozez, A., *Prompt-induced waste in coding agents* (arXiv:2608.01347, 2026).
  Preregistered, 4,644 runs, 24 tasks, 7 models. Redundant verification at level 3+: 18x the
  clean-run median cost, 2.5x tool calls, 3x wall time, no success gain.
- Distefano, D., Fahndrich, M., Logozzo, F., O'Hearn, P., *Scaling static analyses at
  Facebook*, CACM 62(8), 2019. Batch ~0 % fix rate to diff-time >70 %, same analysis, same
  false-positive rate.
- Atlassian, *RovoDev code reviewer: a large-scale online evaluation* (arXiv:2601.01129,
  2026). ModernBERT actionability classifier +20 points of human alignment; an LLM-as-judge
  factual-correctness check had "minimal impact".
- Frommgen, A. et al., *Resolving code review comments with ML*, ICSE-SEIP 2024. Google's
  deployed triage is a probability threshold tuned per language to a target precision,
  reported as recall@X; 7.5 % of all reviewer comments resolved by an ML edit.
- Kang, H., Aw, K. L., Lo, D., *Detecting false alarms from automatic static analysis tools*,
  ICSE 2022 (arXiv:2202.05982). Heuristic-labelled actionability classifiers fall to AUC
  0.59-0.68 once leakage and duplication are removed; the label definition dominates.
- BitsAI-CR (arXiv:2501.15134, FSE 2025). A trained filter moves a 10.14 % generator to
  10.62 % and a 57.03 % generator to 65.59 %: below a precision floor, filtering does nothing.
- *AgentDiet* (arXiv:2509.23586, 2025). Input tokens down 39.9-59.7 %, total cost down only
  21.1-35.9 %, at equal performance.
- Repantis, V. et al., *How many tools should an LLM agent see? A chance-corrected answer*
  (arXiv:2605.24660, 2026). Adaptive depth 93.1 % against 87.1 % at a fixed 5; a fixed K=5
  finds nothing at all on hard queries.
- Microsoft Research, *LazyGraphRAG* (2024-11-25). The relevance-test budget (100 / 500 /
  1,500 binary judgments per query) is the parameter that controls the cost/quality curve.
- Mem0 (arXiv:2504.19413, 2025) and the Anthropic memory tool documentation, for the
  unconditional write path and the ungated retrieval path respectively.
- AWS, Bedrock Guardrails pricing (0.15 USD per 1,000 text units) and the Augmented AI
  condition syntax, including the pattern of reviewing everything below a confidence
  threshold plus a random 5 % above it.
- Azure Retail Prices API, product "Observability": evaluation input 0.02 USD per 1K tokens,
  output 0.06 USD per 1K; Google Vertex legacy model-based metrics at the same effective
  rate. The published Azure pricing page renders these as placeholder dashes.

Two figures that circulate widely and are **not** used here because no primary source was
found: "7 MCP servers = 67k tokens" (and a measured `/context` over-reporting bug of about
3x that inflates much of that literature), and "70-95 % of production agents fail".
