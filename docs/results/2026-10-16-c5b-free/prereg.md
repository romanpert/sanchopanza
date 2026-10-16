# C5b: the free order against page order, again, on QASPER train questions (pre-registration, a delta on C5)

Status: draft for `revisor-prereg`, not sealed. The seal, `prereg.sha256`, is written by `python -I
benchmarks/passage_fit/free_confirm_b.py seal`; it holds the sha256 of this file and of
`c5b-free-run.cmd`, its two local values read as placeholders.
Instrument commit: `3386caa7efb280fe7046bf0b89a783805deb90c3`.

**Lineage.** The seal commit is a descendant of 3386caa on this branch, with no merge of `main`
(`main` changed 36 files under `src/` since, and the instrument check would refuse). The lot is
launched from a `git worktree add --detach` at that seal commit.

This prereg lists what differs from C5's sealed prereg (`docs/results/2026-10-16-c5-free/prereg.md`,
sha256 `8b22ed29…`, sealed in `3a201f0`). Everything it does not change is C5's, word for word:
- the option under test, `select_passages(fit_chars=3400, fit_score=False)`;
- the arms (PAGE, FREE, BM25, GOLD), the budget B = 3,400 and the population;
- the metric, the cluster bootstrap over papers, and the unrounded bound;
- rules 0-4 and what each licenses;
- the launch and relaunch rules, and the stops;
- the model, `jev-1.13.0` (`b6_run.MODEL`);
- the verdict, applied by `free_confirm_b.py report` through C5's `report`.

What follows from the inherited rules, stated here:
- A 402 mid-run (TypeSafe out of funds) is a stop of kind "funds", which allows no relaunch. With
  calls unanswered, rule 0 then applies: "no verdict: incomplete". The balance cannot be checked
  from the session.
- A "busy" stop (the ledger's lock not had within 5 seconds) on the first launch uses the single
  relaunch.

## Why

C5's sealed reading ("FREE loses to page order", −6.9) does not measure the option. The runner
gave its squire a dollar cap equal to the batch cap. The squire's meter counted every
memo-answered decision again, so 1,437 of FREE's decisions came back as defaults without being
asked (`docs/results/2026-10-16-c5-free/README.md`). The same recorded answers with the cap lifted
give +12.0 [+6.7, +17.0], post-data, in line with B4's exploratory +13.6. Neither is a
confirmation. C5b asks C5's question once more, with the fixed runner, on questions no run of
this package has read.

## What changes

1. **Questions: QASPER train** (CC BY 4.0), `allenai/qasper`, the parquet of the
   `refs/convert/parquet` branch: `qasper/train/0000.parquet`, sha256
   `9af08092ee26c4f700202c1f90d1592b662926f23f3a308a10ff0a53345e37fe`, 888 papers.
   - **Export:** C5's recipe (`free_confirm_b.py export`, one paper a JSON line, LF), sha256
     `1f97c5fd3b308e601b82bf00551519ad190597caebc066f44c56cdd160926c74`. `paid`, `dry` and
     `report` refuse another file.
   - **Building:** C5's builder, unchanged: 1,840 questions eligible, 184 not located, 3
     misaligned, 1,653 built.
   - **The draw** (`free_confirm_b.draw`): papers in an order shuffled with seed 20261019 (C5's
     seed + 1, the first one tried), every
     built question of each, until the count reaches 646 (C5's size). This takes **300 papers
     and 646 questions**.
   - None of these papers is in the validation split (tested). No run of this package has read
     the train split.
   - The inherited refusal of a wrong parquet still says "validation" in its message. This is
     cosmetic, left as is to keep the instrument at 3386caa.
2. **The runner's squire has no cap of its own** (`SQUIRE_CAP_USD = 1e9`) in every action,
   `report` included. The caps are the ledger's. C5's `postdata` action is refused here.
3. **Lot `c5b-free`:**
   - recording `fixtures/c5b-free/recording.jsonl`, launches in `~/.cache/sanchopanza/c5b-free/`;
   - launcher `c5b-free-run.cmd` (it refuses to start between 00:00 and 08:00);
   - results folder `docs/results/2026-10-16-c5b-free/`;
   - batch cap **2.00 USD** on the round's shared ledger. That ledger holds 1.257 USD of 6.00
     (C4 0.035, C5 1.222) at the time of writing, so it leaves **4.74 USD**. `paid` refuses
     unless the dry run's pessimistic estimate fits both the batch's room and the round's.
4. **Code:** `benchmarks/passage_fit/free_confirm_b.py` loads a private copy of `free_confirm.py`
   and sets only that copy's constants. C5's file keeps its sealed values (tested), and nothing
   in `src/` changes.
5. **Instrument:** C5's paths. They include `benchmarks/passage_fit/` (so `free_confirm_b.py`)
   and `benchmarks/w17_round.py` (the batch cap). The launcher is not an instrument path: the
   seal fixes it.

## Power

The expected population is about 346 questions, if a share like C5's overflows 3,400 characters
(346 of 646). C5's post-data cluster interval has a half-width of 5.2 points at that size. At
alpha 0.05 two-sided, normal approximation, the chance that rule 1's lower bound clears 0 is:
- 0.99 at a true +12.0;
- 0.86 at +8;
- 0.63 at +6.

## Cost, caps and clock

- **Dry run** (`free_confirm_b.py dry`, B6's stub): 646 questions, 7,379 calls (2,255 tournament,
  5,124 sentence), **1.41 USD** pessimistic, 0.77 at the QASPER whole-papers run's ledger rate.
- **Expected cost:** C5 settled 0.955 of its dry run's pessimistic estimate (1.222 of 1.284
  USD). At that ratio C5b's 1.41 gives about 1.35, and train papers' calls are larger, so the
  expected cost is about **1.3-1.4 USD**, under the 2.00 batch cap.
- **Caps:** batch cap 2.00 USD on the round's shared ledger. Ledger dollars are each call's
  input tokens x 0.042 USD per million, not TypeSafe's bill. The preflight call is outside the
  ledger. Check the TypeSafe balance by hand before the launch. Claude: 0.
- **Clock:** about 25 minutes. It is attended and launched before midnight; the launcher refuses
  to start between 00:00 and 08:00. It does not run at the same time as another lot.
