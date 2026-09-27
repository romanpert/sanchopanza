# The evolution interface

`sanchopanza.evolve` is what an outer self-improvement loop needs in order to tune the squire
without breaking the method this repository is built on. It targets loops in the style of
RRSI (*Regularized Recursive Self-Improvement of Agent Harnesses*, arXiv 2609.24972): a
proposer edits a harness, each candidate is scored on an evolution set, and the incumbent is
replaced only by the best **admissible** candidate. RRSI's result is that the regularized
loop gains less on its evolution set and transfers better out of distribution. The package
applies that result. It does not include a proposer: a proposer can be an LLM, a grid, or a
person, and none of them should have to reimplement the rules below.

Everything in it replays recordings and costs nothing. The one exception is a live decider
that is passed in explicitly.

## The pieces

| Piece | What it is |
|---|---|
| `Knobs` | A frozen, JSON-serializable snapshot of everything a loop may tune: every `Thresholds` value, question-wording overrides (`"point:question"` to text), the tool catalog's `about` texts, and the `ToolWindow` flags `wait_on_deferred` and `scan_untrusted`. `from_squire`, `from_thresholds`, `to_dict` and `from_dict` are provided. Unknown names raise instead of being ignored. |
| `Edit`, `diff(a, b)` | Atomic edits: one kind, one key, `before -> after`. Kinds are `threshold`, `question`, `about` and `flag`. `invalidates_recordings` is True for `question` and `about`. `Knobs.apply` refuses a stale edit, meaning one proposed against a different incumbent. |
| `Split.by_hash` | Splits cases into disjoint `evolve`, `holdout` and `fresh` sets using a salted hash of each case id. The assignment is fixed before anything is scored and does not depend on file order. |
| `Evaluator` | Scores a snapshot on one part of the split by replaying the recording through `eval.bench.run_bench`, so the same `Squire` methods production calls do the scoring. It counts and journals every holdout read, and allows only one fresh read. |
| `noise_floor`, `drift_magnitude` | The gain a candidate has to beat (formula below). |
| `admit` | Returns an `Admission` that lists every condition that failed. |
| `edit_budget` | Cosine-annealed limit on atomic edits per candidate. |
| `Ledger` | Append-only JSONL of tried hypotheses, with `already_refuted`. |
| `leak_check` | Rejects wording edits that quote the bench. |
| `dormant_gates` | Reports gates whose outcome never moved over N journaled decisions. It never removes anything. |

### What the `Evaluator` refuses

Each refusal blocks a way a loop could score an edit it never actually tested.

- **`RecordingInvalidated`.** The snapshot rewords a question or an `about` text. That changes
  the request, so `key_of` changes too and the recording can't answer it. The only honest
  score is a live re-ask, which is allowed only when `live=` is passed. Wrap that live decider
  in `RecordingDecider` so the re-ask becomes a recording.
- **`UnexercisedEdit`.** The edit changes something the bench runner never builds (catalog
  `about` texts, window flags) or something it overrides (`allow_upgrade`, `max_decisions`,
  `max_usd`). If these were scored, the loop would see "no change" for an edit that never ran,
  and it would keep the edit for free.
- **`RecordingMiss`.** A replayed decision came back with no answers. The policy then falls
  back to its default. On a gate whose default happens to be the right label, that fallback
  scores as a hit. In the test bench, an empty recording scores 5/10 on defaults alone.
- **`FreshSplitSpent`.** The fresh split is read once. `score_fresh(final, base)` declares
  both snapshots in that single read. A comparison is fine; coming back later with a third
  snapshot is not.

Every `Score` includes `outcomes`, the per-case predictions, so a loop can tell an **inert**
edit from a neutral one. It also includes `costly_errors`, the wrong decisions made in the
acting direction (stored, dropped, skipped). Agreement treats both error directions the same;
every policy here does not. A loop should hold `costly_errors` at or below the incumbent's
count. `admit` does not enforce this because its signature is the RRSI one, so the demo adds
it as a reason.

## How an RRSI-style loop uses it

```python
split = Split.by_hash(cases, holdout=0.25, fresh=0.25)
ev = Evaluator(split, recording=RecordedDecider.from_file(fixture), base=Knobs.from_thresholds(Thresholds()))
incumbent, inc = base, ev.score(base, "evolve")
floor = ev.noise_floor(base, "evolve", drift=measured_reask_deltas)

for r in range(T):
    budget = edit_budget(r, T, b_max, b_min)
    for candidate in proposer(incumbent, ledger):          # yours
        edits = diff(incumbent, candidate)
        if not all(leak_check(e, split.evolve).ok for e in edits):   # before scoring
            ledger.record(edits, ..., verdict="leak"); continue
        if ledger.already_refuted(edits, incumbent=incumbent.fingerprint()):
            continue
        s = ev.score(candidate, "evolve")
        a = admit(s.accuracy, inc.accuracy, delta=floor.delta,
                  cost_delta=s.cost_per_case - inc.cost_per_case,
                  beta0=..., beta1=..., edits=edits, budget=budget)
        ledger.record(edits, ..., verdict="admitted" if a.admitted else "refuted", reasons=a.reasons)
    best = the admitted candidate with the largest gain, if any
    confirm best on "holdout" (each read is counted), then promote it and recompute the floor

final, shipped = ev.score_fresh(incumbent, base)           # once
```

`examples/evolve/demo.py` is this loop with a proposer that sweeps one threshold per round.
It runs over the fifty-case bench (`benches/*-b.jsonl`, `fixtures/new-points-50-v2.jsonl`) and
costs 0 USD.

## Regularizers and the method rules they encode

| RRSI regularizer | Here | Existing rule it enforces |
|---|---|---|
| Edit budget, annealed `b_max -> b_min` | `edit_budget`, and `admit(..., budget=)` | Two gates on one number are one gate (`policy.py`). A change is only attributable if it is atomic. |
| Ledger of refuted hypotheses | `Ledger.already_refuted` | "Tried, measured and reverted" (`points/memory.py`, the `specific` floor). A refuted change stays refuted, and the record of it is kept. |
| Forced exploration on stagnation | Not built in. It belongs in the proposer. | The ledger records why each candidate failed. Use it to explore somewhere new, not to lower the bar. |
| Leak critic, before evaluation | `leak_check`: shared word 4-grams, numbers, multi-word names and case ids. Anything already present in `before` is exempt. | Never fix on the cases that exposed the failure. |
| Noise floor, calibrated by re-evaluating the base | `noise_floor` plus `Evaluator.flips_under_drift` | Benches are small, so one case is worth 1 to 2 points. The provider drifts up to 0.09 on identical input within a day (`docs/results/2026-09-25-window/` section 7). |
| Cost rule `dcost <= beta0 + beta1 * dscore` | `admit(..., cost_delta, beta0, beta1)` | Spending is deliberate. Threshold and flag edits leave the calls unchanged, so their cost delta is 0 by construction. |
| Pruning components without recent gain | `dormant_gates`, which only reports | Fail-open, and the squire can only improve an agent. A guard that never fired on benign traffic may be the one that matters on the bad day. |
| (not in RRSI) | `RecordingInvalidated`, `RecordingMiss`, `UnexercisedEdit` | Every number comes from a recording. Changing wording invalidates the recording. A default must not be scored as an answer. |
| (not in RRSI) | Holdout read counter, single fresh read | Derive on one set and report on another (`benchmarks/thresholds.py`). |

### The noise floor, exactly

```
sampling = (high - low) / 2           95 % Wilson half-width of the incumbent's accuracy at n
m        = drift_magnitude(deltas)    nearest-rank 95th percentile of |re-ask deltas|
flips    = cases whose correctness changes when every Truth answer moves by +m or -m,
           counted by replaying through the real policy (Evaluator.flips_under_drift)
delta    = min(1, max(sampling + flips / n, 1 / n));   delta = 1 when n = 0
```

The two terms are added because sampling noise and provider drift are separate sources, and
either one alone can produce a gain of this size. The Wilson width is the unpaired one, even
though candidate and incumbent are scored on the same cases. A paired test
(`eval.stats.mcnemar`) would admit more candidates. The loop compares many candidates against
one split over many rounds, though, and that reuse inflates false admissions in a way no
single paired test corrects for. Choosing the stricter width is how this loop gains less.

Choice and Score answers are not perturbed in the drift term, because their drift has not been
measured here. On points driven by Choice or Score answers, the floor understates the drift.

## Overfitting risks specific to this repository

1. **Small n.** The fifty-case bench's evolve split has 112 cases, so one case is 0.9 points.
   The floor there is 0.123, about 14 cases: 0.051 from sampling and 0.071 from drift, because
   8 of the 112 cases change correctness at +/-0.09. A threshold sweep never clears that.
   Separately, `benchmarks/thresholds.py` shows that 50 cases per point support an 80 %
   precision target and nothing higher. Treat any evolved threshold as a candidate for
   derivation, not as a derivation.
2. **Provider drift.** A decision within about 0.1 of its cut is a coin flip between runs. A
   gain that rests on those cases is drift. The floor prices it in, and it also means a live
   re-ask of a reworded question cannot be compared against a recording from another day.
3. **Edits that are not atomic in effect.** Some edits look atomic but aren't.
   - **Joint calls.** One request answers several questions: `loop` asks `goal_met` and
     `repeats_check`; `memory_write` asks `durable`, `specific` and `derivable` (plus `common`);
     `triage` asks four; `tools` asks one question per group plus `deferred`. Rewording one
     question changes the state the model reads, so it **moves the other answers in the same
     call**. A `question` edit counts as one edit, but its effect reaches every question in
     that call, and the recording for all of them is invalidated together.
   - **Shared knobs.** `act` is read by `recall`, `extract_gate`, `memory_collision`, triage's
     source-kind filter and `routing`. One edit to it has five effects. The
     repository split `adds_nothing`, `deferred` and `derivable` out of shared knobs for
     exactly this reason.
4. **A knob the scorer does not read is inert on the bench.** The runner scores each point
   with the thresholds its policy applies (`tests/test_policy_in_force.py`); a bench that
   scored at a fixed 0.5 cut would make every threshold sweep tune nothing. Check every knob
   against this before trusting a sweep: `derivable` was inert at every value tried, and
   `run_bench` forces `allow_upgrade=True`. An inert edit is refuted as inert, never admitted
   as "no harm".
5. **Adaptive reuse of the holdout.** Each holdout read is logged with the snapshot that was
   read. If the count grows with the number of candidates rather than the number of
   promotions, the holdout has become a second evolution set.
6. **Symmetric score, asymmetric policy.** Agreement can go up while more errors land in the
   costly direction. The widened `specific` gate reached 88/100 on `memory_write` while
   storing 8 facts that should have been skipped, which is why it is not shipped
   (`docs/results/2026-09-24-after-fix/`). Watch `Score.costly_errors`.
7. **Missing recordings.** A case whose recording is missing scores the fail-open default,
   which often looks right. The evaluator raises on it unless you pass `allow_missing=True`.

## What NOT to tune automatically

- **Security boundaries**: `guard`, `injection`, the code deny-lists, and `scan_untrusted`.
  Without the scan, 24 of 56 injection payloads widened the tool window; with it, 0 of 56
  (`docs/results/2026-09-25-window/`). A benign bench cannot show the cost of weakening them,
  so a loop will always find them "dormant" or "free".
- **Caps and plumbing**: `max_usd`, `max_decisions`, `max_windows` and `audit`. These are
  spending and audit controls, not quality knobs.
- **Question and `about` wording, unattended.** Each trial costs money, can't be reproduced,
  invalidates recordings for every question in the same call, and is where leakage happens.
  If wording is evolved at all, do it with a live `RecordingDecider`, `leak_check`, fresh
  labels, and a person reviewing the diff.
- **Thresholds below the sample-size floor**: `window_add`, whose derivation on 13 positives
  is on record as impossible, and any point with fewer acted cases than its precision target
  requires.
- **Knobs the bench does not exercise**: `allow_upgrade` anywhere `run_bench` sets it, and any
  knob an `UnexercisedEdit` refusal names.
- **Anything whose only evidence is the split that exposed the failure.**

## An example: the demo as run on 2026-09-25

An example of the loop's output, not the current defaults. It ran against the `memory_write`
policy of that day, a conjunction with `remember` at 0.70. The shipped default is one cut of
0.54 on the weakest margin, derived under a pre-registration on half of the 100 cases and
judged on the other half and on 108 unseen ones (`docs/results/2026-09-27-memory-write-cut/`),
so a rerun of the demo starts from that incumbent.

```
cases: 212; split evolve/holdout/fresh = (112, 46, 54)
incumbent (shipped) on evolve: 103/112, costly-direction errors 1
noise floor: delta 0.123 = Wilson half-width 0.051 + drift 0.071 (8 cases flip at +/-0.09)
round 1 - sweep remember - edit budget 3
  remember 0.70 -> 0.55: 106/112 (+0.027, costly 1) REFUTED - gain +0.0268 does not exceed the noise floor 0.1229
...
ledger: 25 trials, 25 refuted
holdout reads: 0
no candidate cleared the noise floor: the shipped thresholds stand.
```

In that example the best move the sweep found was `remember` at 0.55, worth 3 cases, less
than a quarter of the floor, so nothing was admitted. The same direction later held under
the stricter procedure the loop cannot replace: a pre-registered derivation to a precision
target with a held-out half, which is how the 0.54 default was set. The holdout was never read, and the fresh split is still unspent.
