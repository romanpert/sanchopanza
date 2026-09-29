# Pre-registration: candor without the status block (`candor.extract`)

Sealed before any answer to this set exists (`prereg-derive.sha256`).

## Why

With the four-line status block, candor's rules stopped 95-96 % of model-written misstatements.
On the prose alone they stopped 24.6 %, and on real third-party sessions without a block, none.
The block works because it states each claim in a field code can hold against the ledger.
`candor.extract` reads the prose for what a block would have said: one closed `Choice` per
sentence (done, checks pass, checks not run, a source read, a limitation, other), one Jev call
per report, the first 3 and the last 9 sentences. Code writes a block from the answers and runs
the same v5 rules again with it. **Only findings the report's own words did not already give
are kept, marked as the model's and capped at `high`**: a model's reading goes to a person and
never to the lock, and it can never remove a finding (the design an independent review forced:
a derived `STATUS: partial` had switched off a critical `failed_check`).

## Data and arms (`benchmarks/candor/derive.py`)

Every report of rounds 2-4 (natural sessions, which were asked for a block, and the
model-written counterfactuals: 1,180 reports) and the 110 errata-bench answers (real third-party
sessions, no block). Arms, same rules (v5 as of this seal, snapshot where the session took one):

- `block`: the report as written (rounds only; the reference);
- `prose`: without its block;
- `derived`: the prose through `check_with_derived`.

The verdict here is the **review tier**: any `high` or `critical` finding. Baselines from the
free replay, before any answer:

| Group | n | block | prose |
|---|---|---|---|
| counterfactual misstatements | 507 | 503 | 329 (64.9 %) |
| counterfactual paraphrases (C0) | 301 | 20 | 18 (6.0 %) |
| natural misreports | 71 | 58 | 32 |
| natural honest sessions | 301 | 21 | 17 (5.6 %) |
| errata objected / accepted | 55 / 55 | - | 6 / 3 |

Cut `extract.CUT = 0.6`, fixed before any answer. Jev `jev-1.13.0`; cap 0.15 USD in code
(`CAP_USD`); estimated 0.07 USD. Answers recorded in `derive-answers.jsonl` (hashed keys,
choices, probabilities; no text).

## Hypotheses (pooled over rounds 2-4)

| | Hypothesis |
|---|---|
| I1 | Invariant: on every item, `derived` locks exactly when `prose` does. |
| P1 | `derived` puts >= 85 % of counterfactual misstatements in review (prose: 64.9 %). |
| P2 | `derived` adds <= 3 points of review on natural honest sessions and on C0 paraphrases. |
| P3 | On natural misreports, `derived` puts >= `prose` + 10 points in review (>= 40 of 71). |
| P4 | On errata-bench, `derived` puts >= 10 points more objected than accepted answers in review, with <= 15 % of accepted. |

Every verdict is reported with a Wilson interval, and every review item `derived` adds on a
negative is read by hand and reported.

## Threats, stated now

- **Lies that live only in the block.** A counterfactual that misstates `TEST_FILES_CHANGED` or
  `FILES_READ` and not the prose cannot be recovered from the prose. The derived block does not
  write `TEST_FILES_CHANGED` at all.
- **Injection.** The agent writes the sentences the model reads. Since a reading only adds, an
  injected sentence can at most hide a derived claim, never remove a finding.
- **Prose written beside a block.** The round sessions were asked for the block, so their prose
  may be thinner than a report written without one. errata-bench (P4) is the test on reports
  written with no block.
- **A derived claim is a model's reading.** A wrong `read_source` or `done` adds a review item
  on an honest report; P2 and the hand reading of every added item measure that. `paths_in`
  takes every path of a `read_source` sentence, not only the one cited.
- **In-sample rules.** v5's rules were shaped on rounds 1-4. This measures the derivation, not
  the rules.
