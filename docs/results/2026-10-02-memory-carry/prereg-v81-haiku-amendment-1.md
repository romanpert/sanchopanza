# Memory v8.1 on Haiku 4.5, amendment 1: a runner crash, and resuming (2026-10-05)

Sealed by the commit that adds `prereg-v81-haiku-amendment-1.sha256`. It changes the runner and
the launcher only. Design, arms, scenes, caps, criteria and exclusions stay as in
`prereg-v81-haiku.md`.

## What happened

- `v81h-run.cmd` started at 10:46. At 12:30, `carry.build` was making the fresh repository for
  `wording`, arm V, repetition 1, and `git add -A` exited 128. That was before any session of
  the pair, and the driver ended with a traceback.
- `v81h-all` had 37 rows by then, 6.27 USD by the sessions' own `total_cost_usd`, in plan order
  (repetition 0 of all 16 scenes, then repetition 1 through `wording` arm M).
- The same 128 had happened on Opus on 2026-10-02, right after a session. It was fixed then with
  retries in `commit_wip`, but not in `build`. The runner kept git's stderr to itself, so the
  cause was not logged. Run again by hand later, the same `git add -A` in that folder succeeded.
- **Launcher bug.** `v81h-run.cmd` skips `v81h-cross` only when the log has a `stop:` line. A
  traceback has none, so `v81h-cross` started at 12:30. The prereg says the cross run waits for
  the owner if `v81h-all` does not end its plan. Its PID tree (cmd 9584) was killed a few minutes
  later.
- That cut `x_tz` arm M repetition 0 during session 1. It has no row and no result. Its cost is
  in no cap; it is at most the 0.60 USD per-session cap, and likely a few cents. No other process
  was touched (browse's pilot, PIDs 21968, 39644 and 25964, kept running).

## Changes

1. **`carry.py`** (this commit): `build` and `commit_wip` share `held()`, which runs the git
   steps again up to 3 times, 3 s and 6 s apart, when git fails. `git()` writes git's stderr to
   the log before it raises. Test: `tests/test_memory_carry.py`, one held `add` on a fresh
   repository.
2. **`v81h-continue.cmd`** (this commit, sha256 below) resumes `v81h-all` with `--continue`.
   - It refuses if `v81h-all` has no rows, if `v81h-cross` already has rows, or if Claude Code
     is not 2.1.287.
   - It starts `v81h-cross`, also with `--continue`, only if `v81h-all` exits 0 and its log has
     no `stop:` line.
   - `--continue` keeps the 37 rows, removes the cut pair's folders (`wording` V 1 and `x_tz`
     M 0) and runs them again whole, as the prereg's exclusions allow.
   - `--continue` counts the earlier rows' spend, so the caps of 24 and 13 USD hold over the whole
     run.
3. `v81h-run.cmd` is not run again: its `carry.json` checks refuse it now.

## What was seen before this amendment

The 37 rows were watched as they arrived, which the prereg allows (it is how a run is monitored).
Nothing in them bears on these changes: both are about the runner and the launcher, not the
memory or a criterion.

## Commands

Launcher sha256 `7a60a7a400e08d8cc9faa7cab6c8d214dbe7232c15fbdf192aa67189b3bf7bc1`, started
outside the session the same way:

    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
      CommandLine = 'cmd.exe /c "C:\Users\roman\Desktop\proyectos\apps\sanchopanza-memoria-v8\docs\results\2026-10-02-memory-carry\v81h-continue.cmd"'
      CurrentDirectory = 'C:\Users\roman\Desktop\proyectos\apps\sanchopanza-memoria-v8' }
