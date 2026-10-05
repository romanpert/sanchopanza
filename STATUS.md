# guard-struct: status (2026-10-06, stopped for the day)

Branch `guard-struct` from main `d1e99af`. Local only, nothing pushed. No paid calls were made.

## Done (commit 7ceec0a)

- `src/sanchopanza/context/structural.py`: the structural keep. Every tool result since the
  previous compaction, re-readable ones too. The order: results on files edited since then,
  then recency. At-risk output goes first inside each tier. Only the newest Read or Edit of
  each file is kept. Results are kept whole within `GUARD_STRUCT_CHARS` (default 3000).
  Re-readable results left out get a pointer (file and line range, search, or command), within
  `GUARD_POINTER_CHARS` (default 1500). Web and MCP output is pointed to only, unless
  `GUARD_WEB=1`. The measurement is in the comment beside `STRUCT_CHARS`.
- `guard.Guard` has two new fields, `kind` and `pointers`. `block()` and `instructions()` say
  what the struct block carries (`INSTRUCTIONS_RESULTS`).
- `harness/guard_hook.py`: `struct` is the default chooser. It is built at PreCompact over the
  calls since the last boundary. Any error falls back to the rule's block, logged as
  `struct (error: rule only)`. `keep`, `rule`, `judge` and `decider` can still be chosen.
- 18 new tests in `tests/test_context_structural.py`. They cover:
  - the tiers;
  - the dedupe;
  - pointers;
  - the budget;
  - masking;
  - `since`;
  - the default;
  - a 400k-token transcript through both hooks in under 2 s;
  - the fail-safe;
  - install wiring.

  One older hook test now sets `GUARD_CHOOSER=rule`.
- `install` and `plan()`: unchanged. Install writes no chooser, so the hook default applies.

## Suite

The full suite ran before the last test fix: `1 failed, 3032 passed, 40 skipped in 660.32s`.
The one failure was the old rule-default hook test, which has since been fixed. After the fix,
the guard tests were rerun: `155 passed in 3.29s`. The full suite has not been rerun since.

## Pending

1. Rerun the full suite and record its summary line.
2. Write `docs/results/2026-10-05-guard-struct/README.md` with the replay numbers.
   - The decision: Jev is out of the keep ranking (AUC 0.56 vs recency 0.60). Structure kept
     .67 vs .12 on the owner's real sessions.
   - The free budget replay from today: at 3000 chars the struct order keeps .15 of needed
     results (.17 at-risk), against .21 (.13) for f, recency .15, the rule .12 (.17) and the
     oracle .39. At 44000 chars it keeps .64 (.61). This is in the scratchpad
     `guard-replay/budget.json`.
   - The caveats: "needed" is a proxy, the public set is mostly Haiku, and all of it is offline.
   - Do not copy `real.json`, which names private projects.
3. Update `docs/adapters.md:70`, `README.md:186` and `docs/where-it-pays.md:433`, which still
   describe `rule` as the default.
4. Decide the default budget. At 3000 chars the gain over the rule is small; .64-.67 needs
   `GUARD_STRUCT_CHARS=44000`.

## Next commands

    cd C:\Users\roman\Desktop\proyectos\apps\sanchopanza-guard-struct
    $env:PYTHONPATH="$PWD\src"; ..\sanchopanza\.venv\Scripts\python.exe -m pytest tests -q -p no:cacheprovider
    # write the README (step 2), update the docs (step 3), then:
    git add docs README.md; git commit -m "docs: guard-struct replay, decision and caveats"
