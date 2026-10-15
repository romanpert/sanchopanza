# A5: does a different `unrelated` gate beat the shipped `relate_facts`? (pre-registration, DRAFT)

Status: **draft, not sealed.** Sealing = `python benchmarks/facts_gate/run.py seal` after an
independent review against the code; the paid step refuses to run unless `prereg.sha256`
matches this file. Instrument commit: to be written here at sealing.

## Question

`relate_facts` answers `agree`, `conflict` or `unrelated`, and commits only at confidence >=
`relax` (0.60); below it, it returns no relation. The fifth batch tested accepting `unrelated`
when it is the top option at probability >= 0.5 (`decide_facts(..., unrelated_at=0.5)`) and it
did not beat the shipped policy (`docs/results/2026-09-27-edge-facts/fifth-batch.md`). Does a
gate derived on recorded data beat the shipped policy on new cases with labels by construction?

## Why the fifth batch could not decide it (free, from the recordings; `free.json`)

Replayed on both recordings of jev-1.13.0 (the original fixtures and the 2026-10-15 re-run of
`fixtures/jev114/l1-components-113r.jsonl`), **no gate in 0.40-0.70 adds a single verdict on
the fifth batch** (`graph-e`, 30 cases x 2): none of its `unrelated` cases falls undecided with
`unrelated` on top. The gate acts only on cases in that band, and graph-e has none; "25 of 27
both ways" there says nothing about the gate. On `graph` + `graph-c` (50 cases x 2), the band
holds 12 cases at 0.50 (10 right, 2 wrong: fa-17, an `agree` at 0.63 and 0.59) and 6 at 0.65
(6 right).

## Derivation (done, free, fixed before any new answer)

Family: `unrelated_at` in {0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70}. Rule
(`run.derive`): the gate whose *added* verdicts (cases the shipped policy leaves undecided)
maximise right - 4 x wrong, which is positive exactly when they are right more than 80 % of
the time (the package's precision target); ties to the stricter gate; none if the best is <= 0.
On `graph` + `graph-c`, both recordings: **g\* = 0.65** (net 6: 6 added, 6 right). 0.50 has net 2.
g\* is pinned in `run.py` (`GATE_UNDER_TEST`); `paid` and `report` refuse to run if the
recordings no longer derive it.

## New data: labels by construction (`benchmarks/facts_gate/cases.py`)

500 pairs, seeded (20261016), hashed before any call: sha256 (LF)
`5cb71e7d9e91dede0e42d8835061140805f4ccf7b956a640c295f0ff5ea6c5bf`, also in
`benchmarks/facts_gate/cases.sha256` and pinned in `run.py` (`CASES_SHA256`): `paid` and
`report` refuse any other file.
Invented entities (eight kinds, invented place names), three numeric attributes each, two
wordings in Spanish and two in English, languages alternating:

| shape | label | n |
|---|---|---|
| two attributes of the same entity | unrelated | 150 |
| the same attribute of two entities of the same kind | unrelated | 50 |
| the same attribute and value, other wording | agree | 75 |
| the same, other wording plus its source | agree | 75 |
| the same attribute of the same entity, two values (>= 15 % or >= 2 years apart) | conflict | 150 |

Mix 40/30/30, the fifth batch's. No label is read off a model; no model wrote a case.

## Run

One call per case: the shipped question (`entities.fact_questions`, no examples), point
`facts`, `jev-1.13.0`, recorded in `fixtures/facts-gate/recording.jsonl`. Every gate is applied in code to
the same answers.

## Verdict rule (applied by `run.py report`, as written)

For g\* = 0.65, on the 500 cases, let A be the verdicts it adds to the shipped policy.

1. |A| < 16 (the fewest added verdicts whose Wilson lower bound can reach 0.80):
   **undecided**, too few cases in the band; the shipped policy stays.
2. Else **the gate beats the shipped policy** iff no case of A is a `conflict` (a missed
   conflict) and the Wilson 95 % lower bound of A's precision is >= 0.80.
3. Else **it does not**.

A gate only ever adds `unrelated` verdicts, so the shipped `agree`/`conflict` errors (costly)
cannot change; reported anyway. Every other gate of the family, the shipped totals and the
totals by shape are reported, descriptively. A positive verdict licenses a default change
proposal for `decide_facts`, not the change itself.

## Power

On the derivation recordings 25 % of the `unrelated` cases fell in the band at 0.65. With 150
same-entity pairs (where the band lives) about 40 added verdicts are expected; at a true
precision of 0.95 that is 38 of 40, lower bound 0.83: decides. At 0.90 (36 of 40, 0.77) it
fails. Templated pairs may be easier than written ones, and the band emptier: outcome 1 is
possible and is itself the answer that the gate rarely matters.

## Cost and caps

500 calls. At the median real request (71 micro-USD): **0.036 USD**; at the measured cost of
this question on the fifth batch (0.0034 USD for 120, 28 micro-USD): about 0.014 USD. The
`CappedDecider` per-call estimate (0.006 USD in all) is the lowest of the three here, so it is
not what bounds the run: the ledger cap is. Hard cap **0.10 USD** in the ledger
(`$SANCHOPANZA_A5_RUN/ledger.jsonl`, default `~/.cache/sanchopanza/a5-unrelated`); the runner
refuses a plan whose higher estimate does not fit, asks only what the recording lacks, one
call per case and no re-ask of a failed case (the Jev client itself retries an HTTP 429 or 529
up to 3 times inside one call), and stops at the first refusal, failure or empty answer.
`jev-preflight` first (one call, about 13 micro-USD, outside the ledger).

## Launch (owner's decision)

    python benchmarks/facts_gate/run.py dry      # free: 500 to ask, 0.036 USD at the median
    python benchmarks/facts_gate/run.py seal     # after review
    python benchmarks/facts_gate/run.py paid     # Jev, capped, once
    python benchmarks/facts_gate/run.py report   # free: analysis.json and the verdict
