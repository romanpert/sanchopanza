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
  opens the key file reads question, gold, answer (and, for GAIA, the scorer's doubt) under an
  opaque id, shuffled, with no arm, and writes `{id, ok}`. Hand verdicts take precedence over
  the automatic grade (`with_hand`). The primary grade is `with_hand`; the automatic-only grade
  (`oficial`; for BCP exact match, else the judge) is reported beside it. In a `-conf` phase the
  runner refuses `--verdict` (which names the arm): only blind verdicts exist.
- **Which rows are read by hand** is fixed by code, not by choice: GAIA `needs_review` misses;
  BCP `doubtful` rows (judge yes without exact match, or no parseable judge verdict). A judge
  "no" is not re-read, in either arm.
- **BCP judge**: run after the sessions with `--judge` on the pinned Claude Code (it refuses
  otherwise). While any row without exact match lacks its judge, the report gives no verdict
  ("incompleto"); the judge is resumed until none is left.
- **GAIA leaks**: a session whose tool results mention "GAIA" or the task id is marked `leak`.
  By rule, with no reading, a task with a leak-marked session in either arm leaves the primary
  paired analysis in both arms (`dropped_for_leak`); the analysis with all tasks is reported as
  a sensitivity (`paired_all_tasks`). BCP and LongBench run on local corpora with no web access
  to the sets; their rows carry no leak rule.

## 5. Outcomes and analysis

Analysis set: tasks with a counted first run in both arms (`phase.counted`: no warm-ups, no
`not_run`).

- **Primary**: success (section 4) and list cost per session, Jev included
  (`gaia_stats.cost`: `list_usd` + `jev_usd`).
- **Secondary, reported, never deciding**: cost per correct answer (`usd_per_correct`), wall
  time (same bootstrap), turns, tokens by kind, what each S component did (`components`), Jev
  errors by kind (`jev_error_kinds`).
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
- **Ceilings in code** (`PHASE_CEILINGS` of each runner, commit 1c89461; the phase stops before
  a session whose cap would cross it): GAIA 40 USD, BCP 150 USD, LongBench 20 USD, at list
  prices on the subscription. Jev's spend is outside these ceilings (0.25-1.8 % of an S session).
- **A suite that stops at its ceiling** before its last task: the verdict is computed on the
  pairs it completed and the report says "truncated at N of M tasks". Raising a ceiling is an
  amendment, written before the next session, and needs the owner's OK.
- **Usage limit** (429, weekly limit): STOP-LIMIT, the session is `not_run`, a resume runs it.
- **Jev refusing the account** (HTTP 401/402/403 in the session's journal, commit b575f95): the
  session is recorded `invalid` and `not_run` and the phase stops (exit 4); a resume after the
  recharge runs it again. Other Jev errors (timeouts, 5xx) are S's normal fail-open behaviour:
  the session counts and the errors are reported.
- **Preflight** before every launch, fail closed: pinned Claude Code, data, both arms' user folders
  as a session makes them, S's line proved flag by flag from the frozen commit, permission mode,
  one user folder per session, the deny hook, and one real Jev decision when S runs.
- No retries of finished sessions; resume skips what is done.
- **One S for every suite**: `s_install.json` names its source and commit (the runner refuses a
  sealed line without them, 1c89461); every counted SP row must carry that commit in
  `sp_commit` and the preflight's digest in `s_digest`, or the row is reported as a deviation.

## 6b. Deviations from the common plan, declared

- **No separate margin test** (plan 2.6): GAIA, BCP and LongBench have no per-task history, and
  in dev N failed 20 %, 50 % and 30 % of the tasks; the "sin margen" rule is applied to the
  confirmation's own N instead.
- **No warm-up session** (plan 2.1): each session is a fresh user folder; the prompt cache is the
  account's and both arms share it alike, since arms alternate within each task (CC first).
- **Opus 5.5 is missing** from this preregistration (plan 1): its verdict does not exist until an
  amendment adds it with the owner's OK; Fable 5.1 likewise.
- **S is S0, not the bare default install** (plan 1 allows a decided line): the decision is
  `docs/S-SEAL-DRAFT.md` on main (indagis-95 with indagis-a1, 2026-10-05) and its 2026-10-06
  update (gate A in, check-done and candor kept).

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

BCP's judge runs after its sessions, with the pinned Claude Code first on PATH (from the h2h
worktree, `PYTHONPATH=src`): `python benchmarks/h2h/h2h_bcp.py --judge --phase bcp-conf
--judge-ceiling 3`, repeated until the report shows `unjudged: 0`.

Budget: the owner was told "about 150 USD with Sonnet" for these three confirmations on
2026-10-06 and answered to go ahead ("dale caña, go") after recharging TypeSafe. The ceilings
sum to 210 USD; anything above them is an amendment and a new question to the owner.

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
