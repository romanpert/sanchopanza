# F1. Memory on frontier models: does Claude Code keep what the person said? (DRAFT, 2026-10-05)

**Draft. Not sealed, not committed, nothing launched.** It becomes a prereg only when the owner
has answered the open questions at the end, the engineering below is done and tested, and a
commit adds its sha256. Every number marked **[unverified]** was not checked against a file.

## The question

The owner asks: is Claude Code alone better or worse than Claude Code with sanchopanza, on the
models people actually use? Here that means Sonnet 5.5 (`claude-sonnet-5-5`), the minimum, and
Opus 5.5 (`claude-opus-5-5`). No Haiku. F1 asks it for correctness: is the fact kept. F2
(`prereg-f2-handoff.md`) asks it for the owner's handoff ritual.

## Why

1. **Verdicts move between models.** In the cross-model record, about 5 of 14 mechanisms changed
   verdict from one model to another (count from the caller, not recounted here **[unverified]**).
   The reasons seen:
   - headroom: the stronger model does not fail, so there is nothing to fix;
   - the weaker model cannot use the help (Haiku broke 5 of 16 facts it was given);
   - tool-use style: Sonnet 5.5 edits through Bash, which the file hooks see differently.
2. **Memory carry, v6.2** (`docs/results/2026-10-02-memory-carry/README.md`):
   - Sonnet 5.5: M 23/24 against N 14/24, p = 0.002. Confirmed.
   - Opus 5.5: M 16/16 against N 14/16, p = 0.25. No room.
   - Opus uses its own auto memory (saved in 7 of 32 first sessions); Sonnet did not (0 of 48).
   - So on Opus the carry scenes do not tell N and S apart. New scenes are needed, where a
     frontier model actually fails.
3. **The maintainer's real sessions** (122 Opus 5.5 sessions, 464 user turns, 2026-09-20 to
   2026-10-05; counts from the caller):
   - Cross-session failures: about 1.3 per 100 turns.
   - Most are **durable preferences or principles** said again in a later session: "max-capability
     access", "decide with evidence, don't escalate", "use the decision model instead of fixed
     rules".
   - Often a **stale memory entry** contradicted the newer statement.
   - Lost task facts were rare.
   - The label file (`~/.cache/sanchopanza/memory-real/headroom-2026-10-05/labels.jsonl`,
     private) has 65 labelled turns from 51 sessions. As I read its notes, 7 are cross-session
     failures. In 6 of those 7 the information was at least partly in the repository or in a
     memory file (`inferable`: 2 yes, 4 partial, 1 no). So the real failure is often **use and
     precedence**, not delivery.
4. The carry scenes test task facts said in passing ("finance's macro reads this CSV by column
   position"). The real failures are mostly of another kind. F1 builds three scene families
   that match what was seen.

## Arms

- **N, Claude Code as a user has it.** Its native auto memory on (the default). No sanchopanza.
  The question of *which* user settings load is open (question 1 below):
  - every earlier carry run loaded the maintainer's own user settings in all arms. Checked in
    `gen-opus/columns-opus-N-0/session-1.jsonl`: the `init` event lists 5 MCP servers, 21
    plugins, 119 skills, and 5 `SessionStart:startup` hooks fired, with `--settings "{}"`;
  - whether `~/.claude/CLAUDE.md` loaded is not shown in the stream **[unverified]**, but it
    normally does. That file states rules (immutability, no hardcoded values) that a scene must
    not reuse.
- **S, sanchopanza as a user installs it.** v8.1 at e4a3ec1 (code 1019f8b; `src/` has not changed
  between e4a3ec1 and a83929f, checked with `git log e4a3ec1..HEAD -- src`). What
  `sanchopanza install --memory` writes (printed, not written, on 2026-10-05 against a scratch
  path):
  - the Guardian hook (`sanchopanza hook`): PreToolUse on
    `Agent|Bash|PowerShell|Task|WebSearch|...`, PostToolUse on `Agent|Task`;
  - the compaction guard (`--guard` is on by default): PreCompact, SessionStart `compact`,
    PostToolUse `Bash`;
  - memory: UserPromptSubmit, Stop, SessionEnd, SessionStart, and PostToolUse on
    `Read|Edit|MultiEdit|Write|NotebookEdit|Bash|PowerShell`;
  - env: `SANCHOPANZA_CONTEXT_BUDGET=160000`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000`,
    `SANCHOPANZA_GUARD_PROFILE=coding`;
  - `find_in_repo` in the project's `.mcp.json`, approved in `enabledMcpjsonServers`;
  - the `sanchopanza-code` skill beside the settings.
  - Standing rules are on by default (`memory_rules.rules_on()` reads `MEMORY_RULES`, default
    `on`). So S is carry's arm V plus the Guardian, the guard, `find_in_repo`, the skill and the
    context budget.
  - The decider is Jev through `TYPESAFE_API_KEY`. As in carry, the key reaches only the hooks,
    never the agent's shell. A real user's key sits in their environment; this is a deliberate
    difference.
  - Decoys: S starts with 7 standing rules of other scenes in its store, as V did
    (`carry.decoys`, `carry.said_while`). A project worked on for weeks carries unrelated rules;
    an empty store would hide false sends-back. Open question 3.
- Both arms: same prompts, tools (`Bash, Read, Edit, Write, Glob, Grep`), model, caps, and the
  same pinned Claude Code (question 2).

## Scene families (new; none exists yet)

Every scene follows carry's rules (`scenes.py` docstring): nothing in the repository or in the
last session's prompt states the fact; each check is tested on a hand-written result that keeps
the fact and one that breaks it; checks are Python run in the repository, exit 0 when the fact
holds. Below are sketches, to be written and tested before sealing. Each family has 8 scenes.

### (i) Principles: a working preference, a different task later (`p_*`, 2 sessions)

Session 1 does a small task, and the person states a durable preference about how work is done
in this project. It is not inferable from the repository. Session 2, a new session, gets a task
in another file where the preference applies.

| scene | said in session 1 (paraphrase) | session 2 task | `fact` check |
|---|---|---|---|
| `p_decide` | judgments go through `judge()` in `app/judge.py`, never our own cutoffs | flag spam reviews in `app/reviews.py` | a patched `judge` is called; no numeric cutoff decides alone |
| `p_open` | fetchers are full power by default: no robots.txt, no rate limit unless a flag asks | write `app/fetch_prices.py` | default call makes no robots.txt request and no `time.sleep` (patched to raise) |
| `p_noask` | when a choice is ambiguous, pick one you can defend and log it in `DECISIONS.md`; don't stop to ask | an ambiguous change to a date importer | task check passes and `DECISIONS.md` gained a line |
| `p_loud` | never swallow errors: no fallback to a default value, a failure raises | make `app/rates.py` work when the cache file is missing | with cache and source both failing, the call raises |
| `p_es` | messages to users are in Spanish; code and logs in English | reject passwords under 12 characters in `app/signup.py` | the error text matches a fixed Spanish pattern (e.g. `contrase`, `caracter`) |
| `p_flag` | new behaviour ships behind a `FEATURE_*` env flag, off by default | a discount over 100 in `app/pricing.py` | unset: price unchanged; with the flag the code reads set: discount applied |
| `p_json` | every CLI here prints JSON on stdout, never prose | a totals command in `app/report.py` | stdout parses as JSON |
| `p_owner` | one more, written to match a real failure seen (to choose) | | |

`p_decide`, `p_open` and `p_noask` are written to mirror the three observed preferences. None
may restate a rule of the maintainer's global `CLAUDE.md` while those settings load.

### (ii) Stale: an earlier statement, a newer one that contradicts it (`u_*`, 3 sessions)

Session 1 states rule A while doing a task. Session 1' (a new session, another small task)
states A', which replaces A ("we changed this: ..."). Session 2 gets a task where A, A' and the
model's default all give different code. **The newer must win.**

- The check is three-way: `fact` (A' holds), `stale` (A holds) and neither (the default). The
  primary uses `fact`; the three-way split is reported.
- Sketches: `u_time` (naive ISO UTC, then epoch milliseconds; the default is aware ISO);
  `u_sep` (` | ` fields, then JSON lines); `u_money` (float euros, then integer cents);
  `u_cols` (fixed column order, then columns sorted by name for the new loader); `u_prefix`
  (bare env names, then `SHOP_` prefix); `u_ids` (zero-padded ids, then UUID strings); `u_lang`
  (English errors, then Spanish); `u_page` (offset and limit, then cursor `after`).
- **What S does here, from the code.** v8.1 has no supersession: `memory_rules.py` keeps both
  rules and gives up to 8, newest first (`GIVE_MAX`, `HEADER` says "newest first"). And the
  audit at Stop holds the diff against every stored rule the request did not state, so a diff
  that follows A' can be judged to break A and **sent back quoting the stale rule**. That is the
  failure the real sessions showed, built into the product. A send-back by A counts as false.

### (iii) Parallel: a fact said in another session of the same project (`q_*`, 3 sessions)

Session 1a starts a line of work. Session 1b, another session of the same project, works on
something else, and the person states fact F in passing. Session 2 continues 1a's line ("go on
with the orders export from earlier") and needs F.

- To save engineering, F, its session-1b prompt and its checks are the 8 cross-file scenes
  (`scenes_cross.py`, `x_camel` v2), already tested. New: session 1a and session 2's prompt.
- Two variants, 4 scenes each:
  - **same checkout:** 1a, 1b and 2 run in one folder;
  - **sibling worktree:** 1b runs in a `git worktree` of the same repository, as the maintainer
    works.
- 1b ends before 2 starts. Truly concurrent sessions are left out (not deterministic).
- **What S does here, from the code.** The store is keyed by the transcript's folder
  (`memory_hook.store_for`), which Claude Code names from the working directory. A sibling
  worktree has another folder, so **S has an empty store in session 2 of the worktree variant**.
  Claude Code's docs say auto memory is shared by all worktrees of one repository
  **[unverified here]**. If both hold, N can win the worktree variant by design.

## Headroom gate (run first, N only)

The comparison is sealed only where Claude Code alone breaks the fact often enough to leave room.

- **Run:** N only, all 24 scenes, repetition 0, on Sonnet 5.5 and on Opus 5.5. 64 sessions per
  model (8 x 2 + 8 x 3 + 8 x 3).
- **Rule:** a family enters the comparison on a model if N breaks its fact in **at least 3 of
  its 8 scenes** (37.5 %).
- **What counts as a break (decided 2026-10-05 by session 95, after review).** The fact not kept
  **and** the task done, or the scene has no task check. A session that did not do the task
  did not keep or break anything the scene measures. The gate table reports both counts per
  family and model: every fact not kept, and those with the task done. Only the second decides.
  Planned scenes come from `carry.SETS`. A scene missing or NOT RUN is listed. A family with
  fewer than 8 scenes run and fewer than 3 breaks is `incomplete`, not `fail`.
- **Why 3 of 8.** The full run has 24 pairs per family (8 scenes x 3 repetitions). If S breaks
  5 % of pairs, a one-sided exact McNemar at 0.05 has this power (4,000 simulated runs,
  independent pairs; "clustered" puts the breaks in a few scenes, as seen on Haiku):

  | N's break rate | power, independent | power, clustered | S breaks 10 % |
  |---|---|---|---|
  | 0.25 (2 of 8) | 0.43 | 0.45 | 0.23 |
  | 0.375 (3 of 8) | 0.80 | 0.71 | 0.60 |
  | 0.50 (4 of 8) | 0.97 | 0.91 | 0.89 |

  At 2 of 8 the run would most likely end without a verdict, at 19-54 USD per cell. 3 of 8 is
  the lowest rate where it should not. The gate's own estimate is noisy: 3 of 8 has a 95 %
  interval of about 0.09-0.76.
- **The gate selects families, not scenes.** A family that passes runs all 8 scenes.
  Keeping only the scenes N broke would select on noise and inflate N's later break rate
  (regression to the mean). Open question 4.
- **The gate's rows are not reused** as data for the comparison. The full run uses fresh
  repetitions 1-3.
- **Reported in any case:** N's break rate per family and model. That alone answers part of the
  owner's question: where N never breaks, S cannot make the model better there, only cost more
  or harm.

## Full run (after the gate, per family that passes, per model)

A pair is one scene at one repetition, run in N and in S.

| cell | pairs | sessions | expected | `--total-cap` |
|---|---|---|---|---|
| Sonnet, family (i) | 24 | 96 | 19.2 USD | 25 USD |
| Sonnet, family (ii) or (iii), each | 24 | 144 | 28.7 USD | 36.5 USD |
| Opus, family (i) | 24 | 96 | 36.3 USD | 46.5 USD |
| Opus, family (ii) or (iii), each | 24 | 144 | 54.4 USD | 68.5 USD |
| **all six cells** | 144 | 768 | **221.8 USD** | |

## Cost per session, and how it was computed

From the runs' own `carry.json` (sum of `first.cost` + `second.cost`, which are the sessions'
`total_cost_usd` at list price; the subscription pays):

| run | model | sessions | USD | USD per session | max session |
|---|---|---|---|---|---|
| `v8-cross` | Sonnet 5.5 | 96 | 17.307 | 0.180 | 0.249 |
| `confirm` | Sonnet 5.5 | 64 | 12.079 | 0.189 | 0.294 |
| `gen-opus` | Opus 5.5 | 64 | 22.971 | **0.359** | **0.538** |

- **Sonnet: 0.19 USD per session.** **Opus: 0.36 USD per session.** Opus's run is
  `~/.cache/sanchopanza/memory-carry/gen-opus/carry.json` (found; N 0.371, M 0.347 per session).
- **S costs 10 % more than N** in these estimates **[assumption]**. V cost the same as M on
  Sonnet (0.98), but S adds the Guardian, the guard, `find_in_repo` and the skill, never
  measured together on these scenes.
- Sessions of family (ii) and (iii) are assumed to cost as much as carry's **[assumption]**.
- The Jev decisions are not in these figures. At 29 millionths of a dollar each, even 100 per
  session is 0.003 USD **[the per-session count with the Guardian on is unverified]**.

**Headroom gate:** Sonnet 64 x 0.19 = 12.2 USD; Opus 64 x 0.36 = 23.0 USD; **35.2 USD**.

## Caps, and how they are enforced

- **Per session:** `--max-budget-usd` 0.60 on Sonnet (as before) and **1.00 on Opus**.
  gen-opus's costliest session was 0.538, too close to 0.60 once S adds turns.
- **Per run:** `--total-cap` in `carry.py`. The runner stops before a pair if what was spent plus
  one pair's sessions at the per-session cap could pass it.
  - Today it checks `2 * CALL_CAP` (`carry.py`, `run_plan`), which is wrong for 3-session
    scenes. Engineering task 4.
  - The caps above are about 1.2 x expected plus one pair at the per-session cap.
- **Headroom gate caps:** Sonnet `--total-cap 16.5` (stops past 14.70, 21 % above expected);
  Opus `--total-cap 31` (stops past 28.00, 22 % above).
- **Usage limit:** stops the run (`limit_hit`).
- **Send-backs:** at most one per Stop (`stop_hook_active`).
- **No API key** in the agent's environment (`carry.environment`).
- **Sequence:** the launcher runs the gate, writes its table, and ends. The full run waits for
  the owner, who sees the gate's result and the cells it opens.

## Criteria (fixed sequence; each is confirmatory only if the one before is met)

1. **Sonnet, pooled.** Over every family that passed the gate on Sonnet, S keeps the fact in more
   pairs than N: one-sided exact McNemar, p < 0.05.
2. **Opus, pooled.** The same on Opus. If 1 is not met, direction only. If no family passed the
   gate on Opus, this reads "no room on Opus", not a failure.
3. **No harm, per model, over every pair run:**
   - tests: S passes no more than 3 per 24 pairs fewer than N (v8's margin, 2 per 16);
   - task: the same, over pairs with a task check;
   - false sends-back: S second sessions sent back by a rule other than the scene's own (a decoy,
     or in family (ii) the stale rule A) at most 5 % of S's second sessions (v8's rate, 2 of 40);
   - cost: the paired median S/N at most 1.15 **[proposal]**. On Opus that is about 5 cents a
     session.
4. **Reported, not criteria:**
   - per family and model, the McNemar and the counts;
   - family (ii): the three-way split (newer, stale, neither) per arm;
   - family (iii): the two variants apart, and whether S's store was empty in session 2;
   - every send-back, read by hand and quoted, own or not;
   - sessions where the decider failed (from `hook-log.jsonl`);
   - what Claude Code's own auto memory saved, per arm;
   - sessions that called a subagent, and on which model.

## Power

- Per cell: the table in the gate section. 24 pairs at N's break rate 0.375 give about 0.8 if S
  breaks 5 %.
- Pooled over cells, power rises with the number of cells that pass.
- **Why it is approximate.** It assumes independent pairs. Repetitions of a scene are
  correlated, and breaks cluster in a few scenes, so the effective sample is smaller.

## Exclusions

- A usage limit, the run's cap, or a session that ended before its result: NOT RUN. Nothing is
  retried, except a pair cut by a runner bug, which runs again whole (`--continue`) and goes in
  an amendment.
- **New:** a session stopped by its own `--max-budget-usd` counts as run, with its checks as found.
  Excluding it would hide a cost-driven failure, and S costs more. Engineering task 4 records
  the result's `subtype`. Whether `claude -p` exits non-zero then is **[unverified]**: if it does,
  `analyze.ran` would drop it today.
- A pair is NOT RUN if any `init` event shows another model or Claude Code version.

## Engineering still needed (in a new branch and worktree)

Nothing goes in `sanchopanza-memoria-v8` while `v81h-cross` runs from it.

1. `benchmarks/memory_carry/scenes_principle.py`, family (i), 8 scenes; test file
   `tests/test_memory_carry_principle.py` (keep and break results by hand, no give-away).
2. `scenes_stale.py`, family (ii): `first`, `between` (session 1'), `second`, and checks `fact`
   and `stale`; `tests/test_memory_carry_stale.py`, including a result that applies A.
3. `scenes_parallel.py`, family (iii): from `scenes_cross.CROSS`, add `thread` (session 1a), the
   continuing `second` prompt and `worktree: bool`; `tests/test_memory_carry_parallel.py`.
4. `carry.py`:
   - a scene's sessions as a list (2 or 3);
   - `MODELS["opus"] = "claude-opus-5-5"` (it was added in bef3f16 for gen-opus and is not in
     `MODELS` at a83929f);
   - per-model `CALL_CAP` (Opus 1.00);
   - the total-cap check uses the pair's session count;
   - arm `S`: the settings block from `install.plan(..., memory=True, budget=DEFAULT_BUDGET,
     find=True, profile=None)`, the `.mcp.json` entry and the skill in the scene's repository,
     decoys seeded as for V;
   - worktree builder (`git worktree add`) for family (iii);
   - `native_memory` reads from the config folder actually used (question 1);
   - record the result event's `subtype`.
5. `carry_hook.py`: take the subcommand (`hook`, `guard-hook`, `memory-hook`, `find-mcp`). Every
   S entry must run the worktree's code: the `sanchopanza` on PATH is the venv's editable
   install, `apps/sanchopanza/src` (prereg-v81-haiku, check 2).
6. `analyze.py`: pooling over sets, the three-way split, and the gate table (N only).
7. `sendbacks.py`: glob `*-S-*`; label a send-back by the stale rule A as false.
8. Launchers `f1-gate-run.cmd` and `f1-full-run.cmd`, with their sha256 in the sealing commit,
   pinned Claude Code first on PATH, `DISABLE_AUTOUPDATER=1`.

## Commands (proposed; the flags in brackets do not exist yet)

Dry run of the gate (calls nothing; builds 24 repositories per model, prints 24 rows):

    "%PY%" benchmarks\memory_carry\carry.py --out "%TEMP%\f1-dry\gate" --models sonnet,opus --scenes [principle,stale,parallel] --arms N --repeats 1 --dry

Gate, per model:

    "%PY%" benchmarks\memory_carry\carry.py --out "%OUT%\f1-gate-sonnet" --models sonnet --scenes [principle,stale,parallel] --arms N --repeats 1 --total-cap 16.5
    "%PY%" benchmarks\memory_carry\carry.py --out "%OUT%\f1-gate-opus" --models opus --scenes [principle,stale,parallel] --arms N --repeats 1 --total-cap 31

Full run, per open cell, repetitions 1-3 [`--first-repeat 1`]:

    "%PY%" benchmarks\memory_carry\carry.py --out "%OUT%\f1-<model>-<family>" --models <model> --scenes <family> --arms N,S --repeats 3 [--first-repeat 1] --total-cap <cap>

Analysis:

    "%PY%" benchmarks\memory_carry\analyze.py "%OUT%\f1-sonnet-*" --a S --b N
    "%PY%" benchmarks\memory_carry\sendbacks.py "%OUT%\f1-sonnet-*" "%OUT%\f1-opus-*"

## Checks before launch (all free)

1. The worktree's HEAD is the sealing commit; nothing tracked is modified.
2. With `PYTHONPATH=<worktree>\src`, `import sanchopanza` resolves under that worktree.
3. With a dummy `TYPESAFE_API_KEY`, `decider_from_env` returns `JevDecider`; `httpx` imports.
4. The S settings a dry run writes match `sanchopanza install --memory` printed for the same
   path, entry for entry, except the commands, which point at the launcher.
5. `claude --version`, with the launcher's PATH, prints the pinned version.
6. The dry run builds and prints the expected rows, worktrees included.
7. No other batch is using the subscription. The weekly limit is shared. 35 USD for the gate and
   up to 222 USD for the full run, at list price, is a large part of a week **[the weekly
   allowance in USD is unverified]**.

## What is not known yet

- Whether frontier models break these new facts at all. The gate exists for that.
- What S costs with the Guardian, the guard and `find_in_repo` on together.
- Whether Opus 5.5 obeys a standing rule it is given as reliably as Sonnet did (16/16 on carry
  suggests yes, but there it rarely needed one).
- Whether a stale-rule send-back makes the agent revert to the old rule.
- Whether Claude Code's auto memory is shared across worktrees in the pinned version.
- Headless `claude -p` only. Interactive sessions may save auto memory more often.

## Open questions for the owner

1. **Which N.** The maintainer's own setup (21 plugins, 119 skills, 5 MCP servers, global
   `CLAUDE.md`), as every earlier carry run had? Or a clean user: a fresh `CLAUDE_CONFIG_DIR`
   with only the subscription's token (`claude setup-token`)? The second is closer to "people".
   It breaks comparability with earlier runs, and that it works headless here is
   **[unverified]**.
2. **Which Claude Code.** Keep 2.1.287 pinned (as v8.1 Haiku), or pin the current release at
   sealing?
3. **S's store at the start:** 7 decoys (as V), or empty (a fresh install)?
4. **Gate:** families (as proposed) or scenes? And is 3 of 8 the right bar?
5. **Fix before testing?** Two gaps are visible in the code: no supersession (family ii) and a
   store per worktree (family iii). Test v8.1 as it ships, which answers "is it better today",
   or fix first, which tests a version that does not ship yet?
6. **Budget.** Gate 35 USD. Full run up to 222 USD if all six cells open. Fund all of it,
   Sonnet only first, or 2 repetitions (16 pairs, power about 0.55 at N's rate 0.375)?
7. Where N never breaks (likely on Opus), run a small N-against-S check for harm and cost only
   (8 pairs per family, about 12 USD for family (i) and 18 USD for (ii) or (iii) on Opus)?
