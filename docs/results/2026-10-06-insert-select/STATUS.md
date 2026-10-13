# insert-select: status at stop (2026-10-06)

Branch `insert-select`, commits 32248b7 and fa3f7a0 on top of main. The review is done. No
refinement was started. No code changed, nothing new committed, nothing pushed. This file is not
committed.

## Review findings (ranked, none fixed yet)

1. **Conflict with autopilot arrival (high).** `--autopilot` wires PostToolUse `*` with arrival
   on (6,000-character threshold). With `--insert-select` both hooks act on the same Bash or Read
   result. Claude Code runs them in parallel on the original output, so both write an archive
   file and both return `updatedToolOutput`, and which one wins is undefined. `plan()` accepts
   both flags, and an env-only `SANCHOPANZA_AUTOPILOT=1` is not caught either.
   Fix: `plan()` raises, and the hook steps aside when `autopilot.config_from_env().arrival` is on.
2. **Edit anchoring (high).** A source Read with no named target becomes outline plus head. The
   target region goes through the 1,000-token cap line by line (`fit`), so a 200-line region can
   be cut part-way. Claude Code probably renumbers the replaced `file.content` from `startLine`,
   so the model sees line numbers that do not match the file. That is not verified against
   Claude Code. The markers carry the real numbers.
3. **Re-fetch disables saving (medium).** `cut-<key>` makes any later identical command pass
   whole for the rest of the session, and `seen-<digest>` does the same for identical content.
   That is refinement 1.
4. **Diff context is 1 line (medium).** That is refinement 3.
5. **Privacy (low).** The full text, unredacted, goes to `<cwd>/.sanchopanza/archive/<session>/`,
   which `keep_out_of_git` ignores. That is the same as autopilot. Only the decider pages are
   redacted. State marker files under the guard directory are never pruned.
6. **Line split mismatch (low).** `structure` uses `splitlines()` and so does `line_blocks`, so
   the two agree. But `\x0c` and ` ` count as line breaks there, so marker line numbers can
   drift from `Read` or `grep -n` numbering on such files.
7. **Code rules (low).** `install.py` is at 797 lines, so the next flag needs `merge_insert_select`
   moved out of `_merge`, or a split. The duplication was avoided correctly: `line_blocks`,
   `pages_of`, `last_intent` and `replaced` are extended, not forked. `_cut` reaches into
   autopilot private helpers (`_root`, `_charged`, `_over_ceiling`).
8. **No overlap.** Memory touch (Read/Edit/Bash) only reads the input, and prune and knowledge
   use other matchers.

## Refinements

All are pending:

1. Re-fetch window of 3 calls. Plan: count `tool_use` blocks in the transcript after the cut's
   `tool_use_id`. Never cut a Read of the archive.
2. Edit anchoring. Plan: keep the target region whole, outside the cap. Keep regions touched by
   earlier `Edit`s (find `new_string`). Use a 6k-token threshold for source Reads.
3. Diff context of 3 lines.
4. Conflict guard, as in finding 1.
5. Replay rerun: not run. Numbers are still those of fa3f7a0.
6. Full suite: not run. The feature's 5 test files: `59 passed in 3.26s`.
