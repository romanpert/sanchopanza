# Long bench: paid launches prepared (2026-10-06, branch `long-launch`, from `long-bench` 16c3a6e)

Nothing here spent money: no `claude` that reached a model, no API, no Jev (the preflight was a
stand-in). Not merged, not pushed. The long-bench worktree, its runs and its containers were not
touched.

## What was added

| Item | Where | Tests |
|---|---|---|
| 1 smoke launcher | `long-smoke-run.cmd <seal commit>` -> `benchmarks/adopt/long_launch.py smoke` | `tests/test_adopt_long_launch.py` (cmd.exe end to end) |
| 2 gate launcher | `long-gate-run.cmd` -> `long_launch.py gate` | same |
| 3 preflight, manifests, plan, PIDs, resume | `long_launch.py`, `long_guard.manifest_refusal`, `long_resume.py`, `long_money.held` | `test_adopt_long_launch*.py`, `test_adopt_long_runner.py` |
| 4 check-done term | `benchmarks/adopt/costmodel.py` (the scratchpad draft, now in the repo) | `test_adopt_long_launch_parts.py` |
| 5 N-early and give-ups | `long_run.Profile.window` = `install_defaults.window_for(budget)`; `long_report.give_ups` | both test files |
| 6 window record | `long_window.py`; `--debug=autocompact --debug-file=<evidence>/debug-<k>.log` in every arm | both test files |

## Launch commands (start by WMI, outside any session; one heavy batch at a time)

    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
      CommandLine = "cmd.exe /c <worktree>\long-smoke-run.cmd <seal commit>" }
    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
      CommandLine = "cmd.exe /c <worktree>\long-gate-run.cmd" }

Each sets the pinned 2.1.287 first on PATH, `DISABLE_AUTOUPDATER=1`, `ADOPT_PYTHON`, refuses a
missing manifest or another Claude Code version, and runs `long_launch.py`, which: writes
`launch.json` (its PID, the window's `cmd.exe` PID, each runner's PID with command line and
creation date), refuses a live runner of the same root, checks every chain's manifest (valid,
digest of the cached chain), prints and writes `plan.txt`, runs the Jev preflight for S arms
(non-zero: the launch ends with that code, 10 no_funds ... 14 other), then the runner per model
(the gate's Opus only after Sonnet exits 0), then the grade and `windows.json`. Running a
launcher again resumes. Stop: `STOP` in the root, or `long_run.py kill --root <root>`.

## What each prints (`long_launch.py plan smoke|gate`)

- Smoke (C:\sp-runs\L-smoke): Haiku 1.00 USD per call (`--max-budget-usd 1.00`), 2.00 per arm,
  arms N, Ne, S, 3 bugs + 2 callbacks of pydantic-long60-1; expected N 0.17-2.23, Ne 0.17-3.68,
  S 0.30-3.52, total 0.64-9.43 (5.65 to 48 requests per bug); caps held 6.00; hard ceiling 8.
- Gate (C:\sp-runs\L): Sonnet 4.50 per call (`--max-budget-usd 3.00`), 38 per chain; Opus 8.00
  (3.20), 48 per chain; expected Sonnet N 24.97 per chain, Opus 25.76-42.46; total 101.46-134.86;
  caps held 172.00; ceiling 175.

## Decisions taken here

- **Smoke chain: `pydantic__pydantic-long60-1`** (first 3 bugs), not long40-1: the launcher must
  refuse without a long60 manifest, it is the only validated chain, and it exercises the gate's
  path (guard, token, callbacks after bugs 2 and 3). Its own root; a Haiku smoke does not touch
  the gate's rows.
- **N-early = S's install, by construction**: `Profile.window` is `window_for(budget)` (193,000
  for 160,000; 100,000 for the smoke's 67,000), written as `CLAUDE_CODE_AUTO_COMPACT_WINDOW` in
  the project settings' `env`, the variable and block S's install writes (the BrowseComp-Plus
  line's mechanism). A cross-arm check stops the chain if Ne's value differs from what S's
  install actually wrote. Ne adds nothing else (no `SANCHOPANZA_CONTEXT_BUDGET` marker).
- **Give-ups apart**: a bug call that ran and changed no code outside `changes/`, or whose answer
  says it could not fix/find the bug; counted per arm with the context reached, and how many at
  or past 150k (BCP: N's give-ups past ~150k). In `report.json`, the gate row and the grade print.
- **Window as the session reports it**: the debug line `autocompact: tokens=... effectiveWindow=`
  (read from the 2.1.287 binary; `autocompact_state` stream events exist only for CCR workers);
  window = effective + 20k; source from the clean config's `.claude.json`
  (`autoCompactWindowsCache`, `clientDataCache`). Debug files are trimmed to those lines.
- **Check-done term** (gate-A data on main): 2.41 requests per send-back (41 after 17 on h2h);
  rate per open request 0.038 (finished work, AgentDojo false blocks 13/342), 0.323 (mid: B2 N's
  unfinished share 13/40 x recall 286/313), 0.85 (Q&A misfit 17/20). In coding every request is
  open under gate A. Sonnet L60 S: +2.25 USD (mid), S/N 0.75 instead of the prereg's 0.66.

## Bugs found and fixed on the way

- **A resume could never start** after real spending: the ceiling check added every chain's
  whole caps to the spend (`long_money.held`: each chain at the larger of its caps and spend).
- **A partial arm was skipped as done** (`row.json` existed), its remaining bugs never asked; a
  graceful stop (limit) left the same. Now resumed; a call the usage limit rejected without doing
  anything is asked again; a call a dead runner left half done is charged its caps and retried or
  declared, as pre-mortem 4.
- **`run.child_env` passed the runner's PYTHONPATH** to Claude Code and the hooks: with the
  launcher's `PYTHONPATH=<worktree>\src` the S arm would have run this branch's package instead
  of the frozen seal (install included). Dropped.
- The fake `claude` replayed the same prefix for S and N, so S's prefix check tripped in a dry run:
  the fake now adds 1,000 tokens to an installed arm's first request.

## Dry run (fake claude, stand-in Docker and preflight; `tests/test_adopt_long_launch.py`)

Gate: Sonnet both chains exit 0, Opus stopped by an injected 429 at pydantic's 3rd call (exit 2,
LIMIT.flag); after removing the flag the same launcher resumed ("resumed at request 3 of 8 (3
kept)", conan's arms "done; never run twice"), exit 0, graded, `report.json` with the gate rows,
windows 1,000,000 (effective 980,000, clientdata). Smoke: preflight 10 -> exit 10 with no runs/;
preflight 0 -> three arms of 5 calls, Ne and S at 100,000 (env), N at the server's, graded.
Folders: `launch.json launch.log launch.status plan.txt preflight.txt claude.txt
long-run.status.json runner-<model>.log grade.log report.json windows.json cfg/ runs/ w/ keys/`.

## What still blocks a paid launch

1. **Smoke: the S seal.** `long-smoke-run.cmd` needs the sealed commit (main, carrying f2a0fe2
   gate A and 674806b the 402 breaker; enforced) and its frozen copy:
   `python benchmarks\adopt\freeze.py <seal>` (free, builds a venv). And `long_run.S_FLAGS` /
   `S_ENV` must match the sealed line (today `GUARD_CHOOSER=keep`; main's default chooser is now
   `struct`, guard-struct 20k): the independent verifier's check.
2. **Gate: conan-io__conan-long60-1 has no manifest** (validation running in long-bench). Then
   this branch needs long-bench's manifest commit (or be merged into long-bench) before launch.
3. **The debug line was never seen from a real session** (it would have cost). The smoke's first
   call shows it: `debug-1.log` non-empty and `window_reported` in its row. If empty, the gate
   falls back to the compaction/peak inference and the window criterion may stay "pending".
4. Smoke caps may bind: at Haiku's ~48 requests per bug an arm costs up to ~3.7 USD, so the 2.00
   per arm cap would stop it before the callbacks. Still a valid smoke of injections, invariants
   and meter; say so if it happens.
5. Launch list item 0: tell indagis-a1 the PID, time and cap; C:\sp-runs\LIMIT.flag absent.
   The grade at the end runs each arm's tests in Docker (free, long on pydantic's 5,057-test guard).

## Suite

3110 passed, 40 skipped in 258 s (`-m pytest tests -q -p no:cacheprovider`, PYTHONPATH=src, main venv),
before the last busy-check test (22 passed in its file). Baseline on long-bench: 3075 passed, 40 skipped.
