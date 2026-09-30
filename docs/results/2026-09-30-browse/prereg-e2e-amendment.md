# Browse, Phase 3: amendment 1 (after the pilot, before any counted session)

Written 2026-09-30 after the two pilot sessions (T1, run 0, one per arm, excluded by
registration) and before any counted session ran.

The pilot did what it was for and found two faults, neither in what is measured:

1. **The grader.** T1's LEAN pilot answered "priced at £47.82 with a 4-star rating", right, and
   was graded wrong because the required word was "four". A required item may now list
   alternatives, any of which counts: T1 requires `47.82` and one of `four`, `4-star`, `4 star`,
   `4 stars`, `4/5`, `4 out of 5`. No other task changes.
2. **The hook on Windows.** It read its event with the console's code page; playwright-cli's
   box-drawing update banner became surrogates and every write failed, so the hook passed the
   result through unchanged (it fails open). Fixed by reading and writing UTF-8 bytes, with a
   subprocess regression test (`tests/test_browse.py`). The LEAN pilot therefore ran without the
   hook acting; it is re-run as a second pilot (run -1) to check the fix fires, also excluded.

Nothing else changes: tasks, arms, runs, metrics, decision rule, money.
