# F2: memory against the handoff ritual, Sonnet 5.5 and Opus 5.5. Written before its data

From the draft `docs/results/2026-10-05-memory-frontier/prereg-f2-handoff.md`, with the owner's
answers of 2026-10-15 and an independent review's findings of 2026-10-16 (applied before
sealing). Sealed by `prereg.sha256` (see "Seal"); until that file matches, every live path
refuses. No session of this lot has run.

## Question

The owner carries work across sessions with a handoff: at the end of a session he asks for a
prompt to continue in a clean session and pastes the answer as the next session's first prompt.
Does sanchopanza as it ships (memory on by default since 2026-10-14), with no handoff, keep as
much of what session 1 said? At what cost in dollars, tokens and the user's effort?

## Arms

All three: clean Claude Code exactly as in the memory cell (`docs/results/2026-10-13-memory-cell`):
a fresh `CLAUDE_CONFIG_DIR` per arm run, kept across its sessions, signed in with the
subscription's OAuth token only; Claude Code 2.1.287 pinned; `claude -p` with
`--output-format stream-json --verbose`, `--settings "{}"`, `--allowedTools Bash Read Edit Write
Glob Grep`, default permission mode, `--max-budget-usd` 0.80 (Sonnet 5.5, `claude-sonnet-5-5`)
or 1.50 (Opus 5.5, `claude-opus-5-5`), a 900 s timeout per session. Session 1 is the same
prompt in every arm; its work is committed.

- **N0**: session 2, a new session, gets the scene's `continue` line ("Let's continue with the
  shipping labels.").
- **H**: after session 1, the same session is resumed once: `claude -p --resume <session 1 id>
  "Give me a prompt to continue this work in a clean session."`, same flags, caps and folder,
  600 s timeout. Its result text is `handoff.txt`. Session 2, a new session, gets exactly that
  text, nothing added; that it arrived byte for byte is checked in session 2's own transcript
  (`pasted_verbatim`). The handoff turn's cost and tokens count in H.
- **S**: N0 plus `sanchopanza install --scope project --memory --write` in the scene's
  repository before its start commit (`carry_s.install`, as the memory cell), from `src/` at
  the sealing commit, which is **origin/main 3fb53f1** (the published state; `src/` and
  `pyproject.toml` unchanged on this branch). `--memory` is the default since 2026-10-14 and
  changes nothing (the preflight checks that a bare `install --scope project --write` writes the
  same files); the Stop audit is off by default and stays off. Hooks and the `find_in_repo`
  server run behind `carry_hook.py` with the arm's own state and the TypeSafe key (never in the
  agent's environment); Jev decides. S's store starts with 7 decoy rules of other scenes, never
  one the scene marks `near` (`handoff.decoys`). Session 2 gets the same `continue` line as N0.

Arm order rotates from triple to triple and from repetition to repetition (`build_plan`): in
f2-sonnet each arm runs first in 16 of 48 triples.

### What the agent sees is neutral

- Each arm works in `C:\sp-runs\w16\<r1|r2|r3>\t<NN>-<x>`, its repository in `repo\` under it:
  NN is the triple's number, x a letter per arm shuffled per triple by a seeded RNG
  (`folder_name`). The scene, the arm and the model are only in the lot's own rows.
- The lot's own files (rows, ledger, streams, `handoff.txt`, S's install output, logs) are in
  `C:\sp-runs\memory-f2\<run>\`, which no session is pointed at.
- The agent's environment has no PYTHONPATH, no key and no `SANCHOPANZA_*` variable; the checks
  run with the same environment.
- Tested (`test_memory_carry_handoff_work.py`): in every path and file under the work root, no
  scene name, arm name, model name or name of the lot, and no word that gives away the scene's
  C, D or step 2 (S's installed sanchopanza files are exempt from that last check only).
- What remains, inherent and declared: S's installed hooks name the sealed worktree's path and
  `benchmarks\memory_carry\carry_hook.py`. The launcher refuses a worktree whose path contains
  `f2`, `memory` or `handoff` (create it as, e.g., `..\sp-w16`). A session can open its own
  configuration folder (`..\claude-config`), as any Claude Code user can open `~/.claude`.

## Scenes

12 new scenes, `benchmarks/memory_carry/scenes_handoff.py`, tested on hand-written results
(`tests/test_memory_carry_handoff.py`). Session 1 gives the plan (step 1 today, step 2 next
session, step 2's function named), asks for step 1 only, and says in passing a constraint C and
a decision D about step 2. Nothing in the start repository or the `continue` line gives away
step 2, C or D (tested).

| scene | C (kind) | D (kind) |
|---|---|---|
| `h_batch` | carrier rejects > 50 labels per request (constraint) | use the bulk call (plain) |
| `h_loud` | never swallow errors or fall back; raise (preference) | round each line, then add (plain) |
| `h_spanish` | customers see Spanish only (preference) | every problem at once (plain) |
| `h_flag` | price changes behind a FEATURE_* flag, off by default (preference) | cap discount at 20 % (plain) |
| `h_nomutate` | never modify arguments; return new objects (preference) | coupon on books only, not the whole cart (reversal) |
| `h_dryrun` | data scripts are dry by default, write with --apply (preference) | archive, don't delete (plain) |
| `h_semicolon` | partner reads `;` with a decimal comma (constraint) | one file, oldest first, not one per month (reversal) |
| `h_retry` | receivers dedup by X-Event-Id (constraint) | three attempts in total, then raise (plain) |
| `h_merge` | CRM ignores case and `+tag` in addresses (constraint) | keep the existing record (plain) |
| `h_weeks` | weeks run Sunday to Saturday (constraint) | round weeks to a quarter hour (plain) |
| `h_judge` | text judgments go through `judge()` (preference) | enterprise plan always urgent (plain) |
| `h_pages` | every call asks for a page of at most 100 (constraint) | cursor, not offset (reversal) |

Six scenes have C as a working preference, three have D reversing a plan made earlier in the
same prompt.

**Checks** after session 2 (Python in the repository, exit 0 when true): `task` (step 2 works),
`fact` (C holds in step 2), `decision` (D followed), `intact` (step 1 still works), and the
repository's tests. **Primary outcome, "kept all": `task` and `fact` and `decision`.**

**Checks a natural implementation may pass without knowing C or D** (they cost room, so power):
C in `h_loud` (an unknown currency raises a `KeyError` unless code adds a fallback) and
`h_nomutate` (a comprehension does not mutate), D in `h_batch` (the bulk call is there to be
used) and `h_merge` (keeping the first record seen keeps the existing one). C in `h_pages` was
strengthened before sealing: leaving the limit out does not keep it. If N0 keeps all in every
pilot triple the gate stops the night (d); on the full runs the counts per scene are reported.

## Runs

A triple is one scene at one repetition in N0, H and S.

| run | model | scenes x reps | triples | calls | expected USD | run cap | expected wall time |
|---|---|---|---|---|---|---|---|
| `f2-pilot` | Sonnet 5.5 | 4 x 1 (rep 0) | 4 | 24 + 4 handoffs | 2.2 (draft: 7.4) | 11.5 | 0.5 h |
| `f2-sonnet` | Sonnet 5.5 | 12 x 4 (reps 1-4) | 48 | 288 + 48 | 26 (draft: 88.9) | 109 | 5.5 h |
| `f2-opus` | Opus 5.5 | 12 x 2 (reps 1-2) | 24 | 144 + 24 | 25 (draft: 84.2) | 106 | 4 h |

- **Cost:** the memory cell, clean user, measured 0.056 USD per N session and 0.062 per S session
  on Sonnet 5.5; a two-step session is assumed to cost 1.5 times that **[assumption]**, a handoff
  turn 0.3 of a session **[assumption]**, Opus 1.9 times Sonnet (the draft's ratio from gen-opus
  and confirm). The draft's figures (0.19 USD per Sonnet session, from runs that loaded the
  maintainer's own setup) are kept beside them as the high scenario. Jev: cents.
- **Wall time:** the memory cell's sessions took 26-30 s; assumed 1.5 times, plus building, the
  S install, the checks; Opus about 1.5 times slower **[assumptions]**. About 10 h for the
  night.
- Pilot rows are not data: the pilot's scenes (`h_batch`, `h_spanish`, `h_nomutate`, `h_weeks`)
  run again with fresh repetitions in f2-sonnet.

## Sequence, in one unattended night (`handoff_night.py`)

f2-pilot, then the gate below, then f2-sonnet, then f2-opus. Any stop other than the end of a run
ends the night. A relaunch resumes: recorded arms are kept, the gate's result is read back.

### The pilot's automatic gate (`handoff_analyze.gate`, fixed now)

The night continues past the pilot only if every one of its 12 arms has a row and:

- **(a)** H's handoff was captured and pasted in all 4 H triples: no H row cut at the handoff, a
  non-empty `handoff.txt`, a cost reported by the resumed turn, `context_carried` True (unknown
  fails) and session 2's first user message in its transcript equal to `handoff.txt` byte for
  byte (`pasted_verbatim` True);
- **(b)** every check ran and returned a boolean (`tests`, `task`, `fact`, `decision`,
  `intact`, `kept all`) in every arm, and no arm was cut;
- **(c)** no pilot scene has every arm failing `task`;
- **(d)** N0 did not keep all in all 4 pilot triples;
- **(e)** S's hooks ran: in every pilot S arm, the memory hook answered SessionStart in both
  sessions (`hook_starts` at least 2, from `carry_hook`'s log). This checks the harness, not
  whether S gave anything.

Otherwise the driver writes `gate.md` and `gate.json` with the reasons and stops (exit 5);
nothing larger runs.

## Criteria (fixed sequence, per model, over triples with all three arms run)

1. **S not worse than H on kept all.** The lower bound of the one-sided 95 % Tango score
   interval for the paired difference S - H (Tango 1998; `tango_bound`, tested against both of
   the paper's worked examples), unrounded, is above **-12.5 points**.
2. **S better than N0 on kept all**: one-sided exact McNemar, p < 0.05. Read only if 1 holds.
3. On Opus, 1 and 2 are computed the same way; with 24 triples they are **direction only**.
4. (Opus's reading of 2.)
5. **No harm:** S's repository tests pass in no more than floor(0.125 x triples) fewer triples
   than H's (6 of 48, 3 of 24); S second sessions sent back by a rule other than the scene's C
   in at most 5 % of triples.
6. **Reported, not criteria:** per arm `task`, `fact`, `decision`, `intact`; per triple cost
   (USD, S with Jev) and tokens (input, output, cache read, cache write) per arm, medians and
   paired median S/H, S/N0; the handoff's length (characters, output tokens: median, max);
   whether `handoff.txt` names C and D (the scene's fixed key phrases); H against N0 (McNemar
   both ways); what S gave in session 2 (`hook-log.jsonl`); Claude Code's own auto memory per
   arm; Jev decisions and failures; subagent calls; arms whose sessions crossed midnight; handoff
   turns whose reported cost is at least session 1's (a cumulative report would show so).

**Verdict, the same rule for both models (`handoff_analyze.verdict_of`):**

- "**S not worse than H**" when 1 and 5 hold;
- "**S better than N0**" when 1, 2 and 5 hold;
- "**not shown**" when neither claim holds (so whenever 5 fails);
- Opus's verdict is prefixed "**direction only:**"; a miss reads "not shown", not "worse";
- "**sin veredicto**" when fewer than 40 Sonnet triples (20 Opus) ran.

No pooling across models. The metric is not changed after the data.

## NOT RUN (a row with `cut`, never retried) and stops

- A session that timed out, ended without a result, or whose `init` shows another model or
  Claude Code; a session stopped by its own `--max-budget-usd` counts as run. A timed-out
  session's whole process tree is killed by its own PID (never by name).
- **H's handoff:** session 1 gave no session id; the resumed turn timed out, exited non-zero,
  ran another model or Claude Code, returned no text or reported no cost; its first request held
  less than **50 %** of session 1's last request's context (`context_carried`: a fresh session
  holds only the system prompt and the request; half, not all, because on resume Claude Code may
  drop earlier thinking blocks); or session 2's command line with that text would reach Windows'
  32,767-character limit. The triple is NOT RUN and the count is reported. No retry.
- **S** did not run as S (`carry_s` checks, as the memory cell): the arm is cut and the run
  stops (exit 4).
- **An exception in the runner** during an arm: the arm is NOT RUN (`harness exception:
  <class>`), what it spent is counted, and the night goes on.
- **Usage limit (429, weekly limit):** from the stream's events, or a short or error result (or
  stderr) that says "usage limit", "hit your limit" or "weekly limit". The arm gets no row (its
  folders are kept aside as `*.limit-<time>`), `C:\sp-runs\memory-f2\LIMIT.flag` is written (the
  only place) and the night stops (exit 3). A pause, never a result: after the owner removes the
  flag, a relaunch runs that arm again whole.
- **Crash or reboot:** an arm with a folder and no row is counted (its streams' costs and its
  decisions), its folders are kept aside as `*.interrupted-<time>`, and it runs again whole, at
  most twice; a third interruption makes it NOT RUN.
- Three arms in a row with a session that ended without a result stop the run (exit 7).
- A `STOP` file in the root or a run folder stops before the next arm (exit 6).

## Caps, in code

- Per call: `--max-budget-usd` 0.80 Sonnet, 1.50 Opus, the handoff turn included.
- **One worst turn per call**, since Claude Code checks the cap between turns: a turn that
  reads a 200,000-token context from the cache, writes 50,000 new tokens to it and answers
  20,000, at Claude Code's own rates (`meter.CLAUDE_CODE_RATES`, the dearer cache write):
  Sonnet 5.5 200,000 x 0.2 + 50,000 x 4.0 + 20,000 x 10 per million = **0.44 USD**; Opus 5.5
  200,000 x 0.2 + 50,000 x 8.0 + 20,000 x 20 = **0.84 USD** (`handoff.worst_turn`). The memory
  cell's dearest session was 0.115.
- Per run, before each arm: what the run spent (sessions' own `total_cost_usd`, Jev decisions,
  the Jev preflight, interrupted arms) plus, for each of the arm's calls (3 for H, 2 otherwise),
  its cap and one worst turn, plus for S 0.05 USD of Jev per session, must stay within the run's
  cap (11.5, 109, 106) or the run stops (exit 2). One triple's reserve is 8.78 USD on Sonnet,
  16.48 on Opus.
- Per night: each run's cap is min(its cap, 230 minus what the earlier runs spent); the three
  caps add up to 226.5.

## Clock

A triple does not start when its expected time (3 arms x 300 s Sonnet, 420 s Opus, x 1.5, plus
120 s) would reach midnight, and an arm likewise; the driver waits and goes on after midnight.
The owner accepted the night unattended, 02:00-08:00 included.

## Running it

- **Keys.** The OAuth token and the TypeSafe key are read by `carry.py` from the file
  `SANCHOPANZA_KEYS_ENV` names. That path is not in any tracked file and not part of the seal:
  the lead writes `C:\sp-runs\memory-f2\keys-env.cmd`, a local untracked file outside the
  repository holding only `set SANCHOPANZA_KEYS_ENV=<path>`. The launcher calls it if it exists,
  then refuses to start (exit 1) when the variable is empty or the file it names does not exist;
  it never reads that file. The token reaches only the `claude` processes, the key only S's hooks
  (in `C:\sp-runs\w16\<r>\typesafe.key`, deleted at the start of the night, of each run, and at
  each run's end).
- **The checkout.** From a detached worktree at the sealing commit, at a path that names nothing
  of the lot. `handoff_night.py` refuses (exit 11) unless the files match the seal, HEAD is the
  commit that last wrote `prereg.sha256`, and `git status --porcelain` is empty. The launcher
  refuses a Claude Code other than 2.1.287 (exit 9) and a worktree path that names the lot (exit
  10).
- **Reboot.** A reboot (or any crash) pauses the night: nothing relaunches it. The lead or the
  owner starts the same `f2-night-run.cmd` again, the same way (WMI), and it resumes from what
  is recorded.

## Commands

    rem free: checks, dry run, seal
    set PYTHONPATH=<worktree>\src
    "%PY%" benchmarks\memory_carry\handoff.py --preflight --out C:\sp-runs\memory-f2
    "%PY%" benchmarks\memory_carry\handoff_night.py --root %TEMP%\f2-dry --dry
    "%PY%" benchmarks\memory_carry\handoff.py --seal
    rem paid: by WMI from a detached worktree at the sealing commit (header of f2-night-run.cmd)
    rem analysis (free)
    "%PY%" benchmarks\memory_carry\handoff_analyze.py C:\sp-runs\memory-f2\f2-pilot --gate
    "%PY%" benchmarks\memory_carry\handoff_analyze.py C:\sp-runs\memory-f2\f2-sonnet
    "%PY%" benchmarks\memory_carry\handoff_analyze.py C:\sp-runs\memory-f2\f2-opus

## Seal

`handoff.py --seal` writes `prereg.manifest.json` (sha256, LF bytes, of this file, the launcher,
`pyproject.toml`, `benchmarks/meter.py`, the runner, its modules and tests, every
`benchmarks/memory_carry/*.py` and **every file** under `src/sanchopanza/`, not only its `.py`)
and `prereg.sha256` (the sha256 of the manifest's lines). A different seal is refused. The night
refuses unless the checkout matches it (see "Running it").

## Deviations from the draft

- Sibling modules (`handoff*.py`) instead of new arms in `carry.py` and `analyze.py`: the sealed
  runners of earlier lots stay as they were; `carry.py` and `carry_s.py` are reused unchanged.
- N is the clean user (owner), not the maintainer's setup; S is the install as it ships today,
  memory on by default (owner); no S+H arm (owner).
- The three runs go in one night behind the automatic gate (owner), not after the owner reads
  each.
- A session timeout makes the arm NOT RUN and the night goes on (the memory cell stopped and
  resumed once); the stand-in for an unattended night.
- Opaque work folders, `context_carried` and `pasted_verbatim`, gate (e), the command-line
  limit, runner exceptions, the "three in a row without a result" stop, the interrupted-arm rule,
  the minimum triples for a verdict, and one worst turn per call are added.
- Expected costs are re-estimated from the memory cell's clean-user sessions; the owner's caps
  are unchanged.

## What is not known yet

- Whether `--resume` with `-p`, `--settings` and `stream-json` resumes session 1 in 2.1.287 and
  reports the turn's own `total_cost_usd`. Handled: a failure is NOT RUN and gate (a) fails.
- Two-step session costs and wall times; how long and how good the handoffs are; whether N0 has
  room (gate d).
