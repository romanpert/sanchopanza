# Jev 1.14 with the long window as a substitute for Sonnet 5.5 on long documents (lot lb162): pre-registration

Written 2026-10-15, before any answer on these tasks. Branch `lb162`. `prereg.sha256` holds the
hash of this file together with the code and inputs it names (`prereg.manifest.json`, written by
`python benchmarks/jev114/lb162.py --seal` after an independent `revisor-prereg` review); the
sealing commit's message carries the hash. Every live path (Jev smoke, phase J, phase S)
refuses to spend unless the seal matches. Both phases run from `git worktree add --detach
<sealed commit>`, never from a working branch.

**What the seal covers:** this file; the two runners, the analysis and their tests; every
module of the package (`src/sanchopanza/**/*.py`); every benchmark file the runners load or run
(L4/L6's code, `b3conf_power.py`, `meter.py`, the h2h runner and its modules, hooks, S line and
`launch.ps1`); the frozen id list; LongBench's `data.json`, the 60-task `tasks.jsonl` and this
lot's `tasks.jsonl`; and one aggregate sha256 of the 162 prepared documents. `--preflight` and
both live paths check the documents against it.

## The question

Lot L6 (`docs/results/2026-10-15-jev114-l6`) found, post hoc, that Jev 1.14 reading up to
900,000 characters answering alone where its top-choice probability is >= 0.6, and Sonnet 5.5
elsewhere, tied Sonnet's 31/50 at about half its cost. On fresh tasks: **is this hybrid no worse
than Sonnet 5.5 alone by more than 10 points?** The -10-point margin is the owner's product
decision (it accepts giving up to 5 tasks in 50 for about half of Sonnet's cost), fixed now.
Over all n tasks, -10 points at about 54 % coverage means Jev may be up to about 18 points less
accurate than Sonnet on the tasks it covers.

## Tasks

The 162 fresh LongBench v2 tasks of `docs/results/2026-10-15-jev114-b3conf` (`b3conf_power.py
--pool`): Single- and Multi-Document QA, contexts over 100,000 characters, outside the 60 drawn
on 2026-10-06. Chosen by metadata only (`longdoc_data.eligible`: domain and context length; no
answer or gold read), all of them, sorted. Frozen in `ids.txt`, sha256
`da7d37d327ac7e57b5456f3e02a4d4f2a7f305bdcac3482f35a7085203f1f771` (`ids.sha256`, and
`IDS_SHA256` in code). Length bands 38 short, 88 medium, 36 long; 50 easy, 112 hard; 134 fit the
window whole, 28 are middle-cut; 78.6 M characters shown in all (485,000 a task on average,
against 408,000 in L6).

## Phase J: Jev 1.14, long window (`benchmarks/jev114/lb162.py`)

L6's `j14-L` cell: `jev-1.14.0` pinned, the `TypeSafe-Danger-Zone-Long-Context` header, point
`longbench_choice`, state `{"question", "document"}` with the document middle-cut to 900,000
characters when longer, one Choice `answer` over A-D whose criteria are the choice texts (L6's
instructions, `l6.b3_question`). The answer is the chosen letter and its probability
(`l6.top_of`).

**A task failure** is only an HTTP 400, a ReadTimeout, or a Choice with no probability for its
pick. Such a call is asked again at 0.8 and then 0.64 of the window. Here the shorter retry is
for this one model; in L6 it was joint with `j13r` (both models asked again whenever either
failed), which replaced one `j14-L` answer of 50. Still unanswered after the third length, the
task is **failed**: not covered, and it stays failed on a relaunch.

Launched in a seeded order (20261015), at most 4 tasks in flight, each reading its document
when its turn comes. Answers are recorded with hashed keys (no text) in this folder, so a
relaunch pays only for what is missing. Rows (`jev-scored.jsonl`) hold ids, letters,
probabilities, cost and bands, no text.

## The cut

**Covered: answered with top probability >= 0.6** (tau = 0.6, as L6's sweep reads it). The
covered ids go to `covered-ids.txt` in a seeded random order (20261015); phase S checks that file
against the derivation from `jev-scored.jsonl` and refuses a mismatch.

## Phase S: Sonnet 5.5 in clean Claude Code, on the covered tasks only (`benchmarks/h2h/h2h_lb162.py`)

Arm N of the 2026-10-06 confirmation (`SONNET-CC`), unchanged: `h2h_longdoc.py`'s session
(Claude Code 2.1.287 pinned and first on PATH through `launch.ps1`, a clean user per session,
the document copied as `document.txt`, LongBench v2's official 0-shot template, WebSearch and
WebFetch disallowed and the local hook on every tool), its per-session cap (3.00 USD, passed as
`--max-budget-usd`) and the official `extract_answer` grade on the last line that has one.
One session per covered task, in the file's seeded order, so a stop by the ceiling leaves out a
random subset of the covered tasks. Its own phase (`lb162`) and private session folder
(`~/.cache/sanchopanza/longdoc/h2h/lb162`). Public rows without text (`sonnet-rows.jsonl`): id,
letter, grade, cost, time, turns, `hit_cap`, `is_error`, and Claude Code's `subtype` (or the
runner's on a wall-clock timeout).

**Sessions with no letter.**
- A session stopped by its cap stays wrong, as in the 2026-10-06 confirmation.
- One that ended in an infrastructure error (`is_error` without `hit_cap`, wall-clock timeouts
  included) counts as **not run** in the primary reading: it is excluded like a covered task
  without a session.
- The registered **sensitivity reading** counts those as wrong.
- Bias: excluding them can only raise Sonnet's accuracy on the covered tasks, if those tasks
  are harder than the rest. So the primary is the reading less favourable to the hybrid; the
  sensitivity reading is the more favourable one.

## Primary analysis and verdict (`lb162_stats.py`)

Over the n tasks Jev was asked (all 162 unless a cap stops phase J), the hybrid answers with Jev
on the covered tasks and with Sonnet elsewhere, so

    hybrid - Sonnet = sum over covered (Jev right - Sonnet right) / n

an uncovered task contributing 0. Computed as coverage x the mean gain on the covered tasks that
have a Sonnet session. That is the sum above when every covered task has one. If a stop leaves
some without, it is an approximately unbiased ratio estimator (the covered tasks run in a seeded
random order). The number of Sonnet sessions scored and of covered tasks without one are
reported.

**Paired bootstrap** over the n tasks, 10,000 draws, seed 20261015, percentile 95 % CI. A
resample with no value (covered tasks but none with a Sonnet session) is dropped, and the
number kept is reported. **Exact McNemar** on the covered disagreements (Jev only right against
Sonnet only right).

**Verdict, fixed now.** The CI's bounds are compared with -0.10 unrounded:
- **"no peor"** if the CI's lower bound is > -10 points;
- **"peor"** if the CI's upper bound is < -10 points;
- **"no concluyente"** otherwise (a bound exactly at -10 points does not clear it);
- **"no medido"** if nothing is covered or no CI exists;
- **"pausa"** (no verdict) while the lot is paused:
  - a `LIMIT.flag` or `STOP` in `C:\sp-runs\lb162`;
  - phase J not over (a pause, not its cap);
  - phase S, with covered tasks to run, not ended by finishing or by its ceiling.

**The product claim** ("sustituye") needs "no peor" **and** coverage >= 20 % (L6's
`B3_MIN_COVERAGE`); otherwise "no sustituye".

## Secondary, descriptive

- Coverage.
- Jev's precision on the covered tasks (Wilson 95 %).
- Sonnet's accuracy on the covered tasks.
- Jev's accuracy on all n (failed counts as wrong).
- Failed, unasked and infrastructure-error counts.
- The sensitivity reading above.
- The normal-approximation CI of `b3conf_power.paired_ci` beside the bootstrap.
- The same reading by LongBench length band and by difficulty.

**Cost, measured:** Jev USD on every task (discarded shorter retries included), and Sonnet list
USD on the covered tasks. Sonnet's cost on the uncovered tasks is not measured: it is
**estimated** at 0.123 USD a task (Sonnet's mean in the 2026-10-06 confirmation). The saving
(Sonnet on the covered tasks minus Jev on all) is reported as a share of that estimated
Sonnet-alone cost, labelled an estimate.

## Power

From L6's 50 tasks resampled (`b3conf_power.py`, seed 20261015, 5,000 draws, its
normal-approximation CI with every covered task paired): 162 paired tasks decide at -10 points
about **88 %** of the time ("no peor" 88.2 %, "peor" 0), CI half-width about 6 points. At
-2 points the same design would decide about 10 %. If the ceiling leaves covered tasks without
Sonnet (see below), the CI widens and the chance of a verdict is somewhat lower.

## Money, time and stops

**Jev.**
- A new ledger `C:\sp-runs\lb162\ledger.json`, batch `lb162`, cap **1.20 USD** (ledger and
  batch, the owner's).
- Every call goes through `CappedDecider`, reserved before the call at 0.014 USD per million
  characters sent (L6's dearest call cost 0.0149). The ledger can therefore pass the cap by at
  most the shortfall of the 4 calls in flight. A timed-out call is settled at 0 in the ledger
  although Jev may bill it.
- The smoke (one LongBench dev task outside the 162: lot L6's smoke task) has its own ceiling of
  0.02 on the same batch.
- **Expected 0.92 USD**: 78.6 M characters at L6's 0.0117 USD per million shown, retries
  included. Pessimistic about 1.17 USD at L6's dearest rate, before retries, so the 1.20 cap
  may stop phase J (a final stop, below).
- The runner refuses to start when the tasks without a recorded answer do not fit under the cap
  at L6's rate. A few minutes of wall time.

**Sonnet.**
- Phase ceiling **18.00 USD** in code.
- Before each session the loop holds the session's cap plus one worst turn: **7.32 USD**. The
  worst turn is 4.32 USD: one turn rewriting Sonnet 5.5's whole 1M-token window to the cache and
  answering 32,000 tokens, at Claude Code's own rates (`meter.CLAUDE_CODE_RATES`, the dearer of
  its cache-write rates). `--max-budget-usd` stops between turns only. So the phase **cannot
  pass 18**.
- For context, the 2026-10-06 confirmation's dearest Sonnet session cost 1.87 USD (about 195,000
  tokens written to the cache).
- A **reservation row** is written before each session. A session that dies mid-way (no row
  recorded) keeps its 7.32 against the ceiling on a resume; a recorded session counts at its
  real cost.
- Expected 0.138 USD a covered task (L6) x about 87 covered tasks (54 %) = **about 12 USD**.
- The runner refuses a plan only when its expected cost alone (sessions left x 0.138) exceeds
  18, i.e. more than 130 covered tasks.
- A plan above what the ceiling holds starts, and the guard stops it. At L6's mean cost the
  guard lets **78** sessions run (spent + 7.32 <= 18 before each). At worst, every session at
  its cap plus a worst turn, it guarantees **2**.
- With about 87 covered tasks, a ceiling stop is likely. It leaves a random subset of the
  covered tasks without Sonnet (the seeded order); the estimator above handles it, and the
  README reports how many sessions ran.
- Wall time: sessions took a median 23 s and a mean 38 s in the 2026-10-06 confirmation: about
  55 minutes for 87, one at a time.

**Clock.**
- Phase S does not start before 08:00 (Windows Update restarts 02:00-08:00), nor when its
  sessions at 1.5 x the mean, plus 10 minutes, would cross midnight.
- Before each session it stops if it is before 08:00, the date is not the phase's start date,
  or midnight is less than 10 minutes away.
- A clock stop (kind `clock`, exit 5) is a pause: a relaunch after 08:00 resumes.

**Stops, phase J.**
- A cap refusal is **final**: no further call, the tasks left unasked are out of n, what is
  complete is scored and the README says so; the runner refuses a relaunch.
- Every other stop is a **pause, not a result** (exit 2). These stop every further call:
  - an HTTP 402 (no funds);
  - an HTTP 429: this lot takes 429 out of the Jev client's retryable statuses at run time
    (`no_retry_on_429`, as lot memgate-long), so the first 429 stops;
  - any other error, an **outage**: the network other than a ReadTimeout, HTTP 5xx, 529 after
    the client's three bounded retries, 401/403, a body that is not JSON;
  - **three failed calls in a row** (completion order), of any kind;
  - a `STOP` file in `C:\sp-runs\lb162`.
- After a pause the rows are written with the unasked tasks marked "stopped", not frozen. The
  relaunch asks only those; a failed task stays failed. `jev-stop.json` keeps the stop's kind
  only.

**Stops, phase S** (kind in `sonnet-stop.json`, the kind only):
- finished: `done`, exit 0;
- the ceiling: `ceiling`, exit 1, final;
- a 429 or usage limit ("weekly limit"): `limit`, exit 2. The session is recorded as not run
  and `LIMIT.flag` is written in `C:\sp-runs\lb162`. It is a pause, never scored; the owner
  tells the other sessions and deletes the flag to resume.
- the clock: `clock`, exit 5;
- a `STOP` file: `manual`, exit 6, before the next session.

Processes are stopped by PID only.

## Commands

From the detached worktree of the sealed commit:

```
python benchmarks/jev114/lb162.py --plan          # free
python benchmarks/jev114/lb162.py --preflight     # free
python benchmarks/h2h/h2h_lb162.py --preflight    # free (needs the subscription token)
python benchmarks/jev114/lb162.py --seal
python benchmarks/jev114/lb162.py --smoke --live
python benchmarks/jev114/lb162.py --run --live
powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_lb162.py -RunnerArgs "--phase lb162" -Pin $env:USERPROFILE\.cache\sanchopanza\claude-pin\2.1.287 -Log C:\sp-runs\lb162\sonnet.log -PidFile C:\sp-runs\lb162\sonnet.pids
python benchmarks/h2h/h2h_lb162.py                # rows without text
python benchmarks/jev114/lb162.py                 # the analysis, summary.json
```

`launch.ps1` sets `DISABLE_AUTOUPDATER=1`. With `-KeysEnv <path>` it writes that path, never
the file's content, as `SANCHOPANZA_KEYS_ENV` into the process it starts.

## Not done, and what follows

Not done: Sonnet on the uncovered tasks (their cost stays an estimate), other cuts, Jev 1.13,
any S arm.

- If the verdict is "no peor" with coverage >= 20 %, the README will say that on long-document
  multiple-choice questions Jev 1.14 with the long window can answer alone above 0.6 and leave
  the rest to Sonnet 5.5 within 10 points of Sonnet, at the measured Jev cost and the estimated
  saving.
- "peor" says it cannot.
- "no concluyente" or "no medido" says this evidence does not decide.

Nothing in `policy.py` or `DEFAULT_MODEL` changes in this lot.
