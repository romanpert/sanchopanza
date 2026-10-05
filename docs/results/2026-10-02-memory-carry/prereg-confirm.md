# Memory carry: confirmation, written before its data exists (2026-10-02)

Sealed by the commit that adds this file. Nothing below changes after the first session of the
confirmation starts. Any deviation goes in an amendment, written before the verdict.

## Hypothesis

In a new Claude Code session, a fact the person stated in an earlier session, that the
repository does not show, is kept more often with sanchopanza's memory (`M`) than without it
(`N`, Claude Code as it ships, with its own auto memory on).

## Data

- **Scenes.**
  - The eight held-out scenes of `benchmarks/memory_carry/scenes_held.py`, written after the
    pilot and before any session saw them, with repetitions 0 and 1.
  - The eight pilot scenes of `scenes.py`, unchanged, with one new repetition (repetition 0
    into a new output folder).
  - The pilot run of 2026-10-02 is development and does not count.
- **Pairs.** That is 24 (scene, repetition) pairs, each run in both arms.
- **Model and harness.** Sonnet 5.5 (`claude-sonnet-5-5`) through `claude -p`, on the version
  of Claude Code installed when the run starts (recorded). The subscription pays.
- **Arms and checks.** As in `benchmarks/memory_carry/carry.py` at this commit. The checks are
  each scene's `task` and `fact` and the repository's tests, all fixed and tested by
  `tests/test_memory_carry*.py`.

## Commands

```
python benchmarks/memory_carry/carry.py --out ~/.cache/sanchopanza/memory-carry/confirm --scenes held --repeats 2 --total-cap 13
python benchmarks/memory_carry/carry.py --out ~/.cache/sanchopanza/memory-carry/confirm-pilot --scenes pilot --repeats 1 --total-cap 8
```

## Analysis

- **Primary.** `fact_kept` per pair. A one-sided exact McNemar test (binomial on the
  discordant pairs, p = 0.5), alpha 0.05, over the 24 pairs.
- **Confirmed when all of these hold:**
  1. the primary test gives p < 0.05, in favour of `M`;
  2. on the held-out pairs alone, `M` keeps the fact in more pairs than `N`;
  3. `M` passes the repository's tests in no fewer than `N`'s count minus 2 pairs;
  4. `M` passes the `task` check in no fewer than `N`'s count minus 2 pairs, among pairs that
     have a `task` check.
- **Reported, not criteria:**
  - the paired median cost ratio M/N;
  - which memory path gave the record (prompt or file);
  - how often Claude Code's own auto memory saved anything.
- **Excluded pairs.** A pair where either arm hit the usage limit, or where either session ended
  with an error before writing a result, is excluded and reported as NOT RUN. No retries.
- **The `fact` check is strict as written.** In the pilot, `wording` under `M` kept the message's
  prefix and appended detail, and that counts as not kept. No check is loosened after a session
  runs.
