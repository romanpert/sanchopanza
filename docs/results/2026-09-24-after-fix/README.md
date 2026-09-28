# The widened `specific` gate, measured and not shipped

Re-recorded after pseudonymization hardening (2026-09-28): the cases whose text concerned
pseudonymized persons were reworded and asked again; agreement did not move; the
per-case rows and the calibration figures in `summary.md` are re-derived.

This directory records `memory_write` and `redundant_page` measured with the `specific`
question widened to admit rule-shaped facts - the candidate fix for the defect described in
`../2026-09-24-third-batch/README.md` section 3. It is kept because the package does not ship
it, and the reason is a number, not a preference:

| | agreement | errors in the costly direction | errors in the safe direction |
|---|---|---|---|
| shipped (`../2026-09-24-third-batch`) | 72/100 | 5 | 23 |
| here, with `specific` widened | **88/100** | **8** | 4 |

Sixteen more right answers, bought by storing more facts that should be skipped, such as
`Panama is a country in Central America`. Four of the eight (`mw-78`, `mw-83`, `mw-89`,
`mw-97`) the shipped policy stores as well; the other four are new. For a store that is read
on every later turn, that is the wrong direction to trade in, and `points/memory.py` says so
in its own first paragraph. The pre-registered alternative, a `common` question, is measured
in `../2026-09-25-window/memory.md`.

A run that argues against its own change is worth keeping: without it the decision could not
be explained.

Nothing here is the shipped behaviour. `fixtures/after-fix.jsonl` replays it.
