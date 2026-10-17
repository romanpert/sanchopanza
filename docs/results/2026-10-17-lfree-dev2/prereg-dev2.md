# longdoc-free, dev2: the router with the BM25 prefilter before Jev, pre-registration

Instrument commit: `1dc76910ed5d19acf5d257204a381a3e1df20f1b`

Written 2026-10-17, before any call of dev2. **Not sealed**: reviewed by `revisor-prereg`
(section 11); until `prereg-dev2.sha256` exists this file may change and nothing may be
spent. The owner approved preparing a new dev with the prefilter on 2026-10-17,
after the probe's sealed rule said it was worth preparing (`../2026-10-17-lfree-bm25-dry/`),
within the lot's approvals: Claude, **what has really been spent plus the caps of what is left
never exceeds 105 USD** (8.196 spent, the dev's smoke, N and Haiku arms); Jev, **14.30 USD for
the lot** (1.6072 spent by the dev, 0.0346 by the probe). On a first draft that reused the
dev's N, the owner chose on 2026-10-17 to **run N again** in dev2 and to keep reusing only H0
and HC.

This dev2 has its own folder, not the dev's: the dev's folder holds a sealed, read and published
phase (`../2026-10-16-longdoc-free/`), and dev2 is another instrument (the prefilter), another
lot and another seal; its rows would otherwise sit beside the dev's under similar names. It reads
the dev's rows from there (section 4) and writes nothing there.

## 1. Question

The dev found the router (Jev's passages and Truth gate, Haiku 4.5 on the passages where the
gate says they suffice, Sonnet 5.5 with the whole novel elsewhere) 25 % dearer than Sonnet alone:
Jev cost 0.039 USD a question, more than sending covered questions to Haiku saves. The probe
measured 0.0115 USD a question on 3 questions with a free BM25 shortlist of 200 pages before
Jev's page tournament. On the same 41 dev questions, with the prefilter: does the router now save
money against N without losing F1 beyond the dev's rule, and is a confirmation worth sealing?
Like the dev, dev2 is not a verdict.

## 2. Data

The dev's: ∞Bench En.QA (`longbook_qa_eng`, revision `90f0394`, the pinned sha256 of
`pool.py`), the frozen `../2026-10-16-longdoc-free/ids.json`, **the 41 dev questions on 8
novels** (`jev_phase.phase_ids("dev2")`, the dev's ids), graded by ∞Bench's own `qa_f1_score`
on the answer line, the dev's answer rule unchanged. The confirmation's 310 questions stay
unread.

## 3. Phase J2: Jev (paid, Jev only)

- **Per question**, `jev_phase.ask` with `prefilter_k = PROBE_K = 200`, fixed in code
  (`FIXED_K["dev2"]`), exactly the probe's path (a test pins its output and calls byte for byte
  to the code that ran the probe): the novel in pages of at most 900 characters; the 200 pages
  BM25 scores best for the question (`pages.bm25_shortlist`), in the novel's order, and no
  other; `Squire.select_passages` over them with `fit_chars = 60,000`, the free order, no
  `max_calls`; then the gate, one Truth: "`passages` are excerpts of one novel. They state
  everything needed to answer `question`." Its p is the gate. The kept text is H's file,
  `PRIVATE/dev2/passages/<id>.txt` (`jev_phase.passages_path("dev2", id)`).
- **Jev** `jev-1.13.0`, no long context; B6's asker as the dev and the probe (recording first,
  one live call on a miss, never retried, at most 4 in flight, an identical call asked once,
  stopped by a cap refusal, an outage, another model or three failures in a row; a 429 is not
  retried).
- **Lot** `longdoc-free-dev2` (`jev_phase.lot("dev2")`): recording
  `fixtures/longdoc-free/jev-dev2.jsonl`, ledger `longdoc-free-dev2/ledger.jsonl` under the
  user's sanchopanza cache, prereg this file. Its instrument is the dev's (`src`,
  `benchmarks/longdoc_free`, `benchmarks/b6_es`, `benchmarks/paid_once.py`, `ids.json`) **plus
  the two dev row files dev2 reuses** (section 4).
- **The probe's recording is not replayed.** Ids 0, 7 and 375 are asked again (about 0.035 USD),
  so every question's Jev comes from one launch, one ledger and one model state.

### Money

| | USD |
|---|---|
| The probe's real Jev: mean, dearest question (3 questions) | 0.0115, 0.0203 |
| Expected, 41 x the probe's mean / the dry oracle (`bm25-dry.json`, K = 200) | 0.47 / 0.444 |
| Dry run, the stub's pessimistic estimate (`jev_phase.py dry --phase dev2`, `dry.json`) | 0.347 |
| **Plan for the room check:** max(0.347 x 1.417, 0.444) | **0.492** |
| Every question at the probe's dearest, 41 x 0.0203 | 0.83 |
| **The ledger's cap** (`CAP_USD["dev2"]`) | **1.00** |
| Bound on the overshoot past it (4 calls in flight x 0.000645, the dev's dearest bill) | 0.0026 |
| The preflight, outside the ledger | 0.000013 |
| **Worst total** | **1.0026** |

- **Why 1.00.** Set from real Jev, not the stub (the dev's lesson: its stub undercounted the
  tournament by 39 % and the first launch met its cap): 1.2 times every question at the probe's
  dearest (0.83), 2.1 times the expected 0.47, 2.0 times the plan. A cap stop would leave dev2
  "not run" for good (one launch), so the cap sits well above any realistic spend. The
  arithmetic ceiling (every question's tournament at its 28 calls and the dev's largest
  sentence stage, 41 x 0.031 = 1.27) needs every question at the dev's single worst, and is not
  what the cap is for: the ledger, not the arithmetic, is the guarantee, as in the probe.
- **Lot's Jev:** 1.6072 + 0.0346 + 1.0026 = **2.644** of the owner's 14.30, leaving 11.66 for a
  confirmation (section 5.5).
- **Balance:** before the launch the owner checks the TypeSafe balance holds at least
  **1.10 USD** (a manual check: the preflight detects only zero; a 402 mid-run ends dev2 as not
  run, for good).

### Refusals (each spends nothing), in the order the code checks them

1. The launcher (`longdoc-free-jev-run.cmd dev2`) refuses a phase other than dev, confirm,
   probe or dev2, the hours 00:00 to 08:00, **dev2 from 22:00** (J2 takes minutes: the dev's
   2,779 calls took 4; dev2 plans about 830), and its local values unset.
2. `jev_phase.py paid --phase dev2`: the launcher given is the lot's (digest, local values
   masked).
3. The plan (0.492) fits in what the ledger has left (1.00 before any spend).
4. The seal: `prereg-dev2.sha256` holds this file's sha256 and the launcher's.
5. HEAD descends from the instrument commit and nothing under the instrument paths differs
   from it or is uncommitted; the ∞Bench file has its pinned sha256.
6. HEAD detached at the commit that sealed `prereg-dev2.sha256`, the checkout clean except the
   launcher filled in place.
7. Under the lot's lock, **one launch only**: refused after any earlier launch of this lot,
   whatever it did, when its ledger holds any spend, or when its recording (plain or `.gz`)
   holds any answer (`jev_phase.may_launch`, `ONE_LAUNCH`).
8. The key from the file the launcher names, never printed; then, inside the run's event loop,
   `jev-preflight` for `jev-1.13.0`, and only then the first call.

**Not run.** If the launch does not end with every call answered (the cap, a 402, a 429, an
outage, another model, three failures, one isolated failure, a kill), the launcher does not run
`rows`, no passages are written, no Claude session runs (stage dev2 refuses without them), and
dev2 is reported as not run, with what was spent. There is no relaunch. The owner accepted this
risk with the one-launch design of the probe; it is the same here.

## 4. The Claude Code phases (paid, the subscription): smoke, N, then H

**Stage dev2** of `benchmarks/h2h/h2h_lfree.py`, the dev's design: one phase per model, run in
the dev's order (its smoke, then Sonnet's phase, then Haiku's), not N and H interleaved per
question, because the dev ran them that way and each model phase reserves its own worst turn.
Every session is one headless Claude Code 2.1.287 session (the pinned copy first on PATH,
`DISABLE_AUTOUPDATER=1`), a clean user and an empty `CLAUDE_CONFIG_DIR`, the web taken away, the
local hook, the same tools, the dev's prompt and answer rule. The 41 dev questions in the dev's
seeded order (`random.Random(20261018)`).

| Phase | Sessions | Arm, model, `document.txt` | Session cap | Ceiling | Worst turn | Floor | Most |
|---|---|---|---|---|---|---|---|
| `S2` smoke (`lfree-dev2-smoke`) | 1 | N on the first dev question (the dev's smoke question) | 0.80 | 0.80 | 4.32 | 0.80 | **5.12** |
| `D2N` (`lfree-dev2-sonnet`) | 41 | N: Sonnet 5.5 (`claude-sonnet-5-5`), the whole novel | 3.00 | 12.00 | 4.32 | 0.50 | **12.00** |
| `D2H` (`lfree-dev2-haiku`) | 41 | H: Haiku 4.5 (`claude-haiku-4-5-20251001`), phase J2's kept passages | 1.50 | 5.00 | 2.16 | 0.30 | **5.00** |

- **Money** (lb162x's rule, `cap_for`: a session gets its cap while cap plus one worst turn fits
  under the phase's ceiling; below the floor the phase stops, kind `ceiling`). The smoke and N
  have the dev's exact caps and ceilings. Each ceiling holds its 41 sessions at the larger of
  1.5 times the dev's measured mean and its 95th percentile, after one worst turn and the floor
  (tests): N 12.00 − 4.32 − 0.50 = 7.18 against 41 x 0.1307 = 5.36; H 5.00 − 2.16 − 0.30 = 2.54
  against 41 x 0.0534 = 2.19. The smoke's cap reserves no worst turn, so its most is 0.80 +
  4.32. **At most 22.12 USD**; expected about 4.2 (the dev's smoke 0.10, N 41 x 0.0693 = 2.84,
  H 41 x 0.0313 = 1.28; the passages are shorter than the dev's).
- **The smoke** must pass (a Sonnet session above 0 USD that ended with an answer or at its cap,
  so a smoke at its cap passes, as in the dev: it tests the path, not the answer) before phase N
  starts; a failed smoke stops the stage (`smoke`, a test), its 0-USD rows voided so a resume
  asks it again. Its `usd_by_model` is read by hand for a subagent on another model, as in the
  dev.
- **Refusals before any session** (`refusal("dev2")`): the seal (`prereg-dev2.sha256`); the
  instrument (`src`, `benchmarks`, `ids.json` and the dev rows it reads) unchanged since its
  commit; the pinned input; the seal commit itself, detached and clean; the pinned `claude`
  first on PATH; the dev novels present and equal to their keys; **every dev question's dev2
  passages present and as long as `jev-dev2.jsonl` says** (written only by a complete phase
  J2; so no Claude session, N's included, runs without a complete J2); `launch.ps1` taking the
  runner; no `LIMIT.flag`; not before 08:00; and **the owner's lot rule** (`lot_problem`, a
  test): what every phase of the lot has really spent plus the most the phases left can spend
  (each one's ceiling, a smoke's cap plus a worst turn) at most 105 USD (at the first start:
  8.196 + 22.12 = 30.32).
- **Midnight:** the start budgets every session left at the slowest phase's mean (60 s) times
  1.5, plus 600 s (`clock_budget_s`, lb162's rule): 83 x 60 x 1.5 + 600 = **8,070 s, 2 h 14.5
  min**, so the stage is refused if started **after 21:45** (a test); each phase checks its own
  sessions again at its start, and no session starts within 10 minutes of midnight. The dev's
  measured sessions put the real run near 25 minutes (N 19.7 s and H 14.2 s a session).
- **Stops:** STOP in `C:/sp-runs/longdoc-free`; a usage limit (429, "weekly limit") stops the
  stage and writes `LIMIT.flag` (a pause, never a result); an outage or three infrastructure
  failures in a row stop the phase (lb162x_guard).
- **Pauses and resumes** (decided for the owner before the seal). A paused stage (a 429 and its
  `LIMIT.flag`, a STOP, the clock or midnight, an outage) **may be resumed from the same seal**,
  by the same launch command from the same run worktree: phases already final are skipped,
  sessions already recorded are kept, and only what is left runs, with the same refusals (the
  lot rule included) and the same caps. A weekly-limit 429 waits for the limit to reset (the
  owner removes `LIMIT.flag` then); STOP is removed by hand. Nothing else is relaunched: J2 has
  its one launch (section 3). **Each phase's session dates are reported** (`session_dates`, from
  its reservations), and whether N's and H's sessions all ran on one day
  (`n_and_h_same_day`); if they did not, that is reported as such, beside the result, and
  changes no rule and no verdict.

### N runs again; H0 and HC are the sealed dev's, reused

- **N is dev2's own** (the owner's choice): R − N, the cut, n and the saving pair dev2's H with
  dev2's N, both drawn with the same instrument and seal, on one day unless a pause spreads
  them (reported, above). A drift since the dev (the served model, the service) now shows in
  both arms of R − N, not only in H.
- **H0 and HC are reused** from `../2026-10-16-longdoc-free/dev-haiku-rows.jsonl` (sha256 with
  LF line ends `0b52f1c8...`). **They enter no R − N and no decision on the router**: HC only the
  memory rule (section 5.2), H0 only the with-H0 money figure, which is reported and does not
  decide (section 5.5), and the descriptive controls. One more role, mechanical: a question
  enters the reading's rows only with N, H and H0 all present (`dev_read.stats_rows`, unchanged);
  the dev's H0 has all 41 (`dev.json`: 41 of 41 complete), so H0 removes no question. The reuse
  risk (one earlier draw) therefore touches description only.
- **The dev's N is read for one descriptive figure**, N(dev2) − N(dev) on the same 41 questions
  (`n_rerun`: the mean in points with the novel bootstrap, the SD of the per-question
  difference, how many questions moved, both runs' cost): the run-to-run variance of the arm,
  measured once because both draws exist. It is not planned for a verdict and decides nothing.
  `dev-sonnet-rows.jsonl` (`6b83cb45...`) is pinned for it. Both dev row files are in both
  phases' instrument (`jev_phase.DEV_ROWS`) and a changed file refuses the reading
  (`dev2_read.REUSED_SHA256`). The dev's H is read only for its mean F1 beside dev2's.

## 5. The reading (`dev2_read.py`; the dev's rules, `dev_read.read`, `stats.py`)

**When it reads.** `dev2_read.py` first checks its own code: HEAD descends from the instrument
commit above and nothing under `src`, `benchmarks` (the reading imports `meter.py`,
`jev114/lb162x.py` and `browse/phase.py` besides `longdoc_free`, `h2h` and `paid_once.py`),
`ids.json` or the two dev row files differs from it or is
uncommitted (`require_reading_instrument`, paid_once's check); otherwise it refuses before
reading anything. So the reading runs in a checkout whose instrument files equal the
instrument commit (for instance main after the merge, while those files are unchanged); later
changes there mean reading from a worktree at the instrument. It reads nothing either
(`status` "not read", no confirmation sealed) while a `LIMIT.flag` or STOP is in
`C:/sp-runs/longdoc-free` or any of S2, D2N and D2H lacks a final kind (`h2h_lfree.final_kind`:
a smoke that passed, a phase done or at its ceiling) (`pause_reasons`, tests for each case).
Without a complete J2 it reports "not run".

Applied to the per-question rows (dev2's gate p, N and H; the dev's H0 and HC; Jev's cost a
question is dev2's ledger spend over 41, as in the dev), before any confirmation call:

1. **Read at all:** at least 35 of the 41 questions complete; else dev2 is reported, nothing
   sealed.
2. **Memory:** HC's mean F1 within 10 points of N's: no confirmation (HC is the dev's, 1.0
   against the dev's N 55.0: it fires only if dev2's N falls under 11).
3. **The cut:** the lowest of 0.5, 0.6, 0.7, 0.8, 0.9 that covers at least 29 % and 8
   questions and whose covered questions have H − N ≥ −2 F1 points. None: the router is not
   confirmed, no confirmation is sealed. (At dev2's projected Jev, 0.0115 a question, the
   break-even coverage is 0.0115 / (0.0693 − 0.0313) ≈ 30 %; the dev's 29 % is kept.)
4. **n for the confirmation's 310 questions:** 80 % power for R − N > −5 at one-sided 2.5 %,
   with dev2's SD of R − N at the cut, the design effect of its 8 novel clusters (at least 1.5)
   and dev2's R − N as the true difference (at most 0). Above 310: no confirmation on En.QA.
5. **Money** (two inputs changed, decided now, before any dev2 data):
   - **The confirmation's Haiku phase is H alone, no H0. This needs the owner's yes, asked only
     if dev2 seals a confirmation** (before that confirmation's own seal); it changes nothing
     dev2 runs or spends. By the dev's formula with H0 the confirmation does not fit 105
     whatever dev2 finds (H0's 95th percentile, 0.2276 USD, makes 310 H0 sessions alone 70.6
     USD; the dev's reading: 143 USD). H0 answers attribution (does Jev's passage selection help
     Haiku over the whole novel?), which the dev already read (H − H0 −0.5 [−10.2, +9.3]), and
     neither confirmation hypothesis (R − N, then H − N) needs it. The design left this to the
     owner ("decides whether H0 runs in the confirmation"); the with-H0 figure is reported
     beside it (`confirm_money_with_h0`). If the owner says no, the with-H0 money decides.
   - **The confirmation's Jev cap is what the lot's 14.30 leaves** after every Jev ledger of the
     lot (dev, probe, dev2), not the dev's 12.50 (which, with dev2, would pass 14.30). The
     confirmation's Jev plan at K = 200 is its dry run's stub estimate, 2.2152 USD, times 1.417:
     **3.139** (`dry.json`); it fits when that plan, and the plan times dev2's real over its own
     plan (0.347 x 1.417) times 1.2, are under the cap.
   - Unchanged: per Claude phase, 310 sessions at the larger of 1.5 times the arm's mean and its
     95th percentile (N and H dev2's), plus one worst turn and the floor; Claude fits
     when the lot's real spend (the dev's and dev2's, every session and open reservation) plus
     these ceilings is at most 105.
   **A confirmation is sealed** (its own pre-registration and the owner's approval) only when
   rules 1-4 pass and both monies fit; otherwise the owner decides. Such a confirmation needs
   its own instrument too: the code's `confirm` phase is still the dev's, without a prefilter
   (`prefilter_for("confirm")` is None) and with the dev's 12.50 cap (`CAP_USD["confirm"]`),
   so neither runs the router dev2 measures nor fits what the lot's Jev leaves.

**Reported** (`dev2.json`): the cut; R − N and the saving at the cut with percentile bootstraps
resampling novels (10,000 draws, seeded); every cut's coverage, covered questions, covered
H − N, R − N and saving (point estimates); n needed against 310; both monies; the
confirmation's expected money at dev2's means (Claude without and with H0, Jev at dev2's cost a
question); Jev's real cost a question from the recording (mean, 90th percentile, dearest);
dev2's H mean F1 beside the dev's H; N(dev2) − N(dev) on the same questions (`n_rerun`,
section 4: description only); each phase's session dates and whether N and H ran on one
day; the dev's descriptive controls (median answer words, answer
lines, 12-token F1, gold in the kept passages, sessions at their cap).

### What the dev's rows say before dev2 runs (a projection, not a measurement)

The dev's rows with Jev at the probe's 0.0115 USD a question in place of 0.039 (the gate's p, H
and N as the dev measured them; dev2 will move all three):

| Cut | Coverage | R − N (points) | SD of R − N | n needed | Saving |
|---|---|---|---|---|---|
| 0.5 | 82.9 % | −3.03 | 33.7 | 3,443 | +15.3 % |
| **0.6** (the dev's cut) | 80.5 % | −0.59 | 29.9 | **541** | **+14.8 %** |
| 0.7 | 58.5 % | +3.27 | 25.5 | 320 | +2.4 % |
| 0.8 | 22.0 % | +2.51 | 10.8 | 55 | −8.3 % |

So if the gate and H behaved as in the dev, dev2 would turn the router's cost into a saving of
about 15 % at the same cut and **still seal no confirmation**: power, not money, binds. For n
≤ 310 at a design effect of 1.5, dev2's SD of R − N must be at most about **25.7 points** at
R − N ≥ 0, **22.6** at the dev's −0.59 (the dev's: 29.9). That is the most likely outcome, and it
is reported as it comes; it is stated here so that no one reads it as a surprise.

## 6. Money, all of the lot

| | Cap / most | Expected | Approved |
|---|---|---|---|
| Jev phase J2 | 1.00 ledger, **1.0026** worst | 0.44-0.49 | |
| Jev, the lot (dev 1.6072, probe 0.0346, dev2) | **2.644** worst | 2.09-2.13 | 14.30 |
| Claude smoke `S2` (cap 0.80 + one worst turn 4.32) | **5.12** | 0.10 | |
| Claude phase N `D2N` (ceiling, cap 3.00 + worst turn 4.32 inside it) | **12.00** | 2.84 | |
| Claude phase H `D2H` (ceiling, cap 1.50 + worst turn 2.16 inside it) | **5.00** | 1.28 | |
| Claude, dev2 | **22.12** | about 4.2 | |
| Claude, the lot (8.196 spent + dev2's caps) | **30.32** | about 12.4 | 105 |

A confirmation, if sealed, comes with its own pre-registration and money. At projected numbers
(N as the dev's, 0.0693 and 0.1307 at its 95th percentile; H as the dev's), without H0: Claude
ceilings 45.34 + 19.01 on top of about 12.4 spent, about 77 of 105; Jev 3.14 planned against
11.66 left.

## 7. Departures from the sealed dev and from the design

- **The prefilter** (BM25, K = 200, before the tournament): the instrument under test.
- **H0 and HC reused** from the sealed dev (section 4), not rerun; they enter no R − N. N and H
  run again, in the dev's phases (smoke, N, Haiku) with its caps; the Haiku phase runs H alone.
- **The confirmation's money rule**: H alone in its Haiku phase (the owner's yes, asked only if
  dev2 seals a confirmation) and its Jev cap at what the lot leaves (section 5.5); every other
  rule and threshold is the dev's.
- **Ids 0, 7 and 375 asked again**, not replayed from the probe's recording.
- **One launch only** for J2 (the probe's rule), where the dev had one launch and one relaunch;
  J2 also refused from 22:00. The Claude stage may be resumed after a pause (section 4), as the
  driver allows.
- **The lot's Claude rule in code** (`lot_problem` in `refusal`), where the dev checked it by
  hand; and the reading waits for every phase to be final and checks its own code first.

## 8. What dev2 does not say

It reports no verdict: 41 questions on 8 novels, one session per question and arm, its cut and
its n chosen on it and never reused as evidence. H0 and HC are one earlier draw; N(dev2) −
N(dev) is one pair of draws of one arm, a description of its variance, not an estimate to
plan on. Sonnet 5.5
only; Opus 5.5 is a later lot. Nothing about K other than 200, other `fit_chars`, or documents
Claude Code cannot grep as cheaply.

## 9. Launch sequence (after the review, the owner's approval and the seal)

1. Seal: `python -I benchmarks/longdoc_free/jev_phase.py seal --phase dev2` writes
   `prereg-dev2.sha256` (this file and the launcher with its two values as placeholders); commit
   it. That commit is the seal commit S. The command refuses without the instrument commit
   above and never overwrites a different seal.
2. `git worktree add --detach ../sanchopanza-lfree-dev2-run S`; in that worktree's copy of
   `longdoc-free-jev-run.cmd` only, fill `PY` and `SANCHOPANZA_KEYS_ENV`. Nothing is committed in
   that worktree until dev2 ends.
3. The owner checks the TypeSafe balance holds at least 1.10 USD.
4. **Phase J2**, between 08:00 and 22:00 (the launcher refuses outside), by WMI from outside
   the Claude Code session
   (`New-CimInstance Win32_ProcessStartup -ClientOnly -Property @{CreateFlags=[uint32]512}`,
   then `Invoke-CimMethod Win32_Process Create` with `cmd.exe /c <run worktree>\longdoc-free-jev-run.cmd dev2`
   and the run worktree as its directory). Its log: `longdoc-free-dev2/launch.log` under the
   user's sanchopanza cache; `paid-exit 0` then `rows-exit 0` means the passages and
   `jev-dev2.jsonl` are written. Any other exit: dev2 not run, stop here.
5. **The Claude phases** (smoke, N, H), from the same run worktree, only when no other lot
   draws on the subscription, between 08:00 and **21:45** for a full stage (the stage refuses a
   start whose budget would cross midnight: section 4): `powershell -File
   benchmarks/h2h/launch.ps1 -Runner h2h_lfree.py -RunnerArgs "--stage dev2" -Pin
   %USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287 -KeysEnv <path> -Log
   C:\sp-runs\longdoc-free\dev2-driver.log -PidFile C:\sp-runs\longdoc-free\dev2-driver.pids`.
   Watch the log and the PIDs; stop only by PID. A paused stage is resumed by the same command
   (section 4, "Pauses and resumes"), after a weekly limit has reset.
6. Free, after every phase is final: `python benchmarks/h2h/h2h_lfree.py --stage dev2` (the
   public rows), the recording gzipped, `jev-dev2.jsonl`, `dev2-smoke-rows.jsonl`,
   `dev2-sonnet-rows.jsonl`, `dev2-haiku-rows.jsonl` and their stop files copied to another
   checkout (never `git add -A` in the run worktree: its launcher holds the key file's path),
   then, in a checkout whose instrument files equal the instrument commit (section 5),
   `python -I benchmarks/longdoc_free/dev2_read.py` writes `dev2.json`.

## 10. The seal

`prereg-dev2.sha256`, written by the command of section 9.1, binds this file, the launcher and,
through the instrument commit named at the top, the code, the frozen ids and the dev rows it
reads.
It is **not written yet**.

## 11. Independent review (`revisor-prereg`, before the seal)

On the draft at instrument `32d40c7`: **can be sealed, with fixes**, all made in the instrument
above: the reading waits for every Claude phase to be final and for no LIMIT.flag or STOP, and
checks its code against the instrument commit; the pause and resume rule and the session dates
(section 4); J2 refused from 22:00; the lot's Claude rule in `refusal`; a failed dev2 smoke
stops the stage (a test); the confirmation's own instrument and H0's role in which questions
are read (sections 4, 5); the launcher's header on relaunches.
