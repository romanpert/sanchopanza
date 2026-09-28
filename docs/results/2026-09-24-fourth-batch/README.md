# The fourth batch: the three points that had no sample

Run of 2026-09-24. 94 new cases take `facts`, `edge` and `memory_collision` to 50 each,
`jev-1.13.0`, **0.0080 USD**. Each of these points had twenty cases or fewer: `relate_facts`
16/20, `verify_edge` 15/17 when deciding on twenty cases, and `memory_collision` sixteen cases
across four labels with one branch, `duplicate`, that had **not fired in any run**.

A label with two instances has not been measured, it has been sampled from. All three of the
results below only became visible at fifty.

Re-recorded after pseudonymization hardening (2026-09-28): 17 cases whose text concerned
pseudonymized persons were reworded and asked again; `facts` moved from 35/39 to 36/40
(fa-19 now decides, right), nothing else changed its agreement.

| Point | at 16-20 cases | at 50 | what the sample shows |
|---|---|---|---|
| `memory_collision` | 14/16 | **46/50** | every branch fires; all four errors are safe |
| `edge` | 15/17 | **31/38** | 17 edges committed, 1 backwards; the policy reads direction first |
| `facts` | 16/20 | **36/40** when deciding | the defect is located and deliberately not patched |

## 1. `memory_collision`: the untested branch works

With ten cases of `duplicate`, the branch fires eight times and is right eight times. More important than the score is the shape of the errors:

| expected | predicted | n |
|---|---|---|
| keep_both | keep_both | 22 |
| replace | replace | 8 |
| flag | flag | 8 |
| duplicate | duplicate | 8 |
| duplicate | keep_both | 2 |
| replace | keep_both | 1 |
| flag | keep_both | 1 |

**All four errors land in `keep_both`** - store both, ask nobody, lose nothing. Not one wrong
`replace` (which silently deletes a stored fact) and not one wrong `duplicate` (which silently
drops a new one). On a four-label point with an abstention band, that is the asymmetry
invariant working exactly as designed.

Eight of these cases are triples: the same `new` and `stored` with `newer` set to true, false
and null, labelled `replace`, `keep_both` and `flag`. Nothing in the text distinguishes them -
recency comes from the harness's timestamps and is never asked of the decider, because this
model class reads dates as text. Scoring well on those is evidence the point understands it
is not being asked who is right.

## 2. `edge`: one backwards edge, and a policy that reads direction first

**What it commits.** On fifty cases the point commits **17 edges, 1 of them backwards**:
`ed-26`, `(Industrias Belmonte, audita a, Marquez y Asociados)` against a text that says
Marquez audits Belmonte. The first twenty cases, whose `reversed` label had two instances,
hold no backwards commit; with eleven instances one appears. A backwards
edge is the one error in this point that nothing downstream can catch - everything after it
reads the edge as fact. `tests/test_fourth_batch.py` pins 17 and 1.

**The policy order.** Read with `stated`'s confidence gate first, `reversed` fires **zero
times out of eleven**. The model does tell direction:

| case | stated | stated conf | direction | direction conf | verdict, `stated` first |
|---|---|---|---|---|---|
| ed-22 | 0.51 | 0.02 | **0.05** | **0.90** | review |
| ed-16 | 0.24 | 0.52 | 0.17 | 0.66 | review |
| ed-38 | 0.68 | 0.36 | 0.17 | 0.66 | review |
| ed-47 | 0.93 | 0.86 | 0.57 | **0.14** | **supported** |

On `ed-22` the decision contains *direction 0.05 at confidence 0.90* - the model knew, the
answer was paid for - and a policy that gates on `stated`'s confidence (0.80) before reading
`direction` abstains. And a reversed triple is
precisely the case where `stated` is unsure: the relation is there, but not as written.

`ed-47` is the mirror case. Direction 0.57 at confidence 0.14 is an honest *"I do not
know"*, and the `stated`-first order reads it as "the direction is fine" and commits.

The shipped `decide_edge` makes two changes, both following the package's own invariant 2 -
the costly direction needs more confidence, and committing is the costly direction here:

1. read `direction` first, and return `reversed` on a confident negative;
2. refuse to commit when `direction` is present but not confident.

| policy | agreement when deciding | `reversed` caught | wrong edges committed | held-out 20 cases |
|---|---|---|---|---|
| `stated` first | 28/37 = 76 % | **0/11** | ed-26 | 14/20 |
| direction first (shipped) | **31/38 = 82 %** | **4/11** | ed-26 | **15/20** |

**Both rows replay the identical recorded answers**, so not one decision differs and none of
the difference can be sampling. It is the cheapest kind of improvement there is, and it is
invisible while a label has two instances.

**The alternative, measured and not shipped.** The `stated` question's own criteria say a
text stating the reverse is `false`, so one candidate fix was to rewrite it to ask about
either direction. Measured, that makes things **worse**: wrong committed edges go from one to
two.

## 3. `facts`: located, and deliberately not patched

36/40 when it decides, and it abstains on 10 of 50.

| expected | predicted | n |
|---|---|---|
| conflict | conflict | 17 |
| agree | agree | 16 |
| unrelated | *abstained* | 7 |
| unrelated | unrelated | 3 |
| conflict | *abstained* | 2 |
| agree | *abstained* | 1 |
| unrelated | agree | 2 |
| agree | conflict | 1 |
| conflict | agree | 1 |

**It never confuses `conflict` with `unrelated`, in either direction.** Its entire problem is
that it barely reaches `unrelated`: 3 of 12 such cases, abstaining on 7 and calling 2 `agree`. The likely cause is one line: `unrelated` is the only
one of the three options whose Choice criteria carry **no examples**, while `agree` and
`conflict` both do. An option nobody illustrated is an option the model does not pick.

It is not fixed here. Adding examples derived from the cases that exposed the gap would make
the next score meaningless, and two obvious patches measured the same day (section 2 and
`../2026-09-24-third-batch/`) made things worse. What it needs is pre-registered: examples written for the
`unrelated` option, then a fifth batch of `facts` cases written before the change is measured.

Until then the honest statement for anyone integrating it: **when it speaks it is right 90 %
of the time, it is silent on a fifth of cases, and it is systematically silent on one of its
three labels.**

## 4. What this run says about the method

Three points, three different outcomes, and none of them was predictable from the small
sample: one was fine and nobody knew, one had a policy defect and an optimistic small-sample
figure, one has a question defect. The common cause is the same in all three - **a label with two or four
instances had never been tested, only sampled from** - and the cost of finding all of it was
0.0080 USD plus an afternoon of writing cases.

The counterpart: **two of the three obvious fixes made things worse when measured and were
not shipped**, here and in `../2026-09-24-third-batch/`. The one that survived is the one that changed no
question and no threshold, only the order in which a policy reads answers it had already paid
for.

## 5. A blind second annotator, and it is harder on us than the last one

`claude-opus-5`, 94 calls, **0.3985 USD**. `benchmarks/annotate.py` refuses to run on a point
that has no rubric in `POINTS`, because a run that annotates nothing - zero cases, an empty
label file, a successful exit - looks exactly like a run where everything agreed.

| Point | n | A1 vs A2 | Cohen's kappa | A1 vs evaluator | A2 vs evaluator |
|---|---|---|---|---|---|
| memory_collision | 34 | 91 % | 0.87 | 94 % | 97 % |
| edge | 30 | 90 % | 0.85 | 43 % | 53 % |
| facts | 30 | 87 % | **0.80** | 70 % | 60 % |
| **all** | **94** | **89 %** | **0.88** | 70 % | 71 % |

Three things to read carefully, and two of them are against us.

**`edge`'s 43 % is not the 82 % above and both are honest.** This table counts an abstention
as a disagreement; the bench's "agreement when deciding" does not. A point that abstains on a
quarter of cases has two true numbers and neither should be quoted alone.

**`facts` has the lowest kappa here, 0.80, and the disputes are exactly where its defect is.**
Every one of the four - `fa-30`, `fa-44`, `fa-46`, `fa-48` - is a case the author labelled
`agree` and the blind annotator labelled `unrelated`. Two annotators do not share the line
between "one fact bears on the other" and "different attributes of the same thing". That is
**a question-definition problem, which more cases of the same shape will not fix.** It also
means part of the "`facts` barely reaches `unrelated`" finding rests on labels that are
themselves contested.

**One of the author's labels is probably wrong, and not because a model disagreed.** `ed-41`
asks for `(Sociedad Y, recurrio, resolucion 45/2024)` against *"La sancion fue recurrida y el
tribunal la redujo"* - a passive with no agent. The text does not say who appealed, so the
question's own criterion makes it `unsupported`, which is what both the blind annotator and
the evaluator said. It is recorded here as disputed, with `ed-33` alongside it; the label is
kept as written.

## 6. What this does not settle
- **`facts` and `edge` remain the two weakest points in the package**, at 90 % when speaking
  and 82 % when deciding, and both with a named defect rather than a fix.
- **`select_tools` is measured elsewhere**, in `../2026-09-24-tools/`, and it is the one that
  can cost money.
- **`entity` and `dependency` are still at 24 and 20 cases**, both at 100 %, which after
  today should be read as "not yet measured on hard cases" rather than as a score.

## Reproducing

```
sanchopanza bench benches/graph.jsonl benches/graph-c.jsonl benches/memory.jsonl \
  benches/memory-d.jsonl benches/graph-build.jsonl \
  --provider recorded --fixture fixtures/fourth-batch.jsonl
```

Free. Re-recording against the live model costs 0.0080 USD.
