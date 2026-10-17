# Pre-registration: the BM25 prefilter's probe (Jev only, 3 dev questions, K = 200)

Instrument commit: `073589b3e9e8bff7c0098b6ae83f91484dc3fff9`

Written 2026-10-17, before any call of this probe. Approved by the owner on 2026-10-17 as
proposed in `README.md` (this folder). Sealed by `prereg-probe.sha256` (below) only after an
independent review; until then this file may change and nothing may be spent.

## 1. What is run

- **Model:** Jev `jev-1.13.0` (TypeSafe), no long context, the model of the longdoc-free dev.
  No Claude session of any kind.
- **Questions:** three questions of the longdoc-free dev (∞Bench En.QA `longbook_qa_eng`,
  revision `90f0394`, the frozen `../2026-10-16-longdoc-free/ids.json`): **ids 0, 7 and 375**,
  fixed in code (`jev_phase.PROBE_IDS`). Chosen on the dry run's oracle at K = 200 to span its
  predicted cost: id 0 the dearest (0.0199 USD), id 375 the median (0.0111, the longest novel,
  1,552 pages), id 7 the cheapest (0.0056).
- **Per question**, `jev_phase.ask` with `prefilter_k = PROBE_K = 200`, fixed in code:
  1. the novel in pages (`pages.pages_of`, at most 900 characters, as the dev);
  2. the **200 pages BM25 scores best for the question** (`pages.bm25_shortlist`:
     `text.BM25Index`, ties by position, kept in the novel's order); no other page enters;
  3. `Squire.select_passages` over those 200 pages exactly as the dev ran it: `fit_chars =
     60,000`, the free order (`fit_score = False`), no `max_calls`;
  4. the gate, one Truth: "`passages` are excerpts of one novel. They state everything needed
     to answer `question`."
- **Asker:** B6's (`b6_run.Asker`): recording first, one live call on a miss, never retried, at
  most 4 in flight, an identical call asked once; it stops at a cap refusal, an outage (401, 402,
  403, 429, a 5xx, no connection), an answer from another model or three failures in a row.
- **Command:** the launcher `longdoc-free-jev-run.cmd probe`, which runs
  `jev_phase.py paid --phase probe --launcher <itself>` and, only when that exits 0,
  `jev_phase.py rows --phase probe` (the free replay). Then, by hand and free,
  `probe_read.py`.

## 2. Before the launch (each refusal spends nothing)

- `jev-preflight` for `jev-1.13.0`, in the run's own event loop (`paid_once.preflight`).
- The seal: `prereg-probe.sha256` holds this file's sha256 and the launcher's (its two local
  values, the python and the key file, read as placeholders).
- HEAD detached at the commit that sealed `prereg-probe.sha256`, the checkout clean except the
  launcher filled in place; HEAD descends from the instrument commit above and nothing under
  `src`, `benchmarks/longdoc_free`, `benchmarks/b6_es`, `benchmarks/paid_once.py` or the
  frozen `ids.json` differs from it; the ∞Bench file has its pinned sha256.
- The plan fits in what the lot's ledger has left: the larger of the dry run's stub estimate
  times 1.417 and the oracle's expected 0.0366 (section 3).
- **One launch only:** refused after any earlier launch of this lot, whatever it did, when its
  ledger holds any spend, or when its recording holds any answer.
- The launcher refuses between 00:00 and 08:00, with its local values unset, or with a phase other
  than dev, confirm or probe. It is started outside the Claude Code session (WMI, CreateFlags
  512) from the detached worktree.

## 3. Money

| | USD |
|---|---|
| Expected (the dry oracle: 0.0199 + 0.0111 + 0.0056) | 0.0366 |
| Expected with the 1.5 margin | 0.055 |
| The dry run's stub, pessimistic estimate (`jev_phase.py dry --phase probe`) | 0.0272 |
| **Plan for the room check:** max(0.0272 × 1.417, 0.0366) | **0.0385** |
| Ceiling with the dev's largest sentence stage (3 × 0.031) | 0.094 |
| **The ledger's cap** | **0.095** |
| Worst overshoot past it (4 calls in flight × 0.000645) | 0.0026 |
| **Worst total, against the owner's hard 0.10** | **0.0976** |

- **Why it cannot exceed 0.10:** every call goes through `CappedDecider` on this lot's own
  ledger (`longdoc-free-bm25-probe/ledger.jsonl` under the user's sanchopanza cache), capped at
  **0.095**. It reserves each call's estimate before sending it and refuses any call whose
  reservation would take the ledger past 0.095; a call's bill then settles in place of its
  reservation, and a refused call costs nothing. A bill can exceed its reservation (on the
  dev, tournament calls billed at most 0.81 of it, sentence calls up to 1.55 times and gate
  calls up to 3.3 times), and a call's overshoot is less than its whole bill. Bills already
  settled are in the ledger before the next reservation is checked, so only the calls in
  flight when the cap bites can carry the ledger past it: at most 4 (`b6_run.CONCURRENCY`),
  each billing at most 0.000645 USD, the dev's dearest call (a gate over about 60,000 kept
  characters, the largest input the probe sends; tournament calls send 30 pages of at most
  900 characters, about half of it). So the spend is at most 0.095 + 4 × 0.000645 = **0.0976
  USD**, under the owner's 0.10 (in code: `PROBE_HARD_CAP_USD`, `PROBE_MAX_BILL_USD`,
  `PROBE_IN_FLIGHT`, tested). A call cut in flight or unreachable keeps its reservation, which
  is no overshoot.
- **The plan before the launch:** the stub undercounts real Jev's tournament calls (real/stub
  1.417 pooled on the dev, 0.59 to 2.47 per question), so the room check uses the larger of
  the stub's 0.0272 times 1.417 (0.0385) and the oracle's expected 0.0366: 0.0385, which must
  fit in the ledger's room (0.095 before any spend).
- **Per question:** the tournament over 200 pages makes at most 4 rounds of 7 calls (3 pruning
  rounds and a final one), 28 calls, 0.017 USD at the dev's dearest tournament call; the
  sentence stage has no such ceiling (one call per page passing the final round, up to 200),
  which is why the cap, not the arithmetic, is the guarantee. Reaching it makes the probe "not
  run" (section 6).
- The owner's TypeSafe balance must hold at least 0.10 USD before the launch.

## 4. The decision rule (sealed)

A new dev is worth preparing only if the 3 questions average **at most 0.015 USD** of real Jev
and **none exceeds 0.031**.

"Real Jev" for a question is the sum of the billed `cost_usd` of every call the probe recorded
for it: tournament, sentence stage and gate (`probe_read.py`). Both comparisons are `<=` on the
unrounded sums; the report rounds only for display.

A positive verdict authorises only preparing a new dev (its own pre-registration and the owner's
approval); it is not a result on cost or quality.

## 5. What is reported

`probe_read.py` writes `probe-read.json` (this folder), per question: real tournament calls
against the dry oracle's prediction for the same question and K, real sentence calls, real Jev
USD against the oracle's, and the same question's real Jev over the whole novel in the dev
(0.041, 0.070 and 0.068 USD); the ledger's spend; the launch's end; whether the recording
answers every call; the verdict. `jev_phase.py rows --phase probe` writes `jev-probe.jsonl`
(per question: the gate's p, kept characters, whether ∞Bench's normalised reference is in the
kept text) as description only: three questions say nothing on quality. The recording
(`fixtures/longdoc-free/jev-probe.jsonl`: hashed keys and answers, no text) is committed
gzipped like the dev's.

## 6. Not run

The probe is **not run**, with no verdict, and is not relaunched (one launch only) when:

- it has no launch, or its launch has no end line (killed, a crash, a restart);
- its launch stopped: the cap (`SpendCapReached`), a 402 (no funds), a 429, an outage (401,
  403, a 5xx, no connection), another model answering, or three failures in a row, or any
  call unanswered;
- the replay finds a call the recording does not answer.

Then the report says which, with what was spent, and the proposal goes back to the owner.

## 7. Departures

Anything done otherwise than written here is reported as a departure beside the result. An
amendment is written and sealed before any call; one written after is labelled so and does not
replace this rule.

## 8. The seal

`python -I benchmarks/longdoc_free/jev_phase.py seal --phase probe` writes `prereg-probe.sha256`:
the sha256 of this file (LF) and of `longdoc-free-jev-run.cmd` with its two local values as
placeholders. This file names the instrument commit, so the seal binds the three. It refuses to
write without that commit and never overwrites a different seal.
