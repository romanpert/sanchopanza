# Long-chain runner: status (2026-10-06, stopped by the owner for the day)

> **Historical.** A working note of 2026-10-06, kept as it was and moved here from the
> repository root on 2026-10-15; its state is superseded. Today's is the
> [final scoreboard](../results/2026-10-13-final/README.md) and the
> [roadmap](../ROADMAP.md).

Nothing here spent money: no `claude` session, no API, no Jev. No launcher was run.

## Fixes a-h (pre-mortem), each with a test written red first

| Fix | State | Where | Test |
|---|---|---|---|
| a grade strict only | done | `run.grade_chain`: `resolved_f2p` primary, `resolved_strict`, `regressions` (`resolved` kept strict for sealed phase A) | `test_adopt_long_fixes.py::test_a_*` |
| b agent_diff ignores git's exit | done | `docker_env.agent_diff` through `_git_retry` (bytes, CRLF kept) | `test_b_*` (2) |
| c row.json only at the end | done | `arm_files.write_row` after every call, `"partial": true`; `one_chain` refuses a partial row without `--continue` | `test_c_*` |
| d transcripts from ~/.claude | done | `arm_files.projects_root(env)` (CLAUDE_CONFIG_DIR) | `test_d_*` |
| e caps vs ceiling | done | Opus 48/chain (2x38 + 2x48 = 172 <= 175); `long_guard.plan_refusal` before any call | `test_e_*` |
| f hook Jev ceiling 0.10 | done | `hook_env` reads `ADOPT_JEV_MAX_USD`; the long runner sets 0.50 | `test_f_*` |
| g long.py shared SIZE/RNG | done by the chain agent (6ea83ea: `SEED60`, `SIZE60`, own RNG); no runner-side test added | - |
| h --max-budget-usd basis | done | `meter.claude_code_cap` (Sonnet x2/3, Opus x0.4, Haiku x1), rates fitted exactly on 64 F1 sessions | `test_h_*` (2) |

## Engineering items 2-9

- 2 docker_env/runtests: done (retries, `sp.long` labels removed after each call, `health()`).
- 3 runner: done as `long_run.py` + `long_call.py` + `long_guard.py` (run.py is at 797 lines, so it
  reuses run.py rather than growing it). Arms N, Ne, S (S0 coding line, candor observe), opus in
  `run.MODELS`, clean user from `carry` (`init_facts` now public, `environment(base=)`,
  `record_claude(claude=)`), `--permission-mode default` + `--allowedTools`, never bypass,
  init invariants every call, LIMIT.flag/STOP, per-call row, tree kill, idle 20 min, token per
  chain and arm, prompts by `run.requests_of`, verified kill by PID.
- 4 meter: done. B2 reproduced call by call at 2/10: N 8.741, S 7.318, Sm 6.373 (exact).
- 5 grade: per-bug grade is the chain agent's `perbug.py`; `long_report.grade_arm` uses it (long40:
  `run.bug_result`); B2 stored grades: strict 27/30/0, F2P 27/30/26. Re-reads and check-done
  send-backs in `long_report`.
- 6 statistics: in `long_report.py` (Holm, McNemar exact, cluster bootstrap, -5 margin, cost
  ratio, gate evaluator), not in confirm.py (sealed phase A).
- 7 fake claude: done (`tests/fixtures/long_fake`, `test_adopt_long_runner.py`), long40 chains
  (long60 not validated yet).
- 8 WMI launchers `long-gate-run.cmd`, `long-smoke-run.cmd`: done on branch `long-launch` (STATUS-launch.md).
- 9 costmodel.py check-done term: done on branch `long-launch` (`benchmarks/adopt/costmodel.py`).
- Window probe (pre-mortem 8): every call records the session's own autocompact line (`long_window`, branch `long-launch`). Still pending: a test for g on the runner side.

## Caps (owner USD, in code)

- Gate: Sonnet 4.5/call (passed as 3.00), 38/chain; Opus 8/call (passed as 3.20), 48/chain;
  ceiling 175. Wall 4 h/chain, call timeout 2,700 s.
- Smoke: Haiku 1.0/call, 2.0/arm, hard cap 8 (`ceiling_of` refuses more).

## Next commands (launchers to be written first; start them by WMI, never from a session)

Environment for both: pinned 2.1.287 first on PATH, `DISABLE_AUTOUPDATER=1`,
`ADOPT_PYTHON` and `ADOPT_SANCHO` (this worktree has no .venv), `PYTHONPATH=<worktree>\src`.

    python -u benchmarks\adopt\long_run.py plan --profile smoke --root C:\sp-runs\L-smoke
    python -u benchmarks\adopt\long_run.py run  --profile smoke --root C:\sp-runs\L-smoke
    python -u benchmarks\adopt\long_run.py plan --profile gate
    python -u benchmarks\adopt\long_run.py run  --profile gate --model sonnet
    python -u benchmarks\adopt\long_run.py run  --profile gate --model opus     # only if sonnet exit 0
    python -u benchmarks\adopt\long_run.py grade --profile gate

Exit codes: 0 done, 1 refused, 2 limit/cap/ceiling, 3 set aside, 4 harness.
The gate chains (`conan-io__conan-long60-1`, `pydantic__pydantic-long60-1`) must be validated
into chains-validated.json first (see STATUS-chains.md).

## Suite

3075 passed, 40 skipped in 390.11s (baseline before this work: 3014 passed, 40 skipped).
