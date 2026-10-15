# The memory gate with the long window, confirmed on 84 unseen LongMemEval questions (lot memgate-long): pre-registration

Written 2026-10-15, before any answer on these 84 questions. To be reviewed against the code by
an independent `revisor-prereg` agent before the seal. `prereg.sha256` will hold the hash of
this file together with the code and inputs it names (`prereg.manifest.json`, written by
`python benchmarks/memgate_long/memgate_long.py --seal`). Branch `memgate-long`; the sealing
commit's message carries the hash.

## The question

Lot L6 (`docs/results/2026-10-15-jev114-l6`) found, on 36 LongMemEval S test questions, that
the memory gate reading every session whole in one call (the long window, `L`) lifts gate
recall from 0.723 to 0.908 on jev-1.13.0 (+18.5 points, 95 % CI [+5.7, +32.8], "mejora"), and
ends 3.08 points under BM25 top 3, missing "alcanza" by 0.08 of a point. Those 36 questions
generated the hypothesis. **Does the window's lift hold on the 84 test questions L6 did not
reach, and where does the long gate land against BM25 top 3 there?**

## Questions

The 120 test questions of `docs/results/2026-09-28-memory-gate` (`longmemeval.slices`, seed
20260928), in L6's seeded launch order (`l6.launch_order`, seed 20261015). L6's soft stop left
ranks 0-35; this lot takes **ranks 36-119: 84 questions**. The runner refuses to select unless
L6's scored ids are exactly the head of that order and the rest is 84 distinct ids, disjoint
from L6's 36 and from the 10 dev questions (checked free by `--plan`: 84, disjoint). Run two at
a time, in that order.

## Cells (`benchmarks/memgate_long/memgate_long.py`)

One model: **jev-1.13.0** (`j13r`, the production `DEFAULT_MODEL`), pinned
(`JevDecider(model="jev-1.13.0", images=False)`); an answer served by another model stops the
run (lot L4's `Arm`). Per question, as L6's A7 with one model (L6's `a7_look` and `a7_triage`,
imported):

- `needs_recall` once (no header): the gate keeps the triage's sessions when it looks, none
  when it does not.
- `S`: `memory_gate.triage_memories` as shipped (each session as its head plus the
  best-matching window, 900 characters; 30 a call, a tournament past that).
- `L`: the `TypeSafe-Danger-Zone-Long-Context` header on, every session whole
  (`memory_gate.pages_of(..., limit=400_000)`) in one `triage_many` call with
  `Limits(page_chars=400_000, pages_per_call=1_000)`.
- `bm25@3`: BM25 top 3 sessions, computed (free).
- `rec13-S`: the gate recorded on 2026-09-28, replayed free: a historical reference only.

Production thresholds. S runs first on even ranks within the lot, L first on odd ones. At most
4 calls in flight. A cell fails on a question when any of its calls failed (the triage, or
`needs_recall`) or its triage answered no page.

## Metrics

Per cell, as `longmemeval.report` and L6 (`l6_analysis.a7_cell`): **gate session recall**
(pooled over gold sessions; primary); any-hit, all-hit, characters injected, precision
(secondary); the excerpt ceiling and the look rate. Comparisons use the questions where both
live cells answered (complete cases); the failure-gap rule is computed over every launched
question; L6's "a failed triage injects nothing" reading is reported beside it.

## Verdict rules (decided now)

Statistics are L6's (`l4_stats`, `l6_analysis.paired_stat`): a paired bootstrap over
questions, 10,000 resamples, seed 20261015, percentile 95 % CI; p = twice the smaller share of
resampled differences on either side of 0. **Holm family: one comparison**, recall L − S on
jev-1.13.0 (`recall_window_j13r`), so the Holm p is the raw p. L6's own rule
(`l4_stats.verdict`: "mejora" / "no peor" / "no concluyente o peor") is reported beside it.

1. **"confirmado"** if recall L − S on jev-1.13.0 has a paired bootstrap 95 % CI lower bound
   **> 0**, on at least 20 complete questions, and L failed on no more than 2 % more of the
   launched questions than S (L6's failure-gap rule).
2. **Against BM25 top 3**, for L (the product reading) and for S, L6's definitions verbatim:
   the original criterion 1 (paired CI of recall minus bm25@3 above 0: **"bate a BM25"**) and
   **"alcanza"** (point estimate >= bm25@3 - 0.03, the margin of the original's criteria H and
   C). Reported as "bate" (which implies "alcanza"), "alcanza", or "no alcanza"; fewer than 20
   complete questions gives "no concluyente (n bajo)".
3. **"no confirmado"**: the CI's lower bound is at or below 0. It means the 84 questions do not
   show the window's lift with 95 % confidence, not that the lift is zero; the README reports
   the difference and its CI as they are. A failure gap over 2 % reads "no confirmado
   (fallos)"; fewer than 20 complete questions "no concluyente (n bajo)"; no difference
   computable "no medido".

**Pooled 36 + 84 = 120, descriptive.** The same cells, the L − S difference and the
differences against BM25 on L6's 36 (its `j13r` cells, `a7-scored.jsonl`) plus these 84.
Labelled descriptive: the 36 generated the hypothesis, so the pooled reading carries no
verdict.

## Power

From L6's 36 (`memgate_long_analysis.power`, free, printed by `--plan`): L − S had SE 0.069,
which on 84 questions is about **0.045**. If the true lift is L6's +18.5 points, rule 1 reads
"confirmado" with probability **0.98**; at half of it (+9.2), 0.53; the effect 80 % power
detects is **12.7 points**. Against BM25 the SE on 84 is about 0.038: if the true difference
is L6's −3.08, "alcanza" is a coin flip (0.49); at 0, 0.79. So n = 84 confirms or refutes an
effect the size of L6's, and does not settle a few points either side of BM25.

Known before this seal, free and deterministic: BM25 top 3's recall on the 84 is **0.815**
(157 gold sessions), against 0.938 on L6's 36. The rules above are L6's, not chosen with it.

## Spend, caps and stops

- **Expected cost: 0.52 USD.** L6's A7 spent 0.4425 USD for 36 questions × 2 models
  (`needs_recall` + S + L), 0.00615 USD a question and model; scaled by the sessions'
  characters (41.5 M on the 84 against 17.8 M on the 36), 0.515 USD. Smoke: about 0.012 USD.
- **Hard caps in code:** a new ledger of this lot only, `C:/sp-runs/memgate-long/ledger.json`,
  capped at **1.50 USD** for everything (smoke included); batch `memgate-long` capped at
  **1.50 USD**; the smoke on its own batch `memgate-long-smoke`, capped at **0.05 USD**. Every
  live call goes through `CappedDecider`, which reserves a pessimistic estimate before calling
  and refuses when it does not fit. A new pair of questions is not started when the batch's
  spend plus 0.010 USD a question would pass its cap (soft stop; the run then holds fewer
  questions and reports how many).
- **Stops.** A call the cap refuses, an HTTP 402 or an HTTP 429 stops the run dead: every
  later call is refused without being made (only calls already in flight finish), no rows are
  written and the runner exits with 2; a relaunch replays what was paid. The shipped client's
  three retries on 429 are switched off for this lot (529 keeps its bounded retries); there
  are no other retries. A timeout or an HTTP 400 is a failed cell, counted. A timed-out call is
  settled at 0 in the ledger although Jev may have billed it. The `jev-preflight` for
  jev-1.13.0 (about 13 micro-dollars, off the ledger) runs before the first live call.
- Answers are recorded per cell in this folder (hashed keys, no text); scored rows hold ids,
  session indexes, sizes and the look, no text. A scored file of record is frozen: a live run
  does not ask again.

## The smoke

Two LongMemEval dev questions (the first two of the dev slice in the seeded order), both
cells, on the smoke batch. Seen: that the live path, the caps and the recording work end to
end; nothing in it changes these rules.

## Seal

`prereg.sha256` = sha256 over the lines `"<path> <sha256>\n"` of `prereg.manifest.json`: this
file, the runner, the analysis, its tests, the L6 and L4 modules it imports, L6's
`a7-scored.jsonl`, the LongMemEval and memory-gate benchmark code, the `sanchopanza` modules on
the path (text files hashed with LF line ends), and the hashes of the external inputs under the
home folder (`longmemeval_s_cleaned.json` and the recorded 2026-09-28 decisions). The live
paths (`--smoke --live`, `--run --live`) check it and spend nothing if anything changed. A
re-seal (`--seal --reseal`) is allowed only before the first live call and is said here.

## What is not done

No jev-1.14.0, no other window, no change to `policy.py`, `DEFAULT_MODEL` or the shipped gate
in this lot. If rule 1 reads "confirmado", the README will name the long-window gate a
candidate memory-gate mode for 1.13 and say where it lands against BM25 (rule 2) and at what
cost a prompt; if not, it will say the L6 lift did not hold on unseen questions.
