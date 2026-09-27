# Fifty cases per binary point, a second annotator, and what a precision target costs

> **The headline is in `substitution.md`, and it was a by-product.** Building the second
> annotator meant asking a frontier generative model the same 211 judgments the evaluator
> answers, from the same question builders, blind to the labels. That is the cleanest
> substitution measurement in the repository: **96 % against 97 % agreement at a plain 0.5
> cut, two decisions apart (93 % under the policy of 2026-09-25), at 131x less cost per judgment and
> 10.9x lower latency.** Everything below is how the bench that made it possible was built,
> and what it says about thresholds. Paper Sections 5.10 and 5.13 report it.

Run of 2026-09-24. 212 new cases, `jev-1.13.0`, **0.0060 USD**, 28.4 millionths per decision -
the same per-decision figure as the public run and the 124-case run, now on a third
distribution.

The plan this run answers: *"fifty cases and a second annotator per new point, then
thresholds set the way Google sets them: per point, to a target precision, reported as
recall@X."*

**The answer is negative, which is the useful part: fifty cases do not support moving the
thresholds, and there is a number saying why.**

| | |
|---|---|
| New cases | 212, in `benches/{loop,memory,graph-build,retrieval}-b.jsonl` |
| Points taken to 50 | `goal_met`, `repeats_check`, `memory_write`, `recall`, `extract_gate`, `redundant_page` |
| Recording | `fixtures/new-points-50.jsonl`, replays for free; its re-recording `fixtures/new-points-50-v2.jsonl` is the one the tests replay (`docs/results/2026-09-24-fifty-v2/`), and both give 197/212 under the policy of 2026-09-25 |
| Cost of the evaluator | 0.0060 USD for 212 decisions, 28.4 millionths each |
| Cost of the second annotator | 0.7884 USD for the same 212 judgments, 3,719 millionths each |
| Ratio | **131x**, at 10.9x the latency and two decisions of accuracy at a plain 0.5 cut (seven under the policy of 2026-09-25) |

The original 124-case bench is untouched in its own files and its own fixture, so the run
published in paper Section 5.10 stays reproducible exactly as it was.

---

## 1. The bench was made harder on purpose, and it worked

At a plain 0.5 cut the first batch scored 14/14, 12/12, 14/14 and 16/16 on four of these six
points (under the loop policy, which speaks only from 0.70, `goal_met` is 12/14). A bench
nothing fails measures nothing, so these cases concentrate on the families that are real
failure modes rather than word games: partial completion that reads as complete, effort
narrated as result, corroboration mistaken for repetition, staleness, boilerplate that
nonetheless carries an instance, and facts that are true and durable and still not worth
storing because the source is already in hand. Each file's header names its families.

Agreement on the new cases under two policies and at a plain 0.5 cut. "2026-09-24" is the
policy in force that day, with `redundant_page` reading the 0.80 knob it shared with the search
point; "0.3.0" is the shipped policy, with its own `adds_nothing` = 0.59.

| Point | n | Policy of 2026-09-24 | 0.3.0 policy | At a 0.5 cut | AUC | Brier | ECE |
|---|---|---|---|---|---|---|---|
| extract_gate | 34 | 30/34 | 30/34 | 30/34 | 0.97 | 0.071 | 0.073 |
| goal_met | 36 | 34/36 | 34/36 | 35/36 | 0.99 | 0.038 | 0.109 |
| memory_write | 34 | 26/34 | 26/34 | 31/34 | 0.99 | 0.095 | 0.227 |
| recall | 36 | 36/36 | 36/36 | 36/36 | 1.00 | 0.008 | 0.076 |
| redundant_page | 34 | 26/34 | 33/34 | 33/34 | 1.00 | 0.035 | 0.139 |
| repeats_check | 38 | 38/38 | 38/38 | 37/38 | 1.00 | 0.030 | 0.133 |
| **total** | **212** | **190** | **197** | **202** | | | |

The loop points are scored at `Thresholds.saturated` = 0.70, the only cut `points/loop.py`
reads. There the policy and the 0.5 cut differ by one case each way: `gm-19` (p 0.66, true)
stays silent under the policy, and `rp-37` (p 0.50, false) is a false alarm only at 0.5.

On these harder cases the policy of 2026-09-24 trails a plain cut by twelve decisions, all of
them on `memory_write` (26 against 31) and `redundant_page` (26 against 33); the loop points
trade one case each way and net to zero. AUC is 0.97 to 1.00 everywhere, so no error is an
ordering error.

The two gaps have different causes, which the third batch
(`docs/results/2026-09-24-third-batch/`) separated with 125 more cases. `redundant_page` was
reading the search point's 0.80, a knob serving two points; its own threshold, derived to a
90 % precision target, is 0.59 and scores 33/34 here, which is the 0.3.0 policy. `memory_write`
is not a threshold at all: its `specific` question refuses standing client instructions that
`durable` scores 0.80 to 0.88, a structural defect that no cut on the same answers fixes. Under
the 0.3.0 policy the gap to a plain cut is five decisions, and net of the loop points' trade
all five are `memory_write`.

Every error the policy makes that the 0.5 cut does not is a refusal to act: 14 such cases
against 2 the other way under the policy of 2026-09-24, and 7 against 2 under 0.3.0.
`memory_write` fails only by declining to store something it should have stored;
`redundant_page` fails only by keeping a page it could have dropped.

## 2. Five labels were changed on the question's own criteria, and both sets of numbers are given

On the question's own criteria, not because the model disagreed. Under the policy of
2026-09-24, with the original labels the policy scores 185/212 and a 0.5 cut 197/212; with the
changed ones, 190 and 202. The evaluator's answers were not re-run and did not change.

**`rd-19`, `rd-23`, `rd-35`, `rd-42` (drop to keep).** They were authored on the theory that
a page with no bearing on the purpose "adds nothing". The question asks whether the text
carries *"no new figure, date, name, outcome, qualification or source"* that `known` lacks,
and all four carry several: a magnitude and a depth, a founding year and a headcount, a fleet
size, a set of metro lines. They are off-purpose, not redundant. `decide_redundancy` is never
handed a relevance signal, because dropping an off-topic page is page triage's job and triage
runs first; the original labels were the annotator making one point do two jobs.

The check that this followed the criterion and not the model: after relabelling, **AUC on
`redundant_page` rises from 0.97 to 1.00**. Moving labels to match a model does not generally
make its ordering perfect. `rd-15` in the first batch stays `drop` and is not the same case -
it carries earthquake safety advice and no fact of any kind, so it satisfies the criterion.

**`eg-41` (skip to extract).** A cadastral reference names one specific property and the
chunk states its surface, its year and its share, which is exactly "names at least one
instance and says something about it".

**`eg-47` was left alone** although the evaluator missed it at confidence 0.68. It is a
breadcrumb naming a resolution number and no company or person, and the question's `false`
side lists section paths explicitly. The label is arguable both ways, and moving an arguable
label to match the model is how a bench stops measuring anything.

## 3. What a precision target actually costs, which is the result

`benchmarks/thresholds.py` derives a threshold on one result set and reports every number
from another, and requires the **95 % Wilson lower bound** of precision to clear the target
rather than the point estimate. The second rule is what turns "target precision" into a claim
that can fail, and it changes the answer completely.

Deriving on the observed precision instead, as the plan implied, produces thresholds of
0.13, 0.23 and 0.08, and out of sample two of six points miss their own 90 % target by 10
and 11 points. That is not a threshold, it is an artefact of reading 100 % off a dozen cases.

With the lower bound, the sample-size floor is pure arithmetic:

| Target precision | Acted cases needed at perfect observed precision | Labelled cases per point |
|---|---|---|
| 80 % | 16 | about 32 |
| 90 % | 35 | about 70 |
| 95 % | 73 | about 146 |

**Fifty cases per point supports an 80 % precision target and nothing above it.** The plan
asked for fifty cases and then for thresholds at a target precision, and the two halves of
that sentence are inconsistent for any target worth having.

Deriving on the new cases and reporting on the original ones ("Shipped" is the policy of
2026-09-24):

| Point | Acts by | Shipped | Target | Derived | Precision (held out) | Recall | Agreement derived / shipped |
|---|---|---|---|---|---|---|---|
| goal_met | true | 0.70 | 80 % | 0.34 | 100 % | 100 % | 14/14 / 12/14 |
| repeats_check | true | 0.70 | 80 % | 0.51 | 100 % | 100 % | 12/12 / 12/12 |
| recall | skip | 0.25 | 80 % | 0.13 | 100 % | 100 % | 14/14 / 14/14 |
| memory_write | store | 0.70 | 80 % | unreachable at n=34 | - | - | - / 11/16 |
| redundant_page | drop | 0.80 | 80 % | unreachable at n=34 | - | - | - / 14/16 |
| extract_gate | skip | 0.25 | 80 % | unreachable at n=34 | - | - | - / 15/16 |
| any point | | | 90 %, 95 % | unreachable at this n | - | - | - |

Three of six points reach an 80 % target. For `repeats_check` and `recall` the derived
threshold scores exactly what the shipped one scores out of sample, so there is nothing to
change. For `goal_met` it does not: the derived 0.34 scores 14/14 where the shipped 0.70
(`Thresholds.saturated`, the only value `points/loop.py` reads) scores 12/14. That threshold
does not move either. 80 % is the only target reachable at n = 36, and 0.34 moves in the
costly direction, declaring a goal met sooner; the shipped cut raises no false alarm on any of
the 50 loop cases and pays for it in recall. The three points that cannot reach the target
include both points carrying the whole policy gap.

**So no threshold moves in this run.** Not out of the standing caution, but because the
measurement says the sample cannot support the move. The two points that would benefit,
`memory_write` and `redundant_page`, are precisely the two where the evidence is thinnest.
The third batch supplies it for `redundant_page`: 75 cases built toward `drop` derive 0.59 at a
90 % target, which is the 0.3.0 policy (`docs/results/2026-09-24-third-batch/`, Section 2).

## 4. The second annotator, and the thing it separated

Annotator 1 is the author, who labelled every case before any decision was run. Annotator 2
is `claude-opus-5`, given the same question and the same criteria the evaluator receives -
rendered from the package's own question builders, so the comparison is against the literal
question and not a paraphrase - and blind to both the first label and the evaluator's answer.
Its labels are in `annotator-2.jsonl`; `benchmarks/agreement.py` reproduces the table.

The evaluator columns are given under both policies: the one in force on 2026-09-24 (this
directory's `results.json`) and 0.3.0 (`docs/results/2026-09-24-fifty-v2/`).

| Point | n | A1 vs A2 | Cohen's kappa | A1 vs evaluator, 2026-09-24 | A2 vs evaluator, 2026-09-24 | A1 vs evaluator, 0.3.0 | A2 vs evaluator, 0.3.0 |
|---|---|---|---|---|---|---|---|
| extract_gate | 34 | 91 % | 0.82 | 88 % | 85 % | 88 % | 85 % |
| goal_met | 36 | 97 % | 0.94 | 97 % | 100 % | 94 % | 97 % |
| memory_write | 33 | 100 % | 1.00 | 79 % | 79 % | 79 % | 79 % |
| recall | 36 | 100 % | 1.00 | 100 % | 100 % | 100 % | 100 % |
| redundant_page | 34 | 91 % | 0.80 | 76 % | 79 % | 97 % | 94 % |
| repeats_check | 38 | 100 % | 1.00 | 97 % | 97 % | 100 % | 100 % |
| **all** | **211** | **97 %** | **0.96** | **90 %** | **91 %** | **93 %** | **93 %** |

The 2026-09-24 columns score the loop points from `results.json`, which carries them at a
plain 0.5 cut; the totals are the same either way. Under 0.3.0 the evaluator agrees with
annotator 1 on 197/211 (93.4 %) and with annotator 2 on 196/211 (92.9 %).

One case, `mw-32`, exhausted its retries and carries no second label; it is excluded rather
than counted as agreement.

**The evaluator is as close to the blind annotator as it is to the author** - 91 % against
90 % under the policy of 2026-09-24, 92.9 % against 93.4 % under 0.3.0. That is the
comparison worth keeping: it is not being scored against the person who wrote its questions.

**And the second annotator separates two diagnoses that agreement alone confuses.**

- `memory_write` has **kappa 1.00**: the two annotators agree on all 33 cases, so none of
  them is ambiguous. The evaluator still scores 79 % under either policy. Its errors are
  therefore not on hard cases: they are the policy declining to store cases nobody disputes.
  The third batch locates the cause in the `specific` question, which refuses standing client
  instructions, and not in the 0.70 threshold
  (`docs/results/2026-09-24-third-batch/`, Section 3).
- `redundant_page` (kappa 0.80) and `extract_gate` (kappa 0.82) are the two lowest. Under the
  0.3.0 policy the only `redundant_page` error is `rd-33`, a disputed case; one of the four
  `extract_gate` errors, `eg-47`, is disputed.

Where both annotators agree (204 cases) the evaluator agrees with them 92 % of the time under
the policy of 2026-09-24 and 193 times, 95 %, under 0.3.0. Where they disagree (7 cases) it
sides with annotator 1 three times and annotator 2 four times under the first, four and three
under the second, which is what a coin does, and is the honest summary of those seven.

### The seven disputed cases, including one against the author

| Case | Point | Annotator 1 | Annotator 2 | Evaluator, 2026-09-24 | Evaluator, 0.3.0 |
|---|---|---|---|---|---|
| eg-25 | extract_gate | extract | skip | extract | extract |
| eg-35 | extract_gate | extract | skip | extract | extract |
| eg-47 | extract_gate | extract | skip | **skip** | **skip** |
| gm-50 | goal_met | true | false | **false** | **false** |
| rd-33 | redundant_page | drop | keep | **keep** | **keep** |
| rd-37 | redundant_page | drop | keep | **keep** | drop |
| rd-42 | redundant_page | **keep** | drop | keep | keep |

Three of these deserve saying out loud rather than burying:

- **`eg-47` and `gm-50` are cases this run counts as evaluator errors while the blind
  annotator agreed with the evaluator, not with the author.** `eg-47` was deliberately left
  unrelabelled in Section 2 as "arguable in both directions"; the second annotator
  independently took the other direction, which is evidence that it is arguable rather than
  evidence that the author was right. `gm-50` turns on whether a *multa* and an
  *indemnizacion* are the same thing, and the first batch's `gm-01` assumes they are. Both
  are kept as they are - a label is not changed because a model disagrees with it - and both
  are recorded here as disputed.
- **`rd-42` is the one that went against the author's own relabelling.** Section 2 relabelled
  it from `drop` to `keep` along with three siblings; the blind annotator, which never saw
  either label, said `drop`. It is the weakest of those four: a page explaining how to reach
  a building by metro is neither a restatement of the known address nor a page carrying facts
  bearing on it, so it fits neither side of the question cleanly. The other three
  relabels, `rd-19`, `rd-23` and `rd-35`, drew no dispute.

**This is not two independent human annotators**, and nothing here should be read as if it
were. Two failure modes it cannot see: a criterion that is wrong in the same way for a model
and for the author who wrote it in the model's idiom, and a case whose wording steers both.
A kappa of 0.96 between an author and a model given that author's own criteria is a weaker
fact than a kappa of 0.96 between two people. Where the paper uses these numbers it says so.

## 5. The second annotator is stable, and the one label that moved was already disputed

Re-running the annotator over the same 212 cases with the same prompts, as a second sample:
**210 of 211 labels identical, 99.5 %**. Exactly one moved, `gm-50`, from `false` to `true`.

`gm-50` is the case Section 4 had already recorded as disputed, because it was one of the
seven the two annotators labelled differently and it turns on whether a *multa* and an
*indemnizacion* are the same thing. Two independent signals - a disagreement between
annotators, and instability across samples of one annotator - landed on the same case without
being pointed at it. That is the best evidence available here that the disputed list is
picking out genuine ambiguity rather than noise, and it is why `benchmarks/annotate.py`
refuses to overwrite an existing label file and prints a stability report instead.

`docs/results/2026-09-24-fifty/annotator-2-rerun.jsonl` holds the second sample;
`annotator-stability.md` holds the comparison. The published numbers all come from the first
run, which was recorded before the second existed.

## 5b. What the annotator costs, and how it is metered

The cost in the table at the top, **0.7884 USD for 212 judgments**, is the metered second
sample (`annotator-usage.json`, with a per-call ledger in `annotator-usage.jsonl`). The first
sample, which produced the published labels, ran the same prompts and was not metered. Nothing
caches: the system prompt is about 60 tokens against a minimum cacheable prefix of 512 to
4096, so every one of the 212 calls reads zero from cache and pays full input price.

- **`benchmarks/meter.py`** is the one place that knows list prices and the cache
  arithmetic, shared by the annotator, `benchmarks/ab/run.py` and `benchmarks/cache/run.py`.
  A property check over 2,000 random usages and four models confirms it reproduces the
  benches' earlier arithmetic to the last float rounding. It refuses to price a model it does
  not know rather than defaulting, and its `summary()` always prints the cache line, loudly
  when `cache_read_input_tokens` is zero.
- **`benchmarks/annotate.py`** is the annotator, metered, writing `annotator-usage.json` and
  the per-call ledger beside the labels.
- **The authoritative number needs an Admin API key.** `Meter.cost()` is exact arithmetic
  over reported tokens at list prices; it is not a bill. The organization's Usage and Cost
  report is, and a normal `sk-ant-api...` key is refused by it with a 401 and the message
  *"The Admin API requires an Admin API key or an organization-scoped API key"* - verified,
  not assumed. The report is historical, so an Admin key would also give the billed cost of
  the first, unmetered sample.

## 6. What this does not settle

- `memory_collision` and `edge` are not extended here. They have four and three labels and an
  abstention band, so each has its own treatment. `docs/results/2026-09-24-fourth-batch/`
  takes both to fifty cases: `memory_collision` scores 46/50 with every branch firing, and
  `edge` commits 17 edges of which one is backwards. `docs/results/2026-09-24-collision/`
  reads `memory_collision` as two binary questions plus a `newer` comparison the harness does
  in code: both order perfectly (AUC 1.00), and on a bench of 52 built toward the acting
  branch the shipped cut catches **16 of 18 duplicates with zero false positives, lower bound
  81 %**.
- The 80 %-target result rests on 34 to 38 derivation cases and 12 to 20 held-out ones. The
  held-out halves are small enough that "100 % precision" there carries its own wide interval,
  by exactly the argument this file makes about the derivation half.
- Nothing here is end to end. Source redundancy end to end is
  `docs/results/2026-09-24-fixed-sequence/`, Section 3: handed 193 documents from a
  deliberately redundant corpus, it dropped 4, a null effect on cost.

## Reproducing

```
sanchopanza bench benches/loop-b.jsonl benches/memory-b.jsonl \
  benches/graph-build-b.jsonl benches/retrieval-b.jsonl \
  --provider recorded --fixture fixtures/new-points-50.jsonl

sanchopanza bench benches/loop-b.jsonl benches/memory-b.jsonl \
  benches/graph-build-b.jsonl benches/retrieval-b.jsonl \
  --provider recorded --fixture fixtures/new-points-50-v2.jsonl \
  --out docs/results/2026-09-24-fifty-v2

python benchmarks/substitution.py --results docs/results/2026-09-24-fifty-v2
python benchmarks/agreement.py --results docs/results/2026-09-24-fifty-v2 --benches benches
python benchmarks/thresholds.py --derive docs/results/2026-09-24-fifty --eval <other run>
```

All are free. The first two commands replay under the installed policy, so today they give
the 0.3.0 figures; this directory's `results.json` keeps the answers as scored on 2026-09-24. Re-recording against the live model costs 0.006 USD and needs
`TYPESAFE_API_KEY`.
