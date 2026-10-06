# Preregistration: S against clean N on GAIA, BrowseComp-Plus and LongBench v2, Sonnet 5.5

Status: DRAFT until the seal block at the end is filled. Nothing in this file changes after the
first paid session; a change after that is an amendment, appended with its date and reason.

Written by indagis-dd (line web/h2h, relay of indagis-a1) on 2026-10-06, from the common plan
(`docs/PLAN-COMPARACION-FINAL.md` on main, section 2) and the dev phases of 2026-10-05/06
(`docs/results/2026-10-06-h2h-s1/README.md`). No task text, gold or answer appears here or in
any file of the repository.

## 1. Question

Does Claude Code with sanchopanza's sealed line (S) beat a clean Claude Code (N) on price or on
success, without losing on the other, for one model (Sonnet 5.5), on three suites: web research
with files (GAIA), deep search over a fixed corpus (BrowseComp-Plus) and long-document reading
(LongBench v2)? One verdict per suite. Nothing is aggregated across suites or models.

## 2. Arms

- **N**: Claude Code 2.1.287 (pinned by `launch.ps1`), a clean user per session (`gaia_arms.py`:
  an empty `CLAUDE_CONFIG_DIR` of its own, `--setting-sources user`, folders under
  `C:/sp-runs/h2h`, outside the home folder), permission mode `default` set by flag and in the
  settings, the suite's own tools and deny rules. Nothing of the owner's configuration.
- **S**: N plus what `sanchopanza install` writes with the flags and env of
  `benchmarks/h2h/s_install.json` (S0), run from a frozen copy of sanchopanza at the sealed commit
  named in section 9, with `--provider jev` and the TypeSafe key. The line includes the change
  gate A (main f2a0fe2): check-done and candor act only when the request changed something or
  asks for an action.
- Same model, same prompt, same tools, same caps; arms interleaved within each task (CC then SP
  for each task), so a ceiling stop cuts both arms alike.

S1 (S0 with `--knowledge`) is **not** in this preregistration: it never ran with the candor fix
(d1e99af) nor gate A. It can be added by amendment, before its first session, on GAIA only.

## 3. Tasks

All lists are fixed before any paid session; dev tasks are out of every confirmation.

| Suite | Pool | Out | Confirmation | Runner flags |
|---|---|---|---|---|
| GAIA validation | 155 tasks without video | 20 dev (`gaia-dev-ids.txt`) | **135** | `--no-video --exclude benchmarks/h2h/gaia-dev-ids.txt` |
| BrowseComp-Plus | 100 drawn (`bcp-ids.txt`, seed 20261006) | 10 dev (`bcp-dev-ids.txt`) | **90** | `--ids benchmarks/h2h/bcp-ids.txt` (dev ids left out by the runner) |
| LongBench v2 | 60 drawn (`longdoc_data.py`, seed 20261006) | 10 dev (`longdoc-dev-ids.txt`) | **50** | default order (dev ids left out by the runner) |

`--plan` (free) gives 270, 180 and 100 sessions. One run per task and arm (k = 1). No
selection by historical success: GAIA, BCP and LongBench have no per-task history here; all
remaining tasks are used, and that is said in the report.

## 4. Grading

- **GAIA**: GAIA's `question_scorer` (`gaia_scorer.py`, reproduced case by case) on the last
  FINAL ANSWER. Misses the scorer may have got wrong (`needs_review`) go to a **blind** hand read.
- **BrowseComp-Plus**: exact match after normalisation, else the official judge template on Claude
  Haiku 4.5 through `claude -p` on the subscription (official: Qwen3-32B); doubtful ones
  (`bcp_grade.doubtful`) go to the blind hand read.
- **LongBench v2**: the letter against the gold letter. No hand read.
- **Blind hand read** (`--review`, then `--apply-blind`, commit 7f3a82f): a subagent that never
  opens the key file reads question, gold, answer and the scorer's doubt under an opaque id,
  shuffled, with no arm, and writes `{id, ok}`. Hand verdicts take precedence over the automatic
  grade (`with_hand`). The primary grade is `with_hand`; the automatic-only result is reported
  beside it.
- **GAIA leaks**: a session whose tool results mention "GAIA" or the task id is marked `leak` and
  read by hand. If its answer came from a page that serves the set, the task is dropped from the
  analysis in both arms and counted in the report.

## 5. Outcomes and analysis

Analysis set: tasks with a counted first run in both arms (`phase.counted`: no warm-ups, no
`not_run`).

- **Primary**: success (section 4) and list cost per session, Jev included
  (`gaia_stats.cost`: `list_usd` + `jev_usd`).
- **Secondary, reported, never deciding**: cost per correct answer, wall time (same bootstrap),
  turns, tokens by kind, what each S component did (`components`), Jev errors by kind.
- **Statistics** (`gaia_stats.py`, commit 5b26c5d): McNemar exact two-sided on the discordant
  tasks; paired bootstrap by task, 5,000 replicas, seed 20261005, for the success difference in
  points and for the cost ratio mean(S)/mean(N), 95 % percentile intervals.
- **Verdict** (`gaia_stats.verdict`, computed by the code, one per suite):
  - **sin margen**: N wrong on fewer than 5 % of the tasks.
  - **gana (coste)**: the cost ratio's 95 % interval lies below 1 **and** the success
    difference's 95 % interval stays at or above -2 points (non-inferiority margin of the plan).
  - **gana (éxito)**: McNemar p < 0.05 with S right more often **and** the cost ratio's interval
    does not lie entirely above 1.
  - **no gana**: anything else, said as it is.
- No correction for multiplicity: each suite is its own verdict and none is pooled. Power is
  stated, not assumed: with 135 / 90 / 50 tasks the success interval is several points wide, so
  "gana (coste)" needs S's success to be almost identical to N's.
- Dev expectation, written here so it cannot move: in dev (10 valid tasks each, before gate A) S0
  cost 1.22x (GAIA), 1.69x (BCP) and 1.90x (LongBench) N, mostly from check-done send-backs and
  candor. Gate A was replayed offline (17/17 false send-backs avoided) but never live.

## 6. Session rules

- **Caps**: `--max-budget-usd` per session, GAIA 1.50 USD, BCP and LongBench 3.00 USD (Sonnet). A
  session that hits its cap counts as it ended.
- **Ceilings in code** (phase stops before a session whose cap would cross it): GAIA 40 USD,
  BCP 150 USD, LongBench 20 USD, at list prices on the subscription.
- **Usage limit** (429, weekly limit): STOP-LIMIT, the session is `not_run`, a resume runs it.
- **Jev refusing the account** (HTTP 401/402/403 in the session's journal, commit b575f95): the
  session is recorded `invalid` and `not_run` and the phase stops (exit 4); a resume after the
  recharge runs it again. Other Jev errors (timeouts, 5xx) are S's normal fail-open behaviour:
  the session counts and the errors are reported.
- **Preflight** before every launch, fail closed: pinned Claude Code, data, both arms' user folders
  as a session makes them, S's line proved flag by flag from the frozen commit, permission mode,
  one user folder per session, the deny hook, and one real Jev decision when S runs.
- No retries of finished sessions; resume skips what is done.

## 7. Order and cost

Expected from dev (Sonnet 5.5, list prices, Jev included): GAIA ~0.11 USD per session (~30 USD),
BCP ~0.6 (~110 USD), LongBench ~0.08 (~8 USD): **~150 USD** on the subscription, plus Jev, which
is 0.25-1.8 % of an S session (TypeSafe balance 9.47 USD on 2026-10-06 11:40). Order: LongBench and
GAIA (may run side by side as separate phases), then BCP. One heavy batch of the other lines at
a time, agreed with indagis-e1/d4 (PID, time, ceiling announced). Opus 5.5 is a separate
amendment, only with the owner's OK.

Commands (from the h2h worktree; `launch.ps1` adds `--live` and pins Claude Code):

```
powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_longdoc.py -RunnerArgs "--phase longdoc-conf --models SONNET --brazos CC SP --ceiling 20" -Log C:\sp-runs\h2h\longdoc-conf.log -PidFile C:\sp-runs\h2h\longdoc-conf.pids
powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_gaia.py -RunnerArgs "--phase gaia-conf --models SONNET --brazos CC SP --no-video --exclude benchmarks/h2h/gaia-dev-ids.txt --ceiling 40" -Log C:\sp-runs\h2h\gaia-conf.log -PidFile C:\sp-runs\h2h\gaia-conf.pids
powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_bcp.py -RunnerArgs "--phase bcp-conf --models SONNET --brazos CC SP --ids benchmarks/h2h/bcp-ids.txt --ceiling 150" -Log C:\sp-runs\h2h\bcp-conf.log -PidFile C:\sp-runs\h2h\bcp-conf.pids
```

Each suite has a log and a PID file of its own (the launcher's defaults are shared). Stop a run
by its PIDs only.

BCP's judge runs after its sessions (`--judge`, judge ceiling 3 USD).

## 8. Reading

Every failure of S and every favourable number is read by hand before it is reported. Process
failures go to commits and chat, not to the README. The report holds counts, costs and task ids
only.

## 9. Seal

To fill before the first paid session; this block is the only part written after the draft.

- sanchopanza sealed commit (S line): `<TBD at the 12:00 seal>`
- `s_install.json` sealed: `<TBD>`
- h2h runner commit: `<TBD>`
- sha256 of this file without this block: `<TBD>`
- Independent verification against the code: `<TBD>`
