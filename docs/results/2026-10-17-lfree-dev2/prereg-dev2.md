# longdoc-free, dev2: the router with the BM25 prefilter before Jev, pre-registration

Instrument commit: `e0e46233a12d0fbfe83a9458066b1f10345f5c8a`

Written 2026-10-17, before any call of dev2. **Not sealed**: an independent review
(`revisor-prereg`) goes first; until `prereg-dev2.sha256` exists this file may change and
nothing may be spent. The owner approved preparing a new dev with the prefilter on 2026-10-17,
after the probe's sealed rule said it was worth preparing (`../2026-10-17-lfree-bm25-dry/`),
within the lot's approvals: Claude, **what has really been spent plus the caps of what is left
never exceeds 105 USD** (8.196 spent, the dev's smoke, N and Haiku arms); Jev, **14.30 USD for
the lot** (1.6072 spent by the dev, 0.0346 by the probe).

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
   probe or dev2, the hours 00:00 to 08:00, and its local values unset.
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

## 4. Phase H2: Claude Code, H alone (paid, the subscription)

- **Stage dev2** of `benchmarks/h2h/h2h_lfree.py`, one phase `D2H` (`lfree-dev2-haiku`): **H
  only**, Haiku 4.5 (`claude-haiku-4-5-20251001`) in clean Claude Code 2.1.287 (the pinned copy
  first on PATH, `DISABLE_AUTOUPDATER=1`), a clean user and an empty `CLAUDE_CONFIG_DIR` per
  session, the web taken away, the local hook, the same tools, the dev's prompt and answer rule;
  `document.txt` is phase J2's kept passages. The 41 dev questions in the dev's seeded order
  (`random.Random(20261018)`).
- **Money:** session cap 1.50 (the dev's for Haiku), ceiling **5.00**, worst turn 2.16, floor
  0.30 (`cap_for`, lb162x's rule). The room before a stop, 5.00 − 2.16 − 0.30 = 2.54, holds 41
  sessions at the dev H's 95th percentile (0.0534 USD, above 1.5 times its mean 0.0313): 2.19
  (a test). **At most 5.00 USD**, expected about 1.3 (the dev's H; the passages are shorter).
- **No smoke.** The dev's smoke tested the Sonnet path; this phase is the dev's Haiku arm with
  another file, on the same pinned Claude Code, and the dev's 123 Haiku sessions were all served
  by Haiku, none at its cap. The guard still stops the phase on an outage, three infrastructure
  failures in a row or a session another model served (lb162x_guard).
- **Refusals before any session** (`refusal("dev2")`): the seal (`prereg-dev2.sha256`); the
  instrument (`src`, `benchmarks`, `ids.json` and the reused rows) unchanged since its commit;
  the pinned input; the seal commit itself, detached and clean; the pinned `claude` first on
  PATH; the dev novels present and equal to their keys; **every dev question's dev2 passages
  present and as long as `jev-dev2.jsonl` says** (written only by a complete phase J2);
  `launch.ps1` taking the runner; no `LIMIT.flag`; not before 08:00, and the phase refused when
  its sessions (41 x 45 s x 1.5 + 600 s, about 56 minutes) would cross midnight.
- **Stops:** STOP in `C:/sp-runs/longdoc-free`; a usage limit (429, "weekly limit") stops the
  phase and writes `LIMIT.flag` (a pause, never a result); an outage or three infrastructure
  failures in a row stop it.

### The design choice: N, H0 and HC are the sealed dev's sessions, reused

dev2 reads N (Sonnet 5.5, the whole novel), H0 (Haiku 4.5, the whole novel) and HC (closed book)
from `../2026-10-16-longdoc-free/dev-sonnet-rows.jsonl` and `dev-haiku-rows.jsonl` (sha256 with
LF line ends `6b83cb45...` and `0b52f1c8...`, `dev2_read.REUSED_SHA256`; a changed file refuses
the reading, and both files are in both phases' instrument). The dev's own H rows are not read.

- **Why it is valid.** The same 41 questions, the same prompt and answer rule, the same pinned
  Claude Code 2.1.287, the same model ids, run on 2026-10-17, the day dev2 is prepared. The
  prefilter changes only H's file and the gate's p; N, H0 and HC do not depend on Jev.
- **The risk ("la corrida es la unidad").** One session per question and arm, and a session
  repeated differs: here N's draw is the dev's, H's is new. The router R takes N's own row
  wherever the gate does not cover, so R − N is exactly 0 there, and run-to-run variance enters
  R − N only through the covered questions' H − N. Pairing a new H with an old N adds no bias in
  expectation (two independent draws, as a rerun would be), but dev2's cut is chosen against the
  same N draw the dev chose its cut against, and anything that drifted since (the served model,
  the service) would show up only in H. dev2 cannot tell that drift from the prefilter's effect.
- **The alternative, for the reviewer and the owner:** rerun N too, a phase like the dev's
  (41 Sonnet sessions, cap 3.00, ceiling 12.00) and its smoke (0.80 + 4.32): **17.12 USD more at
  most**, about 2.9 expected, the lot then at most 8.196 + 5.00 + 17.12 = 30.3 of 105. It buys a
  fresh N paired with the fresh H, nothing on power (the SD of R − N is per question either
  way). It is not built; choosing it means a new instrument commit before the seal.

## 5. The reading (`dev2_read.py`; the dev's rules, `dev_read.read`, `stats.py`)

Applied to the per-question rows (dev2's gate p and H, the dev's N, H0 and HC; Jev's cost a
question is dev2's ledger spend over 41, as in the dev), before any confirmation call:

1. **Read at all:** at least 35 of the 41 questions complete; else dev2 is reported, nothing
   sealed.
2. **Memory:** HC's mean F1 within 10 points of N's: no confirmation (HC is the dev's, 1.0
   against 55.0: this cannot fire).
3. **The cut:** the lowest of 0.5, 0.6, 0.7, 0.8, 0.9 that covers at least 29 % and 8
   questions and whose covered questions have H − N ≥ −2 F1 points. None: the router is not
   confirmed, no confirmation is sealed. (At dev2's projected Jev, 0.0115 a question, the
   break-even coverage is 0.0115 / (0.0693 − 0.0313) ≈ 30 %; the dev's 29 % is kept.)
4. **n for the confirmation's 310 questions:** 80 % power for R − N > −5 at one-sided 2.5 %,
   with dev2's SD of R − N at the cut, the design effect of its 8 novel clusters (at least 1.5)
   and dev2's R − N as the true difference (at most 0). Above 310: no confirmation on En.QA.
5. **Money** (two inputs changed, decided now, before any dev2 data):
   - **The confirmation's Haiku phase is H alone, no H0.** By the dev's formula with H0 the
     confirmation does not fit 105 whatever dev2 finds (H0's 95th percentile, 0.2276 USD, makes
     310 H0 sessions alone 70.6 USD; the dev's reading: 143 USD). H0 answers attribution (does
     Jev's passage selection help Haiku over the whole novel?), which the dev already read
     (H − H0 −0.5 [−10.2, +9.3]), and neither confirmation hypothesis (R − N, then H − N) needs
     it. The design left this to the owner ("decides whether H0 runs in the confirmation");
     the with-H0 figure is reported beside it (`confirm_money_with_h0`). **The owner confirms
     this before the seal.**
   - **The confirmation's Jev cap is what the lot's 14.30 leaves** after every Jev ledger of the
     lot (dev, probe, dev2), not the dev's 12.50 (which, with dev2, would pass 14.30). The
     confirmation's Jev plan at K = 200 is its dry run's stub estimate, 2.2152 USD, times 1.417:
     **3.139** (`dry.json`); it fits when that plan, and the plan times dev2's real over its own
     plan (0.347 x 1.417) times 1.2, are under the cap.
   - Unchanged: per Claude phase, 310 sessions at the larger of 1.5 times the arm's mean and its
     95th percentile (N the dev's, H dev2's), plus one worst turn and the floor; Claude fits
     when the lot's real spend (the dev's and dev2's, every session and open reservation) plus
     these ceilings is at most 105.
   **A confirmation is sealed** (its own pre-registration and the owner's approval) only when
   rules 1-4 pass and both monies fit; otherwise the owner decides.

**Reported** (`dev2.json`): the cut; R − N and the saving at the cut with percentile bootstraps
resampling novels (10,000 draws, seeded); every cut's coverage, covered questions, covered
H − N, R − N and saving (point estimates); n needed against 310; both monies; the
confirmation's expected money at dev2's means (Claude without and with H0, Jev at dev2's cost a
question); Jev's real cost a question from the recording (mean, 90th percentile, dearest);
dev2's H mean F1 beside the dev's H; the dev's descriptive controls (median answer words, answer
lines, 12-token F1, gold in the kept passages, sessions at their cap).

### What the dev's rows say before dev2 runs (a projection, not a measurement)

The dev's rows with Jev at the probe's 0.0115 USD a question in place of 0.039 (the gate's p and
H as the dev measured them; dev2 will move both):

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
| Claude phase H2 | **5.00** | about 1.3 | |
| Claude, the lot (8.196 spent + H2's cap) | **13.20** | 9.5 | 105 |
| Not built: N rerun with its smoke | +17.12 | +2.9 | |

A confirmation, if sealed, comes with its own pre-registration and money. At dev2's projected
numbers (N 0.0693 and 0.1307 at its 95th percentile, H as the dev's), without H0: Claude ceilings
45.34 + 19.01 on top of about 9.5 spent, about 74 of 105; Jev 3.14 planned against 11.66 left.

## 7. Departures from the sealed dev and from the design

- **The prefilter** (BM25, K = 200, before the tournament): the instrument under test.
- **N, H0 and HC reused** from the sealed dev (section 4), not rerun.
- **No smoke** (section 4).
- **The confirmation's money rule**: H alone in its Haiku phase and its Jev cap at what the lot
  leaves (section 5.5); every other rule and threshold is the dev's.
- **Ids 0, 7 and 375 asked again**, not replayed from the probe's recording.
- **One launch only** for J2 (the probe's rule), where the dev had one launch and one relaunch.

## 8. What dev2 does not say

It reports no verdict: 41 questions on 8 novels, one session per question and arm, its cut and
its n chosen on it and never reused as evidence. N, H0 and HC are one earlier draw. Sonnet 5.5
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
4. **Phase J2**, between 08:00 and midnight, by WMI from outside the Claude Code session
   (`New-CimInstance Win32_ProcessStartup -ClientOnly -Property @{CreateFlags=[uint32]512}`,
   then `Invoke-CimMethod Win32_Process Create` with `cmd.exe /c <run worktree>\longdoc-free-jev-run.cmd dev2`
   and the run worktree as its directory). Its log: `longdoc-free-dev2/launch.log` under the
   user's sanchopanza cache; `paid-exit 0` then `rows-exit 0` means the passages and
   `jev-dev2.jsonl` are written. Any other exit: dev2 not run, stop here.
5. **Phase H2**, from the same run worktree, only when no other lot draws on the subscription and
   before about 23:00: `powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_lfree.py
   -RunnerArgs "--stage dev2" -Pin %USERPROFILE%\.cache\sanchopanza\claude-pin\2.1.287 -KeysEnv
   <path> -Log C:\sp-runs\longdoc-free\dev2-driver.log -PidFile
   C:\sp-runs\longdoc-free\dev2-driver.pids`. Watch the log and the PIDs; stop only by PID.
6. Free, after: `python benchmarks/h2h/h2h_lfree.py --stage dev2` (the public rows), the
   recording gzipped, `jev-dev2.jsonl`, `dev2-haiku-rows.jsonl` and its stop file copied to
   another checkout (never `git add -A` in the run worktree: its launcher holds the key file's
   path), then `python -I benchmarks/longdoc_free/dev2_read.py` writes `dev2.json`.

## 10. The seal

`prereg-dev2.sha256`, written by the command of section 9.1, binds this file, the launcher and,
through the instrument commit named at the top, the code, the frozen ids and the reused rows.
It is **not written yet**: the independent review comes first.
