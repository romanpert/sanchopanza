# C5b: the free order against page order, again, on QASPER train questions (pre-registration, DRAFT: a delta on C5)

Status: **proposal, not sealed, no code yet.** This draft lists what differs from C5's sealed
prereg (`docs/results/2026-10-16-c5-free/prereg.md`, sha256 `8b22ed29…`). Everything it does not
change is C5's, word for word: the arms, the metric, the intervals, the rules 0-4 and what they
license, the launch and relaunch rules, the stops. Before a seal it needs a `revisor-prereg`
review, the code below at a new instrument commit, and its dry run.

## Why

C5's sealed reading ("FREE loses to page order", −6.9) does not measure the option. The runner
gave its squire a dollar cap equal to the batch cap. The squire's meter counted every
memo-answered decision again, and 1,437 of FREE's decisions were cut to defaults
(`docs/results/2026-10-16-c5-free/README.md`). With the cap lifted, the same recorded answers
give +12.0 [+6.7, +17.0], post-data, in line with B4's exploratory +13.6. Neither is a
confirmation. C5b asks C5's question once more, with the fixed runner, on questions no run of
this package has read.

## What changes

1. **Questions: QASPER train** (CC BY 4.0), `allenai/qasper`, the parquet of the
   `refs/convert/parquet` branch (`qasper/train/0000.parquet`, sha256
   `9af08092ee26c4f700202c1f90d1592b662926f23f3a308a10ff0a53345e37fe`, 888 papers). It is exported
   by C5's recipe (`to_pylist`, one paper a JSON line, LF; sha256
   `1f97c5fd3b308e601b82bf00551519ad190597caebc066f44c56cdd160926c74`). The questions are built by
   C5's `build_rows`: 1,840 eligible, 184 not located, 3 misaligned, **1,653** built.
   - **The draw:** papers in an order shuffled with seed 20261019, every built question of each
     paper, until the count reaches 646 (C5's size). This takes **300 papers and exactly 646
     questions**.
   - None of these papers is in the validation split. No run of this package has used the train
     split (no reference in `benchmarks/`, `src/` or `docs/`).
2. **The runner's squire has no cap of its own** (`SQUIRE_CAP_USD = 1e9`, already in
   `free_confirm.py` since a168ad6, with its test). The caps are the ledger's.
3. **Lot:** `c5b-free`. Its own recording is `fixtures/c5b-free/recording.jsonl`, its launches go
   in `~/.cache/sanchopanza/c5b-free/`, and its launcher is `c5b-free-run.cmd`. Batch cap **2.00 USD** on the round's shared ledger.
   At the time of writing that ledger holds 1.257 USD of 6.00 (C4 0.035, C5 1.222), so it leaves
   **4.74 USD**.
4. **Instrument:** C5's paths plus whatever file holds the split parameter. The launcher stays out
   of the instrument (the seal fixes it).

## Code still to write (none of it changes `src/`)

- `free_confirm.py` takes the split as a lot parameter: the lot name, the parquet and export
  hashes, the export path and the results folder. Alternatively a thin `free_confirm_b.py`
  imports it and sets those constants; C5's values stay as sealed.
- The paper-wise draw above (`draw(rows, seed, size)`), with a test that it takes 300 papers and
  646 questions on the pinned export and that none of the papers is in validation.
- `w17_round.BATCH_CAPS["c5b-free"] = 2.00`; the launcher and its row in `tests/test_launchers.py`.

## Power

The expected population is about 346 questions, if a share like C5's overflows 3,400 characters
(346 of 646). C5's post-data cluster interval has a half-width of 5.2 points at that size. At
alpha 0.05 two-sided, normal approximation, the chance that rule 1's lower bound clears 0 is:
- 0.99 at a true +12.0;
- 0.86 at +8;
- 0.63 at +6.

## Cost and caps

C5 settled 1.222 USD on the ledger for the same number of questions (8,202 calls, 29.1 M input
tokens), so the expected cost is **about 1.2 USD** (1.0-1.5). The batch cap is 2.00 USD. The dry
run's pessimistic estimate must fit both the batch's room and the round's (`paid_once.room`).
Claude: 0. Expected clock: about 25 minutes. It does not run at the same time as another lot.
