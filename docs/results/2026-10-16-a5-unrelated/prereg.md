# A5: does a different `unrelated` gate beat the shipped `relate_facts`? (pre-registration, DRAFT)

Status: **sealed** after four independent reviews against the code. The seal (`prereg.sha256`,
written by `python benchmarks/facts_gate/run.py seal`) holds the sha256 of this file and of
`a5-unrelated-run.cmd` (its two local values read as placeholders).
Instrument commit: `92107d2987cf5a880e8cb95d0f011c41180d65a8`.

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
`d793dd4a2764a5a0d2bdcf1c2cafd56d69193e373a4445fc436607fcf3e14a4e`, also in
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

The two wordings of each of the 24 attributes name the same event or the same magnitude (one
founding, one daily output, the festival's duration, the number of operating theatres), so
every `conflict` is one by construction; `cases.EVENT_STEMS` lists the shared words for all 24
and `tests/test_facts_gate.py` checks every template against them, and that both facts of an
`agree` state the same numbers and those of a `conflict` different ones. Each case carries its
kind and attribute pair (`attributes`). Mix 40/30/30, the fifth batch's. No label is read off a
model; no model wrote a case.

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
cannot change; reported anyway. Every other gate of the family, the shipped totals, the totals
by shape and **A and its errors by (kind, attribute pair)** (`added_by_type`) are reported,
descriptively.

**What a "beats" licenses, and what it does not.** A default change *proposal* for
`decide_facts`, to be checked on written text, not the change itself. Its limits:
- The `agree` cases are easy paraphrases of one value. The only wrong verdict the gate made on
  the recordings, fa-17 (two dated events read as `unrelated`), is of a type this batch does not
  contain, so the batch can understate the wrong `unrelated` verdicts a real mix would add.
- Wilson treats the added verdicts as independent; they come from 8 kinds x 3 attributes x 2
  wordings x 2 languages of templates. If A concentrates in a few (kind, attribute pair) cells,
  the effective sample is smaller than |A|; `added_by_type` shows it.
- On missed conflicts: 0 of the 58 recorded answers on `conflict` cases fall undecided with
  `unrelated` on top (rule of three: at most about 5 %), and this batch's conflicts state two
  plainly different values, so the guard is likely to hold here and says little about subtler
  conflicts.

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
unlikely to be a false win on this batch, within the limits above.

## Cost and caps

1,500 calls. What the ledger settles is each call's computed cost (its input tokens x 0.042 USD
per million); on the fifth batch this question cost 0.0034 USD for 120 calls (28 micro-USD), so
the expected spend is **about 0.042 USD**. At the median real request (71 micro-USD, a figure
for longer requests than this one): 0.107 USD. The `CappedDecider` per-call estimate (0.019 USD
in all) is the lowest of the three, so it is not what bounds the run: the ledger cap is. The
runner refuses a plan whose higher estimate, plus what the ledger already holds, passes the
cap, so the cap is **0.15 USD**, raised from 0.10 because the 71-micro-USD figure for 1,500
calls (0.107) no longer fits under 0.10; the expected spend stays about 0.04 USD. Hard cap in
the ledger at a fixed path, `~/.cache/sanchopanza/a5-unrelated/ledger.jsonl` (no variable moves
it; `dry` and `paid` print it), with the launches beside it in `launches.jsonl` (HEAD and why
each stopped).

`paid` refuses, before the key is read, unless: the estimate plus what the ledger holds fits
under the cap; the seal matches this file and the launcher (and this file names the instrument
commit: `seal` refuses otherwise); HEAD descends from the instrument commit and `src/`,
`benchmarks/paid_once.py`, `benchmarks/facts_gate/`, `benchmarks/thresholds.py`, the three
`benches/graph*.jsonl` and the derivation recordings are identical to it, with nothing
uncommitted under them; the cases have their hash; the recordings derive 0.65; the launch rule
allows a launch; on the first launch, no recording exists yet; no other `paid` of the lot holds
its lock. The key loader and the live client live in `paid_once.py` (sealed with the
instrument); nothing from another lot is imported. Then, in one event loop: `jev-preflight`
(one call, about 13 micro-USD, outside the ledger), the live client (`JevDecider`, jev-1.13.0,
long context and images off) built inside that loop, every call once, in order, and the first
refusal, failure, empty answer or answer from a model other than jev-1.13.0 stops it. Only lines
answered by jev-1.13.0 count as recorded, in `paid`, `dry` and `report` alike. The Jev client
itself retries an HTTP 429 or 529 up to 3 times inside one call.

The key arrives through the file `SANCHOPANZA_KEYS_ENV` names (never printed, never in this
repository); `a5-unrelated-run.cmd` sets it and the python, as placeholders here, filled only in
the sealed worktree's copy.

**Clock.** About 6-15 minutes for 1,500 calls, one at a time. Launch attended, outside
02:00-08:00 (Windows Update restarts).

## Launch (owner's decision)

    python benchmarks/facts_gate/run.py dry      # free: 1,500 to ask, about 0.04 USD expected
    python benchmarks/facts_gate/run.py power    # free: the table above
    python benchmarks/facts_gate/run.py seal     # after review, with the commit written above
    a5-unrelated-run.cmd                         # from the sealed worktree, by WMI: paid, report
