# D1: OpenAI's Decisions API as a provider, on the public benches

Status: **to be sealed** after an independent review against the code. The seal (`prereg.sha256`,
written by `python benchmarks/openai_decisions/run.py seal`) holds the sha256 of this file and of
`openai-decisions-run.cmd` with its two local values read as placeholders.
Instrument commit: `<INSTRUMENT_COMMIT>`.

## Question

sanchopanza is a layer with one decision contract; Jev is the provider every figure was measured
with. OpenAI's Decisions API (`/v1/decisions`, `gpt-6-luna`, public beta since 2026-10-06) is a
second hosted provider of the same kind: typed questions in, probabilities out, input tokens
only billed (0.10 USD per million, 2.4x Jev's 0.042). The adapter `create("openai-decisions")`
(`src/sanchopanza/providers/openai_decisions.py`, commit `3f42339`) was written against OpenAI's
guide and has never been called. **Asked as sanchopanza ships, with its questions, its policies
and thresholds (set against Jev), does it decide the public benches as well as Jev does?**

This is a first measurement of a provider, not a product claim: one draw, the thresholds are
Jev's, and the public benches are small.

## Data

- The public benches: `benches/core.jsonl`, `benches/safety.jsonl`, `benches/graph.jsonl`
  (245 cases; 244 scored rows plus one plan), the same files CI replays.
- They ask **301 distinct queries** whatever the answers: the set is the same under null answers
  and under Jev's recording (checked before this prereg; `run.py` refuses another count).
- **Jev's arm is the existing recording** `fixtures/public-benches.jsonl` (jev-1.13.0, the public
  run), replayed free. No Jev call in this lot.
- **OpenAI's arm**: each of the 301 queries asked once, recorded in
  `fixtures/openai-decisions/public-benches.jsonl`, then replayed through the same bench.

## Run

- `python benchmarks/openai_decisions/run.py paid` through `openai-decisions-run.cmd` only, from a
  detached worktree at the sealed commit, outside the session (WMI), once. `paid_once.run_paid`
  refuses before reading the key unless the seal, the instrument commit (the paths in
  `run.LOT.instrument` unchanged since it), the cap and the launch rule hold (one launch, at most
  one relaunch, none after a 402, a 429 or the cap).
- **Preflight:** one predicate through the lot's own ledger; it must answer, with a model whose
  name is `gpt-6-luna` or `gpt-6-luna-<snapshot>`. Then the client is built in the same event
  loop and the 301 queries are asked in order, one at a time, each recorded as it comes. The run
  stops at the first refusal, failure, empty answer or answer from another model.
- **Key:** `OPENAI_API_KEY` from the file `SANCHOPANZA_KEYS_ENV` names (the launcher's copy only),
  never printed.
- `run.py report` (free): both arms replayed through `sanchopanza.eval.bench` under the shipped
  `Thresholds()` (jev-1.13.0's: no model profile applies to `gpt-6-luna`) and the shipped point
  policies, `relate_facts` with 0.3.2's `unrelated_at=0.65`, the same for both arms; cases paired
  by id.

## Verdict rule (applied by `run.py report`, as written)

- **Primary:** a row is *right* when it is decided and correct under the shipped policy (an
  abstention is not right: the harness falls to its default). Difference **OpenAI minus Jev** in
  the share of the 244 rows right; **paired bootstrap 95 % interval** (10,000 draws, seed
  20261016), compared unrounded; exact McNemar on the discordant rows, reported.
- **Margin −5 points.** "mejor" when the lower bound is above 0; "no peor" when it is above −5;
  "peor" when the upper bound is below −5; otherwise "no concluyente".
- A query left unanswered in the recording (a refusal, a stop) makes its rows abstentions for
  OpenAI in the primary reading; their count is reported (`queries_unanswered_in_recording`).
- **Secondary, descriptive:** per point, agreement when deciding, coverage, AUC, Brier and ECE
  on the binary points, and accuracy at a plain 0.5 cut (`at_0.5`), for both arms; cost and
  median latency per call; calibration by primitive.

## Power, said plainly

Jev is right on 206 of the 244 rows (84.4 %). By simulation with the two arms equal on average,
the chance of "no peor" at −5 is about 0.88 if they disagree on 6 % of the rows, 0.70 at 10 %,
0.54 at 15 % and 0.42 at 20 %; if OpenAI is 2 points worse, about 0.20-0.50. At 244 rows a
"no concluyente" is a likely outcome and would be reported as such. Parity at a tighter margin
would need the 1,437 component items of L1 (about 0.24 USD), a separate lot.

## Cost and caps

- 301 queries. The pessimistic estimate (three characters a token) is about 130,000 tokens,
  0.013 USD; Jev counted 184,535 input tokens on the same queries, and OpenAI's overhead per
  question is unknown, so the expected cost is **0.013-0.04 USD**.
- **Hard cap 0.10 USD** in the lot's ledger (`~/.cache/sanchopanza/openai-decisions/ledger.jsonl`),
  each call reserved before it is made; past it no call is made. The provider's own default
  ledger is not used (the runner builds the client behind its own `CappedDecider`).
- The owner approved spending on OpenAI for this lot on 2026-10-16. The account's balance is
  small (about 6.50 USD); a quota answer (402, or 429 `insufficient_quota`) stops the run and is
  never retried.

## What it would and would not license

- "no peor" or "mejor": OpenAI's Decisions API is a usable second provider for the public
  points as shipped, on this sample; worth a parity lot on the 1,437 component items and a
  threshold profile of its own before recommending it anywhere.
- "no concluyente": the sample cannot tell; the per-point table says where they differ.
- "peor": with Jev's thresholds it decides worse; a profile of its own might change that, which
  this lot does not test.
- Nothing about calibration over images (not wired), long context or latency under load.
