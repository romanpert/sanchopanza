# Memory v8 on Haiku 4.5: written before its data (2026-10-03)

Sealed by the commit that adds `prereg-v8-haiku.sha256`. Code: branch `memoria-v8` at that
commit. The memory and the benchmark are those of 4bfc374 (v8's runs), with one change in the
driver: `carry.py` ignores SIGINT from its start (52b4a5b), so a stray Ctrl+C cannot end the run.

## Why Haiku

On Haiku (`prereg-generalize.md`, amendment 1) the memory gave the earlier request in all 16
second sessions, and Haiku still broke the fact in five of them: `fields`, `legacy`, `nulls`,
`rename` and `wording`. Sonnet broke one in 24. Delivery is not enough on a small model. v8's
audit at Stop holds the diff against every standing rule and sends the agent back once when the
session's own rule is named and judged not kept. This run asks whether that turns a delivered
fact that Haiku breaks into a kept one.

## What changed against v8

1. **The model.** `--models haiku` (`claude-haiku-4-5-20251001`, `carry.MODELS`). Nothing else
   in the memory or the benchmark changes.
2. **The 16 scenes run M and V, repetitions 0-2.** v8 ran V alone there and took M from the
   confirmation; on Haiku the only M is one repetition on another day, and these scenes are
   where Haiku breaks a delivered fact.
3. **The 16 scenes come first.** They are the only set where Haiku's room is measured (M broke
   5 of 16); the cross-file test, v8's primary, follows in a fixed sequence.
4. **The no-harm criterion compares V with M in the same run**, not with a fixed 14 of 16:
   Haiku's M kept 11 of 16, so a fixed count would not measure harm.
5. **The false sends-back limit keeps v8's rate** (2 of 40, 5 %) on 72 second sessions: at most 3.
6. **Claude Code is pinned** to 2.1.287 by a private copy first on PATH, with the auto-updater
   off. v8's launcher used the global install, which updated itself once during another batch.
7. **The driver ignores SIGINT** (52b4a5b, test in `tests/test_memory_carry.py`). Phase A lost a
   batch to a Ctrl+C that reached its console. The run is stopped by PID only.

## Questions settled before sealing

1. **Cost per session.** The README states 5.30 USD for gen-haiku; its `carry.json` sums
   6.444 USD over 32 rows (64 sessions), and that sum is right: it is the sessions' own
   `total_cost_usd`, and the 66 `result` events in the streams give the same 6.444 once the two
   sessions that wrote their result twice are counted once. The README's figure matches no
   running total of the run. The nearest is the Haiku-only part, 6.297 USD (`fields`, arm M,
   session 2 spent 0.147 USD on an Opus 5.5 subagent), so 5.30 is most likely a slip for 6.30.
   It is not corrected in this commit. **The estimate uses 6.444 / 64 = 0.1007 USD per session.**
2. **Repetitions: 3**, approved by the owner (power below).
3. **Order: v8h-all first, v8h-cross second.** The 16 scenes are where Haiku's breaks of a
   delivered fact are measured, so the mechanism under test has room there; the cross-file
   scenes have never run on Haiku.
4. **SIGINT.** The driver ignores it (above).
5. **The decider.** Every Jev call of the M and V hooks goes to TypeSafe. Their cost is not
   recorded per session; v8's hook logs show up to 16 scored values per pair, and rule
   extraction makes calls the log does not score. At 29 millionths
   of a dollar a decision (`docs/where-it-pays.md`), even 100 decisions per session cost
   0.003 USD, under one cent per session and under 1 USD for all 288. A failure of the decider
   fails open (the session goes on without what the hook would have added) and is **reported per
   arm**, with the sessions it touched, from each pair's `hook-log.jsonl`: `error` events,
   `rules` events with an `error` (`part` extract or audit) and prompts whose `reason` is
   `decider timed out`. Such a session is not excluded.

## Development numbers (already seen, Haiku 4.5, Claude Code 2.1.287)

`~/.cache/sanchopanza/memory-carry/gen-haiku/carry.json`, repetition 0, 16 scenes:

| arm | fact kept | broken in |
|---|---|---|
| N | 8 / 16 | `columns`, `legacy`, `wording`, `fields`, `latin1`, `envvar`, `rename`, `nulls` |
| M (v6.2) | 11 / 16 | `legacy`, `wording`, `fields`, `rename`, `nulls` (memory given in all five) |

- Tests 16/16 and task 13/13 in both arms.
- Haiku has never run the 8 cross-file scenes. On Sonnet, M broke 12 of 40 cross pairs (v7 and v8).
- The audit bench (`audit_bench.py`, 175 recorded sessions including Haiku's) caught 43 of 43
  own-rule breaks offline. Whether Haiku repairs the break after a send-back has not been seen.
- Cost: 6.444 USD for 64 sessions, 0.1007 USD per session; per arm, N 3.150 and M 3.294. The
  costliest session, 0.32 USD, is the one with the Opus subagent.
- On Sonnet, V cost the same as M (v8-cross: 0.178 against 0.182 USD per session).

## Runs (Haiku 4.5, `claude -p`, the subscription pays)

A pair is one scene at one repetition, run once in M and once in V (two sessions each).

| run | scenes | arms | repetitions | pairs | sessions | expected | cap |
|---|---|---|---|---|---|---|---|
| `v8h-all` | the 16 pilot and held-out scenes | M, V | 0, 1, 2 | 48 | 192 | 19.3 USD | 24 USD |
| `v8h-cross` | the 8 cross-file scenes, `x_camel` v2 | M, V | 0, 1, 2 | 24 | 96 | 9.7 USD | 13 USD |

- M is v6.2, V is v8 with the same 7 decoys per scene as in v8 (`carry.decoys`, `carry.said_while`).
- N is not run. gen-haiku's N (repetition 0) is reported beside the result for reference, and is
  not a criterion.
- Expected cost: 288 sessions at 0.1007 USD, about 29.0 USD at list price. Send-backs add turns.
  The Jev calls (under 1 USD in all) are not in this figure.
- The runner stops `v8h-all` once more than 22.80 USD is spent and `v8h-cross` once more than
  11.80 USD (the cap less two sessions at their own cap): 18 % and 22 % above the expected
  figure. The plan runs repetition 0 of every scene first, then 1, then 2, so a cut removes the
  last repetitions.

### How the caps are enforced

- **Per session.** `--max-budget-usd 0.60` is passed to every `claude -p`
  (`benchmarks/memory_carry/carry.py:48`, `:144`).
- **Per run.** Before each arm's two sessions, the runner stops if what was spent plus two
  sessions at that cap could pass `--total-cap` (`carry.py:315`). Spent is the sum of the
  sessions' own `total_cost_usd`.
- **Usage limit.** A usage limit stops the run (`carry.py:326-327`).
- **Send-backs.** The audit sends the agent back at most once per Stop
  (`src/sanchopanza/harness/memory_hook.py:796`, `stop_hook_active`).
- **No API key.** `ANTHROPIC_API_KEY` is dropped from the agent's environment (`carry.py:120`).
- **The sequence.** The launcher starts `v8h-cross` only if `v8h-all.log` has no `stop:` line;
  otherwise it writes `cross-skipped` and ends, and `v8h-cross` waits for the owner.

## Criteria (fixed sequence: 2 is confirmatory only if 1 is met)

1. **Primary (the 16 scenes).** V keeps the fact in more of the 48 pairs than M, with a one-sided
   exact McNemar p < 0.05 (`analyze.py v8h-all --a V --b M`).
   - A discordant pair is one where exactly one arm's `fact` check passes after session 2.
2. **Cross-file (v8's primary).** V keeps the fact in more of the 24 pairs than M, one-sided exact
   McNemar p < 0.05 (`analyze.py v8h-cross --a V --b M`). If criterion 1 is not met, this is
   reported as direction only.
3. **False sends-back.** A V second session sent back by a rule other than its scene's own counts
   as false (`sendbacks.py v8h-all v8h-cross`). Criterion: at most 3 of V's 72 second sessions.
4. **No harm (the 16 scenes).** V's tests and task each fall no more than 6 below M's over the 48
   pairs (v8's margin of 2 per 16 pairs).
5. **Reported, not criteria:**
   - per arm, sessions where the memory gave the earlier request (`given`) and the fact was still
     broken ("delivered, broken");
   - every send-back for the scene's own rule, and whether the fact was kept after it (the
     mechanism this run tests);
   - every V session sent back for a decoy, read by hand and quoted;
   - per arm, the sessions where the decider failed (questions settled, 5);
   - the median cost V/M per set;
   - V against gen-haiku's N, repetition 0;
   - whether Claude Code's own auto memory saved anything;
   - sessions that called a subagent, and on which model.

## Power (approximate)

- **The 16 scenes.** Haiku's M broke 5 of 16 (0.31; 95 % interval roughly 0.11-0.59).
  - If V breaks 5 % of pairs, 48 pairs give about 0.95 power; if V breaks 10 %, about 0.78.
  - 32 pairs would give 0.81 and 0.56; 16 pairs give 0.38 and 0.23.
- **Cross.** Haiku's break rate is unmeasured. At Sonnet's 0.30 the power is about 0.64, and at
  0.40 about 0.85 (V at 5 %).
- **Why it is approximate.** These figures assume independent pairs. Repetitions of one scene are
  correlated, and Haiku's breaks cluster in five scenes, so the effective sample is smaller.

## Exclusions

- A usage limit, the cap, or a session that ended before its result, means NOT RUN. Nothing is
  retried, except a pair cut by a runner bug, which runs again whole (`--continue`) and goes in
  an amendment.
- A pair is NOT RUN if any of its sessions' `init` event shows a model other than
  `claude-haiku-4-5-20251001` or a `claude_code_version` other than 2.1.287.

## Commands

A one-time setup copies the pinned Claude Code to a private folder; the global install is not
touched (done 2026-10-03; both files have sha256 `6d5be51f...d2ff98b4`):

    mkdir %USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287
    copy %USERPROFILE%\.local\share\claude\versions\2.1.287 %USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287\claude.exe

Dry run (calls nothing, reads no key): builds 96 and 48 repositories and prints as many rows.

    "%PY%" benchmarks\memory_carry\carry.py --out "%TEMP%\v8h-dry\all" --models haiku --scenes all --arms M,V --repeats 3 --dry
    "%PY%" benchmarks\memory_carry\carry.py --out "%TEMP%\v8h-dry\cross" --models haiku --scenes cross --arms M,V --repeats 3 --dry

The launcher is `docs/results/2026-10-02-memory-carry/v8h-run.cmd`, committed with this file,
sha256 `9b6443ef0700dda43b5275033934ac8fc605be9e05f0f6e060f24088bcc31105`. It sets the pinned
Claude Code first on PATH, `DISABLE_AUTOUPDATER=1` and `PYTHONPATH` to the worktree's `src`;
refuses to start if either run already has a `carry.json` or if `claude --version` is not
2.1.287; runs `v8h-all` (`--total-cap 24`) and then `v8h-cross` (`--total-cap 13`); and logs to
`%USERPROFILE%\.cache\sanchopanza\memory-carry\v8h-all.log`, `v8h-cross.log` and
`v8h-run.status`. It is started outside the session, from PowerShell:

    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
      CommandLine = 'cmd.exe /c "C:\Users\roman\Desktop\proyectos\apps\sanchopanza-memoria-v8\docs\results\2026-10-02-memory-carry\v8h-run.cmd"'
      CurrentDirectory = 'C:\Users\roman\Desktop\proyectos\apps\sanchopanza-memoria-v8' }

`ProcessId` in the result is the `cmd.exe`. The driver's PID:

    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
      Where-Object CommandLine -like '*carry.py*v8h-*' | Select-Object ProcessId, CommandLine

Analysis:

    "%PY%" benchmarks\memory_carry\analyze.py "%OUT%\v8h-all" --a V --b M
    "%PY%" benchmarks\memory_carry\analyze.py "%OUT%\v8h-cross" --a V --b M
    "%PY%" benchmarks\memory_carry\sendbacks.py "%OUT%\v8h-all" "%OUT%\v8h-cross"

## Checks before launch (all free)

1. **The worktree.** HEAD is the sealing commit, and nothing tracked is modified.
2. **The sanchopanza in use is the worktree's.** Run
   `set PYTHONPATH=<worktree>\src` and then
   `"%PY%" -c "import sanchopanza; print(sanchopanza.__file__)"`. The path must be under
   `sanchopanza-memoria-v8\src`.
   - Without PYTHONPATH, the venv's editable install resolves to `apps\sanchopanza\src`.
   - `importlib.metadata.version` reports that install (0.3.0), not the worktree's, so it is not
     a valid check.
   - `carry.py:36-39` and `carry_hook.py` (PYTHONPATH=SRC) both put the worktree first.
3. **The decider is Jev.** With that PYTHONPATH and a dummy `TYPESAFE_API_KEY`,
   `decider_from_env` returns `JevDecider`; no call is made. Also check that `httpx` is
   importable. The adoption runs of phase A lost Jev to a missing `httpx`, in silence.
4. **The key.** The TypeSafe key is in the `.env` of an agent with its own harness, which `carry.keyfile_from_harness_env` reads.
   The run needs under 1 USD of TypeSafe balance; the owner checks the balance on TypeSafe's
   console.
5. **Claude Code.** `claude --version`, run with the launcher's PATH, prints 2.1.287.
6. **The dry run** builds 96 and 48 repositories and prints 96 and 48 rows for model `haiku`.
7. **Coordination.** No other batch is using the subscription; all of them share its weekly limit.

## Order and coordination

The owner approved the full design on 2026-10-03: about 29 USD at list price, caps of 24 USD and
13 USD. The subscription pays, but the run uses part of its weekly limit.
