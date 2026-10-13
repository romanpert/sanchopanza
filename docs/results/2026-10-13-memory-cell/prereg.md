# Memory cell: N against S on Sonnet 5.5, F1 family (iii) parallel. Written before its data (2026-10-13)

Sealed by the commit named under "Sealing". It concretes the draft `prereg-f1-correctness.md`
(docs/results/2026-10-05-memory-frontier/) for the **one cell the headroom gate opened**
(`gate-result.md`: N broke 3 of 8 family (iii) facts on Sonnet 5.5; every other family and model
failed the gate and is not run). The owner approved running this cell on the subscription on
2026-10-13, with the draft's cap for it: `--total-cap 36.5`, and on the same day, through the
coordinating session, the definition of S below (default install plus `--memory`, project scope,
Jev as decider, 7 decoys). No session of this cell has run. Two independent checks of this text
against the code (subagents, 2026-10-13, no paid call) found every number and flag in agreement;
their findings on wording and on four code gaps were fixed before sealing (`carry_s`: an error in
the memory hook now counts as S not running, the Guardian's code-only decisions are not counted as
Jev's, every command is asserted rewired; `carry`: a hung check fails instead of ending the run,
the arm order rotates by repetition too; `cell`: never-started pairs are listed, the fact-alone
criterion below).

## Question and hypothesis

Does Claude Code with sanchopanza installed (S) keep, more often than clean Claude Code (N), a
fact the person said in another session of the same project, when a later session continues a
line of work that needs it? Sonnet 5.5 (`claude-sonnet-5-5`), the 8 scenes of family (iii).

- **H1:** S breaks the fact in fewer pairs than N (one-sided exact McNemar on the discordant pairs,
  p < 0.05).
- H0: no difference. The other direction (S breaks more) is reported, never hidden.

## Arms

Both arms: the same scenes, prompts, model, tools (`--allowedTools Bash Read Edit Write Glob
Grep`), `--settings "{}"`, default permission mode, `--max-budget-usd 0.60` per session, a 900 s
timeout per session, Claude Code 2.1.287 pinned, `claude -p` with `--output-format stream-json
--verbose`, each session new (no `--resume`). Both are a **clean user** exactly as in the gate
(`carry.py --clean-user`): a fresh `CLAUDE_CONFIG_DIR` per pair, kept across that pair's sessions,
signed in with the subscription's OAuth token only; no plugin, skill, MCP server, hook or
`CLAUDE.md` of the maintainer; run folder `C:\sp-runs\memory-carry`, outside the home folder
(`refuse_unclean`). Claude Code's own auto memory is on in both arms (its default).

**N** is the gate's arm, unchanged.

**S** is N plus sanchopanza as a user installs it into the project:

    sanchopanza install --scope project --memory --write

run in the scene's repository before its start commit (`carry_s.install`), from `src/` at the
sealing commit. Every flag but `--scope project` and `--memory` is at its default on that
commit. What it writes,
as printed by the dry run of 2026-10-13 (`install.txt` of each S pair):

- `.claude/settings.json`:
  - the Guardian (`sanchopanza hook`): PreToolUse on
    `Agent|Bash|PowerShell|Task|WebSearch|bash|execute|run_command|shell`, PostToolUse on
    `Agent|Task`;
  - the compaction guard (`sanchopanza guard-hook`): PreCompact `manual|auto`, SessionStart
    `compact` (6 parts), PostToolUse `Bash`;
  - memory (`sanchopanza memory-hook`, v8.3: standing rules on by default, supersession, one store
    per repository shared by its worktrees): UserPromptSubmit, Stop, SessionEnd, SessionStart, and
    PostToolUse on `Read|Edit|MultiEdit|Write|NotebookEdit|Bash|PowerShell`;
  - `env`: `SANCHOPANZA_CONTEXT_BUDGET=160000`, `CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000`,
    `SANCHOPANZA_GUARD_PROFILE=coding`;
  - `enabledMcpjsonServers: ["sanchopanza"]`;
- `.mcp.json`: the `sanchopanza` server (`find-mcp`, `find_in_repo`, `alwaysLoad`);
- `.claude/skills/sanchopanza-code/SKILL.md`.

The runner then puts each `sanchopanza <sub>` command (hooks and server) behind
`benchmarks/memory_carry/carry_hook.py <pair> <keyfile> sub <sub>`, which runs `python -m
sanchopanza <sub>` with `PYTHONPATH` the sealed worktree's `src`, each piece of state in the pair's
folder (memory store `store/`, its log `hook-log.jsonl`, journal `journal.jsonl`, guard `guard/`,
funds breaker `funds/`), the TypeSafe key, and **without** the OAuth token. Nothing else in the
files changes; `tests/test_memory_carry_cell.py` checks that the rewired settings equal a plain
`sanchopanza install` entry for entry except the command lines. The files go into the start
commit, so the worktree session (1b) has them too. The as-written and rewired copies are kept in
each S pair's `install/`.

- **Decider: Jev.** No `SANCHOPANZA_PROVIDER` is set; with `TYPESAFE_API_KEY` in the hooks'
  environment `decider_from_env` builds Jev, as for a user whose key is in their environment. The
  key is in the environment of the hooks and the find server only, never in the agent's. It sits
  in `typesafe.key` in the run folder, whose path the committed `.claude/settings.json` names, so
  the agent could read it; it is not expected to. Jev's cost is counted in the run's spend and in
  S's cost.
- **What S's repository shows the agent and N's does not:** the installed files, whose rewired
  commands name `benchmarks/memory_carry/carry_hook.py` and the pair's folder (`...-S-<rep>`).
  That is inherent to a project install behind a launcher; declared, not removed.
- **Decoys:** S's store starts with the 7 standing rules of other scenes that V had in v7 and v8
  (`carry.seed`, `carry.decoys`), dated 2026-09-21, as a project worked on for weeks carries
  rules unrelated to the task. They can only cost S (false send-backs, longer context); they never
  state the scene's fact or a near one (`carry.SAME`, tested).

### Two declared choices about what "S" is

1. **`--memory` is on although it is not a default.** On main, `sanchopanza install` with no
   flags wires no memory at all (`cli.py`: "--memory ... not measured yet, so off by default").
   This cell measures memory; S as the bare default install would carry no mechanism that can
   keep a fact across sessions, and its result would be known before running. S is therefore the
   default install plus the one flag this axis is about, as the draft (`prereg-f1-correctness.md`,
   "Arms") and the gate's decision 5 (the v8.1 memory gaps fixed before S is sealed) intended. The
   owner may read the cell as "default + memory", not as "bare default".
2. **`--scope project`**, not the default `user` scope. The user scope writes to
   `~/.claude/settings.json` (not the pair's clean configuration folder) and, by design, does not
   register `find_in_repo` (no project `.mcp.json`). Every earlier S run (adopt D, h2h, the long
   bench) installed with `--scope project`; so does this one.

## Scenes and plan

The 8 scenes of `carry.SETS["parallel"]` (`scenes_parallel.py`), unchanged since the gate:
`q_tz`, `q_cents`, `q_print`, `q_camel` (1b in the same checkout) and `q_zeros`, `q_stdlib`,
`q_prefix`, `q_trash` (1b in a sibling `git worktree`). Three sessions per pair: 1a (`thread`)
starts a module, 1b (`first`) does another task and states the fact in passing, 2 (`second`) goes
on with 1a's module and needs the fact. After session 2: the repository's tests, `task` and `fact`.

- **Repetitions 1, 2 and 3** (`--first-repeat 1 --repeats 3`). The gate's repetition 0 is not
  reused. 8 scenes x 3 repetitions = **24 pairs**, 48 arm runs, **144 sessions**.
- **Arms interleaved by pair** (`--rotate`): each pair's N and S run back to back; which arm
  goes first alternates from pair to pair and flips again from one repetition to the next, so 12
  pairs start with N, 12 with S, and every scene runs each order at least once (`build_plan`,
  tested).

## Measures

- **Break** (the gate's definition, unchanged): the fact not kept **and** the task not failed
  (`analyze.broke`). A session that did not do the task did not keep or break what the scene
  measures. Because this forgives a failed task, criterion 2 below also asks the comparison to
  hold on the fact alone, a failed task counting as not kept: S cannot win by failing tasks.
- Reported beside it: every fact not kept, tests passing, task passing, per arm.
- **Cost:** per arm run, the sessions' own `total_cost_usd` (list price; the subscription pays)
  plus, for S, the pair's Jev decisions (`cost_usd` in its journal).

## Decision rule (fixed; `benchmarks/memory_carry/cell.py`)

Over the pairs where both arms ran:

1. **Primary:** one-sided exact McNemar, S better than N on breaks (pairs where N broke and S did
   not, against the reverse): **p < 0.05**.
2. **Fact alone** (`fact_alone`): the same one-sided McNemar on `fact_kept` (a failed task counts
   as not kept), also **p < 0.05**.
3. **No harm, non-inferiority margins fixed now** (`MARGIN = 0.125`: 3 pairs of 24, v8's 2 of 16):
   - tests: S passes in no more than `floor(0.125 x pairs)` fewer pairs than N;
   - task: the same.
4. **False send-backs:** S's last sessions (session 3) sent back by a rule that is not the scene's
   own (a decoy or any other rule S stored), at most `floor(0.05 x pairs)` (1 of 24), from
   `hook-log.jsonl` (`cell.false_sendbacks`). The summary line of `mem-cell-sendbacks.txt` counts
   sessions 2 and 3 and does not decide. Sessions are numbered by memory's logged session starts;
   an S pair whose log does not show exactly 3 is listed (`starts_mismatch`) and read by hand.
5. **Cost:** the median over pairs of S's cost over N's at most **1.15**.

**Verdict:** **"gana"** when 1 to 5 all hold; **"no gana"** otherwise, naming each criterion that
failed; **"sin veredicto"** when fewer than 20 pairs ran (NOT RUN pairs are left out, never
filled). The other one-sided p (`p_a_worse`, S breaks more) is reported whatever it is.
Nothing is pooled with any other cell or model. The metric is not changed after the data.

Reported, never deciding: the counts per arm; the two variants (same checkout, worktree) apart;
a 95 % bootstrap interval of the geometric mean of S/N cost, resampling scenes (10,000, seed
20261013); every break and every send-back by name; what S gave each session (`given`); what
Claude Code's own auto memory saved per arm (`native_after_1`); Jev's decisions and failures per
pair; `init` per session (model, version, `apiKeySource`, MCP servers and their status,
permission mode); S's hook calls that exited non-zero or wrote to stderr (`hook_errors`); the
median per pair of S's wall time over N's (sessions' own seconds); sessions that called a subagent
(read by hand).

### Power

From the draft's simulation (4,000 runs, independent pairs, S breaking 5 %): at N's gate rate of
0.375 the one-sided McNemar has power 0.80 (0.71 if breaks cluster in a few scenes); at 0.25, 0.43.
The gate's 3 of 8 is a noisy, selected estimate (95 % interval 0.09-0.76): regression to the mean
may lower N's rate here, and with it the power. A "no gana" on the primary can therefore mean "no
difference" or "too few breaks to see one"; the counts are reported so the reader can tell.

## NOT RUN and exclusions

A pair (both arms of one scene and repetition) is left out, and listed by name (the 24 planned
pairs come from `carry.SETS["parallel"]` and repetitions 1-3, so a pair never started is listed
too), when either arm:

- hit the usage limit (read from the stream's events, `carry.limited`), which also stops the run;
- had a session time out or end without a result (`cut`);
- had a session whose `init` shows a model other than `claude-sonnet-5-5` or a Claude Code other
  than 2.1.287;
- was never started because the run's cap stopped the plan before it (missing);
- (S only) **did not run as S** (`carry_s`): among the hook calls logged during a session, no
  memory-hook `UserPromptSubmit` that exited 0 without writing to stderr (the hook exits 0 even
  when it fails, and says so on stderr), or a memory-hook error at every `Stop`; a session whose
  `init` shows the `sanchopanza` MCP server not `connected`; or a pair whose decider (decisions
  other than the Guardian's code-only ones) was never asked or failed every time. That pair is
  recorded as cut (`harness: ...`) and **the run stops** (exit 4): the owner decides what
  follows. A row lost from `hooks.jsonl` by two hooks appending at once could stop the run
  falsely; it cannot mislabel a pair.

A session stopped by its own `--max-budget-usd` counts as run, with its checks as found. A hung
check (tests 300 s, a check 120 s) fails instead of ending the run. **Timeout:** a session timeout
stops the run (exit 3) and leaves its pair without a row; the launcher then resumes the run
**once** with `--continue`, which counts the cut pair's spend and runs that pair again whole. A
second stop of any kind is final. Nothing else is retried; a pair with a row (a harness cut among
them) is never run again.

## Caps and spend

- **Per session:** `--max-budget-usd 0.60` (Sonnet, `carry.CALL_CAPS`).
- **Per run, in code:** `--total-cap 36.5` USD, **Jev included**, held as a reserve check before
  each arm run. `--max-budget-usd` is checked by Claude Code between turns, so one session can
  pass 0.60 by a turn; a timed-out session has no result and its cost is unknown (counted as 0).
  The reserve leaves 1.80-1.95 USD of room for that. Before each arm run the
  runner reserves its 3 sessions at 0.60 plus, for S, 0.05 of Jev per session
  (`carry.reserve_of`), and stops if what was spent plus the reserve would pass the cap: it stops
  once more than 34.70 USD (before an N run) or 34.55 USD (before an S run) is spent. Spent is the
  sessions' own `total_cost_usd`, S's journal decisions and the Jev preflight.
- **Jev preflight:** before any pair (and again if the run resumes), one real Jev decision with
  the run's key
  (`sanchopanza jev-preflight`, a few hundred-thousandths of a dollar); the run refuses (exit 1)
  unless it answers.
- **Usage limit (429, weekly limit):** the run stops at once and the pairs left are NOT RUN. It is
  not retried.
- **Expected:** N from the gate's own family (iii) Sonnet cost, 1.36 USD per 24 sessions (0.057
  per session): 72 x 0.057 = 4.1 USD. S has never been measured with every part on together;
  assumed 1.3 x N **[assumption]**: 5.3 USD. Jev: cents at most. **About 9.5 USD expected**,
  against the draft's 28.7 (from runs that loaded the maintainer's setup, 0.19 USD per session).
  The cap stays at the approved 36.5.

## Run

The launcher `mem-cell-run.cmd` (root of the sealed worktree; sha256 under "Sealing") sets `PY`
to the sanchopanza venv's Python, `OUT=C:\sp-runs\memory-carry`, the pinned Claude Code first on
`PATH` (`%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287`), `PYTHONPATH` to the worktree's
`src` and `DISABLE_AUTOUPDATER=1`; refuses (exit 1) if `mem-cell-sonnet-parallel\carry.json`
exists and (exit 3) unless `claude --version` begins with `2.1.287 `; writes HEAD, the tracked
changes, `sanchopanza.__file__`, the `claude` path and version to `mem-cell-run.status`; and runs

    "%PY%" -u benchmarks\memory_carry\carry.py --out "%RUN%" --models sonnet --scenes parallel --arms N,S --repeats 3 --first-repeat 1 --rotate --clean-user --total-cap 36.5
    "%PY%" benchmarks\memory_carry\cell.py "%RUN%" --a S --b N --scenes parallel --repeats 1,2,3 --model sonnet > "%OUT%\mem-cell-table.json"
    "%PY%" benchmarks\memory_carry\sendbacks.py "%RUN%" > "%OUT%\mem-cell-sendbacks.txt"

with `RUN=C:\sp-runs\memory-carry\mem-cell-sonnet-parallel` (cell.py's stderr goes to
`mem-cell-table.err`); after a timeout (exit 3), the same carry.py command with `--continue`, once.
carry.py exits 0 when the plan ran to its end, 1 when it refused or crashed (the log says which),
2 on the cap or the usage limit, 3 on a session timeout, 4 when S did not run as S. It reads `CLAUDE_CODE_OAUTH_TOKEN` and `TYPESAFE_API_KEY` from the owner's Indagis
`.env` (a WMI process inherits no window variable); the token goes only to the `claude` processes
and is scrubbed from the pair's files if found; the key is written to `typesafe.key` in the run
folder for the hooks and removed when the run ends.

**Launch:** from a detached worktree at the sealing commit
(`git worktree add --detach ../sanchopanza-mem-cell <sealing commit>`), never from the main
checkout, started outside the Claude Code session by WMI with a new process group (CreateFlags
512):

    $s = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{CreateFlags = [uint32]512}
    Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
      CommandLine = 'cmd.exe /c "C:\Users\roman\Desktop\proyectos\apps\sanchopanza-mem-cell\mem-cell-run.cmd"'
      CurrentDirectory = 'C:\Users\roman\Desktop\proyectos\apps\sanchopanza-mem-cell'
      ProcessStartupInformation = $s }

It is watched live (`mem-cell-sonnet-parallel.log`, the status file, the spend printed after each
arm run). A stop by hand kills the whole tree (`taskkill /T /F /PID <cmd.exe>`, so no `claude`,
hook or server process outlives it) and then deletes `typesafe.key` from the run folder, which the
runner's own cleanup did not reach. Any stop is recorded as found.

## Checks before launch (all free)

1. The worktree's HEAD is the sealing commit and nothing tracked is modified.
2. With the launcher's `PYTHONPATH`, `import sanchopanza` resolves under that worktree.
3. `claude --version` with the launcher's `PATH` prints `2.1.287 (Claude Code)`.
4. A dry run of the exact plan (`--dry`, other `--out`) builds 48 repositories (24 S installs, 24
   worktrees) and prints 48 rows, calling nothing.
5. In one S pair of the dry run, each hook and the server answer through the launcher with no key
   (a `SessionStart`, a `UserPromptSubmit`, a `PreToolUse` on Bash, the server's `initialize`),
   and the S settings equal a plain install's except the commands (test).
6. All `tests/test_memory_carry*.py` pass.
7. No other paid batch is running on the subscription (the weekly limit is shared with the
   context and scoreboard sessions); the run folder holds no `carry.json`.

## Sealing

- Launcher `mem-cell-run.cmd`, sha256 `7ed50064986b6646146f74281c0568967b3b7defe992a3d72a94e806ce464106`.
- Code: `benchmarks/memory_carry/` and `src/` as of the sealing commit (`src/` is main's e9500ea,
  untouched on this branch).
- Sealing commit: the commit that adds this file
  (`git log --diff-filter=A -- docs/results/2026-10-13-memory-cell/prereg.md`).
