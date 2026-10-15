# Pre-registration: redundant_page on Jev 1.14 with 90 new `drop` cases in its derivation (lot jev114-redundant-drop)

**DRAFT, not sealed.** Written 2026-10-15. Before any paid call: an independent review against
the code (`revisor-prereg`), then `redundant_drop.py seal`, whose two hashes go in the sealing
commit's message.

Jev only. No call to Claude.

## What was seen before this was written

- The recalibration and its confirmation: READMEs, registrations, `analysis.json`, and the
  redundant_page rows of lot L1 and of recalconf.
- The 405 generated cases and their labels. They are fixed by construction (below) and were
  written before any of them was asked.
- The dry plan. No Jev answer to a generated case exists.

## Question

On 1.14 the registered 90 % derivation of `adds_nothing` returned 0.61 on `retrieval-c`
(1.13: 0.59). At 0.61, 1.14 lost held-out drops on both draws: 45 and 44 of 50, against 47 and
48 for 1.13. Recalconf found this "peor".

The cause was one page:

- `rd-118`, a `keep` page, scored 0.60.
- With only 51 `drop` cases, one keep in the acted set holds the Wilson lower bound under 90 %:
  47 of 48 gives 0.891.

**With about 90 more `drop` cases in the calibration part:**

1. Does the derivation clear at a cut that does not hinge on one page?
2. Is 1.14 at that cut no worse than 1.13 at 0.59 on held-out cases?

The arithmetic of the floor, from `thresholds.wilson_lower` at a 90 % target:

| Keeps in the acted set | Acted cases needed |
|---|---|
| 0 | 35 |
| 1 | 53 |
| 2 | 69 |
| 3 | 84 |
| 4 | 99 |

With 141 `drop` cases in calibration, a cut that keeps most drops can carry three or four hard
keeps and still clear.

## The new cases: labels by construction (`benchmarks/jev114/redundant_gen.py`)

**What does not produce them.** No model writes or reads these labels, and no Jev output is
used. TypeSafe's contract (MCA 2.3(b)) forbids training on Jev's outputs or distilling them.

**What does.** Forty-five invented fact records are rendered by fixed templates. They live in
`redundant_scenarios.json`, in Spanish without accents, with invented bodies, firms and places,
and people by initial only.

- **`known`:** the record's primary document, with its body, date and every fact.
- **Six `drop` families:** the ones `retrieval-c` names. Each restates a subset of `known`'s
  facts, or the same facts at less precision, attributed to the same body:
  - the wire copy;
  - the aggregator headline;
  - the database row;
  - the rounded-down summary ("mas de 2.000" for 2.350);
  - the body's own press release;
  - the partial blog summary.
- **Five `keep` families.** Each adds exactly one item the record holds and `known` lacks:
  - the body's later correction: a new figure and a new date;
  - a withheld detail: new names or a breakdown;
  - an independent primary body reaching the same figures: a new source;
  - a caveat: a new qualification;
  - an off-purpose page on the same place, with its own figures. Off-purpose is not redundant,
    by `retrieval-c` rule 1. The off-purpose pages carry new figures, so both readings of the
    criterion agree.
- **How many:** six drops and three keeps per record, the keep families rotating. That makes
  270 `drop` and 135 `keep`.
- **The check.** `redundant_gen.problems` checks every label mechanically, and the tests pin
  that no case fails:
  - every number in a `drop` text is in `known`, except the rounded summary's single
    rounded-down figure after "mas de";
  - no withheld item, and not the corrected figure, appears in a `drop` text;
  - every `keep` text carries its new item;
  - the correction and off-purpose keeps carry a new number.

**The partition is by record.**

- The 15 records with the lowest sha256 of `"redundant-drop:" + id` calibrate. That gives 90
  drop and 45 keep, the "about 90" of the roadmap.
- The other 30 evaluate: 180 drop and 90 keep.
- No `known` crosses the partition.

**The cases are easier than the hand-written ones,** by design of the templates. That is why the
hand-written evaluation cases carry a guard of their own (below). The pooled result is read with
this in mind.

## Parts

| Part | Hand-written (`benches/`) | Generated | drop / keep |
|---|---|---|---|
| Calibration | `retrieval-c` (75: 51 / 24) | 15 records (135: 90 / 45) | 141 / 69 |
| Evaluation | `retrieval` + `retrieval-b` (50: 18 / 32) | 30 records (270: 180 / 90) | 198 / 122 |

**One new draw for everything.** The 125 hand-written cases are asked again in this lot, so
every case comes from the same draw. Lot L1 (draw 1) and recalconf (draw 2) are descriptive.

**Clusters** are cases sharing a `known`: 79 in all.

## Arms

- **`13r`:** `jev-1.13.0` at its shipped 0.59.
- **`14`:** `jev-1.14.0` at the cut this lot derives. If the derivation is unreachable, 1.14
  stays at the profile's 0.61.

Both arms are asked new, one draw each, in one slot with the order alternating. They go through
`run_bench`, the path lot L1 used, so each request is the shipped squire's. The fixtures are
`fixtures/jev114/redundant-drop-<arm>.jsonl`.

## Rules (`benchmarks/jev114/redundant_drop_analysis.py`)

1. **Derivation: rule D of the recalibration.** `thresholds.derive` at a 90 % target on the 95 %
   Wilson lower bound, with the most recall, on the calibration part, for each arm.
   - 1.14's result is the candidate `adds_nothing`.
   - 1.13's result is descriptive. 1.13 keeps 0.59.
2. **Stability: "does not hinge on one page".** The derivation is re-run without each
   calibration case in turn, 210 runs. It is stable when:
   - every one of those cuts is reachable;
   - and they span at most 0.05.

   On lot L1's draw for `retrieval-c` alone, this rule finds the recalibration's 0.61 unstable,
   with `rd-118` among the cases that move it. `tests/test_redundant_drop.py` pins that.
3. **Evaluation: right decisions on the evaluation part.** A page is dropped when p ≥ cut.
   - The comparison is 1.14 at its derived cut minus 1.13 at 0.59.
   - Exact McNemar.
   - A 95 % paired bootstrap over clusters: `l4_stats.paired_binary`, 10,000 replicas, seed
     20261015.
   - Verdict by `jev114_paired.verdict`, with "no peor" when the lower bound is above −2 points.
4. **Guards:**
   - the same comparison on the 50 hand-written evaluation cases alone is not "peor";
   - 1.14 drops at most two more `keep` pages of the evaluation part than 1.13 does.
5. **Proposal.** `adds_nothing` for 1.14 becomes the derived cut only when all of these hold:
   - the derivation is reachable;
   - it is stable;
   - the pooled evaluation is "no peor" or "mejora";
   - both guards hold.

   Otherwise the profile keeps 0.61, and the reasons are listed. The proposal changes
   `policy.MODEL_PROFILES` in a later commit, with a test. This lot does not change it.

A case either arm did not answer is left out of both.

**Descriptive, not part of the verdict:**

- the derivation on `retrieval-c` alone, on this draw;
- 1.14 at 0.61 against 1.13 at 0.59;
- right decisions per family;
- AUC of each arm on the evaluation part, with a cluster interval.

## Power

**The derivation and stability rules need no power.** They are computed, not tested.

**The evaluation is the weaker part.** On the 50 hand-written cases, the arms disagreed on 4 of
50 in each draw, because the cuts differed. On template cases, few disagreements are expected.

- Suppose 3 % of the 320 evaluation cases disagree, with a cluster design effect of 2. The 95 %
  interval of the difference is then about ±2.6 points.
- A tie therefore reads "no concluyente". "No peor" needs 1.14 to be at least about 0.6 points
  ahead.
- This risk is stated now. Under the rule above, a "no concluyente" means no change to the
  profile.

## Bill and caps

| | Value |
|---|---|
| Calls | 1,060: 530 cases × 2 arms, plus 2 preflights |
| Jev, expected | **0.034 USD**, at lot L1's billed 25.2 µUSD per redundant_page call (8.0e-8 USD per character of case input) |
| Jev, `CappedDecider`'s estimate | 0.019 USD. It is lower than the billed rate on these short requests, so each call can overshoot its reservation by a few µUSD. The cap below allows for that three times over. |
| **Hard cap in code** | `BATCH_CAP` 0.10 USD for batch `jev114-redundant-drop`, on the shared ledger `C:/sp-runs/jev114/ledger.json` capped at 4.50 USD (0.6485 left on 2026-10-15) |
| Claude | **0 USD** |

- One relaunch at most, none after a cap, a 402 or a wrong model.
- A `STOP` file in `C:/sp-runs/jev114/redundant-drop/` stops the run between calls.
- **Time:** about 5 minutes.

## Procedure

```bash
python benchmarks/jev114/redundant_gen.py --check       # free: cases.jsonl is what the code writes
python benchmarks/jev114/redundant_drop.py run --dry    # free: the plan above
# revisor-prereg against this file and the code; fix; then:
python benchmarks/jev114/redundant_drop.py seal         # data.sha256 + prereg.sha256
python -m sanchopanza jev-preflight                     # exit 0, else nothing is launched
python benchmarks/jev114/redundant_drop.py run --paid   # from a worktree --detach at the sealed commit
python benchmarks/jev114/redundant_drop.py rows         # free: drop-scored.jsonl
python benchmarks/jev114/redundant_drop_analysis.py     # free: analysis.json, the verdict
```

**What `run --paid` checks before it spends:**

- The seal: `LOT.sealed`, which covers:
  - this file, `cases.jsonl`, the generator and its records;
  - the runner, the analysis, `lot.py`, `l4_stats.py`, `jev114_paired.py` and
    `thresholds.py`;
  - `points/triage.py`, `eval/bench.py`, `policy.py`, `capped.py` and `recorded.py`.
- The inputs: `data.sha256`, over every case's file, id, half, input and label.
- That `cases.jsonl` is exactly what `redundant_gen.py` writes.
- A preflight of both versions.
