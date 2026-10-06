# guard-struct: status (2026-10-06, ready to merge)

Branch `guard-struct`, rebased onto main `aad9903` (clean, no conflicts). Local only, nothing
pushed, not merged. No paid calls were made.

## Commits

- `d06baaf` feat: guard keeps whole tool results by structure (struct, the new default chooser)
- `19a9f1d` feat: struct budget 44,000 characters, block capped under Claude Code's inline limit
- `fbc2a16` docs: guard-struct replay, decision and inline cap; struct is the default guard chooser

## What is in it

- `context/structural.py`: the structural keep (see the previous status for the order).
  `STRUCT_CHARS` = 44,000 (about 20k tokens), with the budget table from the replay in its
  comment. `INLINE_CHARS` = 9,500 caps the whole block; results get the room the requests,
  trail and pointers leave under it (`room_for_results`), about 3,900 to 7,000 characters.
  `FENCE` is 16 (was 12; a kept result's cost now equals what it adds to the block, tested).
- `harness/guard_hook.py`: `GUARD_STRUCT_CHARS` (default 44000), `GUARD_POINTER_CHARS` (1500),
  `GUARD_INLINE_CHARS` (9500, 0 = no cap).
- Why the cap: Claude Code 2.1.282 and 2.1.287 (read in the binaries) keep a hook's
  `additionalContext` (and stdout) inline only up to 10,000 characters (threshold `1e4`); past
  that the text goes to a file and the model sees a `<persisted-output>` notice with a
  2,000-character preview and the path. A 44,000-character block would have reached the model
  as 2,000 characters. Contexts of several SessionStart hooks are capped one by one and then
  concatenated (no aggregate cap seen), so 44,000 inline needs the block split over several
  hook commands.
- `GUARD_POINTER_CHARS` 1,500 kept: about 10 to 20 pointers, 16 % of the capped block.
- Docs: `docs/results/2026-10-05-guard-struct/README.md` (new), `README.md`, `docs/adapters.md`,
  `docs/where-it-pays.md`, `CHANGELOG.md` now describe `struct` as the default.

## Suite

Full suite after the last code and docs change, on top of `aad9903`:
`3140 passed, 42 skipped in 443.30s (0:07:23)`. Ruff check and format clean on the changed files.

## Open

1. Deliver the measured 44,000 characters: split the block across several `SessionStart`
   hook commands, each under 10,000 (install writes N entries, the kept file is read by all and
   swept by age instead of unlinked by the first). Not built; an owner decision.
2. Inside Claude Code today the block carries about 3,900 to 7,000 characters of results: by the
   replay, .15 to .28 of needed results, against .12 for the rule.
3. `struct` has not been run end to end inside Claude Code.
4. The `rule` chooser's block is not capped; its worst case is near 10,000 characters.
