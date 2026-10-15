# F1 headroom gate: does Claude Code alone break these facts on frontier models? Written before its data (2026-10-05)

Sealed by the commit named under "Sealing". Code: branch `memoria-f1`; the benchmark is that of
9cd5a43 (`benchmarks/memory_carry/`, launcher `f1-gate-run.cmd`; HEAD 84cdd49 adds v8.2 under `src/`, which arm N never loads). This seal covers **only the
headroom gate**: arm N, repetition 0, on Sonnet 5.5 and Opus 5.5. The full N-against-S run of
`prereg-f1-correctness.md` (still a draft) is a later, separate seal, written after the gate's
result is known.

## The question, and why

The owner asks whether Claude Code alone is better or worse than Claude Code with sanchopanza on
the models people use. The owner decided on 2026-10-05: **Sonnet 5.5 is the minimum, and Opus 5.5;
N is a clean user; Haiku is used only to study mechanisms.**

On the earlier carry scenes there is no room on Opus: M kept 16 of 16 against N's 14 of 16
(`docs/results/2026-10-02-memory-carry/README.md`). The maintainer's own cross-session failures
were mostly durable preferences said again later, and older statements contradicting newer ones,
not lost task facts (`prereg-f1-correctness.md`, "Why"). F1 adds three scene families of those
kinds. Before paying for a comparison, the gate asks a narrower question: **does N break these
facts often enough, per family and model, for S to have anything to fix?**

## Decisions on the draft's open questions

1. **N is a clean user** (owner, 2026-10-05). `carry.py --clean-user`:
   - each pair gets a fresh `CLAUDE_CONFIG_DIR` (`<pair>\claude-config`), kept across that pair's
     sessions so Claude Code's own auto memory can carry; no plugins, skills, MCP servers, hooks
     or user `CLAUDE.md`;
   - it signs in with the subscription's OAuth token (`CLAUDE_CODE_OAUTH_TOKEN`, from
     `claude setup-token`; the one already in the `.env` of the owner's agent with its own harness for subscription test
     runs), read by `carry.py` from the launcher's environment or from that `.env`, and passed
     only in the `claude` process's environment. Every `ANTHROPIC_*`, `CLAUDE_CODE_USE_*`, `TYPESAFE_*` and
     `SANCHOPANZA_*` variable is dropped. Each pair's files are scanned for the token at its end
     and scrubbed if found; rows are redacted before they are written;
   - the run folder is `C:\sp-runs\memory-carry`, outside the home folder. Under it, Claude
     Code's upward `CLAUDE.md` search could load the maintainer's `C:\Users\roman\.claude\CLAUDE.md`,
     `C:\Users\roman\.claude\rules\` and `C:\Users\roman\CLAUDE.md` (all three exist).
     `carry.refuse_unclean` refuses to start if any memory file is found above the run folder;
   - permission mode is the default (no `--permission-mode` flag), with
     `--allowedTools Bash Read Edit Write Glob Grep` and `--settings "{}"`.
   This breaks comparability with every earlier carry run, which loaded the maintainer's setup.
2. **Claude Code is pinned at 2.1.287** (session 95), as in the v8.1 Haiku seal, for
   comparability with every earlier carry run. The current release is not tested here. The
   launcher puts `%USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287` first on PATH, sets
   `DISABLE_AUTOUPDATER=1`, and refuses to start (exit 3) unless `claude --version` begins with
   `2.1.287 `. `carry.record_claude` refuses a clean-user run on any other version too
   (`carry.PIN`). The pinned `claude.exe` has sha256 `6d5be51f...d2ff98b4`, the same file as
   the v8.1 seal.
3. **S's store decoys**: not applicable. The gate runs N only.
4. **The gate is by family, 3 of 8** (session 95, after code review). A break counts only when
   the task was done too, or the scene has no task check (every F1 scene has one). Both counts
   are reported: every fact not kept, and the breaks with the task done. Only the second decides.
5. **The two v8.1 gaps** (no supersession for family ii; a store per worktree for family iii) are
   fixed before S is sealed (owner). Not part of this gate: N runs no sanchopanza code.

## Scenes

24 scenes, 8 per family, from `carry.SETS["f1"]`. Every session is a new `claude -p` session in
a fresh git repository; every session but the last is committed; after the last, the
repository's tests and the scene's `task` and `fact` checks run (and `stale` in family ii).

### Family i, principles (`scenes_principle.py`, 2 sessions: `first`, `second`)

| scene | said in session 1 | session 2 task | `fact` passes when |
|---|---|---|---|
| `p_decide` | judgments about a text go through `judge()`, no keyword lists or cutoffs | `is_spam` in `app/reviews.py` | the result follows a patched `judge`, and it is called |
| `p_open` | fetchers run at full power: no robots.txt, no delays unless a flag asks | `app/fetch_prices.py` | no sleep and no robots.txt request on a default call |
| `p_noask` | don't stop to ask; pick, go on, log the choice in `DECISIONS.md` | ambiguous `03/04/2026` dates in `app/dates.py` | `DECISIONS.md` exists and names the date choice |
| `p_dryrun` | a script that changes data does nothing without `--apply` | `scripts/archive_orders.py` | no data changes without `--apply`; with it, the move happens |
| `p_es` | what users read is in Spanish; code and logs in English | short-password error in `app/signup.py` | the message contains `contrase` or `caracter` |
| `p_flag` | new behaviour behind a `FEATURE_*` env flag, off by default | 10 % off over 100 in `app/pricing.py` | unset: no discount; set: discount applied |
| `p_json` | every CLI prints JSON on stdout and nothing else | `python -m app.report data/sales.csv` | stdout parses as JSON |
| `p_signoff` | sign-offs are Marta's, whatever the topic; Dana and Iker don't approve | refunds over 500 ask approval by mail in `app/refunds.py` | the request goes to `marta@example.org` |

### Family ii, stale (`scenes_stale.py`, 3 sessions: `first` says A, `between` says A' that replaces it, `second`)

| scene | A (session 1) | A' (session 1') | session 2 task |
|---|---|---|---|
| `u_time` | timestamps are int epoch seconds | int epoch milliseconds | `created_at` in `app/events.py` |
| `u_sep` | log lines are `key=value` pairs | one JSON object per line | `log_failed_login` in `app/auth.py` |
| `u_money` | amounts to the frontend as `'12.50'` | as `'12,50'` | order total in `app/orders_api.py` |
| `u_delim` | CSV files use `;` | tab-separated | `export_stock` in `app/stock.py` |
| `u_bool` | partner API booleans `'Y'`/`'N'` | integers 1/0 | `in_stock` in `app/partner_api.py` |
| `u_lang` | user-facing text in French | in Portuguese | under-18 error in `app/signup.py` |
| `u_sort` | lists sorted by name, A to Z | by creation date, newest first | `list_projects` in `app/projects.py` |
| `u_date` | user dates as `02/01/2026` | as `2 Jan 2026` | `order_line` in `app/emails.py` |

`fact` passes when A' holds, `stale` when A holds; the row's `carried` is `newer`, `stale` or
`neither`. A break is any `fact` not kept.

### Family iii, parallel (`scenes_parallel.py`, 3 sessions: `thread` 1a, `first` 1b, `second`)

Session 1a starts a module "to build on in a later session"; 1b, another session, does a small
task and states the fact; session 2 "goes on with" 1a's module and needs the fact. Fact, its
prompt and checks are the cross scenes' (`scenes_cross.py`, `x_camel` v2). In the four
`worktree` scenes, 1b runs in a sibling `git worktree` (`<pair>\repo-wt`, branch `side`); 1a and
2 run in the main checkout.

| scene | where 1b runs | fact | session 2 task |
|---|---|---|---|
| `q_tz` | same checkout | timestamps are naive UTC | `record()` in `app/audit.py` with an ISO time |
| `q_cents` | same checkout | money is integer cents | `shipping_cost` in `app/shipping.py` (4.99 + 1.50/kg) |
| `q_print` | same checkout | never write to stdout | `summary()` in `app/report.py`, with progress |
| `q_camel` | same checkout | API responses use camelCase keys | `profile_response` in `app/profile.py` |
| `q_zeros` | worktree | customer ids keep their leading zeros | `invoice_number` in `app/invoices.py` |
| `q_stdlib` | worktree | standard library only | `load_settings` reading `config.yaml` |
| `q_prefix` | worktree | env variables start with `ACME_` | `send()` in `app/mailer.py` |
| `q_trash` | worktree | never delete; move to `.trash` | `cleanup()` in `app/cleanup.py` |

Each variant holds two of the four cross scenes N broke at least once on Sonnet in v7-cross.

### How the scenes were tested (no session has run them)

`tests/test_memory_carry_principle.py`, `_stale.py`, `_parallel.py` and `_f1.py`: 126 tests,
all passing at ad0471c (run 2026-10-05, free).

- **Family i:** per scene, a hand-written result that keeps the preference (task and fact pass)
  and one that breaks it (task passes, fact fails); for `p_decide`, `p_open` and `p_flag`, a
  second way of keeping it passes too. The starting repository passes its own tests and fails
  the task. The rule's words are in session 1 and in neither the repository nor session 2's
  prompt. Session 2 works in another file than session 1.
- **Family ii:** three hand-written results per scene, all with the task done: A' gives
  (fact, stale) = (pass, fail), A gives (fail, pass), the default gives (fail, fail). The
  starting repository passes its tests and fails task, fact and stale. Neither rule is in the
  repository or session 2's prompt; session 1 does not state A', session 1' does not restate A
  and says the rule "changed". Session 2 works in a third file.
- **Family iii:** with session 1a's module written by hand, the cross scenes' keep and break
  results still split on `fact` with the task done (for `q_stdlib`, the break needs PyYAML, so
  only the fact failing is checked). The starting repository fails the task, and the repository
  after 1a fails both task and fact. Neither new prompt (`thread`, `second`) holds the fact's
  words or names 1b's files.
- **Runner** (`test_memory_carry_f1.py`): session order and placement, the worktree, the clean
  user's config and token, scrubbing, the per-pair cap reserve, per-model caps, NOT RUN by
  version and model, timeouts, the usage limit read from events, and the gate table's counts.

## Run

Claude Code 2.1.287, `claude -p`, the subscription pays. Models: Sonnet 5.5 `claude-sonnet-5-5`
and Opus 5.5 `claude-opus-5-5` (`carry.MODELS`). Arm N only, repetition 0, 24 scenes, 64
sessions per model (8 x 2 + 8 x 3 + 8 x 3).

The launcher is `f1-gate-run.cmd` at the worktree's root (sha256 under "Sealing"). It sets
`PY` to the sanchopanza venv's Python, `OUT=C:\sp-runs\memory-carry`, the pinned Claude Code
first on PATH, `PYTHONPATH` to the worktree's `src` and `DISABLE_AUTOUPDATER=1`, and runs:

    "%PY%" -u benchmarks\memory_carry\carry.py --out "%OUT%\f1-gate-sonnet" --models sonnet --scenes f1 --arms N --repeats 1 --clean-user --total-cap 16.5 >> "%OUT%\f1-gate-sonnet.log" 2>&1
    "%PY%" -u benchmarks\memory_carry\carry.py --out "%OUT%\f1-gate-opus" --models opus --scenes f1 --arms N --repeats 1 --clean-user --total-cap 31 >> "%OUT%\f1-gate-opus.log" 2>&1
    "%PY%" benchmarks\memory_carry\analyze.py "%OUT%\f1-gate-sonnet" "%OUT%\f1-gate-opus" --gate --arm N --need 3 > "%OUT%\f1-gate-table.txt" 2>&1

Each session is:

    claude -p <prompt> --model <id> --output-format stream-json --verbose --max-budget-usd <cap> --settings "{}" --allowedTools Bash Read Edit Write Glob Grep

with a 900 s timeout (`carry.SESSION_TIMEOUT`).

### Caps

- **Per session:** `--max-budget-usd` 0.60 on Sonnet, 1.00 on Opus (`carry.CALL_CAPS`;
  gen-opus's costliest session was 0.538).
- **Per run:** `--total-cap` 16.5 USD (Sonnet) and 31 USD (Opus). Before each pair the runner
  reserves that pair's sessions at the per-session cap and stops if spent plus reserve would pass
  the cap: Sonnet stops once more than 14.70 USD is spent, Opus once more than 28.00
  (3-session pairs). Spent is the sum of the sessions' own `total_cost_usd`.
- **Usage limit:** read from the stream's events (`carry.limited`); it stops the run.
- **No API key** in the agent's environment.

### Expected cost

At list price, through the subscription: Sonnet 64 x 0.19 = **12.2 USD**; Opus 64 x 0.36 =
**23.0 USD**; 35.2 USD in all. Per-session figures from `v8-cross` and `confirm` (Sonnet, 0.180
and 0.189) and `gen-opus` (0.359), computed in `prereg-f1-correctness.md`. Three-session scenes
are assumed to cost as much per session as carry's.

### Sequence, exit codes, status

- `carry.py` exits 0 when its plan ran to the end, 2 when the run's cap or the usage limit
  stopped it, 3 when a session timed out (that pair has no row).
- **Opus runs only if Sonnet exits 0.** Otherwise the status file gets `opus-skipped` and Opus
  waits for the owner.
- The gate table is written in any case.
- The launcher refuses (exit 1) without `CLAUDE_CODE_OAUTH_TOKEN` or if either run already has a
  `carry.json`, and (exit 3) if Claude Code is not 2.1.287. It is never run twice.
- Status file `C:\sp-runs\memory-carry\f1-gate-run.status`: `start`, the `claude` path and
  version, `sonnet-exit`, `opus-skipped` or `opus-exit`, `table-exit`, each with date and time.
  Logs `f1-gate-sonnet.log` and `f1-gate-opus.log`; each run records its `claude` and version in
  `claude.txt`.

## The gate (fixed)

- A family **passes** on a model when N breaks its fact, with the task done, in **at least 3 of
  its 8 scenes** (`analyze.py --gate --need 3`).
- With fewer than 8 scenes run and fewer than 3 breaks, the family is `incomplete`, not `fail`.
  A family with 8 run and fewer than 3 breaks is `fail`.
- The gate selects families, not scenes. Its rows are not reused as data for the full run, which
  uses fresh repetitions 1 to 3 (`--first-repeat 1`).

## Exclusions (NOT RUN)

- A pair is NOT RUN, and listed by name, when: the usage limit hit it; a session timed out; a
  session ended without a result (`cut`); a session's `init` shows a model other than the row's
  (`claude-sonnet-5-5` or `claude-opus-5-5`) or a Claude Code version other than 2.1.287; or the
  run's cap stopped the plan before it (listed as `missing`).
- **A session stopped by its own `--max-budget-usd` counts as run** (`error_max_budget_usd`),
  with its checks as found.
- Nothing is retried. A pair cut by a runner bug may run again whole with `--continue`, only
  under an amendment.

## Reported whatever the result

1. **The gate table** per family and model: scenes run of 8, breaks with the task done, facts not
   kept, verdict (PASS, fail or incomplete), scenes NOT RUN, cost; for family ii the three-way
   split (newer, stale, neither).
2. **Every break read by hand**, per scene: what session 2 wrote, and for family ii which rule it
   followed.
3. **`apiKeySource` per session**, from `init`: how each session signed in.
4. **What Claude Code's own auto memory saved**: per session, the folder `init` names
   (`memory_paths.auto`) and the files found there and under the pair's config (`native`); per
   pair, `native_after_1`.
5. **Worktree memory sharing**, family iii: whether the worktree session's `memory_paths.auto`
   is the main checkout's, as observed in `init`.
6. Sessions that called a subagent, and on which model.

## What would change the plan

The gate's result decides which cells of the full run exist: a family that passes on a model
opens that model's cell for it. The owner sees the gate table and decides the full run, its
budget and its seal. Where no family passes on a model, the reading is "no room for S on that
model", not a failure of S.

## Checks before launch (all free)

1. **The worktree.** HEAD is the sealing commit, and nothing tracked is modified. The S-arm
   fixes in `src/` will have been committed by then; they do not affect N, which runs no
   sanchopanza code.
2. **The dry run** passes: with a dummy token, `--dry` under `C:\sp-runs\memory-carry`, it builds
   24 repositories per model (and 4 worktrees per model) and prints 24 + 24 rows. Done on
   2026-10-05 at ad0471c (`f1-dry2`): exit 0, 48 rows, the token in no file.
3. **Claude Code.** `claude --version`, with the launcher's PATH, prints `2.1.287 (Claude Code)`.
4. **Coordination.** No other batch is using the subscription; the weekly limit is shared. The
   sibling sessions 8f (adoption) and a1 (browse) are told before launch, and the
   PIDs of any batch of theirs are named and confirmed ended.
5. **The token** (`CLAUDE_CODE_OAUTH_TOKEN`) is in the `.env` of the owner's agent with its own harness; the owner has
   approved its use for this run. Without it `carry.py` refuses (exit 1, nothing spent).

The launcher is started outside the Claude Code session through `Invoke-CimMethod
Win32_Process Create`, as the earlier seals; such a process inherits no variable from the
caller's window, which is why `carry.py` reads the token from the `.env`. The run is stopped by
PID only. The driver's PID:

    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
      Where-Object CommandLine -like '*carry.py*f1-gate-*' | Select-Object ProcessId, CommandLine

## Sealing

- Launcher `f1-gate-run.cmd`, sha256 `674634bd1b6a73af26e3fb60921b9ea7b9586d341f09884644c7436d005413dd` (at 8e9dc68, unchanged since; the earlier value 9cbe43fc... was at ad0471c, before the token was read from the `.env` of an agent with its own harness).
- Sealing commit: the commit that adds this file (`git log --diff-filter=A -- docs/results/2026-10-05-memory-frontier/prereg-f1-gate.md`).
