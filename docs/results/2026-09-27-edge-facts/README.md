# The errors of `verify_edge` and `relate_facts` (2026-09-27, free, descriptive)

Pre-registered in `prereg.md` (sha256 of the LF-normalised file in `prereg.sha256`) before the
script ran. Every number replays recordings; nothing was called. `python
benchmarks/edge_facts_errors.py` writes `analysis.json`; `tests/test_edge_facts.py` pins it.
**Nothing changes in code**: every recording of these two points covers the same 50 + 50
cases, they were read before the pre-registration, and so no held-out check is possible. The
pre-registration says so and fixes the batch that would license each change.

## `verify_edge`: 17 committed, 1 backwards

| | |
|---|---|
| committed | 17, precision 16/17, Wilson 95 % lower bound 73 % |
| the backwards one | `ed-26`: `stated` 0.91, `direction` 0.87 |
| smallest `direction` among the 16 right commits | 0.90 |
| `reversed` caught | 4 of 11 |
| decided in code, never asked (no literal mention) | ed-04, 05, 33, 39, 40, 41, 50 |

**Not a two-gates-on-one-number problem.** Each Truth question has one effective cut: commit
needs `stated` confidence >= 0.80 (p >= 0.90) and `direction` confidence >= 0.60 (p >= 0.80);
`reversed` needs `direction` p <= 0.20.

**Not a threshold the data can move.** A `direction` cut of 0.88 would have refused `ed-26`
and kept all 16 right commits, but that is one case. On the batch that holds it (ed-21..50)
the cut commits 8 of 8 right, Wilson lower bound 68 %: below even the 80 % target that
`benchmarks/thresholds.py` allows at this size. The sample-size floor for 80 % is 16 acted
cases per derivation set; there are 9.

**Most likely a wording problem, unproven.** The `direction` question asks which side "has"
the relation and which it is "had towards", which fits possession (`es matriz de`) and fits
actions badly. The misses cluster there: `ed-26` (`audita a` against a passive "fueron
auditadas por", p 0.87), `ed-24` (passive "fue adjudicado a", 0.76), `ed-30` (0.67), `ed-45`
(0.66), `ed-47` (0.55); the four caught are copular or active. Testing a rephrased question
needs new calls on new cases (the fifth batch in `prereg.md`, ~0.003 USD of Jev).

The seven cases with no literal mention (a pronoun, "portuguesa" for Portugal) are answered
`unsupported` by code. For a triple labelled `supported` that is a refusal to commit, the safe
error; a `review` verdict would describe it better, and it is noted, not changed.

## `relate_facts`: 35 of 39 when it decides

On the fourth-batch recording: 35/39 decided, 2 costly (an `agree` / `conflict` confusion,
`fa-30` and `fa-43`, both p 0.74-0.83 just above the gate), 11 abstentions of which 8 are
`unrelated`. `unrelated` is the top option on 8 of its 12 cases, at p 0.61 to 0.94, and 6 of
those 8 sit below the gate.

**The gate is one number, and it is a policy-shape problem as much as a wording one.** Across
7,162 recorded Choice answers, `confidence = (p_top - 1/k) / (1 - 1/k)` to within 0.022 (the
rounding of the reported probabilities): the Choice analogue of `confidence = |2p - 1|`. So
`relax` 0.60 on a three-option question means p_top >= 0.733, on a seven-option one 0.657,
and it is the same cut for all three options although `unrelated` triggers no action and
`agree` / `conflict` do. The package's asymmetry rule says the cheap verdict needs less
confidence. Accepting `unrelated` at a plain majority, every other option as shipped:

| recording (same cases) | shipped: right / decided, costly | `unrelated` at 0.5 |
|---|---|---|
| fourth batch (50) | 35/39, 2 | 41/46, 2 |
| first recording (20) | 14/15, 0 | 15/17, 0 |
| direction-first re-recording (30) | 21/24, 2 | 26/29, 2 |
| option order reversed (50) | 39/42, 1 | 42/45, 1 |
| option order rotated (50) | 38/41, 1 | 42/45, 1 |
| same order re-asked (50) | 36/40, 2 | 41/46, 2 |

Six recordings, one to six more right answers each (+6, +1, +5, +3, +4, +5), never a costly error more. It is still
one set of cases, read before the rule was written, so it is a candidate and not a result.
The missing examples on `unrelated` (the other two options have them) may be why its
probability is low; the two explanations separate only with new cases asked both ways.

## What changed

Nothing on this reading: every number above replays recordings the rules were written after.
The fifth batch that would decide each change was fixed in `prereg.md` and **measured later the
same day** (`fifth-batch.md`): the `direction` question by roles caught 10 of 12 reversed edges
against 5 with no wrong commit, and is now the default of `graph.edge_questions`. The `unrelated`
gate, the `unrelated` examples and the `direction` cut were not licensed and did not move.
