# Pre-registration: the BM25 prefilter's probe (Jev only, 3 dev questions, K = 200)

Instrument commit: `50e645f42df6d0bb13fd0043ff42749cbe3142ff`

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

By hand, before starting the launcher:

- **The owner checks the TypeSafe balance holds at least 0.10 USD.** This is a manual check: the
  preflight only detects a balance of zero, and a 402 in mid-run makes the probe not run, for
  good (section 6).
- It is started outside the Claude Code session (WMI, CreateFlags 512) from a worktree detached
  at the seal commit, with the launcher's two local values filled in that worktree's copy only.

Then, in the order the code checks them:

1. The launcher refuses a phase other than dev, confirm or probe, the hours 00:00 to 08:00, and
   its local values unset.
2. `jev_phase.py paid`: the launcher given is the lot's (its digest, local values masked).
3. The plan fits in what the lot's ledger has left: the larger of the dry run's stub estimate
   times 1.417 and the oracle's expected 0.0366 (section 3).
4. The seal: `prereg-probe.sha256` holds this file's sha256 and the launcher's.
5. HEAD descends from the instrument commit above and nothing under `src`,
   `benchmarks/longdoc_free`, `benchmarks/b6_es`, `benchmarks/paid_once.py` or the frozen
   `ids.json` differs from it or is uncommitted; the ∞Bench file has its pinned sha256.
6. HEAD detached at the commit that sealed `prereg-probe.sha256`, the checkout clean except the
   launcher filled in place.
7. Under the lot's lock, **one launch only:** refused after any earlier launch of this lot,
   whatever it did, when its ledger holds any spend, or when its recording (the plain file or
   its `.gz`) holds any answer.
8. The key is read from the file the launcher names, never printed.
9. Inside the run's own event loop, the last check: `jev-preflight` for `jev-1.13.0`
   (`paid_once.preflight`, one short decision outside the ledger). Only then is the launch's
   start line written and the first call made.

## 3. Money

| | USD |
|---|---|
| Expected (the dry oracle: 0.0199 + 0.0111 + 0.0056) | 0.0366 |
| Expected with the 1.5 margin | 0.055 |
| The dry run's stub, pessimistic estimate (`jev_phase.py dry --phase probe`) | 0.0272 |
| **Plan for the room check:** max(0.0272 × 1.417, 0.0366) | **0.0385** |
| Ceiling with the dev's largest sentence stage (3 × 0.031) | 0.094 |
| **The ledger's cap** | **0.06** |
| Bound on the overshoot past it (4 calls in flight × 0.000645) | 0.00258 |
| The preflight, outside the ledger | 0.000013 |
| **Worst total, against the owner's hard 0.10** | **0.0626** |

- **Why 0.06.** The rule (section 4) says no once the three questions' bills pass 0.045
  (3 × 0.015). A stop at the cap leaves at least the cap less the call refused and the
  reservations still open (each under 0.001) in the ledger, past 0.045: such a stop already
  decides "no" (section 6), so nothing past 0.06 is worth paying for. The ledger is the measure
  here, not the recorded bills of section 4: it keeps a call cut in flight or unreachable at its
  estimate, with no bill in the recording, so the two differ only after many such calls (about
  13 timeouts to move it by the margin). The plan, 0.0385, fits with 0.0215
  to spare.
- **Why it cannot exceed 0.0626.** Every call goes through `CappedDecider` on this lot's own
  ledger (`longdoc-free-bm25-probe/ledger.jsonl` under the user's sanchopanza cache), capped at
  **0.06**. It reserves each call's estimate before sending it and refuses any call whose
  reservation would take the ledger past 0.06; a call's bill then settles in place of its
  reservation, and a refused call costs nothing. Bills already settled are in the ledger before
  the next reservation is checked, so only the calls in flight when the cap bites can carry the
  ledger past it: at most 4 (`b6_run.CONCURRENCY`). The guarantee takes each one's whole bill as
  its overshoot, at most 0.000645 USD, the dev's dearest call (a gate over about 60,000 kept
  characters, the largest input the probe sends): 0.06 + 4 × 0.000645 + the preflight's
  0.000013 = **0.0626 USD**, under the owner's 0.10 (in code: `PROBE_HARD_CAP_USD`,
  `PROBE_MAX_BILL_USD`, `PROBE_IN_FLIGHT`, `PROBE_PREFLIGHT_USD`, tested). A call cut in flight
  or unreachable keeps its reservation, which is no overshoot.
- **What the overshoot really is.** Over the dev's 3,969 calls, a bill against its reservation:
  tournament calls at most 0.810 of it (never above it: the largest excess −0.000116 USD),
  sentence calls up to 1.548 times (largest excess +0.000013), gate calls up to 3.314 times
  (largest excess +0.000009). Four calls in flight would carry the ledger past its cap by about
  50 micro-USD; the whole-bill bound above is the guarantee.
- **The plan before the launch:** the stub undercounts real Jev's tournament calls (real/stub
  1.417 pooled on the dev, 0.59 to 2.47 per question), so the room check uses the larger of
  the stub's 0.0272 times 1.417 (0.0385) and the oracle's expected 0.0366: 0.0385, which must
  fit in the ledger's room (0.06 before any spend).
- **Per question:** the tournament over 200 pages makes at most 4 rounds of 7 calls (3 pruning
  rounds and a final one), 28 calls, 0.017 USD at the dev's dearest tournament call; the
  sentence stage has no such ceiling (one call per page passing the final round, up to 200),
  which is why the cap, not the arithmetic, is the guarantee.

## 4. The decision rule (sealed)

A new dev is worth preparing only if the 3 questions average **at most 0.015 USD** of real Jev
and **none exceeds 0.031**.

"Real Jev" for a question is the sum of the billed `cost_usd` of every call the probe recorded
for it: tournament, sentence stage and gate (`probe_read.py`). Both comparisons are `<=` on the
unrounded sums; the report rounds only for display.

A positive verdict authorises only preparing a new dev (its own pre-registration and the owner's
approval); it is not a result on cost or quality.

## 5. What is reported

`probe_read.py` writes `probe-read.json` (this folder), per question: whether it completed, real
tournament calls against the dry oracle's prediction for the same question and K, real sentence
calls, real Jev USD against the oracle's, and the same question's real Jev over the whole novel
in the dev (0.041, 0.070 and 0.068 USD); the recorded bills in all, the ledger's spend; the
launch's end; whether the recording answers every call; the verdict. Calls are counted from the
recording, per decision point: only recorded (answered) calls, never calls attempted.
`jev_phase.py rows --phase probe` writes `jev-probe.jsonl` (per question: the gate's p, kept
characters, whether ∞Bench's normalised reference is in the kept text) as description only:
three questions say nothing on quality. The recording (`fixtures/longdoc-free/jev-probe.jsonl`:
hashed keys and answers, no text) is committed gzipped like the dev's; the replay and
`probe_read.py` read the `.gz` when the plain file is gone. The reading also needs the launch
history (`launches.jsonl`, in the lot's folder under the user's sanchopanza cache): on a clean
clone with only the `.gz` it says "no launch", so the official reading is the one written on
this machine, `probe-read.json`, committed beside the recording.

**Results are committed from outside the sealed run worktree:** the recording, `jev-probe.jsonl`
and `probe-read.json` are copied to another checkout and committed there, never with
`git add -A` in the run worktree, whose filled copy of the launcher holds the key file's path.

## 6. Not run, and decided by spend

The probe is not relaunched in any case (one launch only). When its launch did not end with
every call answered, or the replay finds a call the recording does not answer:

- it is **decided by spend**, a no (`prepare_new_dev` false), when what it already billed says
  no whatever the rest would cost, since bills only add up: it stopped at the cap, or its
  recorded bills are past 0.045 in all, or one question's recorded bills are past 0.031;
- otherwise it is **not run**, with no verdict.

"Bills only add up" holds for a run that is a prefix of a complete one. After an isolated
failure that does not stop the run, the unanswered pages pass the tournament's cut and add a few
tournament calls (about 0.0005 USD), so in a narrow band just past 0.045 or 0.031 a run could be
read "decided by spend" that a run without that failure might not have reached. Either label
leads to no new dev.

Stops that lead there: no launch, or a launch with no end line (killed, a crash, a restart); the
cap (`SpendCapReached`); a 402 (no funds); a 429; an outage (401, 403, a 5xx, no connection);
another model answering; three failures in a row; or any call left unanswered at the end. The
report says which, with what was spent, and the proposal goes back to the owner.

**Accepted risk:** one isolated failure, a 30-second timeout or a 400 on a single call, is not
retried and leaves that call unanswered, so the probe ends not run (unless decided by spend),
with no relaunch. The owner accepted this with the one-launch design.

## 7. Departures

Anything done otherwise than written here is reported as a departure beside the result. An
amendment is written and sealed before any call; one written after is labelled so and does not
replace this rule. The owner's manual balance check (section 2) is part of this registration:
launching without it is a departure.

## 8. The seal

`python -I benchmarks/longdoc_free/jev_phase.py seal --phase probe` writes `prereg-probe.sha256`:
the sha256 of this file (LF) and of `longdoc-free-jev-run.cmd` with its two local values as
placeholders. This file names the instrument commit, so the seal binds the three. It refuses to
write without that commit and never overwrites a different seal.

The launcher is shared with the longdoc-free dev and confirmation phases, and its text has
changed since the dev was sealed: the dev's sealed launcher digest
(`../2026-10-16-longdoc-free/prereg-dev-a1.sha256`) is verified at the dev's own seal commit,
not at HEAD. This probe's digest is the one in `prereg-probe.sha256`.

One change reaches the dev's free paths: `lot_asker` now also reads `jev-dev.jsonl.gz`, so the
dev's `rows` and `dry` can replay from the committed recording where before they found nothing to
read. That replay reproduces the published dev rows (`bm25-dry.json`,
`replay_matches_published_rows: true`); the dev's paid path has no launch left.
