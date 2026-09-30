# Adoption study: the task set, sealed before any session (2026-09-30)

Question of the study: is Claude Code with `sanchopanza install` (defaults of 2026-09-30) better
and cheaper than Claude Code alone on real work, measured fairly? This file fixes **which tasks**
and **how they are split**, before any Claude Code session of the study runs. The success
criteria for the held-out confirmation will be registered separately, before it is run.

## Two kinds of task

**Long sessions (chains).** Five real bugs of one repository, asked one after another in one
Claude Code session (one `claude -p` call per request, each resuming the session). The bugs are
SWE-smith's `pr_mirror` instances (dataset `SWE-bench/SWE-smith`): a merged pull request of the
repository undone on a snapshot of it, with the tests the pull request made pass
(FAIL_TO_PASS) and the rest of the suite (PASS_TO_PASS). The issue texts are SWE-smith's.
Selection: `benchmarks/adopt/chains.py`, seed 20260930, bugs of one chain disjoint in files and
in failing tests. Output: `benchmarks/adopt/chains-selected.json` (the ids, and the sha256 of the
SWE-smith rows they were drawn from; the full rows, 14 MB, are rebuilt from those in the cache).

| repository | development | held out |
|---|---|---|
| pygments | 1 | 1 |
| starlette | 1 | 1 |
| pydantic | 0 | 2 |
| conan | 0 | 2 |
| dvc | 0 | 1 |
| astroid | 0 | 1 |

**Single issues.** SWE-bench Verified, seed 20260930, disjoint from every instance the find runs
used: `general-easy` ("<15 min fix") 2 + 10, `general-medium` ("15 min - 1 hour") 2 + 10, and
`hard` ("1-4 hours", ">4 hours") 2 + 6 (development + held out). Selection:
`benchmarks/adopt/singles.py`. Output: `benchmarks/adopt/singles-selected.json`. Graded by the
official harness.

## Validation of a chain (`benchmarks/adopt/validate.py`), before its sessions

With the five bugs baked into the repository's image, every bug's FAIL_TO_PASS must fail, and
fixing that bug alone (its patch reversed) must make all of its FAIL_TO_PASS pass. A bug that
fails either check is replaced by the chain's next spare (drawn by the same seed, in order) that
shares no file and no failing test with the rest; at most four swaps. A bug is graded on its
FAIL_TO_PASS and on PASS_TO_PASS* (the PASS_TO_PASS tests that pass when only that bug is fixed).

Both development chains validated with no swap on 2026-09-30 (pygments 5/5, starlette 5/5).

## Rules that hold for every session

- Both arms: the same model, the same working copy (exported from the chain's image as one
  commit, no history), the same prompts, the same tools (Claude Code's defaults minus WebFetch
  and WebSearch, since the fixes are public), the same budgets, `--setting-sources project`, the
  same `runtests` command for the tests.
- Arm S differs only by `sanchopanza install --scope project --write` in its working copy, run
  through `hook_env.py` for state per session and the TypeSafe key out of the agent's reach.
- The held-out tasks are not run, read for results or used to set anything until the
  confirmation is registered.
