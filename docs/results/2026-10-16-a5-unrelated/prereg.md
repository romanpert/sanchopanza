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
(the shapes copy the cases where the decider hesitates). 1,500 pairs, seeded (20261016),
hashed before any call: sha256 (LF)
`2673a2529751d5349841be74aa0664a8da9c7504ec379683107fe04fe4d8ab3e`, also in
`benchmarks/facts_gate/cases.sha256` and pinned in `run.py` (`CASES_SHA256`); `paid` and
`report` refuse any other file. Invented entities (eight kinds, 120 invented place names),
three numeric attributes each, two wordings in Spanish and two in English, languages
alternating, no pair twice in either order:

| shape | label | n |
|---|---|---|
| two attributes of the same entity | unrelated | 560 |
| the same attribute of two entities of the same kind | unrelated | 40 |
| the same attribute and value, other wording | agree | 225 |
| the same, other wording plus its source | agree | 225 |
| the same attribute of the same entity, two values (>= 15 % or >= 2 years apart) | conflict | 450 |

The size comes from the power below: the same-entity shape, where the band lives, carries the
weight. `agree` and `conflict` keep the 40/30/30 mix of the fifth batch rather than shrink:
the added verdicts' precision depends on how many `agree` cases sit next to the `unrelated`
ones (an `agree` in the band is the wrong verdict the gate can add, fa-17's kind), and the
missed-conflict guard needs as many chances to fire as the mix gives it. Shrinking them would
make the gate look more precise than on the mix every earlier batch used.

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

For g\* = 0.65, on the 1,500 cases, let A be the verdicts it adds to the shipped policy.

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
of the 24 on graph-e; the cases closest to this batch's main shape (two attributes of the same
entity, in graph-e) put 0 of 6 there. A first draft of 200 `unrelated` cases projected 19-25
added verdicts, near the minimum of 16: a coin flip. This batch is sized so that it decides.

`python benchmarks/facts_gate/run.py power` (exact binomial: each case lands in the band with
probability b, each added verdict is right with probability p; the rule as written, minimum 16,
Wilson lower bound >= 0.80; a missed conflict would only lower these):

| band b | counted over | added, expected | P(undecided) | P(beats), p = 0.80 | p = 0.93 | p = 0.95 |
|---|---|---|---|---|---|---|
| 12.5 % (recorded) | 600 unrelated | 75 | 0.000 | 0.019 | **0.895** | 0.979 |
| 12.5 % | 560 same-entity only | 70 | 0.000 | 0.019 | 0.870 | 0.969 |
| 10 % | 560 same-entity only | 56 | 0.000 | 0.019 | 0.774 | 0.920 |
| 8 % (conservative) | 560 same-entity only | 45 | 0.000 | 0.018 | 0.656 | 0.835 |

So: at the recorded band, a gate whose added verdicts are right 93 % of the time is called a
win with probability about 0.87-0.90, one right 80 % of the time at most 0.02 (the false-win
rate), and "undecided" no longer happens. If the band is as thin as graph-e suggests (8 %),
power at 0.93 falls to about 0.66, and a true 0.93 can come out "does not beat"; the false-win
rate stays under 0.02 at every band. Read a "does not beat" with that in mind; a "beats" is
safe.

## Cost and caps

1,500 calls. At the measured cost of this question on the fifth batch (0.0034 USD for 120, 28
micro-USD): **about 0.042 USD**, the expected spend. At the median real request (71 micro-USD,
a figure for longer requests than this one): 0.107 USD. The `CappedDecider` per-call estimate
(0.019 USD in all) is the lowest of the three, so it is not what bounds the run: the ledger cap
is. The runner refuses a plan whose higher estimate passes the cap, so the cap is **0.15 USD**,
raised from 0.10 because the 71-micro-USD figure for 1,500 calls (0.107) no longer fits under
0.10; the expected spend stays about 0.04 USD. Hard cap in the ledger at a fixed path,
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

    python benchmarks/facts_gate/run.py dry      # free: 1,500 to ask, about 0.04 USD expected
    python benchmarks/facts_gate/run.py power    # free: the table above
    python benchmarks/facts_gate/run.py seal     # after review, with the commit written above
    a5-unrelated-run.cmd                         # from the sealed worktree, by WMI: paid, report
