# Lot lbo8: the longdoc router at the 0.8 cut against Opus 5.5, on fresh LongBench v2 tasks

**Not sealed.** Written 2026-10-16, before any session or call of this lot; nothing has been spent.
The owner's decisions of 2026-10-16 are below (margin, population, exposure). Before the seal: the
launcher's runner list, an independent `revisor-prereg` review against the code, then
`python benchmarks/jev114/lbo8.py --seal` and a commit whose message carries the hash (see "Before
a seal"). The live driver (`benchmarks/h2h/h2h_lbo8.py`) refuses to spend (exit 3) unless the seal
matches, HEAD is detached at the commit whose message carries the seal (`git worktree add --detach
<sealed commit>`), the tree is clean but for this lot's own outputs (`lbo8.checkout_problems`), and
the `claude` on PATH is the pinned build.

**What the seal covers** (`lbo8.SEALED`, `SEALED_GLOBS`, `SEALED_DATA`, `prereg.manifest.json`):
this file; `lbo8.py`, `lbo8_stats.py`, `h2h_lbo8.py` and their tests; `ids.txt`; lb162x's
`opus-rows.jsonl` (the descriptive figures below); everything lb162x sealed (its lot module,
analysis, driver, guard and tests, lb162's runner and recordings, the session runner, the hooks,
the S line, `launch.ps1`); every file of the package; LongBench's `data.json`, the 2026-10-06 draw
(`tasks.jsonl`, where the smoke task comes from) and this lot's `lbo8/tasks.jsonl`; the pinned
Claude Code build (`~/.cache/sanchopanza/claude-pin/2.1.287/claude.exe`); and one aggregate sha256
of the 78 prepared documents. A test checks that every file the driver loads is sealed.

## Owner's decisions (2026-10-16)

- **Margin: −5 points** (`lbo8.MARGIN = -0.05`). Why: lb162x already licenses the 0.6 cut at −10
  with 29.5 % of Opus's cost saved. The 0.8 cut saves about a third of that (10.6 % on lb162x),
  so it only earns a place with a clearly tighter claim. −5 is the tightest margin the 78 tasks
  allow: Tango's floor at 78 tasks is −4.7 (see Power). The owner accepts the power that follows:
  about 62 % if 0.8 behaves as it did on lb162x (57-59 % once "no medido" is counted, see
  Power), 17 % if it disagrees with Opus as 0.6 did. What
  a pass licenses: Jev up to about 30 points less accurate than Opus on the ~17 % of tasks it
  answers.
- **Population: the 78** in `ids.txt`.
- **Exposure: 31 USD at worst** (expected about 8.1 USD). Approved above the 10 USD line. The
  caps in code add to 22.36 (smoke 0.80, J 0.20, phase O 21.36); `--max-budget-usd` cuts only
  between turns, so the smoke can pass its 0.80 by one worst turn (8.64, an assumption: Opus
  rewrites a 1M-token window to the cache and answers 32,000 tokens), and 22.36 + 8.64 = 31.00.
  Phase O's sessions keep their worst turn inside its own ceiling (`cap_for`). Phase O's ceiling
  is 21.36, not lb162x's 30, so that the worst case is the approved 31.

## Why

Lot lb162x confirmed the router at the 0.6 cut against Opus 5.5: −3.7 points [−8.0, +0.6], "no
peor" at −10, 29.5 % of Opus's cost saved. Post hoc on the same 162 tasks, the 0.8 cut came to
−0.6 points for a smaller saving (`python benchmarks/jev114/lbo8.py --dry`, descriptive):

| Cut | Covered | Jev / Opus right on them | Jev only / Opus only | Hybrid minus Opus | Opus cost avoided | Net saving (Jev on all 162 paid) |
|---|---|---|---|---|---|---|
| 0.6 | 60 (37.0 %) | 31 / 37 | 4 / 10 | −3.70 points | 6.23 USD | 5.35 USD, 29.5 % |
| 0.7 | 41 (25.3 %) | 21 / 25 | 2 / 6 | −2.47 | 4.27 | 3.40, 18.7 % |
| 0.8 | 27 (16.7 %) | 17 / 18 | 0 / 1 | −0.62 | 2.81 | 1.93, 10.6 % |
| 0.9 | 12 (7.4 %) | 9 / 10 | 0 / 1 | −0.62 | 1.33 | 0.45, 2.5 % |

At 0.8, a paired bootstrap of the 162 gives [−1.9, 0.0] points and a net saving of
[4.9 %, 17.1 %]. Tango's score interval, which keeps a width with one disagreement, gives about
[−3.4, +1.7] (at 0.6: [−8.9, +0.9]). This is a hypothesis to confirm, not a result.

## Tasks: the measured population is spent

LongBench v2 has 503 tasks. The router's population is the Single- and Multi-Document QA domains
over 100,000 characters: 222 tasks, and all 222 are used (the 60 of 2026-10-06 with their 10 dev
tasks, and lb162's 162). Fresh, 281 remain:

- **78 in the same two domains** (55 Single-, 23 Multi-Document QA), all under 100,000 characters
  (48,765 to 99,827, median 72,731), all of the set's "short" band; 53 hard, 25 easy. Frozen by
  metadata only in `ids.txt` (sha256 607d0d3e…). The tests check that none is one of lb162's
  162 or the 10 dev tasks, and none of the 60 of 2026-10-06 where the local cache holds them
  (skipped without it). The freeze itself drew them outside all 222 used ids (`lbo8.used_ids`).
- 203 in other domains: Long In-context Learning 81, Code Repository Understanding 50,
  Long-dialogue History 39, Long Structured Data 33.

**Population (decided): the 78.** The same domains, template and grader, so this tests the cut
and the shorter documents together. A fail would not say which. Documents of 49,000 to 100,000
characters were not measured before: the point's docstring says so.

## Design

One driver, one process, in this order (`lbo8.DRIVEN`): the smoke, phase J, phase O.

- **Smoke:** one Opus session on lb162x's smoke task (a dev task outside the 78; the driver
  refuses it if it were one of them), 0.80 USD cap and ceiling, in this lot's own session folder
  (`lbo8-smoke`) and results (`smoke-rows.jsonl`, `smoke-stop.json`). It tests the path, not
  the answer (lb162x's rule, `h2h_lb162x.smoke_passed`); a failure pauses the lot (exit 9).
- **Phase J:** Jev `jev-1.14.0`, lb162's request to the byte (long-context header, 900,000-
  character middle cut, retries at 0.8 and 0.64 of the window), through `lb162.run_j`. Recorded
  first (`jev-answers-j14-L.jsonl`), live only on a miss. **This lot's own ledger**,
  `C:\sp-runs\lbo8\jev-ledger.jsonl`, batch `lbo8`, cap **0.20 USD** on the ledger and the
  batch (`lbo8.live_decider`): never lb162's ledger nor another lot's (the driver refuses a run
  folder that is `C:\sp-runs\w17-jev`, `lb162` or `lb162x`). Before the first call: the plan
  must fit the cap at the dearest rate per character (`lbo8.jev_plan_refusal`), the key is
  loaded (never printed), the client's 429 retries are taken out, and `jev-preflight` runs.
  Rows hold ids, letters, probabilities and costs, no text (`jev-scored.jsonl`).
- **The cut:** a task is covered when Jev's top-choice probability is **≥ 0.8**.
- **Phase O:** Opus 5.5 (`claude-opus-5-5`) in clean Claude Code 2.1.287 (arm N, as in
  lb162x), one session per task on **all 78**, in `random.Random(20261016).shuffle` order of
  the sorted ids (`lbo8.opus_order`). Opus's answer stands on the uncovered tasks, so only the
  covered ones move the verdict. Running all 78 measures the saving. Graded by LongBench v2's
  official `extract_answer` (`longdoc_data.last_answer`). Session folder `lbo8-opus`; rows
  without text in `opus-rows.jsonl`. The session, its grade, the money rule and each session's
  health (outage, streak, another model) are lb162x's (`h2h_lb162x`, `lb162x_guard`), reused
  as they are with this lot's phases and run folder.

## Primary verdict

- Hybrid minus Opus over the 78, with b the covered tasks only Jev got right, c those only Opus
  got right, and n = 78 less the covered tasks with no Opus grade in the reading (an uncovered
  task is the same answer in both arms): estimate (b − c) / n (`lbo8_stats.verdict`).
- **Tango's score 95 % interval** for a paired difference (`lbo8.tango_ci`). The percentile
  bootstrap of lb162x collapses to a point when the covered tasks show no disagreement, which is
  likely here.
- **Margin −5 points** (decided). "no peor" when the lower bound is above the margin, "peor" when
  the upper bound is below it, else "no concluyente"; compared unrounded.
- What that means at n = 78 (`lbo8.tango_ci`): no disagreement gives [−4.7, +4.7], "no peor";
  b = 1, c = 0 [−3.5, +6.9] and b = 2, c = 1 [−4.7, +7.8], "no peor"; but **one Opus-only
  disagreement alone fails**: b = 0, c = 1 gives [−6.9, +3.5] and b = 1, c = 1 [−5.8, +5.8],
  "no concluyente". "peor" needs at least 8 Opus-only disagreements with none the other way.
- No verdict with fewer than 8 covered tasks with an Opus grade in the reading at hand
  ("no medido"; in the sensitivity reading an infrastructure error counts as a grade); none while a
  phase is paused or a LIMIT.flag or STOP is in the run folder ("pausa").
- Infrastructure errors and lowered-cap stops are read as in lb162x: not run in the primary
  reading, wrong in the sensitivity reading (`lb162x_stats.grade`). A session most of whose
  cost went to another model is out of both. A task phase J left unasked is uncovered.

**Secondary (registered):**
- The saving of Opus's cost: Opus alone minus (Jev on all 78 + Opus on the uncovered), as a
  share of Opus alone, each group's Opus cost its size times its measured mean. Paired bootstrap
  over the tasks (10,000 draws, seed 20261016). "ahorra" when the lower bound is above 0, "no
  ahorra" when the upper bound is at or below 0. Sensitivities: infrastructure errors at their
  cost; a lowered-cap stop at the full cap.
- Jev's precision and Opus's accuracy on the covered tasks (Wilson); McNemar exact on the
  disagreements.
- Descriptive: the 0.6 and 0.7 cuts on the same rows.

`python benchmarks/jev114/lbo8.py --analyse` writes all of it to `summary.json`.

## Power: the task is the unit

Tango's interval has a floor: with no disagreement at all, the lower bound is −z²/(n + z²).
That is **−4.7 points at 78 tasks**, −2.3 at 162 and −1.35 at 281. **A −3-point margin cannot
pass with 78 tasks, whatever the data.**

Chance of "no peor" (`lbo8.power`, 1,000 draws a cell):

| Scenario (coverage; Jev-only and Opus-only rates on the covered) | n | −3 | −5 | −7 | −10 |
|---|---|---|---|---|---|
| As lb162x at 0.8 (16.7 %; 0/27, 1/27) | 78 | 0.00 | 0.62 | 0.92 | 0.98 |
| | 281 | 0.77 | 1.00 | 1.00 | 1.00 |
| 0.7's disagreement rates at 0.8's coverage (16.7 %; 2/41, 6/41) | 78 | 0.02 | 0.16 | 0.45 | 0.78 |
| | 281 | 0.18 | 0.74 | 0.98 | 1.00 |
| 0.6's disagreement rates at 0.8's coverage (16.7 %; 4/60, 10/60) | 78 | 0.03 | 0.17 | 0.39 | 0.72 |
| | 281 | 0.14 | 0.68 | 0.96 | 1.00 |
| 0.6's disagreement rates at 25 % coverage (4/60, 10/60), the most pessimistic | 78 | 0.02 | 0.09 | 0.23 | 0.55 |
| | 281 | 0.05 | 0.34 | 0.76 | 0.99 |

Read plainly:
- **With the 78,** "no peor" at −5 has about 62 % power if 0.8 behaves as it did on lb162x, and
  about 17 % if Jev disagrees with Opus as much as at 0.6 (9 % if it also covers 25 %). At −7:
  92 %, 39 % and 23 %. `lbo8.power` does not apply the rule of 8 covered tasks: the chance of
  fewer than 8 covered of 78 is about 4 % at lb162x's coverage (16.7 %), 27 % at 12 % and 48 % at
  10 %, and coverage on documents of 49,000 to 100,000 characters was never measured; in the good
  scenario the power net of "no medido" is about 57-59 %.
- **A tight claim** ("keeps Opus's accuracy", −3) would need all 281 fresh tasks: about 77 %
  power in the good scenario. But 203 of those tasks are domains the router was never measured
  on.
- **What a pass would license:** at −5 and about 17 % coverage, Jev could be up to about 30
  points less accurate than Opus on the tasks it answers. The margin is a product decision, taken
  by the owner (above).

## Money (hard caps, in code)

| | Expected | Cap |
|---|---|---|
| Phase J, Jev on 78 (5.77 M characters at 0.012 USD per M) | 0.07 USD | 0.20 USD (ledger + batch); 0.086 at the dearest rate before retries |
| Smoke, one Opus session | ~0.2 USD | 0.80 USD |
| Phase O, Opus on 78 (0.10 USD a task: lb162x's short band was 0.099, max 0.19) | 7.8 USD; simulated mean 7.73, p95 8.21 | **ceiling 21.36 USD** |
| **Lot** | **about 8.1 USD** | **22.36 USD in caps; 31.00 at worst** (the smoke's turn past its cap) |

- **Each session:** `--max-budget-usd` 6.00 (arm N's Opus cap, unchanged from lb162x).
  `cap_for` lowers the cap when 6.00 plus one worst turn no longer fits under the ceiling
  (spent above 6.72 USD). Below 1.00 the phase stops (spent above 11.72). The worst turn is
  8.64 USD, an assumption (Opus 5.5 rewrites its whole 1M-token window to the cache and answers
  32,000 tokens), as lb162x stated it. The cap leaves room for it because `--max-budget-usd`
  only cuts between turns.
- **Exposure:** all 78 sessions run up to 1.5 x the expected cost; at 1.6 x about 74 (the
  simulation on lb162x's sessions: mean 74.4, 5th percentile 70). At worst (every session at its
  cap plus a worst turn) one session. Each `--retry-smoke` opens a new 0.80 ceiling; the
  `jev-preflight` decision (about 13 micro-USD) is outside the ledger.
- **Above the 10 USD line:** the lot's worst case is 31 USD; the owner approved it on
  2026-10-16. The expected cost is 8.1.
- **Wall time:** about 30 minutes of Opus sessions (lb162x: mean 22 s a session; the clock rule
  takes 25 s), one at a time, and a few minutes of phase J.

## Clock

- No phase starts before 08:00 (Windows Update restarts 02:00-08:00), nor when its sessions at
  1.5 x the clock rule's mean, plus 10 minutes, would cross midnight. Phase O: 78 x 25 s x 1.5 +
  10 min = 59 minutes, so **the lot starts between 08:00 and 23:01**; the driver checks phase
  O's clock before anything (the smoke is one session, phase J a few minutes). Phase J takes a
  15-minute allowance, checked before its first call. The start check is phase O's alone: a
  launch after about 22:40 can spend the smoke and J and then stop phase O by the clock (exit 5),
  so **launch before 22:40**.
- Before each Opus session (lb162's guard): a stop if it is before 08:00, past the phase's start
  date, or midnight is less than 10 minutes away (kind `clock`, exit 5, a pause).
- Attended throughout; nothing left running between 02:00 and 08:00.

## Stops (kind in `smoke-stop.json` / `jev-stop.json` / `opus-stop.json`, the kind only)

lb162x's, with phase J's own:

- a 429 or usage limit in a Claude Code session: `limit`, exit 2, and `LIMIT.flag` in the run
  folder. **STOP on a 429**: a pause, never a result; warn the other sessions; the owner deletes
  the flag to resume. A launch with the flag present: exit 2.
- a refusal before any session (no seal or a mismatch, not the sealed detached checkout, a
  `claude` on PATH that is not the pinned build, another lot's run folder, a preflight problem):
  `preflight`, exit 3;
- phase J paused (an HTTP 402, Jev's 429, an outage, three failed tasks in a row): `jev`, exit
  4. Jev's 429 is not the subscription's limit and writes no LIMIT.flag. A 402 already in
  `jev-preflight`, before any call, is a refusal: `preflight`, exit 3. A relaunch asks only
  the tasks the pause left unasked; phase J at its cap is final (`ceiling`), scored as it is,
  and phase O runs;
- the clock: `clock`, exit 5;
- a `STOP` file in `C:\sp-runs\lbo8`: `manual`, exit 6 (before the next Jev call or session);
- any other failure: `error`, exit 7; an outage in Claude Code: `outage`, exit 8; the smoke
  failed: `smoke`, exit 9 (`h2h_lbo8.py --retry-smoke` moves a smoke that failed having spent
  aside, never deleting it; each retry is the owner's spend).

Exit 1 means only the ceiling: every phase over, one ended at its ceiling. A phase that ended
(the smoke passed, a phase finished or at its ceiling) is skipped on a relaunch.

## Dry run, done (free)

`python benchmarks/jev114/lbo8.py --pool | --freeze-ids | --prepare | --dry`, 2026-10-16:

- **The pool:** 503 rows, 222 used, 281 fresh, 78 in the QA domains, 0 left in the measured
  population.
- **The documents:** 78 prepared into the local cache (`~/.cache/sanchopanza/longdoc/lbo8`),
  none missing.
- **Phase J, through lb162's own runner** with no live decider and no recordings:
  - 78 rows and 234 tries (three lengths each), 0.00 USD.
  - Every document was read, cut and asked of the replay.
  - Status `failed` on all 78, as expected with nothing recorded.
- **Phase O:** 78 prompts built with h2h_longdoc's official template (at most 2,991
  characters). The official grade read a canned reply right.
- **The money rule** was simulated on lb162x's real Opus sessions: see Money.

`python benchmarks/h2h/h2h_lbo8.py --dry | --preflight`, 2026-10-16: the order S → J → O, 79
Opus sessions and 78 Jev tasks, caps 22.36 USD (31.00 at worst), expected about 8.1, phase O about 32
minutes and a start by 23:01; the smoke task `66eefe85821e116aacb228dc` (118,549 characters);
phase J's ledger `C:\sp-runs\lbo8\jev-ledger.jsonl`, 0 USD spent, all 78 tasks unrecorded (asked
live). The preflight passes the pinned build, Opus's id in it, the data, the documents, the
hooks and the ledger, and refuses only for the subscription token, as expected in a session
(the launcher passes the keys file). Phase J's plan counts one try a task; with documents under
900,000 characters the retries at 0.8 and 0.64 of the window resend the whole document, about
0.26 USD at worst, past the 0.20 cap: `CappedDecider` then refuses, J ends at its ceiling (final)
and what it did not ask counts as not covered.

## Run plan

From a detached worktree of the sealed commit (`PYTHONPATH=<worktree>\src`, the main checkout's
python), launched outside the session by WMI through `launch.ps1` as lb162x was (its own process
group, the pinned Claude Code first on PATH, `DISABLE_AUTOUPDATER=1`), run folder
`C:\sp-runs\lbo8`, smoke first:

```
python -m sanchopanza jev-preflight                # Jev's balance and key (exit 0)
python benchmarks/h2h/h2h_lbo8.py --dry            # free: the plan, money, clock, spent so far
python benchmarks/h2h/h2h_lbo8.py --preflight      # free (needs the subscription token)
powershell -File ..\sanchopanza-lbo8\benchmarks\h2h\launch.ps1 -Runner h2h_lbo8.py -RunnerArgs "--lot lbo8" -Pin $env:USERPROFILE\.cache\sanchopanza\claude-pin\2.1.287 -KeysEnv <path to the keys .env that SANCHOPANZA_KEYS_ENV names> -Log C:\sp-runs\lbo8\driver.log -PidFile C:\sp-runs\lbo8\driver.pids
python benchmarks/h2h/h2h_lbo8.py                  # rows without text, smoke and phase O
python benchmarks/jev114/lbo8.py --analyse         # the analysis, summary.json
```

`launch.ps1` takes the worktree from its own folder: it must be the detached worktree's copy
(the main checkout's would run there and refuse, exit 3). Watch the log and the PIDs; stop with
a `STOP` file in `C:\sp-runs\lbo8` or by verified PID only. Start between 08:00 and 22:40 and
stay with it; STOP on a 429.

## Before a seal

Done (2026-10-16):

1. The owner's decisions: margin −5, the 78, 31 USD exposure at worst.
2. The live driver `benchmarks/h2h/h2h_lbo8.py` over h2h_longdoc, reusing lb162x's driver and
   `lb162x_guard` as they are (no guard of its own was needed: `Budget` takes the phase and the
   run folder).
3. Phase J's live entry (`lbo8.run_phase_j`, its own ledger), the analysis (`lbo8_stats.py`,
   `lbo8.py --analyse`), the seal (`lbo8.py --seal`), and their tests
   (`tests/test_lbo8_live.py`, `tests/test_lbo8_stats.py`).

Left, in order:

1. `launch.ps1` takes `-Runner h2h_lbo8.py` (done, `c74943b`).
2. A `revisor-prereg` review against the code (done, 2026-10-16: no blocker; its two "must"
   items, the smoke's worst turn inside the approved exposure and this section's launcher text,
   are fixed above, and its notes on power, "no medido", the clock, phase J's retries, the exit
   on a 402 and the launcher's folder are in the text).
3. Commit the instrument on a clean tree (the seal hashes every file of the package: no other
   session's uncommitted edit may be in it), `python benchmarks/jev114/lbo8.py --seal`, and a
   commit whose message carries the hash.
4. `git worktree add --detach ..\sanchopanza-lbo8 <sealed commit>`; `jev-preflight` and the
   driver's `--preflight` from there with the keys; then the launch.
