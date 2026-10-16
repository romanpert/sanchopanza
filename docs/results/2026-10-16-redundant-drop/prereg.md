# Pre-registration: redundant_page on Jev 1.14 with 90 new `drop` cases in its derivation (lot jev114-redundant-drop)

**DRAFT, not sealed.** Written 2026-10-15, revised 2026-10-16 after two independent reviews.
Before any paid call: a second review against the code (`revisor-prereg`), then
`redundant_drop.py seal`, then a commit of `prereg.sha256` and `data.sha256`. That commit is the
sealing commit, and its message carries both hashes.

Jev only, no call to Claude. **An attended launch of about 5 minutes.**

## What was seen before this was written, and what that means

- The recalibration and its confirmation: READMEs, registrations, `analysis.json`, and the
  redundant_page rows of lot L1 and of recalconf.
- **The 125 hand-written cases are not fresh.** Both versions answered them twice (L1 and
  recalconf), and this lot was designed after seeing how they did:
  - 0.61 lost 2 and 4 held-out drops;
  - `rd-118` held the derivation.
- **The only fresh data here are the 405 generated cases.** Their labels were fixed by
  construction before any of them was asked.
- **Question 2 on real pages therefore rests on 50 cases already seen in two draws.** A
  favourable answer there confirms parity on known pages. It is not a test on unseen ones.

## Questions

On 1.14 the registered 90 % derivation of `adds_nothing` returned 0.61 on `retrieval-c`, against
0.59 for 1.13, because of one `keep` page (`rd-118`, 0.60).

- With only 51 `drop` cases, one keep in the acted set holds the Wilson lower bound under 90 %:
  47 of 48 gives 0.891.
- At 0.61, 1.14 lost held-out drops in both draws, and recalconf called it "peor".

**Q1.** With 90 more `drop` cases in the calibration part, does the 90 % derivation clear at a
cut that does not hinge on one page?

- The 90 % target is met on the calibration mix of hand-written and generated cases, **not on
  hand-written pages alone**.
- The hand-only precision and recall at the derived cut are reported as descriptive.

**Q2.** Is 1.14 at that cut no worse than 1.13 at 0.59?

- On the hand-written evaluation pages: 50, already seen.
- On fresh generated pages, each stratum weighted equally.

The floor arithmetic, from `thresholds.wilson_lower` at 90 %:

| Keeps in the acted set | Acted cases needed |
|---|---|
| 0 | 35 |
| 1 | 53 |
| 2 | 69 |
| 3 | 84 |
| 4 | 99 |

With 141 `drop` cases in calibration, there is room for three or four hard keeps.

## The new cases: labels by construction (`benchmarks/jev114/redundant_gen.py`)

**What does not produce them.** No model writes or reads these labels, and no Jev output is
used. TypeSafe's contract (MCA 2.3(b)) forbids training on or distilling Jev's outputs.

**What does.** Fixed templates render forty-five invented fact records
(`redundant_scenarios.json`, Spanish without accents, invented bodies, firms and places, people
by initial only):

- **`known`:** the record's primary document, with its body, date and every fact.
- **Six `drop` families:** each restates a subset of `known`'s facts, or the same facts at less
  precision, attributed to the same body:
  - the wire copy;
  - the aggregator headline;
  - the database row;
  - the rounded-down summary;
  - the body's own press release;
  - the partial blog summary.
- **Five `keep` families:** each adds one item the record holds and `known` lacks:
  - `revision`: the body's later correction, a new figure and a new date;
  - `extra`: a withheld detail, new names or a breakdown;
  - `independent`: another primary body reaching the same figures, a new source;
  - `qualify`: a caveat, a new qualification;
  - `offpurpose`: a page on the same place, off the purpose, with its own figures.

**Where the `keep` labels come from.** They follow the question's literal list ("no new figure,
date, name, outcome, qualification or source") and `retrieval-c`'s conventions. They do not
follow the question's reading of `purpose`, which no template varies. Two families are labelled
by convention, and that is stated:

- **`independent`.** The question's criteria call "the same facts from a different source" new
  only "when the work is about corroboration". No purpose here is about corroboration.
  `retrieval-c` labels such pages `keep` (rd-104, rd-121), and so does this lot.
- **`offpurpose`.** These carry new figures, so the literal criterion calls them new. Their
  label also rests on `retrieval-c` rule 1, "off-purpose is not redundant". They differ from
  `rd-118`, which has no figures at all.

**The checks** (`redundant_gen.problems`; the tests pin that no case fails):

- every number in a `drop` text is in `known`, except the rounded summary's single rounded-down
  figure after "mas de";
- no withheld item, and not the corrected figure, appears in a `drop` text;
- the words a `drop` text adds to `known` and the body's name are only its family's frame
  (`FRAME`, for example `agencia`, `segun`, `balance` for the wire copy);
- every `keep` text carries its new item, and the correction and off-purpose keeps carry a new
  number.

Spanish is checked too: contractions ("del", "al"), and no number or gender mismatch with the
document's name, since no template names it any more.

**The partition is by record.**

- The 15 records with the lowest sha256 of `"redundant-drop:" + id` calibrate: 90 drop and 45
  keep.
- The other 30 evaluate: 180 drop and 90 keep.
- The keep families rotate by record, so the calibration half is not balanced: 7 `revision`,
  8 `extra`, 10 `independent`, 9 `qualify` and 11 `offpurpose`. The evaluation half has 20, 19,
  17, 18 and 16.

**The templates are easier than the hand-written pages.** Pooled with them, the hand-written
cases would be diluted. The rule below therefore weights the strata equally and requires the
hand stratum to pass on its own.

## Parts and clusters

| Part | Hand-written (`benches/`) | Generated | drop / keep |
|---|---|---|---|
| Calibration | `retrieval-c` (75: 51 / 24) | 15 records (135: 90 / 45) | 141 / 69 |
| Evaluation | `retrieval` + `retrieval-b` (50: 18 / 32) | 30 records (270: 180 / 90) | 198 / 122 |

**Clusters.**

- A generated case's cluster is its record.
- A hand-written case's cluster is its event, by the registered keys in `redundant_drop.EVENTS`:
  - rd-01 to rd-07, rd-15 to rd-20 and rd-77 to rd-83 and rd-123 are all the Oaxaca earthquake;
  - one group each for Ley 6132, Inversiones Delta, defamation, Constructora Norte, Transportes
    Sur and Aristo Global;
  - otherwise the purpose.
- The 50 hand-written evaluation cases fall into **9 events**, with sizes 13, 7, 7, 6, 6, 4, 3,
  2 and 2.

**One new draw for everything.** The 125 hand-written cases are asked again, so every case comes
from the same draw.

## Arms

- **`13r`:** `jev-1.13.0` at its shipped 0.59.
- **`14`:** `jev-1.14.0` at the cut this lot derives. If the derivation is unreachable, 1.14
  stays at the profile's 0.61.

**How each arm is asked:**

- Both arms are asked new, one draw each, in one slot with the order alternating.
- The cases go in the registered shuffled order (seed 20261016).
- They go through `run_bench`, as lot L1 did.
- **`data.sha256` signs the request itself.** That is the key of `redundancy_questions` with
  the squire's `Limits().triage_chars`, and a test pins that the bench path sends exactly that
  request.
- Answers are read through `Decision.answer`, so a NaN is a missing answer.
- Recordings live in `C:/sp-runs/jev114/redundant-drop/` and are published to
  `fixtures/jev114/redundant-drop-<arm>.jsonl` afterwards.
- **One event loop.** Every live Jev client is built and closed inside the run's single `asyncio.run`,
  fresh for each pass; the preflight builds and closes its own. `tests/test_jev114_lot.py` runs
  the paid path with a fake client that fails when reused under a second loop.

## Rules (`benchmarks/jev114/redundant_drop_analysis.py`)

1. **Derivation: rule D.** `thresholds.derive` at a 90 % target on the 95 % Wilson lower bound,
   with the most recall, on the calibration part, for each arm. 1.14's cut is the candidate;
   1.13's is descriptive.
2. **Stability.** The derivation is re-run without each calibration case in turn (210 runs).
   It is stable when every cut is reachable and they span at most 0.05. On lot L1's draw, this
   rule finds the recalibration's 0.61 unstable, with `rd-118` among the cases that move it, and
   a test pins that.
3. **Primary: stratified.** Right decisions, 1.14 at its derived cut minus 1.13 at 0.59. The
   statistic is the mean of the hand stratum's difference (50) and the template stratum's (270),
   with equal weights.
   - 95 % interval by bootstrap, 10,000 replicas, seed 20261015.
   - In the hand stratum, events are resampled.
   - In the template stratum, records and families are resampled independently, and each case is
     weighted by how often its record and its family were drawn. The 11 families are correlated
     across records.
   - Verdict by `lot_stats.verdict_of`, margin −2 points. "Mejora" also needs the interval
     above 0; the McNemar p is unclustered.
4. **The hand stratum on its own must be "no peor" or "mejora"** (event-cluster bootstrap, same
   margin).
5. **Count guard on the hand stratum.** Both of these must hold:
   - 1.14 loses at most one more case than it wins;
   - 1.14 catches at least as many of the 18 hand-written `drop` pages as 1.13.
6. **Costly drops.** 1.14 drops at most two more `keep` pages of the evaluation part than 1.13.
7. **No verdict unless the last launch completed**, read from the launch log `publish` copies.
   No proposal when either of these holds:
   - more than 2 % of the cases lack an answer from either arm;
   - 1.14 leaves 2 points more unanswered than 1.13.
8. **Proposal.** `adds_nothing` for 1.14 becomes the derived cut only when every check above
   holds. Otherwise the profile keeps 0.61, and the failed checks are listed. The change itself
   would be a later commit with a test. This lot changes no threshold.

**Descriptive, declared now:**

- the derivation on `retrieval-c` alone, and on templates alone;
- hand-written precision and recall at the cuts used, in each half;
- per family, each arm at its cut, over all cases;
- 1.14 at 0.61 through the same stratified comparison;
- AUC of each arm on the evaluation part, with a cluster interval.

## Power, as it stands (`redundant_drop_analysis.py --power`, and the tests' synthetic lots)

**The hand stratum decides.** On 50 cases, one net loss is exactly the 2-point margin. Below,
1.14's wins and losses are placed at random among the 50 hand-written evaluation cases (200
placements each), and the verdict is read from the event-cluster bootstrap:

| 1.14 wins / losses | "no peor" | "no concluyente" | "peor" |
|---|---|---|---|
| 0 / 0 | 1.00 | | |
| 2 / 0 | 1.00 | | |
| 1 / 1 | 0.15 | 0.85 | |
| 3 / 3 | 0.01 | 0.99 | |
| 5 / 5 | 0.01 | 0.99 | |
| 0 / 1, 0 / 2, 1 / 3 | | 1.00 | |
| 0 / 4 | | 0.46 | 0.54 |

**Reading:**

- **Rule 4 is met only when the arms agree on every hand-written evaluation page, or 1.14 only
  wins.** Any loss in the hand stratum withholds the proposal. That is stricter than the count
  guard of rule 5, and it is the rule as written.
- In the recalibration's two draws, the arms disagreed on 4 of these 50 each time, all at the
  cuts.
- **In the template stratum, "no peor" means above all that the arms agree on templates.**
- With templates in full agreement, the stratified primary reads:
  - 0 hand losses: "no peor";
  - 1 hand loss: "no concluyente" (−1.0 [−2.9, 0.0]);
  - 4 hand losses: "peor" (−4.0 [−7.6, −1.0]).
- With no hand loss, 3 and 6 template disagreements read "no concluyente".

These come from the tests' synthetic lots, which have 3 families and not 11, so the real
template interval is wider.

**Q1 needs no power.** The derivation and the stability check are computed, not tested.

## Bill, caps and balance

| | Value |
|---|---|
| Calls | 1,060 for the cases, plus 2 preflights: 1,062 |
| Jev, expected | **0.034 USD**, at lot L1's billed 25.2 µUSD per redundant_page call |
| Jev, `CappedDecider`'s estimate | 0.019 USD. It is lower than the billed rate on these short requests, so each call can overshoot its reservation by a few µUSD. The cap allows for that three times over. |
| **Hard cap in code** | `BATCH_CAP` 0.10 USD for batch `jev114-redundant-drop`, on the shared ledger `C:/sp-runs/jev114/ledger.json` capped at 4.50 USD (0.6485 left on 2026-10-16) |
| Claude | **0 USD** |

**The TypeSafe balance must be at least 0.30 USD before launch,** checked by the owner on the
console. The preflight cannot read the balance.

**What stops the run:**

- One relaunch at most, and none after a cap, a 402, a wrong model or a completed launch.
- A `STOP` file in `C:/sp-runs/jev114/redundant-drop/` stops it between calls.

## Seal and launch

**The seal** is one sha256 over `LOT.sealed`. It covers:

- this file, `cases.jsonl` and the launcher `redundant-drop-run.cmd`;
- the generator and its records, the runner, the analysis and `thresholds.py`;
- the three `benches/retrieval*.jsonl`;
- `points/triage.py`, `eval/bench.py`, `eval/stats.py` and `dag.py`;
- `lot.COMMON_SEALED`: the lot machinery, the key loader, the Jev client and model keys, the
  ledger and cap, the recordings, `squire`, `limits`, `text`, `contract`, `policy` and the rest.

**`data.sha256`** signs every case's file, id, half, label, cluster and request key.

**`run --paid` refuses unless:**

- HEAD is the sealing commit;
- the worktree is clean;
- every sealed file and input matches;
- `cases.jsonl` is what the generator writes;
- both versions pass a preflight.

**The launcher.** `redundant-drop-run.cmd` sets `PYTHONPATH` to the worktree's own `src`.
`SANCHOPANZA_KEYS_ENV` is a path placeholder filled in **before the seal**, and the launcher
refuses a paid run while it is the placeholder. It is started by WMI from a
`git worktree add --detach` at the sealing commit. `redundant-drop-run.cmd dry` runs the free
plan.

```bash
python benchmarks/jev114/redundant_gen.py --check       # free: cases.jsonl is what the code writes
python benchmarks/jev114/redundant_drop.py run --dry    # free: the plan above
python benchmarks/jev114/redundant_drop_analysis.py --power   # free: the power table
# revisor-prereg; fix; fill <KEYS_ENV_PATH> in the launcher (a path only); then:
python benchmarks/jev114/redundant_drop.py seal         # data.sha256 + prereg.sha256, commit them
# owner: TypeSafe balance >= 0.30 USD; git worktree add --detach at the sealing commit
redundant-drop-run.cmd                                  # by WMI, from the detached worktree
python benchmarks/jev114/redundant_drop.py publish      # free: recordings + launch log
python benchmarks/jev114/redundant_drop.py rows         # free: drop-scored.jsonl
python benchmarks/jev114/redundant_drop_analysis.py     # free: analysis.json, the verdict
```
