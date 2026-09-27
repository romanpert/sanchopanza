# `memory_collision` is two binary questions, and the shipped cut works on both

Run of 2026-09-24, on two batches:

| batch | cases | recording | cost |
|---|---|---|---|
| the original cases, `benches/memory.jsonl` | 16 | `fixtures/new-points.jsonl` | 0 (replayed) |
| built toward the branch that acts, `benches/memory-collision-toward-branch.jsonl` | 52 | `fixtures/collision-toward-branch.jsonl` | 0.0016 USD, 30.8 millionths per decision |

Everything replays for free with `python benchmarks/collision.py`. No labels were added to the
original batch and no existing bench file was edited.

**The result:** both questions the point asks order their cases perfectly (AUC 1.00 on both
batches), and at the shipped `t.act = 0.75` the `duplicate` branch catches **16 of 18
fact-level duplicates with zero false positives, 95 % lower bound 81 %**. No threshold moves.

This is the treatment `docs/results/2026-09-24-fifty/README.md` asked for: *"`memory_collision`
and `edge` are not extended... both need their own treatment."* The treatment turned out not to
be more cases of the same shape.

---

## 1. The point is two binary questions and a timestamp comparison

`memory_collision` reports four labels, which makes it look like a 4-way classification.
`decide_collision` says otherwise. The model answers **two** independent Truth questions:

- `contradicts` - do the two facts state incompatible values for the same field?
- `adds_nothing` - does the new fact add nothing at all to the stored one?

and the four actions are those two probabilities plus `newer`, which is **never asked of the
model**. The harness supplies it from timestamps it already holds, deliberately, because this
model class reads dates as text and its own card says so.

So: two binary judgments, one comparison done in code, and a label that reads like a
four-way choice.

**The consequence is mechanical.** In `eval/bench.py` this point leaves `probability` at
`None`, because there is no single probability to report, and a row without a probability is
excluded from the binary table. The generic bench therefore reports no AUC, Brier or ECE for
this point, while all six of its neighbours have all three. `benchmarks/collision.py` scores
the two questions directly.

## 2. The two binary truths are recovered, not annotated

The 4-way label plus `newer`, which is part of the case input, determines both binary
answers exactly. `truths()` in `benchmarks/collision.py` is the inverse of
`decide_collision`:

| label | `newer` | `adds_nothing` | `contradicts` |
|---|---|---|---|
| `duplicate` | any | true | **not constrained** - the branch returns before `contradicts` is read |
| `replace` | true | false | true |
| `flag` | unknown | false | true |
| `keep_both` | false | false | true |
| `keep_both` | true or unknown | false | false |

That is why the metric costs nothing and applies to every collision case ever labelled, and
why `contradicts` has a smaller n than the case count.

## 3. The measurement

| batch | agreement | errors |
|---|---|---|
| original, 16 | 14/16 | `mc-01`, `mc-07`, both `duplicate` |
| toward the branch, 52 | **50/52 = 96 %**, ECE 0.031, median latency 235 ms | `mc-101`, `mc-103`, both `duplicate` |

| batch | question | n | positives | AUC | Brier | ECE | max negative -> min positive |
|---|---|---|---|---|---|---|---|
| original | `contradicts` | 14 | 7 | **1.00** | 0.014 | 0.101 | 0.21 -> 0.80 |
| original | `adds_nothing` | 16 | 2 | **1.00** | 0.038 | 0.105 | 0.38 -> 0.41 |
| toward the branch | `contradicts` | 34 | 10 | **1.00** | 0.015 | 0.083 | 0.55 -> 0.84 |
| toward the branch | `adds_nothing` | 52 | 18 | **1.00** | 0.009 | 0.060 | 0.07 -> 0.61 |

Both questions order their cases perfectly on both batches. The point has no ordering error.

**Both are gated on the same `t.act = 0.75`.** For `contradicts` that cut lands inside a wide
gap on both batches and separates without effort: this model answers it with conviction, 0.80
to 0.97 on positives. `adds_nothing`, asked about two facts rather than two pages, is answered
more moderately, and that is where the cut matters.

The sweep on the batch built toward the branch:

| cut | duplicates caught | false positives | precision | 95 % lower bound |
|---|---|---|---|---|
| **0.75 (`t.act`, in force)** | **16/18** | **0** | **100 %** | **81 %** |
| 0.59 (`t.adds_nothing`) | 18/18 | 0 | 100 % | 82 % |
| 0.50 | 18/18 | 0 | 100 % | 82 % |

The two it misses are `mc-101` at 0.61 (an acronym expanded: *Junta Central Electoral* against
*JCE*) and `mc-103` at 0.63 (*12.500.000 pesos* against *RD$12.500.000*, with `ascendio a` for
`se adjudico por`). Both are restatements that change the surface a lot, which is a reasonable
reason for a moderate score.

The original batch cannot say much about this branch on its own. It holds two duplicates, and
the 0.75 cut catches neither (top positive 0.69): at 0.59 it catches one of two, at 0.40 both,
with precision lower bounds of 21 % and 34 %. Both of its positives are hard cases:

- `mc-01` is disputed on its own terms (section 5): a *multa* is paid to the state, an
  *indemnizacion* to the plaintiff, so it is not clearly a duplicate at all.
- `mc-07` is the *anular* / *declarar inconstitucional* equivalence, the same semantic pair
  that the `edge` point rejects at confidence 1.00 and that the paper records as a confident
  error.

Read together, the two batches say the same thing: what the 16 original cases measured was the
difficulty of two cases, not the reach of the threshold. A branch with two positives is not
evidence either way, and a batch built toward it is how that is settled.

## 4. No threshold moves

Requiring the 95 % Wilson lower bound on precision to clear the target - the rule
`benchmarks/thresholds.py` enforces - needs **16 acted cases for an 80 % target, 35 for 90 %,
73 for 95 %**. The batch built toward the branch supplies exactly 16 acted cases at the
shipped cut, so it clears an 80 % target on its lower bound, and no more than that.

At 0.75 the branch already runs at 100 % precision with an 81 % lower bound. Moving to 0.59
buys two cases of recall and keeps zero false positives, so it is defensible; it is not
necessary, and the conservative direction is the safe one for a gate that suppresses a fact.
What would justify the move is a batch where the cost of the missed duplicates is measured end
to end, not a better-looking recall column.

## 5. The neighbour, and the question it raises

`redundant_page` asks the **same predicate** - the wording is nearly identical, down to the
worked example about 1,240 damaged homes - about a page and what the agent already knows,
rather than about two facts. That point has 125 labelled cases and its own threshold,
`t.adds_nothing = 0.59`, derived to a 90 % target and validated out of sample. The collision
point uses the generic `t.act`.

Which opens a question this repository cannot yet answer:

> **Does a threshold derived for a predicate at one granularity transfer to the same
> predicate at another?**

If it transfers, a derived cut is a property of the question and the catalogue gets cheaper
to calibrate. If it does not, a threshold is a property of the pair (predicate, granularity)
and several numbers in this repository are narrower than they look. The evidence here points
weakly at "it transfers": on the batch built toward the branch, 0.59 catches all 18 duplicates
with no false positives. Eighteen positives on one batch cannot carry that claim.

## 6. How the batch toward the branch was built

A bench balanced across four labels spends most of its cases on branches driven by `newer`,
which the model never sees. This one is balanced toward what a precision target needs, which
is acted cases: 18 `duplicate`, 24 `keep_both` near-misses, 6 `replace`, 4 `flag`. The
near-misses are the whole test, because they are the only credible source of a false
positive:

- the same figure from a second source, when the work is corroboration;
- a narrower restatement (`sole shareholder` against `belongs to`);
- the same value carrying one new qualifier, date or attribution;
- a numeric coincidence across two fields.

The cases also spread across corporate registry, seismology, judicial, public procurement and
press, because the first batches drew on one corpus and a disputed semantic pair propagates
across points that share a domain. `mc-01` is that pair:

```
new    : La multa fue de 500.000 pesos.
stored: Lo condenan al pago de una indemnizacion de RD$500.000 a favor del querellante.
```

A *multa* is punitive and paid to the state; an *indemnizacion* is paid to the plaintiff.
They share a figure and nothing else, so `duplicate` is arguable at best, and the model's
0.41 - "adds something" - is defensible. It is the same ambiguity recorded for `gm-50`, which
"turns on whether a *multa* and an *indemnizacion* are the same thing", surfacing in a second
point. The label is left as it is and recorded as disputed; a label is not changed because a
model disagrees with it.

## 7. Two method rules the script follows

- **Rows are bound to case ids by replaying through the squire, never by position.** Pairing
  a recording to a bench by order produces a tidy and wrong story on this data (an AUC of 0.86
  on `contradicts` and two confident errors in opposite directions) that the per-case output
  contradicts. A result that is interestingly bad deserves the same suspicion as one that is
  flatteringly good.
- **The wording is derived from the numbers every time.** `benchmarks/collision.py` computes
  the top of the positive range and says one of three things - unreachable, partial with the
  recall, or clean with the gap - so its prose cannot describe one batch while printing the
  table of another.

## What is still open

`edge` has had none of this treatment. Its acting branch is `supported` - commit the triple -
and on 20 cases it committed 8, so an 80 % target needs about 40 cases and a 90 % target
about 88. Its one confident error, `ed-04`, is the `anular` pair above, which means the same
semantic ambiguity has evidence in two points and a fix in neither.

### Two claims from the other second batch

The 34 cases in `benches/memory-d.jsonl` were written independently the same day and measure
the point from a different angle (`docs/results/2026-09-24-fourth-batch/README.md`). Both
batches agree that `duplicate` fires; neither makes the other redundant, and together they
form an unplanned replication.

- **The errors are asymmetric.** Across all 50 cases of that batch, **all four errors land in
  `keep_both`**: two duplicates, one replace, one flag, every one of them a refusal to act.
  That is a different claim from precision on the acted branch, and it is the one that says
  the point is safe to deploy - it fails by keeping a fact, never by suppressing one.
- **Recency is not being asked of the model, and there is direct evidence.** Eight of those
  cases are triples: identical `new` and `stored`, `newer` set to true, false and null, and
  labelled `replace`, `keep_both` and `flag` respectively. **Nothing in the text
  distinguishes them.** A point that changed its answer across a triple would be reading
  dates out of the prose, which is the weakness the design routes around by putting recency
  in code. It is the only direct test of that assertion in either batch.

## Reproducing

```
python benchmarks/collision.py
python benchmarks/collision.py --bench benches/memory-collision-toward-branch.jsonl \
  --fixture fixtures/collision-toward-branch.jsonl
```

Free.
