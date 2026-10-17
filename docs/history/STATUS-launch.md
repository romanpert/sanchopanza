# Long bench: paid launches prepared (2026-10-06, branch `long-launch`, from `long-bench` 16c3a6e)

> **Historical.** A working note of 2026-10-06 to 2026-10-07, kept as it was and moved here from the
> repository root on 2026-10-15; its state is superseded. Today's is the
> [final scoreboard](../results/2026-10-13-final/README.md) and the
> [roadmap](../ROADMAP.md).

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

- Smoke (C:\sp-runs\L-smoke): Haiku 1.00 USD per call (`--max-budget-usd` at most 1.00, less one
  turn), 2.00 per arm, arms N, Ne, S, 3 bugs + 2 callbacks of pydantic-long60-1; one turn past a
  cap costs up to 0.56 (N, window 200k: the arm starts no call past 0.44 spent at that context)
  and 0.36 (Ne, S, window 100k: past 0.64); expected N 0.17-2.23, Ne 0.17-3.68, S 0.30-3.52, total
  0.64-9.43; caps held 6.00 under the hard ceiling 8: fits.
- Gate (C:\sp-runs\L): Sonnet 4.50 per call (at most 3.00 in Claude Code's prices, less one
  turn), 38 per chain; Opus 8.00 (3.20), 48 per chain; one turn past a cap at a 1M window: Sonnet
  6.48 (no call past 27.02 of 38), Opus 10.80 (past 29.20 of 48); expected Sonnet N 24.97 per
  chain, Opus 25.76-42.46; caps held 172.00 under the ceiling 175: fits.

## One turn past a cap (live probe 2026-10-06: Opus given 0.34 USD spent 0.94)

`--max-budget-usd` stops Claude Code between turns, never inside one. `long_money.turn_cost`: the
context written at the 1-hour cache rate plus 32k output, at list prices (Opus 1M: 10.80; Sonnet
1M: 6.48, 193k: 1.64; Haiku 200k: 0.56, 100k: 0.36). At run time the next call's turn is taken at
the last call's peak + 50k, never past the arm's window (configured, else reported, else 1M for
Sonnet and Opus, 200k for Haiku). Each call gets `--max-budget-usd = cap - that turn`, and starts
only with room for cap + turn under its chain (arm) cap and the ceiling. The chains still hold at
most their caps, so 172 <= 175 and 6 <= 8 stand; what changes is where an arm stops: at the
modelled peaks (Sonnet 385k, Opus 292k) a Sonnet arm starts no call past ~30.4 of 38 (expected
24.97: fits) and an Opus arm past ~35.8 of 48 (expected 25.76-42.46: the long end would be cut).

## The S seal (owner, 2026-10-06)

S is main **cb0062e** (gate A, jev-402, real costs, guard-struct, guard-split), frozen at
`~\.cache\sanchopanza\adopt\frozen\cb0062e36340-jev-mcp\` (`freeze.py cb0062e`,
done). `S_ENV` sets no guard chooser: the install's default, struct over 6 SessionStart(compact)
parts (GUARD_STRUCT_CHARS 44000, GUARD_INLINE_CHARS 9500), checked by a test that installs the
sealed copy. The launcher refuses any other seal. The smoke dry run used the frozen copy:
"S runs ...\cb0062e36340-jev-mcp\Scripts\sanchopanza.exe" and
"guard: 6 SessionStart(compact) parts, chooser the install's default".

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

## When each can be launched

**Smoke: ready.** From this worktree, by WMI, outside any session:

    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
      CommandLine = "cmd.exe /c <worktree>\long-smoke-run.cmd cb0062e"
      CurrentDirectory = "<worktree>" }

Before it: tell session a1 the PID, time and cap (8 USD hard); C:\sp-runs\LIMIT.flag absent;
TypeSafe topped up (the launcher's preflight is one real decision, ~13 micro-USD, and stops the
launch with 10-14 if Jev does not answer). Watch on the first call: `debug-1.log` non-empty and
`window_reported` in its row (the debug line was never seen from a real session). At Haiku's
~48 requests per bug an arm may stop at its 2.00 cap before the callbacks; say so if it happens.

**Gate: blocked.** long-bench 91af96c says conan-io__conan-long60-1 validated to 56 clean bugs
and is invalid for want of spares; its manifest says `valid: false`, so the launcher refuses (as
it should). It needs spares or another gate chain, with a new manifest, and this branch then
needs that commit. The grade at the end runs each arm's tests in Docker (free, long).

## Suite

3116 passed, 40 skipped in 284 s (`-m pytest tests -q -p no:cacheprovider`, PYTHONPATH=src, main venv),
after the one-turn and seal changes. Baseline on long-bench: 3075 passed, 40 skipped.

## Smoke run, live (2026-10-07, session 6c)

Root `C:\sp-runs\L-smoke`, seal cb0062e, Haiku 4.5, pydantic-long60-1, 3 bugs + 2 callbacks.
Spent **2.88 USD** of the 8 hard ceiling (N 1.13 with the forced cut charged at its 1.00 cap,
Ne 0.87, S 0.88; Jev 0.0011).

- First try 11:48 stopped before any call: `adopt-pydantic--pydantic-long60-1:bugs` was gone
  (Docker restarted; the after-conan queue removes images). Rebuilt free with
  `validate.py --bake pydantic__pydantic-long60-1` (F2P still fail on the baked image).
- Long-bench merged in (3c02265: conan-long60-1 **valid at 60 bugs**, c68ce7a); launcher
  tests 52 passed.
- Every arm stopped on its chain cap after 2 of 5 calls (exit 2, resumed twice by running the
  launcher again): the room check holds a whole call cap (1.00) and one turn (0.36) under the
  arm's 2.00, so an arm starts no call past 0.64 spent. **Callbacks were never asked live.**
- Worked live: preflight, frozen seal, guard in 6 SessionStart(compact) parts (S kept 12-17k
  after compacting, Ne 4k), N-early and S at window 100000 from env (both compacted at
  ~67-68k), the forced 90 s cut charged at its cap, cap stops, resume skipping finished arms,
  the Docker grade and `report.json`.
- **The debug line is not emitted per request under `claude -p` 2.1.287**, with or without a
  window in env: `debug-<k>.log` held 0 matching lines after trimming. The report already
  bounds N's window from the peak with no compaction ("at least 95638"); for the gate, read N's
  window from the `pre` of its compactions in the stream.
- Grade: 0 of 3 resolved in every arm (bug 2 partly: N 0/4, Ne 3/4, S 2/4 F2P); S alone broke
  one guard test (`test_docs_examples[docs/errors/usage_errors.md:83-95]`), from its own patch;
  token 2 ok, 1 missing (bug 3 never ran).

Gate: unblocked by the conan manifest; it runs N only, so the callback path is the one part
not seen live. Waiting on the owner's choice of the Opus chain cap (48 with the long tail cut
near 35.8, or 56 with the ceiling at 190).

## Pilot of bet A, passages on arrival (branch `pilot-a`, 2026-10-07)

Nothing here spent money. Arm A = N + `sanchopanza install --passages --provider jev` (A10:
`--passages-fraction 0.10`) with `--no-guard --no-find --no-skill --context-budget 0`; the runner
then keeps only the passages hook (the cut on Bash|PowerShell|Read and, from lean edd37bb, the
Write guard) and refuses the arm otherwise (`long_pilot.install_breaks`). The archive's folder
(under the evidence) goes to `permissions.additionalDirectories`. Profile `pilot-a`: Sonnet, the
gate's chains, 4.50 per call, 38 per chain, hard ceiling 80 per root (76 held); A in
`C:\sp-runs\L-pilot-a`, A10 in `C:\sp-runs\L-pilot-a10`. The frozen copy is the launcher's own
commit (674806b in its history, `passages-hook --help` answering); S keeps its seal. Abort in
code: >= 10 cuts and more than half asked again whole -> stopped "rerequest", exit 5. Rows and
`report.json` carry cuts, chars in/out, re-requests (whole, identical, targeted), r and r_whole.
Compare (free, k=1, descriptive): `python benchmarks/adopt/pilot_a_compare.py`.

Before launching: `python benchmarks/adopt/freeze.py edd37bb` (free), then by WMI:

    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
      CommandLine = "cmd.exe /c <worktree>\long-pilot-a-run.cmd edd37bb A"
      CurrentDirectory = "<worktree>" }
## Gate (headroom), live (2026-10-07, session 6c)

Root `C:\sp-runs\L`, arm N only, clean user, Claude Code 2.1.287. Spent **168.57 USD** (list,
subscription) under the 230 ceiling (owner raised Opus to 75 a chain twice the same day).

| Model | Chain | Resolved | Cost USD | Requests asked | Peak context | Give-ups (at/past 150k) | Gate check |
|---|---|---|---|---|---|---|---|
| Sonnet 5.5 | conan-long60-1 | 44 of 60 | 28.45 real (32.06 charged) | 51 of 62 (cap) | 435k | 1 (0) | passes |
| Sonnet 5.5 | pydantic-long60-1 | 44 of 60 | 23.55 | 62 of 62 | 362k | 7 (6) | pending (window "at least") |
| Opus 5.5 | conan-long60-1 | 57 of 60 | 61.34 | 59 of 62 (cap) | 452k | 2 (1) | **sin margen** (F2P 0.95) |
| Opus 5.5 | pydantic-long60-1 | 53 of 60 | 51.63 | 62 of 62 | 416k | 7 (6) | passes |

- **Sonnet leaves room** (27 % unresolved in both chains); **Opus barely does on conan** (5 %), some
  on pydantic (12 %). Against Opus, S can win on cost there, hardly on success.
- **The cost model was short**: Sonnet expected 24.97 a chain, conan's whole chain heads to ~41;
  Opus expected 25.76-42.46, conan took 61.34 for 59 requests.
- **N never compacted** up to 452k: its window is at least that (the report says "at least").
- **Give-ups pile up past 150k** (pydantic: 6 of 7 in both models).
- Incidents: the runner died once on a Docker race (`docker rm` on a container already being
  removed, after call 51 of Sonnet's conan; fixed in 4849111, resumed); call 51 was charged its
  4.50 cap (real 0.89), which ended that chain one request early.

## Give-ups: the raw count is not the measure (2026-10-07, sessions e8 and 6c)

`long_report.give_ups` counts a bug call that changed no code outside `changes/`, or whose answer
says it could not fix the bug. That also takes a bug an earlier bug's fix already fixed ("no
further change was needed, see bug 5"): 3 of 7 in the gate's Sonnet pydantic N, 3 of 6 in its
second run, 3 of 4 in pilot A. From now on the measure is the **unresolved give-up** (given up
AND left unresolved by the grade), with its context: `give_ups(..., grade)` returns `unresolved`,
`unresolved_at_or_past_150k` and `unresolved_contexts`, `report.json` carries them and the grade
line prints them. The raw count is still published beside it. Decided before any quality result
of N-early was seen (its cost and context had been watched live).

## Conan repeat round: N2, Ne2, A2 (2026-10-07 evening, session 5a relaying 6c, with session e8)

Owner approved 100 USD hard. Launched 20:02 from run-noise (comun 1bf7343), Sonnet 5.5,
conan-long60-1, roots `C:\sp-runs\L-n2c` (N, 38), `L-ne2c` (Ne, 25), `L-a2c` (A from lean
edd37bb, 37). Spent **79.35 USD** as charged by the runner (N2 30.61, Ne2 19.37, A2 29.37;
Ne2's report.json says 18.79).

- All three stopped on their chain cap (exit 2): N2 after call 49, A2 after 50, Ne2 after 52.
  **The launcher grades only on exit 0**, so each was graded by hand, free:
  `long_run.py grade --profile conan-<x>2 --root <root> --manifests <run-noise>\benchmarks\adopt\long60`
  from the run-noise worktree with the launcher's env (start/exit lines `grade-by-hand` in
  `launch.status`). The gate's and the first round's capped roots had the same gap.
- Resolved of 60: N 44, N2 47, Ne 37, **Ne2 51**, A 47, A2 46. On the 48 bugs all six ran: 40,
  47, 30, 48, 41, 45; bugs 1-11 (before any compaction): 10, 11, 5, 11, 11, 11 (e8's `diff-11`
  snapshot agrees); bugs 12+: 30, 36, 25, 37, 30, 34 of 37.
- Unresolved give-ups (the main measure): N 1, N2 0, Ne 3, Ne2 0, A 0, A2 0.
- USD at call 50: N 27.56, N2 30.61, Ne 14.06, Ne2 18.24, A 24.61, A2 29.37. Ne/N x0.46-0.66
  by pairing (x0.56 on means); A/N x0.80-1.07 (x0.93); N/N2 x0.90.
- Same arm twice: N/N2 0 vs 7 discordant (McNemar p 0.016), Ne/Ne2 0 vs 19, A/A2 1 vs 5. **Bugs of
  one chain are not independent; the run is the unit of replication**: per-bug p values on a
  chain are not evidence (PLAN-GANAR-H2H.md 6 and 7).
- Reading (PLAN-GANAR-H2H.md 6, "Repetición en conan"): no evidence N-early loses quality
  (37-51 vs N 44-47; its bad run was bad before compacting); A's edge does not hold (46-47 vs
  44-47); Ne's cost holds as a direction; the main measure separates no arm.
- Seen live (A arms): Claude Code ignores the permission to read the cut outputs' archive, since
  the working folder is not trusted. Same in A and A2; fix before the next A batch.
