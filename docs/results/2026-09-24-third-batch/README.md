# The third batch: one threshold derived, one defect located, one fix measured and not shipped

Pseudonymization hardening (2026-09-28): rd-91 to rd-96 and mw-03 were reworded and their
entries in `fixtures/third-batch.jsonl` re-recorded; agreement under replay did not move, and
the rows and figures published here come from this run's own sitting and are left as they were.

Run of 2026-09-24. 125 new cases take `memory_write` to 100 and `redundant_page` to 125,
`jev-1.13.0`, **0.0038 USD** for the new cases and 0.0084 USD for the re-run over all three
batches. It takes up the twelve-decision gap `docs/results/2026-09-24-fifty` found between
what the model orders correctly and what the shipped policy acts on. With more acted cases the
gap resolves into two different things: on `redundant_page` a knob shared with another point,
which a derived threshold now replaces, and on `memory_write` a question defect, which no
threshold can fix.

| | |
|---|---|
| New cases | 125 in `benches/memory-c.jsonl` and `benches/retrieval-c.jsonl` |
| `memory_write` | 50 to 100 cases, 51 `store` labels |
| `redundant_page` | 50 to 125 cases, 69 `drop` labels |
| Recording | `fixtures/reverted.jsonl`, replays for free |
| Net effect on the fifty-case run | 190/212 to 197/212; the gap against a plain cut 12 to 5 |

## 1. Why more cases, and why this many

`benchmarks/thresholds.py` publishes a sample-size floor that is pure arithmetic: requiring
the **95 % Wilson lower bound** of precision to clear a target, a 90 % target needs 35 acted
cases and a 95 % target needs 73. `redundant_page` had 50 cases of which only **18** were
labelled `drop`, and `drop` is the acted direction - so no derivation could ever have had
more than 18 acted cases to work with, whatever the model did. Adding cases in the same
proportion would not have helped. The new batches are deliberately unbalanced towards the
acted label for that reason: 51 of 75 `drop`, 25 of 50 `store`.

## 2. The threshold that moved, and it is the first one that ever has

Derived on the 75 new `redundant_page` cases, reported on the 34 cases of the second batch,
which the derivation never saw:

| Target | Derived | Precision (held out) | Recall | Agreement at derived | Agreement at shipped |
|---|---|---|---|---|---|
| 80 % | 0.06 | **55 %, misses its own target** | 100 % | 24/34 | 26/34 |
| **90 %** | **0.59** | **100 %** | **92 %** | **33/34** | 26/34 |
| 95 % | unreachable at n=75 | - | - | - | - |

Two things in that table are worth more than the number.

**The looser target produced the worse threshold.** Asking for 80 % precision let the search
pick 0.06, which maximises recall among thresholds whose lower bound clears a low bar, and
out of sample it delivered 55 %. Asking for 90 % produced 0.59, which held. A precision
target is not a safety margin you can dial down when the strict one is inconvenient; a low
target selects an extreme.

**The knob was serving two points.** `decide_redundancy` read `t.redundant`, the threshold
the *search* point uses for a repeated query, on the explicit theory - written in the module -
that "it is the same reading". It is not. Search's 0.80 is the value measured at 17/18 on its
own bench; page redundancy's derived value is 0.59, and at 0.80 it was scoring 26/34. Neither
point could move without breaking the other. `t.adds_nothing` is now its own number and `tests/test_memory_graph_loop.py` pins that the two
are separate as well as what they are.

Effect on the earlier batches: `redundant_page` 26/34 to **33/34** on the second, 14/16 to
**15/16** on the first.

## 3. The defect that is not a threshold, and the fix that is not shipped

`memory_write` loses one family and it is not a hard one. On `mw-54`, `mw-59`, `mw-69`,
`mw-72`, `mw-74` - standing instructions and agreements from the client - the three questions
answer like this:

| | durable | specific | derivable |
|---|---|---|---|
| "the client wants amounts in euros at the rate of the day of the event" | 0.81 | 0.33 | 0.36 |
| "do not contact anyone in the family circle, in any phase" | 0.86 | 0.43 | 0.58 |
| "social-media mentions do not count as a source unless verified" | 0.88 | 0.50 | 0.38 |

`durable` sees them perfectly - and its own criteria list *"the client asked for the report in
Spanish"* as a true example. Then `specific` throws them away, because it asks whether a fact
"names things, figures, dates or outcomes" and an instruction names none of those. **Two
questions in one decision disagreeing about what the point is for**, which is the same shape
as the redundant-gate defect of 0.2.0, one level up: there two gates read one number, here two
questions encode two different intents.

The obvious patch is to widen `specific` to admit a rule-shaped fact. It was measured and is
not shipped, and the measurement is the reason:

| | agreement | errors in the costly direction | errors in the safe direction |
|---|---|---|---|
| shipped | 72/100 | **5** | 23 |
| with `specific` widened | 88/100 | **8** | 4 |

Sixteen more right answers, and eight facts stored that should not be against five. The
widened gate stores general knowledge and quotation - `Panama is a country in Central
America`, `article 29 of Ley 6132 defines defamation as...` - which the narrow `specific` gate
filters **as a side effect** of asking about figures, doing the right job for the wrong
reason; widening it removes that filter without putting anything in its place. Two of its
eight, `the ruling has forty-seven pages` and `the administrator named in the minutes is J.
Perez` (`mw-78`, `mw-97`), the shipped policy stores as well: that is `derivable` missing
verbatim detail, a separate defect (`docs/results/2026-09-25-window/memory.md`). `derivable` cannot take over: world knowledge is not
re-readable from a source the agent holds, so the question correctly answers 0.37 on the ISO
example and lets it straight through.

For a memory that is the wrong trade, and the module says so in its own first paragraph: *"A
junk memory is read on every later turn, for free to the model that wrote it and at a price to
every one after."* An incomplete memory is a worse answer once; a rotting one is a worse
answer forever.

**So the real gap is that none of the three questions asks whether the fact is something any
competent reader already knows.** The fix is a fourth question, not a looser third one, and it
is not in this release because it would be derived from the cases that exposed it. What it
needs, pre-registered here so it can fail: a `common` question, a fourth batch of cases
written before it is measured, and the same derive-on-one-set-report-on-another rule. That
measurement is `docs/results/2026-09-25-window/memory.md`.

## 4. What this does to the substitution claim

`docs/results/2026-09-24-fifty-v2/substitution.md`, under the 0.3.0 policy (paper Section
5.13):

| | Evaluator, shipped | Evaluator, plain 0.5 cut | `claude-opus-5` |
|---|---|---|---|
| Agreement with the bench labels | 197/211 | 202/211 | 204/211 |

With `redundant_page` reading the search point's 0.80 knob, the policy in force on 2026-09-24,
the same three columns are 190 / 202 / 204 (`docs/results/2026-09-24-fifty/substitution.md`).
The frontier model is ahead, by two decisions at a plain cut and seven under the shipped
policy, at **131x the cost per judgment**. The five decisions between the shipped policy and
a plain cut are `memory_write` (the loop points trade one case each way), the defect of
Section 3: located, with a named fix, rather than conservatism. `benchmarks/substitution.py`
computes its verdict sentence from the numbers, so the prose moves with them.

## 5. A blind second annotator, and what it confirms

`claude-opus-5`, given the same questions from the same builders, blind to the author's label
and to the evaluator's answer. 125 calls, **0.5622 USD**, 94 seconds.

| Point | n | A1 vs A2 | Cohen's kappa | A1 vs evaluator | A2 vs evaluator |
|---|---|---|---|---|---|
| memory_write | 50 | 96 % | 0.92 | 62 % | 62 % |
| redundant_page | 75 | 97 % | 0.94 | 91 % | 88 % |
| **all** | **125** | **97 %** | **0.96** | **79 %** | **78 %** |

Two things follow, and the second is the one that matters.

**The new cases are not idiosyncratic.** A model that never saw the labels agrees with the
author on 121 of 125, and the four it disputes are `mw-60`, `mw-86`, `rd-93` and `rd-118` -
recorded as disputed rather than resolved, as in the second batch.

**And the memory_write diagnosis survives its strongest test.** Kappa 0.92 with two disputed
cases out of fifty means almost nothing in that set is ambiguous, and the evaluator still
scores 62 %. Its errors are therefore not on hard cases - there are barely any - they are the
`specific` gate refusing a family nobody disputes. That is the same argument the fifty-case
run made from kappa 1.00, reproduced on a different batch with a different annotator sample,
and it is why Section 3 calls this a defect rather than conservatism.

The evaluator is as close to the blind annotator as to the author, 78 % against 79 %, which
is the comparison worth keeping: it is not being scored against the person who wrote its
questions.

## 6. What this does not settle

- **`memory_write` is 72/100 and the defect is documented, not fixed.** Anyone reading 72 %
  should read Section 3 with it.
- **One case moved between two recordings of the identical question.** `memory_write` on the
  first batch scored 16/16 in the recording of the morning and 15/16 in the re-recording of
  the afternoon, with no change to that question. The evaluator is not deterministic: the
  same state re-asked moves by up to 0.09 within a day
  (`docs/results/2026-09-25-window/README.md`), which is why every figure here is quoted from
  a recording.
- **Nothing here is end to end.** `docs/results/2026-09-24-agentdojo-e2e/` is that.

## Reproducing

```
sanchopanza bench benches/memory.jsonl benches/memory-b.jsonl benches/memory-c.jsonl \
  benches/retrieval.jsonl benches/retrieval-b.jsonl benches/retrieval-c.jsonl \
  --provider recorded --fixture fixtures/reverted.jsonl

python benchmarks/thresholds.py --derive docs/results/2026-09-24-third-batch \
  --eval docs/results/2026-09-24-fifty
```

Both free. Re-recording against the live model costs 0.0084 USD.
