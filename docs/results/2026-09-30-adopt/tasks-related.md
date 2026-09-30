# Adoption study: related chains, sealed before any session on them (2026-09-30)

An addition to `tasks.md`, which stays as sealed. The chains of `tasks.md` hold five bugs of one
repository that touch pairwise different files: they measure whether sanchopanza does harm in a
long session, and in them no request re-reads what an earlier one read (development transcripts,
2026-09-30). Memory between requests and sessions (`sanchopanza install --memory`) can only pay
where a later request touches what an earlier one touched, so this file adds chains drawn that
way. It fixes which tasks and how they are split, before any Claude Code session runs on them.
The criteria for any confirmation will be registered separately, before it runs.

## What a related chain is

Five SWE-smith `pr_mirror` bugs of one repository (`SWE-bench/SWE-smith`, the same source file
as `tasks.md`), none of them in any chain of `tasks.md` or among its spares, asked in order:
each later bug shares at least one code file with a bug before it; no two share a FAIL_TO_PASS
test; and no two have overlapping hunks in a file, since all five are undone together in one
image. Generated files (pygments' `_mapping.py`) do not count as shared.

SWE-smith's `pr_mirror` patches also take the final newline off every file they touch. Two such
patches on one file cannot both apply, and that hunk is not part of any bug, so the selection
drops it and keeps the original patch beside the normalised one. Found by the first bake of
`encode__starlette-rel-1`, before any session ran; the non-overlap rule was added then too.

Selection: `benchmarks/adopt/related.py`, seed 20261001. Output:
`benchmarks/adopt/related-selected.json` (ids, spares and files per bug).

| chain | split | bugs (pr) | spares |
|---|---|---|---|
| encode__starlette-rel-1 | development | 2576, 2041, 2341, 2732, 2761 | 2334, 2583, 2443 |
| encode__starlette-rel-2 | held out | 2351, 2352, 2366, 2703, 2264 | none |
| pydantic__pydantic-rel-1 | held out | 7891, 10347, 11116, 5869, 7786 | 8262, 10242, 6287 |
| conan-io__conan-rel-1 | held out | 16289, 15368, 14526, 12243, 12913 | 12536, 15153, 14555 |
| conan-io__conan-rel-2 | held out | 13346, 11618, 17629, 13450, 16973 | 14781 |
| iterative__dvc-rel-1 | held out | 9277, 10303, 9354, 9298, 10240 | 9261, 9825 |

Pygments has no related chain (its five `carbon.py` bugs share failing tests), and astroid has
none once hunks may not overlap; conan, with 632 usable bugs, takes a second chain.

## Validation, before any session

`benchmarks/adopt/validate.py <chain>`, as for `tasks.md`: every bug's FAIL_TO_PASS fails with
the five bugs in, and passes when only that bug is fixed. A related chain replaces a bug that
fails with its next spare that shares a code file, no failing test and no overlapping hunk.

- `encode__starlette-rel-1` (development): valid, the five drawn bugs, no swap (106 s).
- The held-out chains are validated one repository at a time before a confirmation is sealed.

## Arms these chains are for

Development first (Haiku 4.5, subscription, list price). `N` (one session, Claude Code alone),
and the arms of `benchmarks/adopt/run.py` `ARM_SPECS`: `Nf` and `Sf` ask each request in a new
session in the same working copy (alone; with the default install plus `--memory`), `Sm` keeps
one session with the default install plus `--memory` and a 100k context budget.
