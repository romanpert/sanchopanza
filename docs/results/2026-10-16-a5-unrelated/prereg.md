# A5: does a different `unrelated` gate beat the shipped `relate_facts`? (pre-registration, DRAFT)

Status: **draft, not sealed.** Sealing: write the instrument commit below, then
`python benchmarks/facts_gate/run.py seal` after an independent review against the code. The seal
(`prereg.sha256`) holds the sha256 of this file and of `a5-unrelated-run.cmd` (its two local
values read as placeholders). Instrument commit: to be written here at sealing, as
`` Instrument commit: `<40 hex>` ``.

## Question

`relate_facts` answers `agree`, `conflict` or `unrelated`, and commits only at confidence >=
`relax` (0.60); below it, it returns no relation. The fifth batch tested accepting `unrelated`
when it is the top option at probability >= 0.5 (`decide_facts(..., unrelated_at=0.5)`) and it
did not beat the shipped policy (`docs/results/2026-09-27-edge-facts/fifth-batch.md`). Does a
gate derived on recorded data beat the shipped policy on new cases with labels by construction?

## Why the fifth batch could not decide it (free, from the recordings; `free.json`)

Replayed on both recordings of jev-1.13.0 (the original fixtures and the 2026-10-15 re-run in
`fixtures/jev114/l1-components-113r.jsonl`), **no gate in 0.40-0.70 adds a single verdict on
the fifth batch** (`graph-e`, 30 cases x 2): none of its `unrelated` cases falls undecided with
`unrelated` on top. The gate acts only on cases in that band, and graph-e has none; "25 of 27
both ways" there says nothing about the gate.

## Derivation (done, free, fixed before any new answer)

Family: `unrelated_at` in {0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70}. Rule
(`run.derive`): the gate whose *added* verdicts (cases the shipped policy leaves undecided)
maximise right - 4 x wrong, which is positive exactly when they are right more than 80 % of
the time (the package's precision target); ties to the stricter gate; none if the best is <= 0.
On `graph` + `graph-c` (50 cases x 2 recordings): **g\* = 0.65**, net 6: 6 added answers, all
right, but only **4 distinct cases** (fa-38 once, fa-42 and fa-45 in both recordings, fa-19 in
the re-run), top probabilities 0.67-0.72. 0.50 has net 2 (12 added, 10 right; fa-17, an
`agree`, at 0.63 and 0.59 is the wrong one twice). g\* is pinned in `run.py`
(`GATE_UNDER_TEST`); `paid` and `report` refuse to run if the recordings no longer derive it.

## New data: labels by construction (`benchmarks/facts_gate/cases.py`)

**Written after the recorded answers on `graph`, `graph-c` and `graph-e` had been looked at**
(the shapes copy the cases where the decider hesitates). 500 pairs, seeded (20261016), hashed
before any call: sha256 (LF) `a219ba794172621e2877f8492df34bdd8b7391421215bed7cb8dc52e24039b53`,
also in `benchmarks/facts_gate/cases.sha256` and pinned in `run.py` (`CASES_SHA256`); `paid`
and `report` refuse any other file. Invented entities (eight kinds, invented place names), three
numeric attributes each, two wordings in Spanish and two in English, languages alternating:

| shape | label | n |
|---|---|---|
| two attributes of the same entity | unrelated | 150 |
| the same attribute of two entities of the same kind | unrelated | 50 |
| the same attribute and value, other wording | agree | 75 |
| the same, other wording plus its source | agree | 75 |
| the same attribute of the same entity, two values (>= 15 % or >= 2 years apart) | conflict | 150 |

The two wordings of an attribute name the same event or count (one founding, one inauguration,
N editions held), so every `conflict` is one by construction; `cases.EVENT_STEMS` lists the
shared word per attribute and `tests/test_facts_gate.py` checks it, and that both facts of an
`agree` state the same numbers and those of a `conflict` different ones. Mix 40/30/30, the fifth
batch's. No label is read off a model; no model wrote a case.

## Run

One call per case: the shipped question (`entities.fact_questions`, no examples), point
`facts`, `jev-1.13.0`, recorded in `fixtures/facts-gate/recording.jsonl`. Every gate is applied
in code to the same answers.

**Unanswered cases.** One launch and at most one relaunch (`paid_once.may_launch`), none after
an HTTP 402, a 429 or the cap. Within a launch a failed case is not re-asked: the launch stops;
a relaunch asks only what the recording lacks. While a relaunch is still allowed, `report`
refuses to score with cases missing; after it (or after a stop that allows none), every case
still without an answer counts as **undecided under every policy** (shipped and every gate),
and their number is reported (`unanswered`).

## Verdict rule (applied by `run.py report`, as written)

For g\* = 0.65, on the 500 cases, let A be the verdicts it adds to the shipped policy.

1. |A| < 16 (the fewest added verdicts whose Wilson lower bound can reach 0.80):
   **undecided**, too few cases in the band; the shipped policy stays.
2. Else **the gate beats the shipped policy** iff no case of A is a `conflict` (a missed
   conflict) and the Wilson 95 % lower bound of A's precision, **unrounded**, is >= 0.80.
3. Else **it does not**.

A gate only ever adds `unrelated` verdicts, so the shipped `agree`/`conflict` errors (costly)
cannot change; reported anyway. Every other gate of the family, the shipped totals and the
totals by shape are reported, descriptively. A positive verdict licenses a default change
proposal for `decide_facts`, not the change itself.

## Power, said plainly

The band the gate acts on is thin. Of the 48 recorded answers on `unrelated` cases (graph,
graph-c and graph-e, both recordings), 6 fall in it at 0.65 (12.5 %, 4 distinct cases), and 0
of the 24 on graph-e. The cases closest to this batch's main shape (two attributes of the same
entity, in graph-e) put **0 of 6** answers in the band. On 200 `unrelated` cases that projects
**about 19-25 added verdicts, close to the minimum of 16**, and possibly fewer: outcome 1 is a
coin flip or worse. When it does decide, the rule is strict: at 20 added it needs **20 of 20**
right (19 of 20 has a lower bound of 0.764), at 25 it needs 24 (0.805). The likeliest outcomes
are "undecided" or "does not beat"; "beats" needs a band that is both fuller and cleaner than
the recordings show. The run is cheap enough that the answer "the gate rarely matters" is worth
its cents.

## Cost and caps

500 calls. At the median real request (71 micro-USD): **0.036 USD**; at the measured cost of
this question on the fifth batch (0.0034 USD for 120, 28 micro-USD): about 0.014 USD. The
`CappedDecider` per-call estimate (0.006 USD in all) is the lowest of the three here, so it is
not what bounds the run: the ledger cap is. Hard cap **0.10 USD** in the ledger at a fixed path,
`~/.cache/sanchopanza/a5-unrelated/ledger.jsonl` (no variable moves it; `dry` and `paid` print
it), with the launches beside it in `launches.jsonl` (HEAD and why each stopped).

`paid` refuses, before the key is read, unless: the higher estimate fits under the cap; the
seal matches this file and the launcher; HEAD descends from the instrument commit and `src/`,
`benchmarks/paid_once.py`, `benchmarks/facts_gate/`, `benchmarks/jev114/l4.py`,
`benchmarks/thresholds.py`, the three `benches/graph*.jsonl` and the derivation recordings are
identical to it, with nothing uncommitted under them; the cases have their hash; the recordings
derive 0.65; the launch rule allows a launch; no other `paid` of the lot holds its lock. Then,
in one event loop: `jev-preflight` (one call, about 13 micro-USD, outside the ledger), the live
client built inside that loop, every call once, in order, and the first refusal, failure, empty
answer or answer from a model other than jev-1.13.0 stops it. The Jev client itself retries an
HTTP 429 or 529 up to 3 times inside one call.

The key arrives through the file `SANCHOPANZA_KEYS_ENV` names (never printed, never in this
repository); `a5-unrelated-run.cmd` sets it and the python, as placeholders here, filled only in
the sealed worktree's copy.

## Launch (owner's decision)

    python benchmarks/facts_gate/run.py dry      # free: 500 to ask, 0.036 USD at the median
    python benchmarks/facts_gate/run.py seal     # after review, with the commit written above
    a5-unrelated-run.cmd                         # from the sealed worktree, by WMI: paid, report
