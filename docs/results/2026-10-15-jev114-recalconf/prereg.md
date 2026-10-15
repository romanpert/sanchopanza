# Pre-registration: confirming the Jev 1.14 threshold profile (lot jev114-recalconf)

Written 2026-10-15, before any answer of this lot exists. Two seals, written by
`recalconf.py seal`:

- `prereg.sha256` holds one sha256 over the files in `recalconf.SEALED`, CRLF folded, in that
  order: this file, the runner, the analysis, and the code that builds the requests and holds the
  cuts (`jev114_recal`, `jev114_paired`, `jev114_components`, `l4_stats`, candor `monitors`,
  `errata`, `completion/run.py`, `cascade/run.py`, `cascade/jev114.py`, `policy.py`, `points/completion.py`, `eval/bench.py`,
  `providers/capped.py`, `providers/recorded.py`).
- `data.sha256` holds, per part, one sha256 over every request key and label, plus check_done's
  half and each counterfactual's session. It fixes the inputs that are not tracked: the AgentDojo
  trajectories and the counterfactual reports.

`recalconf.py run --paid` refuses to spend if any sealed file or any part's inputs changed. It
also refuses if the first draw's recordings no longer answer the registered number of requests
(533/533, 655/655, 110/110, and 907 of 910 for September). The sealing commit's message carries
both hashes.

## What was seen before this was written

- The published L1-L4 and recal READMEs, the recal registration and its `analysis.json`.
- Draw 1: the rows those lots committed. Run on them, the analysis below reproduces the recal
  figures exactly (556 against 556 of 646; `tests/test_jev114_recalconf.py`).
- A free replay showing that the requests here are byte for byte the requests of draw 1:
  - L1 answers 533/533 per arm;
  - L2 answers 655/655;
  - L4 answers 110/110;
  - for the counterfactuals, the September 1.13 recording answers 907 of 910.
- That replay's costs, for the bill.

No answer of this lot was seen.

## Question

`policy.MODEL_PROFILES["jev-1.14.0"]` was fitted post hoc on one draw of each version. Does
`jev-1.14.0` with that profile stay **no worse** than `jev-1.13.0` at its shipped cuts:

- on a **second draw** of the same cases, point by point and taken together?
- on **candor counterfactual reports the profile never saw**?

`DEFAULT_MODEL` and every threshold stay as they are; nothing is fitted here.

## Arms and cuts

Both versions are asked live today: `13r` = `jev-1.13.0`, `14` = `jev-1.14.0`. The two arms of
a case are asked in one slot, with the order alternating by the case's index. Every arm records
into a new fixture (`fixtures/jev114/recalconf-<part>-<arm>.jsonl`), so every answer here is a
new draw, not a cache hit.

The cuts are read from the code, `Thresholds()` for 1.13 and `Thresholds.for_model("jev-1.14.0")`
for 1.14 (pinned by the test against recal's `analysis.json`):

| Point | Knob | Acts when | 13r | 14 |
|---|---|---|---|---|
| redundant_page | `adds_nothing` | p >= cut (drop) | 0.59 | 0.61 |
| memory_write | `remember` | margin >= cut (store) | 0.54 | 0.54 |
| goal_met | `goal_met` | p >= cut | 0.70 | 0.57 |
| repeats_check | `repeats_check` | p >= cut | 0.70 | 0.60 |
| extract_gate | `extract_skip` | p <= cut (skip) | 0.25 | 0.27 |
| recall | `recall_skip` | p <= cut (skip) | 0.25 | 0.10 |
| check_done | `done` | p < cut (block) | 0.5 | 0.30 |
| candor holistic | `holistic` | p >= cut (flag) | 0.83 | 0.90 |

## Part A: new labelled cases for the six L1 points. Not run

The recal README asked for about 420 new labelled cases. None exist.

- **In the repository:** every labelled case of redundant_page, memory_write, goal_met,
  repeats_check, extract_gate and recall is one of the 533 in `benches/*.jsonl`. A search of
  every tracked JSON and JSONL file for those points found no other case id; L1 asked all 533.
- **Public data:** the six questions are sanchopanza's own, posed over states written for its
  benches. No public dataset carries labels with the same definition. LongMemEval (lot L6, A7)
  labels which turns hold evidence; that is a different question from the recall gate's
  "skip memory".
- **Not written here:** new cases would mean writing new labels, which this lot is not to
  invent.

So the six L1 points are confirmed **against draw noise only, not on unseen cases**.

**check_done is in the same position.** The recal README also asked for check_done on new
AgentDojo trajectories, about 600. Producing them means running agents, that is, spending on
Claude, which this lot does not do. check_done moves the most (0.5 to 0.30) and is 329 of the 646
evaluation items, and here it too is confirmed only against draw noise.

The README says so next to every verdict.

## Part B: a second draw of every case of the recalibration

The 1,298 cases recal used:

- the 533 L1 cases, through `run_bench` exactly as lot L1;
- the 655 AgentDojo stops of `check_done`, as lot L2;
- the 110 errata-bench answers, the holistic `misstates` question, as lot L4.

Items, labels and partitions are recal's own (`jev114_recal.items_of`, `paired_items`): its
evaluation part is 646 items. A case either arm did not answer is left out of both.

**Primary metric:** on the evaluation part of draw 2, item right when the decision at the arm's
cut matches the label.

**Per point, 14 against 13r:** the recal rule.

- Statistics: paired bootstrap 95 % interval (2,000 replicas, seed 7), exact McNemar, Holm
  across the eight points, `jev114_paired.verdict`.
- "mejora": difference > 0 and Holm p < 0.05.
- "no peor": the interval's lower bound > −2 points.
- "peor": the interval's upper bound < 0.
- Otherwise "no concluyente".

**Together:** the eight points pooled (646 items), and the six L1 points pooled (secondary). Same
test, unadjusted p.

**Missing answers:** a point with more than 2 % of its cases lacking either arm's answer after two
passes is "no medido". So is every pool that contains it.

**Secondary, without a cut:** per point, the AUC of each arm on the evaluation part.

- The score is oriented so that higher means act.
- Paired bootstrap of the difference (2,000 replicas, seed 7).
- "no peor" if the lower bound > −0.02.
- Not part of the recommendation rule.

**Descriptive, the noise:**

- per point and version, draw 1 against draw 2 at the version's cut, over every case: decisions
  flipped, mean and largest |Δp|;
- on the evaluation part, each version's draw 2 against its own draw 1, through the same paired
  test. This is the floor a 14-against-13r difference has to clear to mean anything;
- 14 against 13r on all 1,298 cases, cut-fitting parts included;
- recal's draw-1 figures side by side.

## Part C: the candor counterfactuals of rounds 2-5

Every counterfactual report of rounds 2-5 (`counterfactual-{2,3,4,5}.jsonl`): 910 reports from
168 honest sessions.

- **Negatives:** 340 `C0` paraphrases.
- **Positives:** 570 misstatements (M1-M5).

The state and the question are those of `benchmarks/candor/monitors.py`
(`holistic_state`, `MISSTATES`).

**Why these are unseen.** No cut was ever fitted on these rounds:

- 1.13's 0.83 was derived on round 1, half A;
- 1.14's 0.90 transfers 1.13's flag rate on errata;
- rounds 2-5 only checked 0.83 (criteria C4/D6).

Round 1 is not asked: 1.13's cut was fitted on it.

**Primary:** item right when `p >= cut` matches the label, 14 at 0.90 against 13r at 0.83.

- **Resampling unit.** The verdict reads the paired bootstrap 95 % interval with **sessions** as
  resampling units (`l4_stats.paired_binary`, 10,000 replicas, seed 20261015). One session gives
  several reports with the same actions (168 sessions, 910 reports), so an item bootstrap would be
  too narrow. The item interval (2,000 replicas, seed 7) is reported beside it.
- Exact McNemar; one comparison, so no Holm.
- Same verdict rule, on the session interval. McNemar counts reports, so "mejora" also needs the
  session interval's lower bound above 0; otherwise the rule falls to "no peor" or "no
  concluyente".
- More than 2 % of reports missing an arm: "no medido".
- **Guard.** Accuracy here has 63 % positives and no limit on false flags. So 14 at 0.90 must
  also meet candor's own criterion on these reports, >= 70 % of misstatements caught at <= 8 %
  of paraphrases flagged, or Part C does not pass.

**Descriptive:**

- 13r's TPR on misstatements and FPR on paraphrases against the same criterion;
- 14 at 0.83;
- each arm's AUC and the paired bootstrap of the difference, with the same −0.02 rule, not part
  of the recommendation;
- per round;
- the September 1.13 answers at 0.83.

## Recommendation rule

The DEFAULT_MODEL switch is **admisible** only when all three hold:

- Part B's pooled verdict over the eight points is "no peor" or "mejora";
- no point of Part B is "peor";
- Part C's verdict is "no peor" or "mejora", **and** 14 at 0.90 meets candor's criterion on the
  counterfactuals (the guard above).

Otherwise it is **no admisible**, and the recommendation is not to switch.

Even when admisible, Part A is missing. The six L1 points' cuts and check_done's cut stay
unconfirmed on unseen cases. The README states that limit beside the recommendation, and it does
not change the rule.

## Bill and caps

At the costs of draw 1, both arms come to about 0.20 USD:

| Part | USD |
|---|---|
| L1 | 0.033 |
| check_done | 0.061 |
| errata | 0.019 |
| counterfactuals (September 1.13 at 0.042 per arm) | about 0.085 |
| two preflights | under 0.0002 |

`recalconf.py plan` prints these figures. They are what the earlier draw cost, not an upper
bound: the cap in code is the bound.

The caps:

- **In code:** the lot cap `BATCH_CAP` = 0.45 USD and the shared ledger
  `C:\sp-runs\jev114\ledger.json` at 4.50 USD, through `CappedDecider`, which refuses a call
  before making it. The ledger stood at 3.654 USD when this was written.
- **Concurrency:** at most 4 requests in flight.
- **Retries:** two passes, the second over what is missing.
- **Stops:** a cap, a 402, a model served under another name, 25 failed calls within one part,
  or a `STOP` file. A refusal inside the squire, which fails open in `run_bench`, reaches the
  probe as an error and stops the run like any other.
- **What the ledger can miss:** a call that raises is settled at 0. If Jev billed an answer the
  client then could not use, the ledger would be short by that call.
- **Wrong model:** an answer served under another model name is refused before it is recorded.

The run asks L1, then check_done, then errata, then the counterfactuals. `--only` is refused on a
paid run.

**Relaunching.** A relaunch replays what is recorded and asks only what is missing. It is
allowed:

- once, with `launches.jsonl` in the run directory counting the launches;
- only after a stop for failures, a preflight that failed for a reason other than funds or the
  model, a `STOP` file, or a process that died with no stop recorded;
- never after a cap, a 402 (in a part or in the preflight), a wrong model or a completed run.

The first launch is refused if any `recalconf-*` fixture already exists, so every answer is a new
draw.

The README reports every launch. A part still incomplete after that is "no medido" by the 2 %
rule; nothing is re-planned.

**Time:** about 4,400 calls with 4 in flight, of the order of half an hour.

## Limits, stated now

- **Part B is the same cases.** It measures whether the profile's parity survives a new draw,
  not whether it generalises. Only Part C is unseen data, and only for the holistic cut.
- **Small evaluation parts.** The four loop/gate points have 12 to 16 items. A single
  disagreement against 1.14 turns them "no concluyente".
- **Errata.** The holistic point's Part-B evaluation part is errata, where both versions rank
  near chance (L4).
- **Two draws.** Two draws are still a small sample of Jev's day-to-day movement.
- **If Jev repeats itself.** If no decision flips between draws, Part B adds nothing beyond draw
  1, and the README says so.
- **Two known quirks of the inputs, neither affecting a verdict:**
  - one check_done request appears under two ids, both in the derivation half;
  - 3 of the 910 counterfactual requests have no September answer. They are asked here like the
    rest and are missing only from the September reference.
