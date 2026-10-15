# The lb162 router against Opus 5.5, and its saving measured (lot lb162x): pre-registration

**DRAFT, not sealed.** Written 2026-10-16, before any session of this lot. Before the seal: an
independent `revisor-prereg` review against the code, then `python benchmarks/jev114/lb162x.py
--seal` and a commit whose message carries the hash. The owner approved both phases on
2026-10-15 (expected about 39 USD of Claude Code list price, hard ceilings 45 + 16). The live
driver refuses to spend unless the seal matches, and runs from `git worktree add --detach
<sealed commit>`, never from a working branch.

**What the seal covers** (`lb162x.SEALED`, `SEALED_GLOBS`, `SEALED_DATA`, `prereg.manifest.json`):
this file; the lot module, the analysis, the driver and their tests; this lot's two frozen
orders (`opus-ids.txt`, `uncovered-ids.txt`); lb162's recordings this lot reads (`ids.txt`,
`covered-ids.txt`, `jev-scored.jsonl`, `jev-answers-j14-L.jsonl`, `sonnet-rows.jsonl`); every
module of the package (`src/sanchopanza/**/*.py`); every benchmark file the driver loads (lb162's
and h2h's runners, L4/L6's code, `b3conf_power.py`, `meter.py`, the hooks, the S line,
`launch.ps1`); LongBench's `data.json` and both `tasks.jsonl`; and one aggregate sha256 of the
162 prepared documents. A test checks that every file the driver loads is sealed.

## The questions

Lot lb162 (`docs/results/2026-10-15-lb162`, sealed c483beb) routed 162 fresh LongBench v2 tasks:
Jev 1.14 with the long window answered alone where its top choice was >= 0.6 (60 tasks, 37 %),
Sonnet 5.5 the rest. It was "no peor" than Sonnet alone at -10 points (+1.2, [-3.1, +5.6]),
"sustituye". Two things were left open:

1. **Phase B (primary).** With **Opus 5.5** as the expensive model, is the hybrid (Jev on the 60
   covered, Opus elsewhere) no worse than Opus alone by more than 10 points? And how much of
   Opus's cost does it save, measured?
2. **Phase A (secondary).** lb162's saving was an estimate: Sonnet never ran on the 102
   uncovered tasks. **How much of Sonnet's cost does the router save, measured?** And how
   accurate is Sonnet alone on all 162?

**No Jev call.** Jev's answers, grades and costs are lb162's recordings, used as committed. The
code holds their sha256 (`lb162x.RECORDED`: `jev-scored.jsonl`, `covered-ids.txt`,
`sonnet-rows.jsonl`) and refuses the lot if any differs; the preflight also replays
`jev-answers-j14-L.jsonl` for free and refuses unless it gives `jev-scored.jsonl` exactly.

## Tasks and order

- **Phase B:** all 162 tasks of lb162's `ids.txt` (none failed, none unasked), in
  `random.Random(20261016).shuffle` order of the sorted ids, frozen in `opus-ids.txt`. Bands:
  38 short, 88 medium, 36 long; 50 easy, 112 hard.
- **Phase A:** the 102 of them not in lb162's `covered-ids.txt` (asked, top choice < 0.6),
  shuffled the same way, frozen in `uncovered-ids.txt`. Bands: 20 short, 53 medium, 29 long; 31
  easy, 71 hard; 789,000 characters a document on average (the covered 60: 443,000).
- Both files are derived by code (`lb162x.derive`) from lb162's rows; the driver refuses a file
  that is not the derivation. A ceiling stop therefore leaves out a random subset.

## The arm (both phases)

Arm N of lb162's phase S, unchanged (`h2h_longdoc.py`'s session through `h2h_lb162x.py`):
- the model in Claude Code 2.1.287, pinned and first on PATH (`launch.ps1`,
  `DISABLE_AUTOUPDATER=1`); phase B `claude-opus-5-5`, phase A `claude-sonnet-5-5`;
- a clean user per session: a new `CLAUDE_CONFIG_DIR`, the session folder under `C:\sp-runs\h2h`
  (outside the user's home), its own private session file per phase (`lb162x-opus`,
  `lb162x-sonnet`);
- the document copied as `document.txt`, LongBench v2's official 0-shot template, WebSearch and
  WebFetch disallowed, the local hook on every tool;
- graded by the official `extract_answer` on the last line that has one;
- one session per task, one at a time, in the frozen order.

The only change from lb162 is the per-session cap when a phase's money is short (below).

## Order of the phases: B, then A

One driver runs both, in one process: **phase B first**, then phase A once B has ended by
finishing or by its ceiling. B carries the primary verdict, so a pause that the lot cannot
control (the subscription's weekly limit, shared by every session of the account; the clock; a
STOP) falls on the descriptive phase rather than on the verdict. Each phase has its own ceiling,
so running B first takes no money from A. A relaunch skips a phase that has ended and resumes
the other for free (recorded sessions are not asked again).

## Money

Claude Code's list price (`list_usd`, its own rates, `meter.CLAUDE_CODE_RATES`), as in lb162.

| | Phase B (Opus 5.5) | Phase A (Sonnet 5.5) |
|---|---|---|
| Ceiling, hard, in code | **45.00 USD** | **16.00 USD** |
| Full cap a session (`--max-budget-usd`) | 6.00 (`h2h_longdoc.CAPS["OPUS"]`) | 3.00 (arm N's) |
| Worst turn | **8.64** | **4.32** (lb162's) |
| Floor (no session below) | 1.00 | 0.50 |
| Full cap while spent <= | 30.36 | 8.68 |
| Phase stops when spent > | 35.36 | 11.18 |
| Expected | **29.7 USD** | **9.1 USD** |

- **The worst turn**, as in lb162: one turn rewriting the whole 1M-token window to the cache at
  the dearer (1-hour) write rate and answering 32,000 tokens, at Claude Code's rates. Sonnet 5.5:
  1M x 4.0 + 32k x 10 = 4.32 USD (lb162's figure, checked against `meter.CLAUDE_CODE_RATES`).
  Opus 5.5: 1M x 8.0 + 32k x 20 = **8.64 USD**. Both assume a 1M-token window (lb162's constant).
  `--max-budget-usd` stops between turns only, so a session spends at most its cap plus one
  worst turn.
- **The cap of each session** (`lb162x.cap_for`, enforced by `h2h_lb162x.Budget` before each
  session from the phase's recorded sessions plus the reserve of any session started without a
  row): the full cap while the full cap plus one worst turn fits under the ceiling; above that,
  the room left after one worst turn, down to the cent; none below the floor (the phase stops,
  kind `ceiling`, final). The phase loop's own check stops at the same line. **Neither phase can
  pass its ceiling; the lot cannot pass 61 USD.**
- A **reservation row** (the session's cap plus the worst turn) is written before each session.
  A session that dies mid-way keeps that reserve against the ceiling on a resume.
- Why the cap moves: with a fixed cap the reserve (B 14.64, A 7.32) would stop B at 30.36 and
  A at 8.68 spent. Lowering the cap only when money is short
  changes no session that costs what these sessions cost: 109 of the 110 arm N LongBench
  sessions on record cost under 0.41 USD (Sonnet), under 0.65 re-priced at Opus rates (the
  other cost 1.87, 3.15 at Opus rates).
- **Guaranteed at worst** (every session at its cap plus a worst turn): **B 3 sessions, A 2.**
- **Opus's cost a task is an estimate.** No Opus 5.5 session on LongBench exists in this
  repository's records (the 2026-10-06 confirmation and lb162 ran Sonnet only). It is planned as
  lb162's 60 real Sonnet sessions by length band times **2.0**, the highest ratio of Claude
  Code's Opus 5.5 rates to Sonnet 5.5's in `meter.py` (input 4/2, output 20/10, cache writes 5/2.5
  and 8/4; reads 0.2 both): long 0.112, medium 0.213, short 0.182 USD a task, **29.7 USD for the
  162** (0.183 a task). Re-pricing those 60 sessions' tokens at Opus rates gives 1.79 x (1.74 x
  for 2026-10-06's 50), so 2.0 already allows Opus about 12 % more tokens than Sonnet used.
- **Phase A's cost** is lb162's Sonnet sessions by band: long 0.056, medium 0.107, short 0.091,
  **9.1 USD for the 102** (12.5 at 2026-10-06's flat 0.123 a task).

**How often each phase finishes** (`lb162x.py --dry`: the money rule simulated, 5,000 draws, each
session's cost drawn from lb162's 60 session costs of its band, times the phase's scale, times):

| Costs | Phase B: all 162 run | B: sessions (mean, p5) | B: spent | Phase A: all 102 run | A: sessions | A: spent |
|---|---|---|---|---|---|---|
| x 1.0 (the estimate) | **99.9 %** | 162, 162 | 29.7 (p95 32.7) | **99.9 %** | 102, 102 | 9.1 (p95 10.3) |
| x 1.3 (about 2026-10-06's level) | 10 % | 148, 132 | 35.5 | 29 % | 96, 84 | 11.1 |
| x 1.6 | 0 % | 121, 106 | 35.6 | 0.1 % | 79, 66 | 11.3 |

Said plainly: at the costs lb162 measured, both phases finish (B at 2.0 x Sonnet's tokens). If
the sessions cost as 2026-10-06's did, B runs about 148 of 162 and A about 96 of 102, and the
ceiling stops each with a random subset left out; the estimators below handle that. At every
session's mean cost alone (deterministic), B runs all 162 (193 before the guard) and 149 at
1.3 x; A all 102 (126), 97 at 1.3 x.

## Clock

- No phase starts before 08:00 (Windows Update restarts 02:00-08:00), nor when its sessions at
  1.5 x the clock rule's mean, plus 10 minutes, would cross midnight. The clock rule's mean is
  38 s for Sonnet (2026-10-06's, the slower lot) and **60 s for Opus** (no Opus timing on
  record). **Phase B starts between 08:00 and 19:46; phase A between 08:00 and 22:13.** The
  driver checks the first phase to run before anything, and phase A again when B ends; a phase
  the clock refuses is a pause (kind `clock`, exit 5): a relaunch after 08:00 resumes it.
- Before each session (lb162's guard): a stop if it is before 08:00, past the phase's start
  date, or midnight is less than 10 minutes away (kind `clock`, exit 5, a pause).
- **Expected wall time:** phase B about 55 minutes if Opus is as fast as Sonnet was in lb162,
  162 minutes at the 60-s clock mean; phase A about 34 minutes at lb162's time by band, 65 at
  38 s. Start in the morning so both phases end the same day. Attended throughout.

## Stops (kind in `opus-stop.json` / `sonnet-stop.json`, the kind only)

- finished: `done`, exit 0 (the lot: both `done`);
- the ceiling: `ceiling`, exit 1, final (the lot: both over, one at its ceiling);
- a 429 or usage limit ("weekly limit"): `limit`, exit 2. The session is recorded as not run and
  `LIMIT.flag` is written in `C:\sp-runs\lb162x`; a pause, never scored. The owner tells the
  other sessions and deletes the flag to resume.
- the clock: `clock`, exit 5;
- a `STOP` file in `C:\sp-runs\lb162x`: `manual`, exit 6, before the next session.
- A preflight problem (exit 3) starts no session.

Processes are stopped by PID only (`driver.pids`).

## Phase B: primary analysis and verdict (`lb162x_stats.phase_b`)

Over the 162 tasks, the hybrid answers with Jev on the covered tasks and with Opus elsewhere, so

    hybrid - Opus = sum over covered (Jev right - Opus right) / 162

an uncovered task contributing 0. Computed as coverage x the mean gain on the covered tasks that
have an Opus session (`lb162_stats.estimate`, unchanged). That is the sum above when every
covered task has one. If the ceiling leaves some without (the 162 run in a seeded random order),
it is an approximately unbiased ratio estimator; the number of Opus sessions scored and of
covered tasks without one are reported.

**Sessions with no letter.**
- Stopped by the full cap (6.00): wrong, as in lb162 and 2026-10-06.
- Stopped by a **lowered** cap (below 6.00), or ended in an infrastructure error (`is_error`
  without `hit_cap`, wall-clock timeouts included): **not run** in the primary reading (excluded
  like a covered task without a session).
- The registered **sensitivity reading** counts both as wrong. Counting them wrong lowers Opus
  and favours the hybrid, so the primary is the reading less favourable to the hybrid.

**Paired bootstrap** over the 162 tasks, 10,000 draws, seed 20261015, percentile 95 % CI
(`l4_stats.bootstrap`); a resample with covered tasks but none with an Opus session is dropped,
and the number kept is reported. **Exact McNemar** on the covered disagreements (Jev only right
against Opus only right).

**Verdict, fixed now.** The CI's bounds are compared with -0.10 unrounded:
- **"no peor"** if the CI's lower bound is > -10 points;
- **"peor"** if the CI's upper bound is < -10 points;
- **"no concluyente"** otherwise (a bound exactly at -10 points does not clear it);
- **"no medido"** if no CI exists;
- **"pausa"** (no verdict) while a `LIMIT.flag` or `STOP` is in `C:\sp-runs\lb162x`, or phase B
  has not ended by finishing or by its ceiling.

**The product claim** ("sustituye", with Opus 5.5) needs "no peor" **and** coverage >= 20 %
(lb162's rule; coverage is lb162's 60 of 162, 37 %); otherwise "no sustituye".

Over all 162, -10 points at 37 % coverage means Jev may be up to about 27 points less accurate
than Opus on the tasks it covers.

**Power** (`lb162x.power_b`, 2,000 draws, b3conf_power's normal CI, every task with a session;
Jev's recorded grades fixed, Opus right on a share p of the covered tasks): with Opus agreeing
with Jev as Sonnet did in lb162 (right on 23 of the 31 Jev got and 6 of the 29 it missed,
shifted to reach p), "no peor" comes out 99.9 % at p = 0.50, **87 % at 0.60**, 62 % at 0.65,
31 % at 0.70, 12 % at 0.75; with Opus independent of Jev (the widest CI) 95 %, 55 %, 26 %, 7 %,
1 %. "peor" needs Opus right on about 90 % or more of the covered tasks (10 % of draws at 0.90
independent, 51 % at 0.95).
So: if Opus is about as good as Jev on the covered tasks (Jev 51.7 %, Sonnet 48.3 %), the lot
decides; if Opus is clearly better there, "no concluyente" is likely, and that is the answer.

## Phase B: secondary, registered

**The saving of Opus's cost** over the 162 (`lb162x_stats.saving`):

    Opus alone = Opus on the 60 covered + Opus on the 102 uncovered
    hybrid     = Jev on all 162 (lb162) + Opus on the 102 uncovered
    saving share = (Opus alone - hybrid) / Opus alone

each group's cost its size times its measured mean (a ratio estimator under a ceiling stop).
Paired bootstrap as above. **Reading, fixed now** (bounds unrounded): **"ahorra"** if the CI's
lower bound is > 0; **"no ahorra"** if its upper bound is <= 0; **"no concluyente"** otherwise;
**"no medido"** without a CI; **"pausa"** as above. An infrastructure error is excluded from the
cost (counted at its cost in a sensitivity reading); a lowered-cap stop counts at its cost (at
6.00 in a second sensitivity reading).

## Phase A: secondary, registered (`lb162x_stats.phase_a`)

**The measured saving of Sonnet's cost** over the 162, as the Opus one with Sonnet: Sonnet on
the 60 covered from lb162's sessions, Sonnet on the 102 from this lot, Jev from lb162. Same
estimator, bootstrap, readings ("ahorra", "no ahorra", "no concluyente", "no medido", "pausa"
while a flag is present or phase A has not ended by finishing or by its ceiling) and
sensitivity readings (full cap 3.00). Reported beside it: where lb162's estimate of 26.7 %
falls ("inside", "above" or "below" the CI). The README then gives the measured share and its
CI in place of the estimate. Precision expected: about +/- 10 points around 25-35 %.

## Descriptive, not registered as verdicts

- **Sonnet alone on all 162** (lb162's 60 plus this lot's 102): right, accuracy, Wilson 95 %;
  the hybrid's accuracy; and lb162's hybrid minus Sonnet re-read with the same bootstrap. An
  uncovered task adds 0, so the re-read equals lb162's +1.2 points while lb162's 60 sessions
  stand: **lb162's verdict stands as sealed**; this is a check, not a new verdict.
- **Opus alone on the 162**: right, accuracy (Wilson), on the covered and the uncovered; the
  hybrid's accuracy; USD per right answer for Opus alone and the hybrid.
- On the uncovered tasks, for each model: Jev right against the model right (exact McNemar):
  what Jev alone would have given up where it was unsure.
- Opus against Sonnet on the tasks both answered (exact McNemar).
- Sessions per phase: count, total, mean, median and maximum cost; infrastructure errors; caps
  hit; caps below the full one, how many were hit, and lowered-cap stops without a letter.
- Every reading by LongBench length band and by difficulty (small bands, none a finding).
- b3conf_power's normal-approximation CI beside the bootstrap (phase B, with every covered task
  answered by Opus).

## Commands

From the detached worktree of the sealed commit (`PYTHONPATH=src`, the main checkout's python):

```
python benchmarks/jev114/lb162x.py --dry           # free: both phases, money, clock, power
python benchmarks/h2h/h2h_lb162x.py --dry          # free: the same plus what each phase spent
python benchmarks/h2h/h2h_lb162x.py --preflight    # free (needs the subscription token)
python benchmarks/jev114/lb162x.py --seal
powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_lb162x.py -RunnerArgs "--lot lb162x" -Pin $env:USERPROFILE\.cache\sanchopanza\claude-pin\2.1.287 -KeysEnv <path to the keys .env that SANCHOPANZA_KEYS_ENV names> -Log C:\sp-runs\lb162x\driver.log -PidFile C:\sp-runs\lb162x\driver.pids
python benchmarks/h2h/h2h_lb162x.py                # rows without text, both phases
python benchmarks/jev114/lb162x.py                 # the analysis, summary.json
```

`-KeysEnv` passes the path (never the content) of the file that holds the subscription token;
this lot makes no Jev call. Public rows (`opus-rows.jsonl`, `sonnet-rows.jsonl`) hold the id,
letter, grade, cost, time, turns, `hit_cap`, `is_error`, Claude Code's `subtype` and the
session's cap. No text.

## What follows

- Phase B "no peor" with coverage >= 20 %: the README says that on long-document multiple-choice
  questions Jev 1.14 with the long window can answer alone above 0.6 and leave the rest to
  Opus 5.5 within 10 points of Opus alone, at the measured saving of Opus's cost. "peor" says it
  cannot; "no concluyente" or "no medido" says this evidence does not decide.
- Phase A "ahorra": the README replaces lb162's estimated saving with the measured share and its
  CI, for Sonnet 5.5. "no concluyente" or "no medido": it stays an estimate, said so.
- Nothing in `policy.py`, `DEFAULT_MODEL` or `install` changes in this lot.

**Not done:** other cuts, Jev 1.13, any S arm, a free-text long-document set (where Jev would
judge a cheaper model's answer instead of answering; it needs its own pre-registration and a
calibration check first).
