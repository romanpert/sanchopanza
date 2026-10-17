# W17 memory lots: the default install at user scope against clean Claude Code, Sonnet 5.5 and Opus 5.5. Written before its data

Two lots on F2's runner and scenes (`docs/results/2026-10-16-memory-f2`, sealed 763dafd),
parameterised, not forked: `benchmarks/memory_carry/handoff*.py` with the runs `w17-sonnet` and
`w17-opus` and the lot `w17` (`handoff.LOTS`). The owner approved both lots on 2026-10-16
(about 34 USD at list price together, hard cap 45 USD over both). Sealed by `prereg.sha256` (see
"Seal"); until that file matches, every live path refuses. No session of these lots has run.

## Questions

- **Lot S (Sonnet 5.5).** F2 found that S (the project-scope install, memory on) finished the
  next step from a plain "let's continue with ..." line in 48 of 48 triples against N0's 4, but
  at 1.23x N0's cost [1.14, 1.26], so it was not a "gana". Does the new default install at
  **user** scope (S'), as `sanchopanza install --write` leaves it today, keep that gain, also
  when the line names nothing ("Let's continue."), and does it now win without losing on cost?
- **Lot O (Opus 5.5).** On Opus F2 found no room (Claude Code's own auto memory saved the plan
  after every session 1; N0 21 of 24, S 22) and S cost 1.105x N0 [1.011, 1.158] with no gain.
  **The question is cost**: where S' has no room, does it still cost extra?

## Arms

Both arms: clean Claude Code exactly as in F2: a fresh `CLAUDE_CONFIG_DIR` per arm run, kept
across its two sessions, signed in with the subscription's OAuth token only; Claude Code 2.1.287
pinned; `claude -p` with `--output-format stream-json --verbose`, `--settings "{}"`,
`--allowedTools Bash Read Edit Write Glob Grep`, default permission mode, a 900 s timeout per
session. `--max-budget-usd` is **0.50 USD on Sonnet 5.5** (`claude-sonnet-5-5`) and **0.80
USD on Opus 5.5** (`claude-opus-5-5`): about 3.9 and 2.6 times F2's dearest session (0.128 and
0.307; F2's caps were 0.80 and 1.50), lowered so that both lots fit the 45 USD cap pair by pair
(see "Caps"). A session stopped by its own cap counts as run, with its checks as found. Session 1
is the scene's `first` prompt in both arms; its work is committed; session 2 is a new session.

- **N0**: clean Claude Code. Session 2 gets the pair's line (below).
- **S'** (arm `S` in the rows): N0 plus the default install at user scope:
  `sanchopanza install --scope user --memory --write --path <arm's CLAUDE_CONFIG_DIR>/settings.json`
  (`carry_s.U_INSTALL`, `carry_s.install_user`), run from that configuration folder, from `src/`
  at the sealing commit, which is **`src/` at local main cbfd932** (unreleased: memory's C8
  fixes, the lean install; `src/` and `pyproject.toml` unchanged on this branch). Main has since
  moved (50f1ddb and later): the opt-in memory bridge (`install --memory-native`,
  `SANCHOPANZA_MEMORY_NATIVE`, off by default), `memory_gate.memory_dir_for` now derived from
  Claude Code's own auto-memory folder, check_done's evidence windows (opt-in), OpenAI's
  Decisions provider, and soon `decide_facts`' `unrelated_at` default 0.65 (C4). **None of these
  is on the default path S' exercises:** the installed `memory-hook` does not call
  `memory_dir_for` (only the opt-in autopilot and the `memory-dir` helper do) nor
  `relate_facts`/`decide_facts` (only the eval bench does); on main its new bridge code runs only
  when `memory_native.native_on()`, which is off by default; check_done is not installed by
  default. Not rebased: S' is cbfd932's `src/`. Under `CLAUDE_CONFIG_DIR`
  Claude Code reads the user's settings and skills from that folder; the user scope's default
  path is `~/.claude/settings.json`, and `--path` only points it there. The preflight checks that
  the runner's install writes byte for byte the same `settings.json` and skill as a bare
  `sanchopanza install --write` writes into `~/.claude` with the home pointed at an empty folder
  (`handoff_preflight.user_check`). `--memory` is the default and changes nothing.
  - What that install is: the Guardian hook, the compaction guard (pointers), the context budget,
    the coding guard profile, memory's five hook entries, the `sanchopanza-code` skill, and the
    three variables it writes in the settings' `env`, part of the product:
    `SANCHOPANZA_CONTEXT_BUDGET=160000`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000` and
    `SANCHOPANZA_GUARD_PROFILE=coding` (Claude Code passes them to the session's tools, so S's
    shell sees them; declared as a tell below). **No MCP server**: at user scope `install` only prints the
    `claude mcp add-json --scope user ...` line for `find_in_repo`; the runner does not run it
    (as the h2h S line did, `benchmarks/h2h/s_line.py`). Nothing is written in the repository,
    so S' and N0 start from the same repository bytes.
  - Every `sanchopanza ...` command the install wrote is put behind `carry_hook.py ... sub`
    (the pair's own state, the TypeSafe key never in the agent's environment), as in F2. Jev
    decides with the shipped `jev-1.13.0`.
  - **Jev's cap in code:** each hook's decider goes through `CappedDecider` on the run's own
    `SpendLedger` (`capped_sub.py`; `jev-ledger.jsonl` beside the run's key, cap **0.50 USD per
    run**, `RUNS[...]["jev_cap"]`). A call that would not fit is not made and the squire falls
    to its default. F2's Jev spend was 0.012 USD over 48 Sonnet triples. The runner's own
    reserve holds 0.05 USD of Jev per S' session, so in the worst case Jev could pass a run's
    cap by at most 0.40 USD (its 0.50 cap less one arm's reserve).
  - S's store starts with the same 7 decoy rules of other scenes as F2 (`handoff.decoys`, never
    one the scene marks `near`). The Stop audit is off by default and stays off.

**Session 2's line, two strata.**
- **named**: the scene's own F2 line ("Let's continue with the shipping labels."), repetitions
  1-2 in both lots.
- **bare**: `BARE_LINE` = "Let's continue.", naming nothing, repetitions 3-4 on Sonnet and 3 on
  Opus. It matches memory's continuation cue (`memory_recall.continuation`, C8: a session's
  first prompt that only says to go on gets the latest record by code), so S' gets session 1's
  record at the prompt; N0 gets nothing to go on but Claude Code's own auto memory.

Arm order rotates from pair to pair and from repetition to repetition (`build_plan`): each arm
runs first in half of the pairs of each lot (24 of 48 on Sonnet, 18 of 36 on Opus).

### What the agent sees is neutral

- Each arm works in `C:\sp-runs\w18\<r1|r2>\t<NN>-<x>`, its repository in `repo\`, its Claude
  Code configuration in `claude-config\`; NN is the pair's number, x a letter per arm drawn from
  a seeded shuffle of a/b/c (`folder_name`). The scene, the arm, the stratum and the model are
  only in the lot's own rows.
- The lot's own files (rows, ledger, streams, S's install output, logs) are in
  `C:\sp-runs\memory-w17\<run>\`, which no session is pointed at.
- The environment the runner starts Claude Code with has no PYTHONPATH, no key and no
  `SANCHOPANZA_*` variable, in both arms; the checks run with the same environment. In S', Claude
  Code adds the three variables of the installed settings' `env` (above) to its tools'
  environment.
- Tested (`tests/test_memory_carry_w17.py`): in every path and file under the work root of every
  scene, both arms and both strata, no scene name, arm name, model name, stratum label or name of
  the lot, and no word that gives away the scene's C, D or step 2 (S's installed
  `claude-config\settings.json` and skill are exempt from that last check only). The skill names
  no lot, model or ritual (tested).
- What remains, inherent and declared:
  - S's installed hooks, in `claude-config\settings.json`, name the sealed worktree's path and
    `benchmarks\memory_carry\carry_hook.py`. The launcher refuses a worktree whose path contains
    `f2`, `memory`, `handoff`, `memlot`, `w17`, `sonnet` or `opus` (create it as, e.g.,
    `..\sp-w18`).
  - The skill as shipped says that a plain "let's continue" line is enough to start the next
    session and to do the step the record left for next. That is the product being measured.
  - S's shell sees `SANCHOPANZA_CONTEXT_BUDGET`, `SANCHOPANZA_GUARD_PROFILE` and
    `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (the installed `env`): a tell of the arm, not of the scene.
  - **Beside the arm.** `..` from the repository is the arm's own folder: S's `store\`,
    `hooks.jsonl`, `journal.jsonl` and `claude-config\`. `..\..` is the run's folder: every other
    arm's folder of that run (finished repositories of earlier pairs, and the pair's other arm,
    finished when it ran first), and while the run lasts `typesafe.key` (as in F2),
    `jev-cap.json` and `jev-ledger.jsonl`. Each arm keeps F2's layout (no folder of its own above
    it). The runner reports, per arm and session, tool calls that name `..\..`, another arm's
    folder (`t<NN>-<x>` other than its own), `typesafe.key`, `jev-` files, `store`,
    `hooks.jsonl`, `journal.jsonl`, `claude-config`, `.claude/`, `.mcp.json` or `carry_hook`
    (`handoff_call.TOUCH`; counts per arm in the analysis).
  - A session can open its own configuration folder, as any Claude Code user can open
    `~/.claude`.
  - **Shared prompt cache.** Both arms run on the same account, one after the other: Anthropic's
    server-side prompt cache can serve one arm a prefix the other just wrote (the same system
    prompt and tools, and in session 1 the same first prompt). Arm order alternates, so neither
    arm is favoured on average; cache reads and writes are reported per arm.

## Scenes and checks

F2's 12 scenes (`benchmarks/memory_carry/scenes_handoff.py`), unchanged, with F2's checks after
session 2 (Python in the repository, exit 0 when true): `task`, `fact` (C), `decision` (D),
`intact`, and the repository's tests. **Primary outcome, "kept all": `task` and `fact` and
`decision`.** F2's note on checks a natural implementation may pass without knowing C or D
(`h_loud`, `h_nomutate`, `h_batch`, `h_merge`) holds here too.

## Runs

A pair is one scene at one repetition in N0 and S'.

| run | model | scenes x reps | pairs | named / bare | sessions | expected USD | run cap |
|---|---|---|---|---|---|---|---|
| `w17-sonnet` | Sonnet 5.5 | 12 x 4 (reps 1-4) | 48 | 24 / 24 | 192 | 11.4 | 17.0 |
| `w17-opus` | Opus 5.5 | 12 x 3 (reps 1-3) | 36 | 24 / 12 | 144 | 22.8 | 33.0 |

Both run caps are bound by the lot's **45 USD** in code (see "Caps"): whichever runs second gets
at most 45 less what the first spent.

- **Expected cost** from F2's arm means at list price (Sonnet N0 0.109, S 0.129; Opus N0 0.298,
  S 0.335 USD per arm run): 48 x 0.238 and 36 x 0.633. **[assumption]** S' costs no more than
  F2's S (it loads no MCP server and a shorter skill listing) and the bare line does not raise
  either arm's cost. A high scenario of +15 % gives 13.1 and 26.2. Jev: cents. **Expected total
  34.2 USD; hard cap 45 USD.**
- **Expected wall time** from F2's sessions (Sonnet arm 46-55 s, Opus 82-91 s) plus about 6 s of
  building, installing and checking per arm: about **1.5 h for w17-sonnet and 1.9 h for
  w17-opus, 3.4 h together**.

## Sequence (`handoff_night.py --lot w17`, `memlot-night-run.cmd`)

w17-sonnet, then w17-opus; or one of them alone (`memlot-night-run.cmd sonnet|opus`). No pilot
and no gate: S' not running as S' stops the run at its first such arm (below). Any stop other
than the end of a run ends the night. A relaunch resumes: recorded arms are kept.

## Criteria (fixed now, per model, over pairs with both arms run; `handoff_pairs.analyse`)

The **cost ratio** of a pair is S's cost (sessions' own `total_cost_usd` plus its Jev decisions)
over N0's. Its statistic is the **median over pairs**; its interval the percentile bootstrap 95 %
of that median (linear interpolation), pairs taken in (scene, repetition) order and resampled
with replacement, **10,000 draws, seed 20261017** (`handoff_pairs.ratio_interval`, F2's
descriptive statistic made a rule here). The rules read the interval unrounded (`ci95_raw`).

### Lot S, Sonnet 5.5 (`w17-sonnet`)

- **S1 (primary): S' better than N0 on kept all**: one-sided exact McNemar, p < 0.05.
- **S2 (cost): the cost ratio's upper bound <= 1.10.**
- **S3 (no harm):** S's repository tests pass in no more than floor(0.125 x pairs) fewer pairs
  than N0's (6 of 48); S's sessions 2 sent back by a rule other than the scene's C in at most
  5 % of the pairs.
- **Sealed secondary (does not change the verdict): the bare stratum alone**, S' better than N0
  on kept all, one-sided exact McNemar p < 0.05 over its 24 pairs: "the continuation path works
  on a line that names nothing".

**Verdict:** "**gana**" when S1, S2 and S3 hold; "**S' better than N0; no gana (cost)**" when S1
and S3 hold and S2 does not; "**not shown**" otherwise; "**sin veredicto**" with fewer than 40
pairs run.

### Lot O, Opus 5.5 (`w17-opus`)

- **O1 (primary, cost): the cost ratio's upper bound <= 1.05.**
- **O2: kept all not worse**: the lower bound of the one-sided 95 % Tango score interval for the
  paired difference S' - N0 (F2's `tango_bound`), unrounded, above **-12.5 points**.
- **O3 (no harm):** as S3 (4 of 36 for the tests).

**Verdict, in this order:** "**costs extra**" when the cost ratio's lower bound is above 1.00,
whatever O1 says (an interval such as [1.01, 1.04] is extra cost, however small);
"**no extra cost**" when O1, O2 and O3 hold (so its interval also reaches 1.00 or below);
"**not determined**" otherwise; "**sin veredicto**" with fewer than 30 pairs run.

### The scoreboard's "gana" (both lots, `handoff_pairs.scoreboard`)

The final scoreboard's rule (`docs/results/2026-10-13-final`): "gana", per model, is the cost
interval below 1 with success not worse than the margin, or more success at p < 0.05 without
losing on cost. Made exact here, in order:
- "**sin margen**" when N0 failed kept all in fewer than 5 % of the pairs (Opus: in at most 1 of
  36; Sonnet: at most 2 of 48);
- "**gana (coste)**" when the cost ratio's upper bound is below 1.00, O2's bound holds and there
  is no harm;
- "**gana (éxito)**" when S1 holds, the cost ratio's upper bound is within the lot's bound (1.10
  Sonnet, 1.05 Opus) and there is no harm;
- "**no gana**" otherwise. On Sonnet the lot's "gana" and the scoreboard's "gana (éxito)" are the
  same rule.

### What would make each lot a "gana", computed now

- **Sonnet.** Success is not the obstacle: with no pair where only N0 kept all, 5 pairs where
  only S' did give p = 0.031; F2 had 44 to 0. **The obstacle is S2.** With F2's spread of the
  paired log ratio (sd 0.171 over 48 triples), the upper bound is <= 1.10 with probability 0.85
  if S' truly costs the same as N0, 0.57 at 1.03x, 0.33 at 1.05x, 0.09 at 1.08x and 0 at 1.15x
  (simulation, 300 runs of 1,000 draws). So a "gana" needs S' within about 3 % of N0's cost per
  pair. **Expected: no gana on cost.** F2's S cost 1.23x, and most of the gap is N0 asking a
  question in session 2 instead of working (N0 session 2 mean 0.050 USD against S's 0.066), which
  a better install cannot remove; S's own overhead in session 1, where both arms do the same
  work, was 1.077x on Sonnet.
- **Opus.** Success cannot win (F2's N0 kept all in 21 of 24; S1 would need N0 to fail at least
  5 pairs more than S'). "gana (coste)" needs S' cheaper than N0 with the whole interval below
  1: about 0.90x. **Expected: "sin margen" or "no gana"; the lot answers the cost question.**

### Power

- **S1 (Sonnet, 48 pairs):** about 1.00 if S' keeps all in 95 % and N0 in 10 % (F2: 100 % and
  8 %); 0.95 if S' kept only 40 % against N0's 10 %. **Bare stratum, 24 pairs:** 0.97 if S'
  keeps 50 % and N0 5 %.
- **S2 (Sonnet):** above.
- **O1 (Opus, 36 pairs, sd 0.169):** P(upper bound <= 1.05) is 0.84 at a true 0.95x, 0.51 at
  0.98x, 0.25 at 1.00x, 0.03 at 1.05x. **"costs extra"** (lower bound > 1) is seen with
  probability 0.83 at a true 1.105x (F2's S), 0.33 at 1.05x (and wins over O1 when both hold).
  So "no extra cost" is shown only if S' is cheaper than N0; at parity the likely verdict is
  "not determined".
- **O2 (Opus, 36 pairs, margin -12.5):** two more pairs kept by N0 alone than by S' already fail
  it (0 to 2 gives -15.5; 1 to 1 gives -9.2). Power 0.43 if each arm fails 12.5 % of the pairs
  independently, 0.72 if two thirds of the failures fall on the same pairs (F2: both arms' Opus
  failures were mostly `h_judge`).

## Reported, not deciding

Per arm `task`, `fact`, `decision`, `intact`, tests; everything per stratum (kept all, McNemar,
cost ratio and interval); **S's session 1 over N0's session 1** (the same prompt and the same
work, so the install's own overhead; median and the same bootstrap); cost medians per arm and
tokens (input, output, cache read, cache write); session 2's wall time; what S' gave in session
2 (`hook-log.jsonl`), and whether the record came at the prompt; S's memory hook answering both
SessionStarts; Claude Code's own auto memory after session 1 per arm (`native_after_1`); Jev
decisions, failures and dollars; subagent calls; arms whose sessions crossed midnight; per arm
and session the harness files and folders the agent's tool calls named (`handoff_call.TOUCH`:
`.claude/`, `.mcp.json`, `carry_hook`, `claude-config`, `store`, `..\..`, another arm's folder,
`typesafe.key`, `jev-` files, `hooks.jsonl`, `journal.jsonl`); sessions charged for reporting
no cost (`cost_charged`); NOT RUN rows and their reasons.

No pooling across models. The metric is not changed after the data.

## NOT RUN (a row with `cut`, never retried) and stops

As F2 (its "NOT RUN" section), less what concerns H:
- A session that timed out, ended without a result, or whose `init` shows another model or
  Claude Code; a session stopped by its own `--max-budget-usd` counts as run.
- **S' did not run as S'** (`carry_s.session_breaks` with no server, `pair_breaks`): in a
  session, the memory hook answered no prompt without an error, failed at every Stop, or **did
  not answer the session's SessionStart** (the proof that Claude Code loaded the user settings
  from the arm's configuration folder), or **the session's `init` does not list the
  `sanchopanza-code` skill** (`carry.init_facts`' `skill_names`); or the decider was asked
  nothing in the pair or failed every time. The arm is cut and the run stops (exit 4), after S's
  first session when it is that session that failed.
- An exception in the runner: the arm is NOT RUN, its spend counted, the night goes on.
- **Usage limit (429, weekly limit):** no row, folders kept aside, `LIMIT.flag` in the root, the
  night stops (exit 3). A pause, never a result: after the flag is removed, a relaunch runs that
  arm again whole.
- Crash or reboot: the arm's spend counted, its folders kept aside, it runs again whole, at most
  twice.
- Three arms in a row with a session that ended without a result stop the run (exit 7).
- A `STOP` file in the root or a run folder stops before the next arm (exit 6).
- **Quiet hours:** no arm starts whose expected time (below) would reach 02:00-08:00 (Windows
  Update restarts this machine then); the run stops (exit 8) and a relaunch after 08:00 resumes.

## Caps, in code

- Per call: `--max-budget-usd` 0.50 Sonnet, 0.80 Opus (`RUNS[...]["call_caps"]`).
- **One worst turn per call**, since Claude Code checks the cap between turns (and a resumed call
  reloads its context; these lots resume none): F2's `worst_turn`, 0.44 USD Sonnet 5.5 and 0.84
  USD Opus 5.5 (200,000 cached tokens read, 50,000 written, 20,000 out, at Claude Code's rates).
  A session can cost at most 0.94 USD on Sonnet and 1.64 on Opus.
- **A session that reported no cost** (no `result` event: a timeout, a crash, a killed process)
  is charged its cap plus one worst turn (`handoff.charged`), in its row and in the ledger; so is
  each such stream of an interrupted arm (`lost_cost`). No uncounted call can let the run pass
  its cap.
- Per run, **before each pair** (both arms' reserves) and before each arm: what the run spent
  (sessions' own `total_cost_usd` or their charge, Jev, the Jev preflight, interrupted arms)
  plus, for each call still to make, its cap and one worst turn, plus for S' 0.05 USD of Jev per
  session, must stay within the run's cap or the run stops (exit 2) with no orphan arm. One
  pair's reserve: 3.86 USD on Sonnet, 6.66 on Opus.
- Per night: each run's cap is min(its cap, **45 USD** minus what the lot's other run spent), so
  the two lots together never pass 45 USD whichever runs first.
- **Where the runs stop.** w17-sonnet starts no pair once it has spent 13.14 USD (17.0 - 3.86):
  above its +15 % scenario (13.1). w17-opus, run second, has min(33.0, 45 - Sonnet's spend): with
  Sonnet at its expected 11.4 it starts no pair past 26.34 USD, above its +15 % scenario (26.2);
  if both lots run 15 % high (Sonnet 13.1, so Opus capped at 31.9, stopping past 25.24), Opus
  loses its last one or two pairs, which are bare-stratum pairs (repetition 3 runs last).
  Declared now; a run stopped by its cap is analysed over the pairs it ran.
- Jev: 0.50 USD per run through `CappedDecider` (above).
- Every cap is counted in Claude Code's own `total_cost_usd` (its price table, plus Jev's own
  costs); at the owner's rates in `benchmarks/meter.py` the same tokens can come to about 1.5 to
  2 times as much.

## Clock

- **Midnight:** a pair does not start when its expected time (2 arms x 300 s Sonnet, 420 s
  Opus, x 1.5, plus 120 s: 17 and 23 minutes) would reach midnight, and an arm likewise; the
  driver waits and goes on after midnight (F2's rule).
- **Quiet hours** as above: the night is not left to run into 02:00-08:00.
- With the expected 3.4 h, a launch by about 20:00 ends both lots before midnight; w17-sonnet
  alone (1.5 h) fits a launch by about 22:00.

## Running it

- **Keys.** As F2: the lead writes `C:\sp-runs\memory-w17\keys-env.cmd` (untracked, outside the
  repository, only `set SANCHOPANZA_KEYS_ENV=<path>`); the launcher refuses (exit 1) without it
  and never reads the file it names. The token reaches only the `claude` processes, the key only
  S's hooks (`C:\sp-runs\w18\<r>\typesafe.key`, deleted at the start and end of each run); both
  are scrubbed from each arm's files and redacted from every row.
- **Python.** The launcher names no local path: the lead writes
  `C:\sp-runs\memory-w17\python-env.cmd` (untracked, only `set PY=<main checkout>\.venv\Scripts\python.exe`);
  without it the launcher refuses (exit 1).
- **The checkout's path** is checked twice: by the launcher (exit 10) and by `handoff_night.py`
  (`handoff_seal.path_refusal`, exit 11).
- **Jev.** `python -m sanchopanza jev-preflight` (exit 0) before launching; the runner itself makes
  one real Jev decision with the run's key before each run and refuses without an answer.
- **The checkout.** A detached worktree at the sealing commit, at a path that names nothing of
  the lot. `handoff_night.py` refuses (exit 11) unless the files match the seal, HEAD is the
  commit that last wrote `prereg.sha256`, and `git status --porcelain` is empty. The launcher
  refuses a Claude Code other than 2.1.287 (exit 9), with the pin first on PATH and
  `DISABLE_AUTOUPDATER=1`.
- **Launch** by WMI with CreateFlags 512 (header of `memlot-night-run.cmd`). Tell the other
  sessions (PID, time, cap): the subscription's weekly limit is shared.
- **Reboot.** Nothing relaunches the night; start the same launcher again the same way.

## Commands

    rem free: checks, dry run, seal
    set PYTHONPATH=<worktree>\src
    "%PY%" benchmarks\memory_carry\handoff.py --preflight --lot w17 --out C:\sp-runs\memory-w17
    memlot-night-run.cmd dry
    "%PY%" benchmarks\memory_carry\handoff.py --seal --lot w17
    rem paid: by WMI from a detached worktree at the sealing commit
    rem analysis (free; the night also writes <run>-table.json)
    "%PY%" benchmarks\memory_carry\handoff_pairs.py C:\sp-runs\memory-w17\w17-sonnet
    "%PY%" benchmarks\memory_carry\handoff_pairs.py C:\sp-runs\memory-w17\w17-opus

## Seal

`handoff.py --seal --lot w17` writes `prereg.manifest.json` (sha256, LF bytes, of this file and of
`handoff_seal.SEALED_FIXED_W17`: the launcher, `pyproject.toml`, `benchmarks/meter.py`, the
runner, its modules and tests, plus every `benchmarks/memory_carry/*.py` and **every file**
under `src/sanchopanza/`) and `prereg.sha256` (the sha256 of the manifest's lines). A different
seal is refused.

## Deviations from F2

- Two arms, no H; S' at user scope (owner); the bare-line stratum (owner); Opus with three
  repetitions instead of two.
- Lower call caps than F2's (0.50 and 0.80 against 0.80 and 1.50; still 3.9 and 2.6 times F2's
  dearest session), a reserve per pair, and a charge for any session that reported no cost.
- No pilot and no gate: what F2's gate checked for S (hooks answering) is checked per session
  and stops the run at the first failure; H, which needed the gate, is not here.
- Quiet hours (F2's night was accepted unattended).
- Jev through `CappedDecider` on a ledger (F2 only reserved for it).
- A sealed cost rule per lot (F2 sealed none).

## What is not known yet

- **Whether Claude Code 2.1.287 under `-p` loads the user settings and skills from
  `CLAUDE_CONFIG_DIR`** beside `--settings "{}"`. The h2h runs installed there and ran; here
  the first S' session's check (the memory hook answering its SessionStart and prompt, and the
  skill in its init) settles it, and a failure stops the run at that arm, after its first
  session when that session failed (at most about 0.13 USD on Sonnet).
- S's cost at user scope, and how N0 answers a line that names nothing.

## Amendment 1 (2026-10-17, before the Opus redo's data)

Written before any session of the redo has run. It replaces the seal of 5d416fa (instrument
f31caf8, sha256 `49b86f8b873f7260bf5855664bdc237ef12411bbe3d4fe9bb11fb54c13e01cdc`) for the
redo of `w17-opus` only; `w17-sonnet` ran whole under that seal and its published result
(`README.md`) stands as it is. The new seal is the only child of the commit that adds this
section; until it is written, every live path refuses ("no seal").

**Why the redo.** On 2026-10-16 at 22:37 the machine went down (System event 41) while
`w17-opus` ran. Its rows file `f2.json` came back zero-filled, and so did the end of its
`ledger.jsonl`: both were written with a temporary file and `os.replace`, or an append, with no
`fsync`, so the rename reached the disk before the data. The relaunch at 22:51 stopped with an
error (exit 1) before any arm: `f2.json` could not be read. The owner decided to run `w17-opus`
again, whole and clean.

**The interrupted run is discarded.** 23 arm folders had started (pairs t00 to t11); its
ledger's readable lines hold **6.56 USD** (the Jev preflight and 21 arms); its zero-filled last
line and the arm cut at 22:37 are not in that figure (about 0.6 USD more at F2's Opus arm
means). None of it is read, resumed or used for any verdict, figure or table. Its
folders (`C:\sp-runs\memory-w17\w17-opus`, `C:\sp-runs\w18\r2`) are left where they are, as
evidence, and are not deleted.

**What changes.**
1. **State that survives an unclean shutdown.** Main's fix (88f5400, here cherry-picked with
   `-x`) writes through `sanchopanza.durable`: a file is flushed and `os.fsync`ed before its
   rename, an appended line after it is written. In this runner: the rows (`handoff.write_rows`),
   the ledger (`handoff.book`) and `interrupts.json`. In `src/`: the Jev cap's `SpendLedger`
   lines, the funds breaker and memory's episodes store. The bytes written are the same; only how
   they are written changes (`tests/test_durable.py`, each writer syncs before its rename with
   unchanged bytes).
2. **The quiet hours lift while Windows Update is paused.** The rule of "NOT RUN and stops" (no
   arm starts whose expected time would reach 02:00-08:00, exit 8) exists only because Windows
   Update restarts this machine then. It now lifts while updates are **paused at least 24 hours
   past each check** (`benchmarks/memory_carry/winupdate.py`, the same module and tests as the
   guard-pointers lot's Amendment 1: the earliest end of `PauseUpdatesExpiryTime` and
   `PauseQualityUpdatesEndTime` under `HKLM\SOFTWARE\Microsoft\WindowsUpdate\UX\Settings`; no
   pause, or a value that cannot be read, keeps the rule). It is checked where the rule was,
   before each arm (`handoff.run_plan`); each lift is written to the runner's log (`night.log`:
   "quiet hours lifted for t<NN>-<x>: Windows Update paused until ..."). If the pause ends during
   the run, the rule is back before the next arm. **The midnight rule does not change** (a pair or
   an arm does not start when it would reach midnight; the driver waits). This runner has no
   pending-restart check, sealed or new.
3. **New roots.** The redo's own files go to `C:\sp-runs\memory-w17-redo\w17-opus\` (keys and
   Python files: `C:\sp-runs\memory-w17-redo\keys-env.cmd` and `python-env.cmd`, as before) and
   its arms work in `C:\sp-runs\w19\r2\t<NN>-<x>` (`handoff.LOTS["w17"]`). `handoff_night.py`
   refuses, dry or live and before writing anything, the interrupted run's root or work folder
   (`handoff.W17_INTERRUPTED`, exit 11). So the redo cannot resume from, set aside, or charge an
   arm of the interrupted run, and its Jev cap starts from an empty `jev-ledger.jsonl`.
4. **The launcher runs only the redo**: `memlot-night-run.cmd opus` (or `dry`, which builds the
   Opus arms under the new root and calls nothing). No argument and `sonnet` are refused (exit 2).

**What does not change.** The arms N0 and S' and how they are built; S' is still `src/` as at
cbfd932 plus the writes of change 1 (the same installed `settings.json`, hooks, skill and `env`;
the preflight's byte-for-byte check against a bare `sanchopanza install --write` holds as
sealed); the 12 scenes and their checks; `w17-opus`'s three repetitions (named 1-2, bare 3), 36
pairs, 144 sessions, its plan and arm order; the call caps (0.80 USD Opus, one worst turn of
0.84 per call), the reserve per pair (6.66 USD), the charge for a session that reported no cost,
Jev's 0.50 USD cap per run; Opus's criteria O1-O3 and their verdict order; the scoreboard's rule;
the analysis (`handoff_pairs.analyse`, the bootstrap and its seed) and what is reported.

**Caps and cost.** The run cap stays the sealed **33.00 USD**. The code computes it as
min(33.0, 45 - what the lot's other run spent in the root): the new root holds no `w17-sonnet`
ledger, so 45 - 0 = 45 and the cap is 33.00 (in the old root it was min(33.0, 45 - 11.18 =
33.82) = 33.00, the same). The redo starts no pair past 26.34 USD (33.00 - 6.66), above its +15 %
scenario (26.2). Expected at list price: **22.8 USD** (36 x 0.633). The lot's spend:
**Sonnet 11.18 + interrupted Opus 6.56 + redo ~22.8 = ~40.5 USD (about 41)**. Worst case with
the redo at its cap: **11.18 + 6.56 + 33.00 = 50.74 USD** (51.14 with Jev's possible 0.40 past
the run cap), above the 45 USD sealed for the lot: the interrupted run's spend is not counted
against the redo, which is bound by its own 33.00 USD. The owner approved the redo at about 23
USD expected.

**Seal and launch.** As "Seal" and "Running it", with the new roots: the instrument is the commit
that adds this section; `handoff.py --seal --lot w17` in a clean checkout of it writes
`prereg.manifest.json` and `prereg.sha256` (the old seal files are removed by the instrument
commit, so that `seal` writes a new one), committed alone; the run goes from a detached worktree
at that sealing commit whose path names nothing of the lot. An independent review of this
amendment against the code (`revisor-prereg`) goes before the seal.
