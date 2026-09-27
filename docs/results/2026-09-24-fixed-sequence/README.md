# The fetch-heavy A/B, with the document sequence held fixed. It is not null.

Run of 2026-09-24. **2.92 USD of real spend.** `benchmarks/ab/fixed.py`, 10 tasks, 20
documents walked per task, both arms driven through the identical sequence, one model call
per arm from what survived. `claude-sonnet-5`, effort `low`, `jev-1.13.0`.

`docs/paper.md` Section 5.15 reports it. It settles what the free-fetch A/B and the pilot
of the same morning could not.

**The two levers are measured separately here, and they give opposite answers.** Page triage
has a large effect with a price in answers; source redundancy has none.

---

## 1. The design, and why the sequence is fixed

An A/B in which each arm chooses its own fetches cannot answer this, for the reason
`where-it-pays.md` gives:

> An avoidance lever can only act on what the agent fetches, and the run that fetches many
> redundant sources is the run that was already going badly. The lever's opportunity is
> correlated with the arm having a bad draw.

Here the agent does not choose. For each task the retriever returns a deterministic ranked
list of 20 documents, the harness walks it in order, each document passes through the lever
(or not), and one call answers from the survivors. **Both arms see byte-identical input
before the squire acts**, so the paired difference is the lever and nothing else.

What that buys, and what it costs: the comparison is now clean, and it is no longer an agent
loop. It says nothing about how a lever changes an agent's *behaviour* - re-fetching, giving
up, burning turns. `run.py` still measures the loop; this measures the lever.

The sequences were checked before spending: every task's answer documents are inside its 20,
so a failure here is the lever discarding the answer, never the retriever failing to find it.

## 2. Page triage: a 75 % saving, and it costs four answers in ten

| | bare | squire | paired ratio, 95 % |
|---|---|---|---|
| Input tokens | 342,042 | 84,685 | **-75.2 % [-86.8 %, -63.9 %]** |
| Cost USD | 0.6924 | 0.1882 | **-72.8 % [-84.1 %, -61.6 %]** |
| **Correct** | **10/10** | **6/10** | lower bounds 0.72 / 0.31 |

170 of 193 documents dropped. The saving is large and its interval is nowhere near zero -
this is the first time an avoidance lever in this repository has produced an effect that
survives a paired interval.

**And it is the cost of not answering.** The per-case attribution is exact:

| task | correct | dropped | answer documents dropped |
|---|---|---|---|
| injection | **no** | 20/20 | **1/1** (`paper-06`) |
| cost | yes | 13/20 | 0/1 |
| breakeven | yes | 16/20 | 0/1 |
| dag | yes | 18/20 | 0/1 |
| entity | yes | 17/20 | 0/1 |
| viviendas | yes | 11/13 | 0/1 |
| toolselect | yes | 17/20 | 0/1 |
| classify | **no** | 19/20 | **1/1** (`paper-06`) |
| spread-adapters | **no** | 19/20 | **4/4** |
| spread-costs | **no** | 20/20 | **3/3** |

**Ten for ten.** Every failure dropped the answer; no success did. That is the mechanism, not
a correlation, and it is visible case by case rather than inferred from an aggregate.

### The failure has a shape, and it is the one this repository already found once

The two worst cases are the **compound** questions - *name the entry point each of these four
adapters uses*, *give three figures from the cost documentation* - and triage dropped
**every** answer document in both, 4 of 4 and 3 of 3. The reason is structural: the purpose
handed to triage is the whole question, and no single document satisfies the whole question.
Each document is a partial answer, and a relevance judgment asked "does this page address
this purpose" correctly says no to each one, right up to the point where the answer is gone.

This is `st-01` from the steerability run, one level up. There, a criterion about provenance
was written into free-text prose while a Choice question already answered it. Here, a
criterion about *sufficiency* is being asked of a question that measures *aboutness*.
**Triage answers the question it was asked. The question is wrong for a compound purpose.**

The two single-fact failures, `injection` and `classify`, both lost the same document,
`paper-06`, which is a long results section holding many numbers and matching no single topic
cleanly. Same shape, weaker form.

## 3. Source redundancy: it does not fire, even on a redundant corpus

| | bare | squire | paired ratio, 95 % |
|---|---|---|---|
| Input tokens | 342,042 | 329,949 | -3.5 % [-12.1 %, +0.0 %] |
| Cost USD | 0.6926 | 0.6789 | -2.0 % [-10.1 %, +1.5 %] |
| Correct | 9/10 | 9/10 | - |

**4 drops in 193 documents.** The interval touches zero, so this is null, and quality is
untouched.

A workload that does not feed the lever, such as the free-fetch A/B at 1.8 fetches per task,
cannot explain this result. The lever was handed 193 documents drawn from the same handful of
source files - about as redundant a corpus as this repository contains - and it said
`adds_nothing` four times.

That is a fact about the point, not about the workload, and it is consistent with the
decision-level evidence that `duplicate` and `drop` are conservative branches. What it means
practically: **source redundancy should not be presented as a cost lever.** Its decision-level
accuracy is real; its end-to-end effect does not appear under conditions designed
specifically to produce it.

## 4. The pre-registration, scored

Recorded in `benchmarks/ab/fixed.py` before any money was spent: *a real effect on input
tokens, a smaller one on cost, and quality holding.*

- Real effect on input tokens: **yes**, -75.2 % for triage.
- Smaller effect on cost than on tokens: **yes**, -72.8 % against -75.2 %.
- Quality holding: **no**, 10/10 to 6/10.

Two of three, and the one that failed is the one worth having. A prediction that had come out
right in all three parts would have licensed a headline saving figure that is not real.

## 5. What this means

- **Page triage has a large effect.** When the agent chooses its own fetches, the lever's
  opportunity moves with the arm's draw and the effect disappears into the noise; isolated,
  it is large.
- **And it is not a saving.** A 73 % cost reduction that loses 40 % of the answers is the
  same shape as a search router that routes into a hole and comes back 75 % cheaper. It is
  the default outcome of an avoidance lever, not an accident.
- **The lever is not ready to ship as-is on compound purposes.** The fix suggested by the
  failure shape is not a threshold: it is to stop asking one relevance question about a
  multi-part purpose. Splitting the purpose, or gating on *sufficiency of the set* rather
  than relevance of each page, is the experiment this points at. Moving the threshold would
  buy back answers by dropping less, which is just turning the lever off slowly.
- **Redundancy belongs outside the cost story.** "Workload-dependent, prove it on your own
  traffic" understates this run: it did not fire on the workload built to make it fire.

## 6. Threats to this result

- **One repetition per cell.** The effect sizes are large and their intervals are tight, but
  the correctness comparison is 10 against 10 with wide Wilson bounds (0.72 and 0.31), and
  the bare arm answered a task differently between two runs on identical input during the
  pilot, so the model is not deterministic even here.
- **One corpus, one retriever, one model, one effort level.** The corpus is this
  repository's own documentation, so "compound question over sections of one document set"
  may be over-represented relative to real research.
- **The pipeline is not an agent.** A real agent that loses a document can search again; this
  one cannot. That makes this a lower bound on quality for triage, and it is the reason
  `run.py` is not being retired.

## Reproducing

```
python -m benchmarks.ab.fixed --dry-run                       # the plan and the bill, free
python -m benchmarks.ab.fixed --repeats 1 --lever triage --out <dir>
python -m benchmarks.ab.fixed --repeats 1 --lever redundancy --out <dir>
```

Rows, summaries and the per-document drop lists are in `triage/` and `redundancy/` beside
this file.

---

## 7. It replicates on a different point, and that changes what it is

Written after this run, from an independent measurement of `select_tools` over 97 AgentDojo
tasks with **derived** ground truth (the groups a task needs are the groups whose tools its
`ground_truth()` calls, so no annotator is involved). Full account and credit:
`docs/results/2026-09-24-tools/README.md` §4.

| groups the task needs | tasks | all survive | mean catalog reduction |
|---|---|---|---|
| 1 | 53 | **53/53 = 100 %** | 86 % |
| 2 | 37 | 33/37 = 89 % | 70 % |
| 3 | 7 | 6/7 = 86 % | 56 % |

**Not one single-part task fails, and every failure the selector has is composite.**
Different point, different corpus, different ground truth, same shape as the triage result
above. The split there is cleaner than here because the number of parts is a property of the
task rather than a reading of the question.

So the statement is more general than "page triage mishandles compound purposes":

> An independent per-item question cannot express a covering constraint. Asking "is item X
> needed for purpose P" once per item and thresholding each answer on its own is a correct
> procedure for a one-part purpose and the wrong procedure for a several-part one. **Every
> item can be individually unnecessary while the set is jointly required.**

That is an architectural property of pointwise filtering, not a defect of either point, and
it is why neither of these should be fixed by moving a threshold: in both runs the model
answered its question correctly.

### The confound, stated before anyone quotes this

**We have an effect and not a mechanism.** In the tool corpus "needs three groups" and "asks
three things" are the same variable; in this one, "compound question" and "answer spread
across documents" are also the same variable. Either could be doing the work. The experiment
that separates them varies the number of parts in the purpose while holding the number of
required items fixed, and neither run has done it.

The caution is concrete. A structurally identical story - that requests which defer their
instructions to fetched content are the requests an injection lands in, two points seeing one
property from opposite ends - is **inverted** by the end-to-end logs: of 21 tasks, 0 of the 2
deferring ones were injectable and 19 of 19 injectable ones were not deferring. A tidy
mechanism with one confounded variable behind it reads exactly like that one did.

### And the number that must not travel alone

**-75.2 % and 10/10 -> 6/10 are one result.** The selector has the same structure: 85 %
reduction at 90 % survival, or 77 % at 95 %. In both, the saving is largest exactly where
the filter is most wrong, because dropping everything is simultaneously the cheapest and the
most destructive thing a filter can do. Quoted apart, the wrong half is the half that
travels.

### Where to look: the policy over the answers

A pointwise gate applied to a covering purpose is a defect in the **policy over the answers**,
not in the answers, and it is the third of that kind measured on 2026-09-24: `decide_edge`
consulting `stated`'s confidence gate before reading `direction` (`reversed` fired 0 times in
11 while `direction` sat at 0.05 with confidence 0.90), and one knob, `t.redundant`, serving
both page redundancy and search-repeat. In all three the model answered correctly and the
policy had the wrong shape. The audit of that layer is `docs/results/2026-09-25-window/audit.md`.
