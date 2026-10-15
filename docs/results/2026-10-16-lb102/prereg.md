# Sonnet 5.5 on the 102 tasks Jev did not cover: the router's saving, measured (lot lb102): pre-registration

**DRAFT, not sealed.** Written 2026-10-15, before any session on these tasks. Before the seal:
an independent `revisor-prereg` review against the code, the owner's go (expected about 9-12 USD
of Claude, ceiling 16), then `python benchmarks/jev114/lb102.py --seal` and a commit whose
message carries the hash. The live path refuses to spend unless the seal matches, and runs from
`git worktree add --detach <sealed commit>`, never from a working branch.

**What the seal covers** (`lb102.SEALED`, `SEALED_GLOBS`, `SEALED_DATA`): this file; the
runner, the analysis and their tests; lb162's ids, covered ids, Jev rows and Sonnet rows; this
lot's frozen order (`uncovered-ids.txt`); every module of the package; every benchmark file the
runner loads (lb162's and h2h's, `meter.py`, the hooks, the S line and `launch.ps1`);
LongBench's `data.json`, both `tasks.jsonl`; and one aggregate sha256 of the 162 prepared
documents. A test checks that every file the runner loads is sealed.

## The question

Lot lb162 (`docs/results/2026-10-15-lb162`) routed 162 fresh LongBench v2 tasks: Jev 1.14 with
the long window answered alone where its top choice was >= 0.6 (60 tasks), Sonnet 5.5 the
rest. It was "no peor" than Sonnet alone at -10 points (+1.2, [-3.1, +5.6]). Its saving was
**estimated**: Sonnet was not run on the 102 uncovered tasks, so their cost was taken at
0.123 USD a task (Sonnet's mean on 2026-10-06), giving 26.7 % of Sonnet's cost.

**How much of Sonnet's cost does the router save on these 162 tasks, measured?** No Jev call:
Jev's answers and costs are lb162's recorded rows. Only Sonnet runs, on the 102.

## Tasks

The 102 tasks of lb162's `ids.txt` that are not in its `covered-ids.txt` (asked, not covered at
0.6; none failed). Derived by `lb102.uncovered` from lb162's `jev-scored.jsonl`, shuffled with
`random.Random(20261016)`, frozen in `uncovered-ids.txt` (sha256 `cb95fab6…`). The runner
refuses a file that is not the derivation. Bands: 20 short, 53 medium, 29 long; 31 easy, 71
hard; 789,000 characters a document on average (the covered 60: 443,000).

## The arm

Arm N of lb162's phase S, unchanged (`h2h_longdoc.py`'s session through `h2h_lb102.py`):
- Sonnet 5.5 (`claude-sonnet-5-5`) in Claude Code 2.1.287 pinned and first on PATH
  (`launch.ps1`, `DISABLE_AUTOUPDATER=1`);
- a clean user per session: a new `CLAUDE_CONFIG_DIR`, the session folder under `C:\sp-runs\h2h`
  (outside the user's home);
- the document copied as `document.txt`, LongBench v2's official 0-shot template, WebSearch and
  WebFetch disallowed, the local hook on every tool;
- graded by the official `extract_answer` on the last line that has one;
- one session per task, one at a time, in the frozen order; phase `lb102`, its own private
  session folder.

The only change is the per-session cap when money is short (next section).

## Money

- **Ceiling 16.00 USD** in code (`lb102.CEILING_USD`, the owner's), Claude Code's list price
  (`list_usd`).
- **The cap of each session** (`lb102.cap_for`, enforced by `h2h_lb102.Budget` before each
  session, from the recorded sessions plus the reserve of any session started without a row):
  - arm N's 3.00 USD while 3.00 plus one worst turn fits: spent <= 8.68;
  - above that, the room left after one worst turn, down to the cent;
  - no session below 0.50 USD: spent > 11.18 stops the phase (kind `ceiling`, exit 1, final).
- **The worst turn** is lb162's, 4.32 USD: one turn rewriting Sonnet 5.5's whole 1M-token window
  to the cache and answering 32,000 tokens at Claude Code's own rates. `--max-budget-usd` stops
  between turns only, so a session spends at most its cap plus that turn. The phase **cannot
  pass 16**.
- A **reservation row** (the session's cap plus the worst turn) is written before each session.
  A session that dies mid-way keeps that reserve against the ceiling on a resume.
- Why the cap moves: with a fixed 3.00 cap the reserve is 7.32, so sessions stop at 8.68 spent.
  At lb162's costs that finishes the 102 in about a third of the runs. Lowering the cap only
  when the money is short changes no session that costs what these sessions cost: 109 of the
  110 arm N LongBench sessions on record (lb162's 60, 2026-10-06's 50) cost under 0.41 USD.
- **Expected** (`lb102.py --dry`, lb162's 60 real session costs by length band):
  - 9.08 USD by band (long 0.056, medium 0.107, short 0.091 a session); 12.55 at 2026-10-06's
    flat 0.123;
  - simulated money rule (5,000 draws): at lb162's costs all 102 run 99.9 % of the time, about
    5.5 sessions on a lowered cap, spend 9.09 (p95 10.30); at 1.3 x those costs (about
    2026-10-06's level) all 102 run 29 % of the time, 96 on average (p5 84), spend 11.13.

## Clock

- No start before 08:00 (Windows Update restarts 02:00-08:00), nor when 102 sessions at 1.5 x
  38 s plus 10 minutes would cross midnight: **start between 08:00 and 22:13**.
- Before each session (lb162's guard): a stop if it is before 08:00, past the start date, or
  midnight is less than 10 minutes away (kind `clock`, exit 5, a pause: a relaunch after 08:00
  resumes).
- Expected wall time: about 34 minutes at lb162's mean by band, about 65 at 38 s a session; the
  longest arm N LongBench session took 468 s. It is attended throughout.

## Stops (kind in `sonnet-stop.json`, the kind only)

- finished: `done`, exit 0;
- the ceiling: `ceiling`, exit 1, final;
- a 429 or usage limit ("weekly limit"): `limit`, exit 2. The session is recorded as not run and
  `LIMIT.flag` is written in `C:\sp-runs\lb102`; a pause, never scored. The owner tells the
  other sessions and deletes the flag to resume.
- the clock: `clock`, exit 5;
- a `STOP` file in `C:\sp-runs\lb102`: `manual`, exit 6, before the next session.

Processes are stopped by PID only (`sonnet.pids`).

## Primary analysis (`lb102_stats.py`)

Over lb162's 162 tasks:

    Sonnet alone = Sonnet on the 60 covered (lb162) + Sonnet on the 102 (this lot)
    hybrid       = Jev on all 162 (lb162)           + Sonnet on the 102 (this lot)
    saving share = (Sonnet alone - hybrid) / Sonnet alone

- Each group's Sonnet cost is its size times its measured mean. With every session run it is
  the sum. If a stop leaves some of the 102 without a session (they run in a seeded random
  order), it is an approximately unbiased ratio estimator; the number measured is reported.
- **Paired bootstrap** over the 162 tasks (l4_stats: 10,000 draws, seed 20261015, percentile
  95 % CI); a resample whose uncovered tasks have no session is dropped and counted.
- **Reading, fixed now** (bounds compared unrounded):
  - **"ahorra"** if the CI's lower bound is > 0;
  - **"no ahorra"** if its upper bound is <= 0;
  - **"no concluyente"** otherwise;
  - **"no medido"** with no session on the 102;
  - **"pausa"** while a `LIMIT.flag` or `STOP` is in `C:\sp-runs\lb102`, or the phase did not
    end by finishing or by its ceiling.
- Reported beside it: the measured share against lb162's estimate of 26.7 % ("inside", "above"
  or "below" the CI). The README then states the measured share and its CI in place of the
  estimate.
- **Precision expected:** with the 102 drawn from lb162's costs by band, the CI is about ±10
  points around a share of 25-35 %.

**Sessions with no letter.** A session that ended in an infrastructure error (`is_error` without
`hit_cap`, wall-clock timeouts included) is not a cost measurement: excluded in the primary
(as not run), counted at its cost in a sensitivity reading. A session stopped by a cap below
3.00 is counted at its cost in the primary, and at 3.00 in a second sensitivity reading (an
upper bound on what the lowered cap cut).

## Secondary, descriptive

- Sessions: count, total, mean, median and maximum cost; infrastructure errors; caps hit; caps
  below 3.00 and how many of them were hit; the lowest cap used.
- Accuracy on the 102: Sonnet right, Jev right, the exact McNemar of their disagreements (what
  Jev alone would have given up where it was unsure).
- Over the tasks with both answers known: Sonnet alone and the hybrid right, and USD per right
  answer for each. Hybrid minus Sonnet is lb162's +1.2 points by construction (an uncovered task
  adds 0), so this lot gives no new accuracy verdict.
- The share and Sonnet's mean cost on the 102 by length band and by difficulty.

## Commands

From the detached worktree of the sealed commit:

```
python benchmarks/h2h/h2h_lb102.py --dry          # free: the 102, cost, simulation, clock
python benchmarks/h2h/h2h_lb102.py --preflight    # free (needs the subscription token)
python benchmarks/jev114/lb102.py --seal
powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_lb102.py -RunnerArgs "--phase lb102" -Pin $env:USERPROFILE\.cache\sanchopanza\claude-pin\2.1.287 -Log C:\sp-runs\lb102\sonnet.log -PidFile C:\sp-runs\lb102\sonnet.pids
python benchmarks/h2h/h2h_lb102.py                # rows without text
python benchmarks/jev114/lb102.py                 # the analysis, summary.json
```

No `-KeysEnv`: no Jev call. Public rows (`sonnet-rows.jsonl`) hold the id, letter, grade, cost,
time, turns, `hit_cap`, `is_error`, Claude Code's `subtype` and the session's cap. No text.

## What follows

- "ahorra": the README replaces the estimated saving with the measured share and its CI, for
  long-document multiple-choice questions, Jev 1.14 at 0.6 and Sonnet 5.5.
- "no concluyente" or "no medido": the saving stays an estimate and the README says so.

Nothing in `policy.py`, `DEFAULT_MODEL` or `install` changes in this lot.

## Out of this lot (a proposal, not prepared)

Two measurements lb162 left open before a product claim beyond multiple choice. Neither is
prepared or registered here; each needs its own pre-registration and the owner's approval
(both are above 10 USD).

**1. Opus 5.5 as the expensive model.** The same router (Jev 1.14 at 0.6, lb162's recorded
answers, so Jev is free) with Opus 5.5 in clean Claude Code answering the rest.
- Opus must run on all 162: on the 60 covered for the no-worse verdict (Jev tied Sonnet there;
  Opus may be stronger) and on the 102 for the saving.
- **Cost from real data:** the 110 arm N LongBench sessions' tokens, re-priced at Claude Code's
  Opus 5.5 rates (4/20, read 0.2, write 8; `meter.CLAUDE_CODE_RATES`), cost 1.74-1.79 x Sonnet:
  0.172 USD a task (lb162's 60) to 0.213 (2026-10-06's 50).
  - 162 tasks: **about 28-35 USD**, assuming Opus spends the tokens Sonnet did.
  - A worst turn at Opus rates is 8.64 USD (1M tokens written at 8, 32k out at 20). With this
    lot's moving cap, a ceiling of about 45 USD lets the 162 finish at those costs.
- Power: lb162's design decided at -10 points 88 % of the time with Sonnet; with Opus the
  covered-task tie may not hold, and a power check from these rows comes first.

**2. A long-document set graded on free-text answers.** LongBench v2 is four-option, graded by
the letter; Jev's Choice answers those directly. On free text Jev cannot write the answer, so
the router changes shape: a cheaper model answers, Jev judges whether that answer is supported
by the document (the long window), and below a cut the expensive model answers.
- Candidate sets, graded by their official token F1 with no judge model: LongBench v1's
  NarrativeQA or ∞Bench En.QA (counts, licence and grader to check before preparing).
- **Cost from real data, per task:**
  - the cheaper model, Haiku 4.5 in clean Claude Code: the same 110 sessions re-priced at Haiku
    rates are 0.5 x Sonnet, 0.048-0.061 USD;
  - Jev's judgment with the long window: lb162's 0.874 USD over 162 tasks is 0.0054 a task,
    about 0.011 USD per million characters shown (0.010 at the 900,000-character cut);
  - the expensive arm on every task (to measure the saving and the no-worse verdict): Sonnet
    0.096-0.123, Opus 0.172-0.213.
  - **150 tasks: about 22-28 USD of Claude with Sonnet as the expensive model, 33-41 with
    Opus**, plus 0.8-1.5 USD of Jev.
- Before any of it: whether Jev's "supported" judgment is calibrated on a cheap dev slice, since
  this is a different question from lb162's.
