# Jev 1.14 with the long window as a substitute for Sonnet 5.5 on long documents (lot lb162): pre-registration

Written 2026-10-15, before any answer on these tasks. Branch `lb162`. `prereg.sha256` holds the
hash of this file together with the code and inputs it names (`prereg.manifest.json`, written by
`python benchmarks/jev114/lb162.py --seal` after an independent `revisor-prereg` review); the
sealing commit's message carries the hash. Every live path (Jev smoke, phase J, phase S)
refuses to spend unless the seal matches.

## The question

Lot L6 (`docs/results/2026-10-15-jev114-l6`) found, post hoc, that Jev 1.14 reading up to
900,000 characters answering alone where its top-choice probability is >= 0.6, and Sonnet 5.5
elsewhere, tied Sonnet's 31/50 at about half its cost. On fresh tasks: **is this hybrid no worse
than Sonnet 5.5 alone by more than 10 points?** The -10-point margin is the owner's product
decision (it accepts giving up to 5 tasks in 50 for about half of Sonnet's cost), fixed now.

## Tasks

The 162 fresh LongBench v2 tasks of `docs/results/2026-10-15-jev114-b3conf` (`b3conf_power.py
--pool`): Single- and Multi-Document QA, contexts over 100,000 characters, outside the 60 drawn
on 2026-10-06. Chosen by metadata only (`longdoc_data.eligible`: domain and context length; no
answer or gold read), all of them, sorted. Frozen in `ids.txt`, sha256
`da7d37d327ac7e57b5456f3e02a4d4f2a7f305bdcac3482f35a7085203f1f771` (`ids.sha256`, and
`IDS_SHA256` in code). Length bands 38 short, 88 medium, 36 long; 50 easy, 112 hard; 134 fit the
window whole, 28 are middle-cut.

## Phase J: Jev 1.14, long window (`benchmarks/jev114/lb162.py`)

Exactly lot L6's `j14-L` cell: `jev-1.14.0` pinned, the `TypeSafe-Danger-Zone-Long-Context`
header, point `longbench_choice`, state `{"question", "document"}` with the document middle-cut
to 900,000 characters when longer, one Choice `answer` over A-D whose criteria are the choice
texts (L6's instructions, `l6.b3_question`). A call left unanswered (HTTP 400, timeout, no
probability for its pick) is asked again at 0.8 and then 0.64 of the window; still unanswered
after the third length the task is **failed** (not covered). The answer is the chosen letter and
its probability (`l6.top_of`). Launched in a seeded order (20261015), at most 4 calls in flight.
Answers are recorded with hashed keys (no text) in this folder, so a relaunch pays only for what
is missing. Rows (`jev-scored.jsonl`) hold ids, letters, probabilities, cost and bands, no text.

## The cut

**Covered: answered with top probability >= 0.6** (tau = 0.6, as L6's sweep reads it). The
covered ids go to `covered-ids.txt` in a seeded random order (20261015); phase S checks that file
against the derivation from `jev-scored.jsonl` and refuses a mismatch.

## Phase S: Sonnet 5.5 in clean Claude Code, on the covered tasks only (`benchmarks/h2h/h2h_lb162.py`)

Arm N of the 2026-10-06 confirmation (`SONNET-CC`), unchanged: `h2h_longdoc.py`'s session
(Claude Code 2.1.287 pinned and first on PATH through `launch.ps1`, a clean user per session,
the document copied as `document.txt`, LongBench v2's official 0-shot template, WebSearch and
WebFetch disallowed and the local hook on every tool), its per-session cap (3.00 USD, passed as
`--max-budget-usd`) and the official `extract_answer` grade on the last line that has one; no
letter is wrong. One session per covered task, in the file's seeded order, so a stop by the
ceiling leaves out a random subset of the covered tasks. Its own phase (`lb162`),
private session folder (`~/.cache/sanchopanza/longdoc/h2h/lb162`) and public rows without text
(`sonnet-rows.jsonl`: id, letter, grade, cost, time).

## Primary analysis and verdict (`lb162_stats.py`)

Over the n tasks Jev was asked (all 162 unless a cap stops phase J), the hybrid answers with Jev
on the covered tasks and with Sonnet elsewhere, so

    hybrid - Sonnet = sum over covered (Jev right - Sonnet right) / n

an uncovered task contributing 0. Computed as coverage x the mean gain on the covered tasks that
have a Sonnet session: the sum above when every covered task has one, and unbiased if a stop
leaves some without (the covered tasks run in a seeded random order). The number of Sonnet
sessions scored and of covered tasks without one are reported. **Paired bootstrap** over the n tasks, 10,000 draws, seed 20261015,
percentile 95 % CI; **exact McNemar** on the covered disagreements (Jev only right against
Sonnet only right).

**Verdict, fixed now:**
- **"no peor"** if the CI's lower bound is > -10 points;
- **"peor"** if the CI's upper bound is < -10 points;
- **"no concluyente"** otherwise (a bound exactly at -10 points does not clear it).

## Secondary, descriptive

Coverage; Jev's precision on the covered tasks (Wilson 95 %); Sonnet's accuracy on the covered
tasks; Jev's accuracy on all n (failed counts as wrong); failed and unasked counts; the
normal-approximation CI of `b3conf_power.paired_ci` beside the bootstrap; the same reading by
LongBench length band and by difficulty. Cost, measured: Jev USD on every task (discarded shorter
retries included) and Sonnet list USD on the covered tasks. Sonnet's cost on the uncovered tasks
is not measured: it is **estimated** at 0.123 USD a task (Sonnet's mean in the 2026-10-06
confirmation), and the saving (Sonnet on the covered tasks minus Jev on all) is reported as a
share of that estimated Sonnet-alone cost, labelled an estimate.

## Power

From L6's 50 tasks resampled (`b3conf_power.py`, seed 20261015, 5,000 draws): 162 paired tasks
decide at -10 points about **88 %** of the time ("no peor" 88.2 %, "peor" 0), CI half-width
about 6 points. At -2 points the same design would decide about 10 %.

## Money, time and stops

- **Jev:** a new ledger `C:\sp-runs\lb162\ledger.json`, batch `lb162`, cap **1.20 USD** (ledger
  and batch), every call through `CappedDecider`, reserved before the call. The smoke (one
  LongBench dev task, outside the 162: lot L6's smoke task) has its own ceiling of 0.02 on the
  same batch. Expected 162 x 0.0048 = **0.78 USD**, a few minutes. The runner refuses to start
  when the tasks left at 0.0048 do not fit under the cap.
- **Sonnet:** phase ceiling **18.00 USD** in code. Before each session the loop reserves the
  session's cap plus one worst turn (1.68 USD: one Sonnet 5.5 turn writing 200,000 tokens to the
  cache at the 1-hour rate and answering 32,000; `--max-budget-usd` stops between turns only), so
  the phase cannot pass 18. Expected 0.138 USD a covered task (L6) x about 87 covered tasks
  (54 %) = **about 12 USD**. The runner refuses a plan only when its expected cost alone (sessions
  left x 0.138) exceeds 18, i.e. more than 130 covered tasks. A plan above what the ceiling holds
  starts and the guard stops it: at L6's mean cost the guard lets **97** sessions run (spent +
  4.68 <= 18 before each); at worst, every session at its cap plus one worst turn, it guarantees
  **3**. A ceiling stop leaves a random subset of the covered tasks without Sonnet (the seeded
  order); the estimator above stays unbiased and the README reports how many sessions ran. Wall
  time: sessions took a median 23 s and a mean 38 s in the
  2026-10-06 confirmation: about 55 minutes for 87, one at a time.
- **Clock:** phase S does not start before 08:00 (Windows Update restarts 02:00-08:00) nor when
  its sessions at 1.5 x the mean, plus 10 minutes, would cross midnight; no session starts within
  10 minutes of midnight. A clock stop is a pause: a relaunch after 08:00 resumes.
- **Stops, phase J.** A cap refusal is **final**: no further call, the tasks left unasked are
  out of n, what is complete is scored and the README says so; the runner refuses a relaunch.
  An HTTP 402 (no funds), an HTTP 429 or a `STOP` file in `C:\sp-runs\lb162` stop every
  further call. This lot takes 429 out of the Jev client's retryable statuses at run time
  (`no_retry_on_429`, as lot memgate-long), so the first 429 stops; a 529 keeps the client's
  three bounded retries. Each is a **pause, not a result**; the relaunch
  asks only the unasked tasks (a failed task stays failed).
- **Stops, phase S.** A 429 or usage limit ("weekly limit") stops the phase at once, the session
  is recorded as not run and `LIMIT.flag` is written in `C:\sp-runs\lb162`: a pause, never
  scored; the owner tells the other sessions and deletes the flag to resume. A ceiling stop ends
  phase S: what is complete is scored (the estimator above) and the README says so. A `STOP`
  file stops before the next session. Processes are stopped by PID only.

## Commands

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

## Not done, and what follows

Not done: Sonnet on the uncovered tasks (their cost stays an estimate), other cuts, Jev 1.13,
any S arm. If the verdict is "no peor", the README will say that on long-document multiple-choice
questions Jev 1.14 with the long window can answer alone above 0.6 and leave the rest to Sonnet
5.5 within 10 points of Sonnet, at the measured Jev cost and the estimated saving; "peor" says it
cannot; "no concluyente" says this evidence does not decide. Nothing in `policy.py` or
`DEFAULT_MODEL` changes in this lot.
