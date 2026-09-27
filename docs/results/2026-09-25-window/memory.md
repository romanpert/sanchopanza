# `memory_write`: the pre-registered fourth question, three batches written first

Run of 2026-09-25, `jev-1.13.0`, **0.014 USD** for 322 recorded decisions
(`fixtures/memory-common.jsonl`). `benchmarks/memory_common.py` reproduces every number for
free; `tests/test_window_bench.py` pins them.

## What was pre-registered, and when

`docs/results/2026-09-24-third-batch/` located the defect: the shipped policy loses the
client's standing instructions ("the client wants amounts in euros at the rate of the day of
the event"), because `specific` asks whether a fact names figures, dates or outcomes and an
instruction names none. Widening `specific` recovers them at the price of more junk stored,
and is not shipped. What was pre-registered:
a fourth question, `common` ("is this something any competent reader already knows?"), a
batch of cases written before it is measured, and derive on one set, report on another.

Each step below was fixed in code and in a file header **before** the batch it was judged on
was measured, and every criterion is reported whether it passed or not.

| step | written before | policy | criterion | result |
|---|---|---|---|---|
| 1 | `memory-e` (48) | P1: `common` < 0.5 replaces `specific` | beat shipped, no more costly errors | **PASSES**: 45 vs 25, costly 1 vs 3 |
| 2 | `memory-f` (36) | P3: P1 + `specific` >= 0.15 | fewer pointers stored than P1, lose no instruction P1 keeps, no more costly errors | **FAILS**: pointers 12 vs 7 right, costly 3 vs 8, but one instruction lost |
| 3 | `memory-g` (24) | P4: P1 + `specific` >= 0.08 | same as P3 | **FAILS**: pointers stored 0 vs 3, costly 0 vs 3, one instruction lost |

"Costly" is storing what should be skipped: a junk memory is read on every later turn.

## Agreement / costly errors, every batch

| batch | shipped | P1 | P3 | P4 |
|---|---|---|---|---|
| memory-e, 48 (families A-D) | 25 / 3 | 45 / 1 | 45 / 0 | **46 / 0** |
| memory-f, 36 (E, F, H) | 23 / 1 | 28 / 8 | 32 / 3 | **33 / 3** |
| memory-g, 24 (E2, F2) | 12 / 0 | 20 / 3 | 22 / 0 | **22 / 0** |
| earlier 100, in-sample | 70 / 7 | 86 / 9 | 88 / 7 | 88 / 7 |

By family, agreement out of 12:

| family | shipped | P1 | P3 | P4 |
|---|---|---|---|---|
| A standing instructions | **0** | 12 | 11 | 12 |
| B general knowledge | 9 | 12 | 12 | 12 |
| C findings learned by doing | 4 | 10 | 10 | 10 |
| D transient state | 12 | 11 | 12 | 12 |
| E vacuous pointers | 12 | **7** | 12 | 12 |
| F standing instructions | **0** | 12 | 11 | 12 |
| H verbatim detail of a held document | 11 | 9 | 9 | 9 |
| E2 vacuous pointers | 12 | 9 | 12 | 12 |
| F2 instructions, evidence rules | **0** | 11 | 10 | 10 |

## What it says

**The located defect was real and the pre-registered fix fixes it.** The shipped policy
stores **none** of 36 standing instructions across three batches written to test exactly
that. With `common`, 32 to 35 of them depending on the floor (P1 35, P4 34, P3 32). It was not a threshold: `specific` scores those
instructions 0.13 to 0.67, and no cut on it separates them from what it was filtering.

**`specific` was doing a second job nobody had named.** Dropping it (P1) lets vacuous
pointers through - "there is relevant information about the company in several sources",
`specific` 0.02-0.04. A floor on it stops every one of them. Across the 39 cases seen, pointers
never scored above 0.04 and instructions never below 0.13, and both floors tested fell in
that gap - yet each lost one instruction on its own fresh batch, at 0.13 and below 0.08. The
gap is real and narrow, and two batches of 24 and 36 are not enough to place a cut in it.

**So the trade is stable and it is a product decision.** Any floor costs about one standing
instruction in twelve and saves three to five junk memories per batch. The module's own
asymmetry ("an incomplete memory is a worse answer once; a rotting one is a worse answer
forever") argues for the floor. The pre-registered criterion said "lose none", and it is the
criterion that is reported. `memory.decide_write_common(..., specific_floor=...)` exposes the
choice; the shipped default is unchanged and does not ask `common`.

**What none of the variants fixes: `derivable` misses verbatim detail.** "The ruling has
forty-seven pages", "the administrator named in the minutes is J. Perez", "the downloaded
deed gives a share capital of 60,000 euros" score 0.55-0.71 on `derivable`, under its 0.75
cut, under every policy. Family H: shipped 11/12, all `common` variants 9/12. That is the next
located defect, and it is `derivable`'s, not `common`'s.

## The earlier 100 cases, and the widened gate

On the 2026-09-24 recordings (`docs/results/2026-09-24-third-batch/`) the shipped policy
scores 72/100 and **stores five facts labelled skip** (mw-78, 83, 89, 97, 100); widening
`specific` scores 88/100 and stores eight. Two of the shipped five, "the ruling has
forty-seven pages" and "the administrator named in the minutes is J. Perez" (mw-78, mw-97),
are the `derivable` defect above, which no variant of `specific` touches. The "earlier 100"
row in the table differs from 72 / 5 by six cases that had no recording for the
three-question call in this fixture and were asked on 2026-09-25: with them the shipped
figure is 70/100 with 7 costly (mw-13 and mw-25 added). Either way the widened gate stores
more junk than the shipped one, and `common` is the alternative the third-batch report
pre-registered.

## What this does not settle

- **One annotator, who also wrote the question.** Every label in the three new batches is by
  the same author as `common`, the same day. The families were chosen to test the defect,
  which makes them clean; real memory candidates are messier. A second annotator on a sample
  of real candidates is the next step before the default changes.
- **Adding `common` to the joint call moved the other answers little but not zero**: the
  shipped policy scores 24/48 on the four-question call against 25/48 on the three-question
  one. Anyone switching the default must re-record the memory benches.
- **Small batches.** 12 cases per family. The floor question in particular needs a batch of
  low-`specific` instructions large enough to see where they end.
