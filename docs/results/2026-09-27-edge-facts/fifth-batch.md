# The fifth batch of `edge` and `facts` (2026-09-27): measured, one change licensed

The protocol is the section "What would license a change later (the fifth batch)" of
`prereg.md` in this directory. The batch was written, hashed and blind-annotated first; the
first attempt to record it got HTTP 402 from TypeSafe (no credits, nothing billed). With the
account recharged the same evening, `benchmarks/fifth_batch.py --record` asked Jev 120 times
(`jev-1.13.0`, **0.0034 USD**) and the four pre-registered rules were applied as written.

**Result: one rule licenses a change, the `direction` question by roles. It is now the default.
The other three do not, and nothing else moved.**

| Rule (prereg) | Shipped | Variant | Licensed |
|---|---|---|---|
| `facts` policy: `unrelated` at 0.5 (shipped question) | 25 right of 27 decided, 1 costly | 25 of 27, 1 costly | **no**: not more right |
| `facts` wording: examples on `unrelated` (shipped policy) | 25 of 27, 1 costly | 25 of 26, 1 costly | **no**: not more right |
| `edge` wording: `direction` by roles (shipped policy) | 5 of 12 `reversed` caught (1 of 8 passive), 1 wrong commit (`ed-57`) | **10 of 12** caught (**6 of 8** passive), **0** wrong commits | **yes** |
| `edge` threshold: `direction` cut 0.88 from the fourth batch | | 9 of 10 commits right here, Wilson lower bound 0.60 | **no**: the batch could not reach 80 % even at 12 of 12 |

The by-roles question also decided more (25 of 30 against 20, all 25 right) and committed all
12 `supported` edges where the old wording committed 11 and one backwards. The weakness the
edge-facts README diagnosed, a `direction` question worded for possession that reads passives
badly, is what moved: passive `reversed` cases went from 1 of 8 caught to 6 of 8.

Outside the rules, descriptive only: with the examples on `unrelated` *and* the 0.5 gate, 27
of 28 decided were right with 1 costly. That combination was not a pre-registered arm and
licenses nothing.

## What exists

| | |
|---|---|
| `benches/graph-e.jsonl` | 30 `facts` cases, fa-51..80: 12 `unrelated`, 9 `agree`, 9 `conflict` |
| `benches/graph-d.jsonl` | 30 `edge` cases, ed-51..80: 12 `reversed` (8 against a passive sentence), 12 `supported`, 6 `unsupported`. Every subject and object appears literally in its text, so every case reaches the decider |
| `fifth-batch/hashes.txt` | sha256 of both files, LF-normalised, written 2026-09-27 20:34 +02:00, before the second annotator and before any call |
| `fifth-batch/annotator-2.jsonl` | the blind second annotator's labels |
| `benchmarks/fifth_batch.py` | `--record` asks Jev once, capped; without it, replays and applies the four rules |
| `tests/test_fifth_batch.py` | pins all of the above |

The `facts` cases are in a `graph-*` file, not `memory-*`: the point lives in
`points/entities.py`, and its earlier cases are in `graph.jsonl` and `graph-c.jsonl`.
Content is invented entities and public bodies; no private persons.

## Second annotator: kappa 1.00

One general-purpose model, given only the cases without labels and the label definitions of
`benchmarks/annotate.py` (plus the Choice criteria of `fact_questions`), told not to open any
file. It agreed with the author on all 60: `facts` 30/30, `edge` 30/30, Cohen's kappa 1.00,
no disputed case. The rule of the earlier batches (`2026-09-24-fifty/README.md`) keeps labels
as written and lists disputed cases; there are none to list or exclude.

Read this as the earlier batches say to: a model given the author's own criteria is not two
independent humans. And agreement this complete also says the batch may be easier than the
fourth one, which the measurement would have to show.

## The variants, in code

- `graph.edge_questions(..., direction_by_roles=True)` asks `direction` as `DIRECTION_BY_ROLES`:
  who does, holds or is the source of the relation against who it is done to, and how to read a
  passive. **Default since this batch**, and `Squire.verify_edge` uses it.
  `direction_by_roles=False` is the earlier possession wording: `eval.bench` passes it for the
  recorded edge benches (a case opts in with `"direction_by_roles": true`), and the fourth-batch
  and edge-facts analyses pass it, so every earlier recording still replays.
- `entities.fact_questions(..., unrelated_examples=True)` and
  `entities.decide_facts(..., unrelated_at=0.5)` stay available and **off**.

## Why the threshold rule could not pass on this batch

Derived on the fourth-batch recording under the rule of `benchmarks/thresholds.py` (the least
strict cut whose Wilson 95 % lower bound clears 80 %), the cut is **0.88**: 16 of 16 commits
right, lower bound 0.806. Reporting it needs the fifth batch to clear 80 % too, and the fifth
batch has 12 `supported` cases: a perfect 12 of 12 has a lower bound of **0.757**. The
pre-registered composition could not license it whatever Jev answered; measured, it committed
10 with 9 right (0.60). That arm needs a batch with at least 16 `supported` cases.

## Reproducing

    python benchmarks/fifth_batch.py      # free, replays fixtures/fifth-batch/recording.jsonl

`tests/test_fifth_batch.py` pins every number above and the defaults that follow from them.
