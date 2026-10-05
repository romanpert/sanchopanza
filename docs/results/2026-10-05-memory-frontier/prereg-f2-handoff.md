# F2. Memory against the handoff ritual, on frontier models (DRAFT, 2026-10-05)

**Draft. Not sealed, not committed, nothing launched.** It becomes a prereg only when the owner
has answered the open questions at the end, the engineering below is done and tested, and a
commit adds its sha256. Every number marked **[unverified]** was not checked against a file.
Shared parts (arms N and S, cost per session, the pinned Claude Code, the engineering of arm S)
are in `prereg-f1-correctness.md` and are not repeated here.

## The question

The owner's own way to carry work across sessions is a handoff. At the end of a session he asks
"give me a prompt to continue in a clean session", and pastes the answer as the first prompt of
the next one. Does sanchopanza's memory, with no handoff, do as well? At what cost in tokens,
dollars and the user's effort? Models: Sonnet 5.5 (`claude-sonnet-5-5`) and Opus 5.5
(`claude-opus-5-5`). No Haiku.

## Why

- **The ritual is common.** In the maintainer's real sessions (122 Opus 5.5 sessions,
  2026-09-20 to 2026-10-05; counts from the caller), 61 % start with a pasted handoff and 34 %
  end asking for a prompt to continue. That is the baseline a user of a frontier model actually
  has. "Nothing" (N0) is not the baseline the owner beats today.
- **Cross-session failures are rare but costly** (about 1.3 per 100 turns), and most are durable
  preferences or stale memory, not lost task facts (F1, "Why"). A handoff written by the model
  carries what the model thought mattered. A preference said in passing may not be in it.
- **Memory carry on Sonnet 5.5** kept facts said in passing 23/24 against 14/24
  (`docs/results/2026-10-02-memory-carry/README.md`). It was never compared with a handoff.
- **What S does here, from the code.** With a short "continue" prompt that names no file:
  - SessionStart gives the standing rules (up to 8, newest first);
  - prompt recall at the first request is gated in v5: a record that changed files enters only
    if the prompt names one of them (`memory_hook` docstring, `MEMORY_PROMPT_NAMED`), so session
    1's record does not enter at the prompt;
  - it can still enter when the agent opens a file session 1 changed (the touch).
  So S may keep the constraints and lose "what was next" until a file is opened. That is a
  prediction, not a result.

## Arms

- **N0, nothing.** Claude Code as a user has it (arm N of F1). Session 2 gets a short
  continuation line, fixed per scene, as a user without a handoff would type it ("Let's continue
  with the invoice export.").
- **H, the handoff.** N, plus the ritual:
  1. after session 1, the same session is resumed once (`claude -p --resume <session_id>`) with
     "Give me a prompt to continue this work in a clean session.";
  2. the text of that turn's result is saved as `handoff.txt`;
  3. session 2, a new session, gets exactly that text as its first prompt, nothing added.
- **S, sanchopanza, no handoff.** Arm S of F1 (`sanchopanza install --memory` as a user would
  install it, v8.1 at e4a3ec1). Session 2 gets the same continuation line as N0.
- All three: same model, tools, caps, Claude Code; session 1 identical.

## Scenes (new; 12, none exists yet)

A scene is one feature in two steps, over two sessions.

- **Session 1** prompt: the person describes the feature and the plan ("step 1 today, step 2
  next session"). While step 1 is done, the person states, in passing:
  - **C, a constraint** not inferable from the repository (as carry's facts);
  - **D, a decision** about step 2 ("for step 2 use the batch endpoint, not one call per item").
- **Session 2** must do step 2.
- **Checks** (Python in the repository, exit 0 when true; each tested on hand-written results
  that keep and break it):
  - `task`: step 2 is done;
  - `fact`: C holds;
  - `decision`: D was followed;
  - `intact`: step 1's work was not undone;
  - the repository's tests.
- **Primary outcome, "kept all":** `task` and `fact` and `decision` all pass.
- Nothing in the repository (no TODO, no plan file) or in the continuation line gives away step
  2, C or D.
- Scene topics follow the real failures where possible: at least 4 of the 12 have C as a working
  preference (as F1 family (i)), and at least 2 have a decision that reverses one made earlier
  in session 1 (as F1 family (ii)).

## Pilot (development, before sealing)

- Sonnet 5.5, 4 scenes, repetition 0, all three arms. 4 triples, 24 sessions plus 4 handoff
  turns. About **7.4 USD**, `--total-cap 11.5`.
- What it is for: the checks see real outputs; the handoff capture works end to end; and whether
  N0 already keeps everything (then the scene has no room and is rewritten).
- Its rows are not data. The 4 scenes may be revised. They stay among the 12 and run again with
  fresh repetitions, reported apart, as carry's confirmation did with its pilot scenes.

## Runs

A triple is one scene at one repetition, run in N0, H and S.

| run | model | scenes x repetitions | triples | sessions | expected | `--total-cap` |
|---|---|---|---|---|---|---|
| `f2-pilot` | Sonnet 5.5 | 4 x 1 | 4 | 24 + 4 handoffs | 7.4 USD | 11.5 USD |
| `f2-sonnet` | Sonnet 5.5 | 12 x 4 | 48 | 288 + 48 handoffs | 88.9 USD | 109 USD |
| `f2-opus` | Opus 5.5 | 12 x 2 | 24 | 144 + 24 handoffs | 84.2 USD | 106 USD |
| **total** | | | | | **180.5 USD** | |

### How the cost was estimated

- Per carry session, measured (`carry.json` of each run, sessions' own `total_cost_usd`):
  Sonnet 0.19 USD (`v8-cross` 0.180, `confirm` 0.189); Opus 0.36 USD (`gen-opus` 22.971 USD
  over 64 sessions, 0.359).
- **A two-step session costs 1.5 times a carry session [assumption]:** Sonnet 0.285, Opus 0.54.
- **A handoff turn costs 0.3 of a session [assumption]:** one resumed request over a cached
  context, with a few hundred to a few thousand output tokens.
- **S costs 10 % more than N [assumption]**, as in F1.
- Per triple: Sonnet 0.570 (N0) + 0.627 (S) + 0.656 (H) = 1.853 USD; Opus 1.080 + 1.188 +
  1.242 = 3.510 USD.
- The Jev decisions are not in these figures (cents per run).

## Caps, and how they are enforced

- **Per session:** `--max-budget-usd` 0.80 on Sonnet and 1.50 on Opus **[proposal]**. Two-step
  sessions have never been measured, and the largest carry session was 0.294 (Sonnet) and 0.538
  (Opus). The handoff turn runs under the same cap.
- **Per run:** `--total-cap` as in the table, about 1.2 x expected plus one arm's sessions at the
  per-session cap. The runner checks before each arm, counting 3 calls for H.
- **Usage limit:** stops the run.
- **No API key** in the agent's environment; the TypeSafe key only in S's hooks.
- **Sequence:** the pilot ends and waits for the owner. `f2-sonnet` ends and waits.
  `f2-opus` starts only on the owner's word.

## Criteria (fixed sequence; each is confirmatory only if the one before is met)

1. **Sonnet: S is not worse than H** on "kept all". The lower bound of the one-sided 95 %
   interval for the paired difference S - H (Tango's score interval) is above **-12.5
   percentage points**.
2. **Sonnet: S is better than N0** on "kept all": one-sided exact McNemar, p < 0.05.
3. **Opus: S is not worse than H**, as in 1. With 24 triples its power is low (below), so unless
   the owner funds 48, a miss reads "not shown", not "worse".
4. **Opus: S is better than N0**, as in 2.
5. **No harm, per model:** S's tests fall no more than 6 per 48 triples (3 per 24) below H's;
   S second sessions sent back by a rule other than the scene's own C at most 5 %.
6. **Reported, not criteria:**
   - per arm: `task`, `fact`, `decision` and `intact` apart;
   - **cost per triple**: USD and tokens (input, output, cache read, cache write) per arm, with
     H's handoff turn counted in H; the paired median S/H and S/N0;
   - **user effort**: H needs one more request and one paste per session; the handoff's length
     in characters and tokens (median, maximum); S and N0 need none after a one-time install;
   - whether H's handoff text names C and D (a fixed key phrase per scene, searched in
     `handoff.txt`);
   - H against N0 (does the ritual help at all);
   - what S gave in session 2 (`hook-log.jsonl`: rules at start, records at the prompt, at a
     touch) and when, against the moment the agent first opened a file;
   - what Claude Code's own auto memory saved, per arm;
   - decider failures, subagent calls and their models.

### Why a margin of 12.5 points

- It is the no-harm margin every carry prereg has used (2 per 16 pairs).
- What the user gains from S is a request and a paste saved at a third of session ends. Losing
  more than 1 task in 8 would cost more than that, and the owner would notice.
- A tighter margin is not affordable. At 5 points, with 10 % discordant triples, 80 % power
  needs about 250 triples, near 460 USD on Sonnet alone.

## Power (approximate)

Simulated (6,000 runs, independent triples, H keeps all in 0.85 of triples **[assumption]**,
a Wald interval on the paired difference as a stand-in for Tango's):

| triples | discordant S/H | true S - H | power for criterion 1 |
|---|---|---|---|
| 48 | 10 % | 0 | 0.84 |
| 48 | 20 % | 0 | 0.64 |
| 48 | 10 % | -5 points | 0.53 |
| 24 | 10 % | 0 | 0.68 |
| 24 | 20 % | 0 | 0.42 |

- Criteria 2 and 4 depend on N0's room, which the pilot gives a first look at. On carry's
  Sonnet scenes N broke 10 of 24; whether N0 misses step 2, C or D at a similar rate is
  unknown.
- Repetitions of a scene are correlated, so the effective sample is smaller than the count.

## Exclusions

- As in F1: usage limit, the run's cap, or a session that ended before its result: NOT RUN.
  A session stopped by its own budget counts as run, checks as found. Model or version other
  than the pinned ones: NOT RUN. No retries except a runner bug (`--continue`, amendment).
- **The handoff turn returns no text, or an error:** the triple is NOT RUN, and the count is
  reported per model. In real use the person would just ask again. Retrying here would hide how
  often it fails.

## Engineering still needed (in a new branch and worktree, after or apart from `v81h-cross`)

1. `benchmarks/memory_carry/scenes_handoff.py`: 12 scenes with `first`, `continue` (the N0/S
   line), and checks `task`, `fact`, `decision`, `intact`, and the key phrases for C and D;
   `tests/test_memory_carry_handoff.py` (keep and break results by hand, no give-away).
2. `carry.py`:
   - arms `N0`, `H`, `S` (S shared with F1);
   - the handoff step: read `session_id` from session 1's `init` event, run
     `claude -p --resume <id> "<request>"` with H's settings and caps, keep its stream as
     `handoff.jsonl` and its result text as `handoff.txt`, add its cost to H's row;
   - session 2 of H takes `handoff.txt` as its prompt;
   - the total-cap check counts 3 calls for H;
   - per-row tokens from the result event's `usage`.
3. `analyze.py`: triples; Tango's score interval for paired proportions, with a test against a
   published worked example; McNemar S vs N0; per-arm cost and token medians.
4. Launchers `f2-pilot.cmd`, `f2-sonnet.cmd` and `f2-opus.cmd` with sha256 in the sealing
   commit, the pinned Claude Code first on PATH.
5. To check during the pilot: that `--resume` with `-p`, `--settings` and `stream-json` resumes
   session 1 in the pinned Claude Code, and that the resumed turn reports its own
   `total_cost_usd` **[both unverified]**.

## Commands (proposed; the flags in brackets do not exist yet)

    "%PY%" benchmarks\memory_carry\carry.py --out "%TEMP%\f2-dry" --models sonnet --scenes [handoff] --arms N0,H,S --repeats 1 --dry
    "%PY%" benchmarks\memory_carry\carry.py --out "%OUT%\f2-pilot" --models sonnet --scenes [handoff-pilot] --arms N0,H,S --repeats 1 --total-cap 11.5
    "%PY%" benchmarks\memory_carry\carry.py --out "%OUT%\f2-sonnet" --models sonnet --scenes [handoff] --arms N0,H,S --repeats 4 [--first-repeat 1] --total-cap 109
    "%PY%" benchmarks\memory_carry\carry.py --out "%OUT%\f2-opus" --models opus --scenes [handoff] --arms N0,H,S --repeats 2 [--first-repeat 1] --total-cap 106
    "%PY%" benchmarks\memory_carry\analyze.py "%OUT%\f2-sonnet" --a S --b H [--noninferior 0.125]
    "%PY%" benchmarks\memory_carry\analyze.py "%OUT%\f2-sonnet" --a S --b N0

## Checks before launch (all free, except the pilot)

1. to 6. As in F1 (worktree, `PYTHONPATH`, Jev and `httpx`, S settings against
   `install --memory`, Claude Code version, dry run).
7. The dry run prints, per triple, the three arms and H's handoff step.
8. The pilot ran and the owner read it: handoff captured in all 4 H triples, checks behaving.
9. No other batch is on the subscription. F1 and F2 together are up to about 440 USD at list
   price if every cell runs.

## What is not known yet

- How long and how good the model's own handoffs are, and whether they carry constraints said
  in passing.
- Whether S's touch delivers "what was next" early enough with a prompt that names no file.
- Two-step session costs (assumed 1.5 times carry's) and handoff turn costs (assumed 0.3).
- Whether N0 has room: a strong model might find step 2 from the code and git log alone.
- Headless only. In real use the person reads the handoff and sometimes edits it. Here it is
  pasted as is.

## Open questions for the owner

1. **The request's wording.** Your real request is in Spanish ("dame un prompt para continuar en
   una sesion limpia"). Use that, or an English translation to match the scenes?
2. **Which N** (F1, question 1): your setup or a clean user. It matters more here, since your
   global `CLAUDE.md` and skills may shape how handoffs are written.
3. **Test v8.1 as is?** The v5 prompt gate likely holds back session 1's record at a "continue"
   prompt. Test as it ships, or add a "continue" path first and test that?
4. **A fourth arm, S+H?** It answers whether S adds anything on top of the ritual, for about a
   third more cost.
5. **The margin:** 12.5 points, as proposed, or another?
6. **Budget:** pilot 7.4 USD; Sonnet 89 USD (48 triples); Opus 84 USD (24 triples, direction
   only) or 168 USD (48 triples, confirmatory). Which, and after F1's gate or before?
