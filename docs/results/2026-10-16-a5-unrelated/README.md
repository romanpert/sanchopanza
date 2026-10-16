# A different `unrelated` gate for `relate_facts` (A5)

**The result:** below the shipped confidence gate, accepting `unrelated` when it is the top
option at probability >= 0.65 (`decide_facts(..., unrelated_at=0.65)`) **beats the shipped
policy under the sealed rule**. On 1,500 new pairs with labels by construction it added 39
verdicts. All 39 were right, none was a missed conflict, and the Wilson 95 % lower bound is
0.910.

The verdict licenses a *proposal* to make 0.65 the default in `relate_facts`, not the change.
The band was thinner than planned: 39 added verdicts against about 70 expected. And this
batch's `agree` and `conflict` cases are easy, so it could hardly show the gate's wrong
verdicts. Both limits are below.

Pre-registered in `prereg.md`:
- instrument commit `92107d2`, sealed in `f392ee8`;
- cases sha256 `d793dd4a…4a4e`;
- `prereg.sha256` holds the hash of `prereg.md` and of `a5-unrelated-run.cmd`;
- reviewed by `revisor-prereg` before the seal.

Run on 2026-10-16 from a detached worktree at the seal commit, started outside the session
(WMI). The paid step ran from 10:26:02 to 10:31:44 and the report finished at 10:31:45. Jev
(`jev-1.13.0`) answered **1,500 of 1,500** calls on the first launch, with no relaunch, no
unanswered case and no refusal. The ledger settled **0.0348 USD** under the 0.15 cap (23
micro-USD a call, against 28 measured on the fifth batch). Claude: 0.

## The question

`relate_facts` answers `agree`, `conflict` or `unrelated` and commits only at confidence >= 0.60
(`relax`); below that it returns no relation. The fifth batch had tested `unrelated_at=0.5` and
found no gain. On the recordings, no gate in 0.40-0.70 added a single verdict there: that batch
had no case in the band, so it could not decide. The gate tested here, 0.65, was derived
before the run on the recorded `graph` and `graph-c` answers (`free.json`). It was then
measured on cases nobody had looked at.

## What ran

- **Cases.** 1,500 pairs over invented entities: eight kinds, three numeric attributes each,
  two wordings per language, Spanish and English alternating. Labels come by construction:
  - 560 `unrelated`: two attributes of one entity;
  - 40 `unrelated`: the same attribute of two entities;
  - 225 `agree`: the same value, reworded;
  - 225 `agree`: the same value, reworded, with its source;
  - 450 `conflict`: two values of the same attribute.

  Both wordings of each attribute name the same event or magnitude, and a test checks this for
  all 24 attributes.
- **Calls.** One per case: the shipped question, point `facts`. Every gate is applied in code to
  the same answers.

## The verdict, by the sealed rule

| Condition (prereg) | Needed | Measured |
|---|---|---|
| Added verdicts at 0.65 | at least 16 | **39** |
| Missed conflicts among them | 0 | **0** |
| Wilson 95 % lower bound of their precision (unrounded) | >= 0.80 | **0.910** (39 of 39 right) |

**The gate beats the shipped policy.**

## Every gate of the family (descriptive: only 0.65 was under test)

| `unrelated_at` | Added verdicts | Right | Missed conflicts | Wilson 95 % low |
|---|---|---|---|---|
| 0.40 | 227 | 227 | 0 | 0.983 |
| 0.45 | 227 | 227 | 0 | 0.983 |
| 0.50 | 227 | 227 | 0 | 0.983 |
| 0.55 | 143 | 143 | 0 | 0.974 |
| 0.60 | 91 | 91 | 0 | 0.959 |
| **0.65** | **39** | **39** | **0** | **0.910** |
| 0.70 | 11 | 11 | 0 | 0.741 |

On this batch no gate added a wrong verdict, down to 0.40. That says more about the batch than
about the gate (see the limits). The lower gates were not the registered test and license
nothing. The 0.5 that failed to help on the fifth batch adds 227 right verdicts here.

## The shipped policy on this batch

| Shape | n | Decided | Right | Unrelated read as `agree` |
|---|---|---|---|---|
| unrelated, two attributes of one entity | 560 | 52 | 13 | **39** |
| unrelated, two entities | 40 | 39 | 39 | 0 |
| agree, reworded | 225 | 225 | 225 | 0 |
| agree, with source | 225 | 225 | 225 | 0 |
| conflict | 450 | 449 | 449 | 0 |
| **all** | 1,500 | 990 | 951 | 39 |

No costly (`agree`/`conflict`) error. The shipped policy leaves 508 of the 560 same-entity
pairs undecided; at 0.65 the gate decides 39 of them. Its 39 wrong verdicts are same-entity
`unrelated` pairs read as confident `agree`. An `unrelated` gate cannot touch them, and they
stay as they are.

## Where the added verdicts come from (`added_by_type`)

| Kind: attribute pair | Added | Wrong |
|---|---|---|
| bridge: lanes + year | 9 | 0 |
| plant: staff + year | 7 | 0 |
| hospital: theatres + year | 6 | 0 |
| hospital: beds + theatres | 3 | 0 |
| museum: visitors + works | 3 | 0 |
| reservoir: capacity + year | 3 | 0 |
| company: employees + year | 2 | 0 |
| cooperative: hectares + members | 2 | 0 |
| bridge: lanes + length | 1 | 0 |
| cooperative: hectares + year | 1 | 0 |
| festival: attendance + days | 1 | 0 |
| plant: output + staff | 1 | 0 |

The 39 come from 12 of the batch's cells. Three cells hold 22 of them, and 28 pair an attribute
with a year.

## Expected band against the real one

The prereg projected about 70 added verdicts: the 12.5 % band of the recordings over the 560
same-entity pairs, or 45 at a conservative 8 %. The real band was **39 of 560 (7.0 %)**, under
the conservative figure. The rule still decided, because every added verdict was right. With
two wrong of 41, the bound would have fallen to about 0.84 and still passed. The power the
prereg planned around 0.93 precision never came into play.

## What it licenses, and what it does not

As the prereg wrote before the run: a **proposal** to make `unrelated_at=0.65` the default of
`decide_facts` (and so of `relate_facts`), to be checked on written text before the change.
**Not the change.** `decide_facts` keeps `unrelated_at=None` by default.

The limits, as registered:
- **The `agree` cases are easy paraphrases of one value.** All 450 were decided and right, and
  none came near the band. The only wrong verdict the gate ever made on the recordings was
  fa-17: two dated events read as `unrelated`, at 0.63 and 0.59. Its type is absent here. So
  this batch cannot measure the wrong `unrelated` verdicts a real mix would add, and the 100 %
  precision is an upper reading.
- **The cells are not independent.** The 39 come from templated cells (8 kinds × 3 attributes
  × 2 wordings × 2 languages), concentrated as the table above shows. Wilson treats them as 39
  independent draws, and the effective sample is smaller.
- **Missed conflicts.** None of the 450 conflicts entered the band at any gate. Before the run,
  0 of 58 recorded conflicts had either (rule of three: at most about 5 %). This batch's
  conflicts state two plainly different values, so the guard held where it was easiest to hold.

## Cost and clock

- **Cost.** 0.0348 USD settled in the ledger: 1,500 calls, each priced at its input tokens ×
  0.042 USD per million. That is under the 0.042 expected and the 0.15 cap.
- **Clock.** About 5.7 minutes, at the low end of the 6-15 planned.

## Not done

- The default did not move: `unrelated_at` stays `None`.
- No check on written text. A batch with fa-17's kind of pair (two dated events, a role and an
  act, a figure and its subset) is what the proposal needs before the change.
- The 39 same-entity pairs the shipped policy reads as confident `agree` are untouched, and no
  gate on `unrelated` reaches them.
- Only `jev-1.13.0`. Jev 1.14 was not asked.

## Reproducing

    python benchmarks/facts_gate/run.py report   # free, from fixtures/facts-gate/recording.jsonl

`analysis.json` is the report the sealed run wrote. `fixtures/facts-gate/recording.jsonl` holds
keys, token counts, costs and the answers (probabilities of `agree`, `conflict` and
`unrelated`), no text. `free.json` is the derivation on the earlier recordings.
