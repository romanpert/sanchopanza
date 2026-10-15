# F1 headroom gate: result (2026-10-05)

Sealed pre-registration `prereg-f1-gate.md` (c4b853c) and its amendment 1 (1b2e8e7), both written
before any data. Run 2026-10-05 by WMI from `f1-gate-run.cmd`: start 19:16, Sonnet 5.5 exit 0 at
19:53, Opus 5.5 exit 0 at 20:32, table exit 0 at 20:33 (`C:\sp-runs\memory-carry\f1-gate-run.status`).
Claude Code 2.1.287, the pinned `claude.exe` (`claude.txt` in both runs). Arm N only, as a clean
user, repetition 0, 24 scenes, 64 sessions per model. No amendment was made after the data.

Spend, the sum of the sessions' own `total_cost_usd`: **Sonnet 3.95 USD, Opus 7.66 USD**, 11.61 in
all, against an estimate of 12.2 and 23.0 (caps 16.5 and 31). Per session: Sonnet 0.062 (estimate
0.19, highest 0.130 against a cap of 0.60), Opus 0.120 (estimate 0.36, highest 0.204 against 1.00).
The estimate came from runs that loaded the maintainer's setup; a clean user's prompt is much
smaller, which is the likely reason, not checked.

## The gate table

The sealed command, run again by hand on the same folders
(`analyze.py f1-gate-sonnet f1-gate-opus --gate --arm N --need 3`, the sanchopanza venv's Python,
`PYTHONPATH` the F1 worktree's `src`, HEAD 1b2e8e7), prints a file byte for byte identical to
`f1-gate-table.txt`.

| family | model | ran | breaks, task done | not kept | verdict | USD | broken scenes |
|---|---|---|---|---|---|---|---|
| (iii) parallel | Sonnet 5.5 | 8/8 | **3** | 3 | **PASS** | 1.36 | q_cents, q_stdlib, q_tz |
| (iii) parallel | Opus 5.5 | 8/8 | 1 | 1 | fail | 3.12 | q_stdlib |
| (i) principle | Sonnet 5.5 | 8/8 | 2 | 2 | fail | 1.08 | p_flag, p_noask |
| (i) principle | Opus 5.5 | 8/8 | 0 | 0 | fail | 1.91 | - |
| (ii) stale | Sonnet 5.5 | 8/8 | 0 | 0 | fail | 1.51 | - (newer 8, stale 0, neither 0) |
| (ii) stale | Opus 5.5 | 8/8 | 0 | 0 | fail | 2.63 | - (newer 8, stale 0, neither 0) |

- No pair is NOT RUN: no usage limit, no timeout, no session without a result, no wrong model or
  version, no `missing`. Every fact not kept had its task done, so the two counts are the same.
- Exact 95 % intervals on N's break rate: 3/8 is 0.09-0.76; 2/8 is 0.03-0.65; 1/8 is 0.003-0.53;
  0/8 is 0-0.37. Over all 24 scenes: Sonnet 5/24 (0.07-0.42), Opus 1/24 (0.001-0.21).

## What opens

By the sealed rule, a family that passes on a model opens that model's cell. **Only one cell
opens: Sonnet 5.5, family (iii) parallel.** The other five cells stay closed: Sonnet principle
(2 of 8, one short), Sonnet stale, and all three on Opus. The owner decides the full run, its
budget and its seal; nothing here starts it.

**No headroom on Opus 5.5.** Claude Code alone, as a clean user, broke 1 fact in 24 new scenes
built from the maintainer's own kinds of cross-session failure. That is the second bench where Opus
leaves no room (carry v6.2: N 14/16). For the product claim this means: on Opus 5.5, sanchopanza's
memory cannot be shown to make Claude Code keep more of what the person said, because Claude Code
already keeps it; there it can only tie, cost more or harm. Any claim of better memory has to be
scoped to Sonnet 5.5 (and to the parallel-session case) until a bench shows Opus failing. This is
the "no room for S on that model" reading the seal fixed in advance, not a failure of S. The
maintainer's real Opus failures (about 1.3 per 100 turns) are not reproduced by these scenes; the
gate does not say why.

**Family (ii), stale: Claude Code's own memory followed the newer rule 16 of 16.** On both models
the auto memory, read after session 1', held only the newer rule in all 8 scenes: the file was
rewritten or replaced (Sonnet `u_delim` renamed it to `csv-tab-separator.md`), and most say the old
rule was superseded. Every session 2 had that index injected at start, and all 16 code changes
follow the newer rule (`carried` newer 16, stale 0). Where Claude Code's memory already resolves
precedence, S can only tie or harm: a send-back on the stale rule would be pure loss. Family (ii)
stays useful as a harm check for S's supersession (v8.2/v8.3), not as a place to show gain.

## The five breaks, read by hand

Every check was rerun by hand in every repository (task, fact and, in family (ii), stale; with
bytecode writing off so the data stay as found): **48 of 48 match `carry.json`**, so no break is a
checker artifact. Reasons below come from `session-*.jsonl`, the session transcripts under
`claude-config/projects/`, and `git diff HEAD` in `repo/`.

| scene, model | what session 2 did | fact in auto memory before session 2 | session 2 read it | why it broke |
|---|---|---|---|---|
| `p_flag`, Sonnet | `price()` applies 10 % over 100 unconditionally; no `FEATURE_*` read (check: "on by default") | no; session 1 saved nothing | nothing to read | Session 1 followed the rule (`FEATURE_VAT_REJECT_NEGATIVE` in `tax.py`) but never saved it. Session 2 read only `pricing.py` and its test; it never looked at `tax.py`, where the pattern was. |
| `p_noask`, Sonnet | picked day-first without asking (half the rule), explained it in a code comment and its answer; did not touch `DECISIONS.md` | no | nothing to read | `DECISIONS.md` existed with session 1's one line, but session 2 never opened it. The logging half of the rule lived only in session 1's prompt. |
| `q_tz`, Sonnet | `record()` stores `datetime.now(timezone.utc).isoformat()`, with `+00:00` (check: offset present) | no; 1a and 1b saved nothing | nothing to read | 1b repeated the rule in its answer ("When a timestamp is added, it should be naive UTC") but saved nothing; nothing in the code showed it, since `events.py` has no timestamp. |
| `q_cents`, Sonnet | `shipping_cost` returns floats (1 kg gives 4.99) | no | nothing to read | Session 2 read `cart.py`, saw integer prices, and still chose floats because the prompt said "4.99"; its answer says "If so, you may want `shipping_cost` to return cents too". 1b had said "prices stay integer cents" but saved nothing. |
| `q_stdlib`, Sonnet | `load_settings` uses `import yaml` (check: `['yaml']`) | no | nothing to read | 1b ran in the worktree (branch `side`, invisible from main), said "standard library only" and saved nothing. Session 2 checked that PyYAML was installed and used it. |
| `q_stdlib`, Opus | same: `yaml.safe_load` | **no**: memory held only 1a's "settings module in progress" note | yes: the index was injected and it read that note | 1b (worktree) loaded the shared memory, did the task with `urllib`, said in its answer "standard library only" and **wrote no memory**. The only Opus pair of 8 in family (iii) where 1b did not save the fact. Session 2 even updated the progress note to "PyYAML ... not declared". |

The pattern in all five: the fact never reached Claude Code's auto memory. Observationally, over
both models, every pair where the scene's fact (for family (ii), the newer rule) was in auto memory
before session 2 kept it (37 of 37), and the pairs where it was not broke 5 of 11 times. The 6 kept
without memory held by the repository or by default: Sonnet `q_print` and `q_camel` copied the
start repository's own `sync.py` logging and `orders_api.py` camelCase, `q_prefix` copied
`ACME_LOG_LEVEL` from the start `config.py` (it says so), `q_zeros` kept ids as strings by default,
and `p_open` wrote a fetcher that makes no robots.txt request and no sleep on a default call. Pairs, not
causes: who saves is not assigned at random.

## Kept pairs, a sample read by hand

Four per family and model; in each, session 2's diff does what the fact asks, and the hand rerun
passes.

- Sonnet principle: `p_open` (no sleep, no robots.txt), `p_decide` (`is_spam` calls `judge()`),
  `p_es` ("La contraseña debe tener al menos 12 caracteres"), `p_signoff` (mail to Marta). The
  last three had the rule in memory; session 2 had the index injected and read the topic file in
  `p_decide` and `p_signoff`.
- Sonnet stale: `u_time` (`int(time.time() * 1000)`), `u_delim` (`delimiter='\t'`), `u_lang`
  (Portuguese message), `u_sort` (newest first).
- Sonnet parallel: `q_print`, `q_camel`, `q_zeros`, `q_prefix`, all without memory (see above).
- Opus principle: `p_noask` (wrote the date choice to `DECISIONS.md`), `p_flag`
  (`FEATURE_BULK_DISCOUNT == "1"`), `p_json` (`json.dump` to stdout), `p_dryrun` (dry run unless
  `--apply`).
- Opus stale: `u_money` (`'12,50'`), `u_bool` (1/0), `u_lang` (Portuguese), `u_date`
  (`2 Jan 2026`).
- Opus parallel: `q_tz` (naive UTC), `q_cents` (499 + 150 per kg, int), `q_zeros` (string ids),
  `q_prefix` (`ACME_SMTP_*`); in all four 1b saved the fact and session 2 had it injected.

## Exclusions and items reported whatever the result

- **`init`, all 128 sessions:** the row's model (`claude-sonnet-5-5` or `claude-opus-5-5`) and
  `claude_code_version` 2.1.287. No exclusion applies.
- **`apiKeySource`: `none` in 128 of 128.** The sessions signed in with the OAuth token from the
  environment, which `init` does not report as an API key; no API key reached any session.
- **Plugins and skills: built in only.** Every `init` lists the same 3 plugins, all
  `@builtin` (`cc-plugin-agents-md`, `cc-plugin-telemetry`, `cc-plugin-plugin-authoring`), the
  same 19 bundled skills, the 5 built-in agents, and no MCP server. Nothing from the maintainer's
  setup loaded.
- **`permissionMode`: `auto` in session 1 of every pair (48 of 48), `default` in every later
  session (80 of 80).** The run passes no `--permission-mode`. Each pair's cached
  `remote-settings.json` is `{}`, and after the first start `.claude.json` caches the flag
  `tengu_auto_mode_default_on: false`; the pattern fits a server-side default for a fresh
  configuration's first start, but its source is not established from these files. In practice:
  24 tool calls were denied, all `PowerShell` (not in `--allowedTools`), in 17 `default`
  sessions (Sonnet `p_open` and `u_delim` session 2; 15 Opus sessions), none in a break pair;
  every one of those sessions still ended `success`. No session 1 had a denial.
- **What auto memory saved** (files under the pair's `claude-config/projects/*/memory/`, after
  each session):

  | family | model | after session 1 (1a in iii) | after 1' or 1b | fact or newer rule there before session 2 |
  |---|---|---|---|---|
  | (i) principle | Sonnet | 5/8 | - | 5/8 (not p_open, p_noask, p_flag) |
  | (i) principle | Opus | 8/8 | - | 8/8 |
  | (ii) stale | Sonnet | 7/8 (not u_lang) | 8/8 | 8/8 newer only |
  | (ii) stale | Opus | 8/8 | 8/8 | 8/8 newer only |
  | (iii) parallel | Sonnet | 0/8 | 1/8 (q_trash) | 1/8 |
  | (iii) parallel | Opus | 8/8 (progress notes on 1a's module) | 8/8 | 7/8 (not q_stdlib) |

  Sonnet saved in 12 of its 24 first sessions here, against 0 of 48 in carry v6.2 under the
  maintainer's setup; Opus in 24 of 24 (7 of 32 there). The setups differ in more than memory, so
  this is a difference, not a cause. Sonnet 1a saved nothing in family (iii), so the module's
  existence reached session 2 only through the repository.
- **Worktree memory sharing (family iii, `q_zeros`, `q_stdlib`, `q_prefix`, `q_trash`): shared,
  on both models, 8 of 8 pairs.** Session 1b ran with `cwd` `repo-wt` and its transcript went to a
  separate `...-repo-wt` project folder, but its `init` `memory_paths.auto` was the main
  checkout's folder (`...-repo\memory\`), the same string as in 1a and in session 2. No `memory`
  folder exists under `...-repo-wt`. It carried: Sonnet `q_trash` and Opus `q_zeros`, `q_prefix`,
  `q_trash` wrote the fact from the worktree and session 2 in main had it injected. In 2.1.287 auto
  memory is keyed by the repository, not the worktree, as v8.2's store now is.
- **Subagents: none.** No `Task` or `Agent` call and no event with a `parent_tool_use_id` in any
  of the 128 streams.
- **Budget and time:** every session ended `success` / `completed`; none was stopped by
  `--max-budget-usd` and none timed out (longest 60.1 s against 900 s).
- **Token:** no pair has `token_scrubbed` or `token_in_git`.
- **Runner notes:** the log shows git "Permission denied" on the between-session commit in Sonnet
  `p_flag`, `q_print`, `q_camel` and Opus `q_trash`; `commit_wip` retried and every one of those
  repositories has its `wip` commits, so no session started from an uncommitted state.

## What this does not show

- Eight scenes per cell, one repetition. 3 of 8 is compatible with a true rate from 9 % to 76 %;
  the full run, if sealed, may see Sonnet parallel break less often than here (selection on a
  noisy pass), and Sonnet principle at 2 of 8 may have room the gate could not see.
- Headless `claude -p` only, a clean user, Claude Code 2.1.287. The current release and
  interactive sessions may save memory differently.
- The gate says nothing about S. Whether S keeps more on Sonnet parallel, and at what cost, is the
  full run's question.

2026-10-15: text redacted to remove the name of another project; the sealed original (`f1-gate-run.cmd`, hash 9ed786d5f7ee3cd96139bc6fb2455db2f5384f38743bd397eb47e272b705e241) is kept in the git history.
