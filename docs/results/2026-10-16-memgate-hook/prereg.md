# The installed memory hook with the long window, on SWE-chat records (lot memgate-hook): pre-registration

Written 2026-10-15 and revised on 2026-10-16 after a code review and two independent
`revisor-prereg` reviews, before any answer of either arm on these requests. `prereg.sha256`
holds the hash of this file together with the code and inputs it names (`prereg.manifest.json`,
written by `python benchmarks/memgate_hook/memgate_hook.py --seal`), in a commit of its own whose
message carries the hash.

## The question

The long window (every candidate read whole in one call) is the default of the library gate
`memory_gate.gate`, confirmed on 84 unseen LongMemEval questions
(`docs/results/2026-10-15-memgate-long`: recall 0.726 to 0.905, +17.8 points [+10.7, +25.7]).
The installed hook (`memory_hook`, what `sanchopanza install` wires) stays on the short window:
at a session's first prompt it judges records of earlier requests, each as its 880-character
page, and nothing measured the long window there. Records are bounded by code (request, report
and output at about 1,000 characters each), so the LongMemEval gain, found where evidence sat
deep in a long session, may not carry over.

**At a session's first prompt, does the installed hook give a related earlier record more often
when the decider reads each candidate record whole (`SANCHOPANZA_MEMORY_WINDOW=long`) than when
it reads its page (the default), without giving records more often where nothing is related?**

## Data

`SALT-NLP/SWE-chat` (ODC-BY): real Claude Code sessions in public repositories. The three sets
of `docs/results/2026-10-01-memory-real`: `selection.json` (60 groups, development and held out),
`selection-2.json` (74 groups) and `selection-3.json` (101 groups); 1,151 sessions, disjoint
across the sets. The transcripts are public; they are read from the local cache
(`~/.cache/sanchopanza/memory-real/transcripts`), not redistributed.

Items (`--build`, free, `build_v4b.items_for` as in v4.1 and v5): the first request of every
later session of every group that has a pool (the records of the group's earlier sessions):
**909 first requests**. Each item stores the session's first prompt whole, as UserPromptSubmit
carries it (`replay_v5.first_prompt`), so the sealed items file holds every input of the run.
Labels by code from the transcripts, as `build.py`: a record is `lineage` when the request
rewrites a line it wrote, `file` when the request changes a file it changed, none otherwise.
Public data and public code: anyone with the dataset rebuilds them.

**Not held out.** These sets were used to design and confirm the hook's touch and its
first-prompt recall (v3 to v6), always on the short window: the hook's K, cut, name gate and
render cap were tuned on them, and the aggregate numbers of the short window's first-prompt
recall on them are published. **S is tuned to these data, which favours S.** The long window has
never been run on them; the hypothesis comes from LongMemEval, not from these records.

## Arms (`benchmarks/memgate_hook/memgate_hook.py`)

Each request goes through the installed hook's own recall (`memory_hook.recall`) twice, in an
environment where every memory variable is unset except: decider mode, recall at the first
prompt, the store and log in a temporary folder, the working-tree snapshot off (no cwd). The
pool is saved to the store as the hook would hold it, each record file dated at its record's
time (`save_pool`): the hook loads the newest 300 record files (`episodes.LOAD_LIMIT`) by date,
and 2 of the 905 pools hold more than 300 records (the largest 326). A fresh squire per call
(`Squire(decider, redact=redact_secrets)`, default thresholds and limits), as one hook process
has.

- **S**: nothing else set: the hook's default, the short window (each candidate's page).
- **L**: `SANCHOPANZA_MEMORY_WINDOW=long`: each candidate whole (`Episode.text()`), on the same
  decider while the request is under Jev's short window (`SHORT_WINDOW_CHARS`), within the
  hook's decider time less 3 s, falling back to the pages when it cannot run (the shipped
  `memory_window.run_long`).

BM25's candidates (`MEMORY_K` 5), the v5 name gate, the cut (`MEMORY_KEEP_AT` 0.8) and the
character cap (`MEMORY_CHARS` 6,000) are the shipped ones and the same in both arms; only the
decider's reading differs. The free dry run checked it: the decider is asked on the same 659
requests in both arms, with the same candidates. A request whose arms saw different candidates
is counted and left out of the comparison.

One model: **jev-1.13.0** (the production `DEFAULT_MODEL`, which the installed hook asks),
pinned (`JevDecider(model="jev-1.13.0", long_context=False, images=False)`), with the client's
**10 s** a request, as installed. An answer served by another model is not recorded and pauses
the run. No request of either arm needs Jev's long-context header here: the largest L request in
the dry run is 26,345 characters, under the 190,000 of `SHORT_WINDOW_CHARS`. So this lot measures
whole records on the same decider, not the long-context header.

**Order.** The 909 requests in a seeded order (seed 20261016 over the sorted request ids). The
first 4 the hook would ask (a BM25 candidate passes the name gate; free to check) are the smoke
and are out of the run: **905 requests** in the run, **659** of which the hook asks. Both arms
back to back per request, S first at even positions and L first at odd ones, one call at a time,
in one event loop per invocation (the arms' clients are made inside it).

## Metrics

On the requests the hook asks in both arms, with the same candidates, where neither arm failed
(complete cases).

- A request is **related** when a candidate the decider was shown is labelled `lineage` or
  `file` (176 in the dry run). It is **hittable** when such a candidate also passes the v5 name
  gate for that prompt: only then can either arm give a related record (**126**). The 50
  related requests the gate blocks are counted and left out of the primary.
- **Primary, hit (L against S):** on hittable requests, whether the hook gave at least one
  related record at the prompt. Paired binary.
- **Guard, false alarm (L against S):** on requests without a related candidate (**483**),
  whether the hook gave anything at the prompt. Paired binary. Reported beside it, split by
  what was given: a record that changed files, or one that changed nothing (a question, an
  investigation, which the labels can never credit).
- **Descriptive**, per arm, over all 905 first requests, v5's first-request reading for the
  prompt alone (no touch): recall (requests with a related record in the pool given one),
  precision (records given that are related), noise (requests with nothing related in the pool
  given anything), records given, failed requests, L's fall backs by class, long-call dollars.
- **Test-retest, descriptive** (free, after the run): S's probabilities against the answers v5's
  passes cached for the same request and candidates (`score.ANSWERS`, keyed by prompt and record
  keys): records matched, mean and median absolute difference, agreement at the 0.8 cut.

A failed arm on a request: it asked and got no probability at all (after any fall back), or the
hook's decider time ran out.

## Statistics

Lot L4's (`l4_stats.paired_binary`): exact two-sided McNemar on the discordant pairs; the
difference's 95 % CI by a paired bootstrap over requests (10,000 resamples, seed 20261015,
percentile), and a second CI by a bootstrap over the groups the requests come from (one person
on one repository). Where a rule reads a CI, it reads the wider of the two (the smaller lower
bound, the larger upper bound), except where it names the group CI. No multiplicity correction:
one primary test; the guard and the net condition are conditions, not further claims.

## Verdict rule (decided now, in this order)

1. **"no concluyente (n bajo)"**: fewer than 30 complete hittable requests, or fewer than 30
   complete requests without a related candidate.
2. **"no medido"**: no difference or no CI computable.
3. **"no medido (fallos)"**: L failed on more than 2 % more of the asked requests than S.
4. **"peor en ruido"**: the false-alarm difference L − S has an upper bound above **+5 points**
   in either CI (requests or groups), whatever the hit result.
5. **"mejora"**: all of: exact McNemar p < 0.05 on hits with L ahead; the **group** CI of the
   hit difference above 0; and, in counts, L's extra hits (L-only minus S-only on hittable
   requests) at least L's extra false alarms (L-only minus S-only on requests without a related
   candidate).
6. **"no peor"**: the hit difference's lower bound at or above **−5 points** in both CIs.
7. **"peor"**: otherwise.

Only **"mejora"** supports proposing the long window as the installed hook's default; the owner
decides. Every other reading keeps the hook on the short window: "no peor" shows no gain to pay
for (L's requests are larger, about 1.6 times S's characters at the median).

## Power

From the dry run's **126 hittable requests** (`memgate_hook_analysis.power_table`, exact, the
McNemar part of rule 5 only): 80 % power needs L alone to hit on about **11.5 %** of them with S
alone on 2 %. By scenario (L-only, S-only): 0.10/0.02 → 0.70; 0.08/0.02 → 0.48; 0.06/0.02 →
0.24; 0.05/0.01 → 0.31; 0.15/0.05 → 0.66. The group-CI and net conditions lower these further.
So this lot sees a net gain of about 9 points or more and can miss a smaller one: a "no peor"
here does not rule out a gain of several points.

## Spend, caps and stops

- **Expected cost.** From the dry run (`--dry`, free): 659 calls an arm, none recorded yet.
  Pessimistic (`CappedDecider`'s estimate, a token per three characters at 0.042 USD a million):
  S 0.070 USD, L 0.120 USD, **0.19 USD** in all. At Jev's median billed request (71
  micro-dollars): 0.094 USD. If every L call fell back, its short call adds up to 0.07 USD more:
  0.26 USD at worst. Smoke: about 0.001 USD.
- **Hard caps in code:** a new ledger of this lot only, `C:/sp-runs/memgate-hook/ledger.json`,
  capped at **0.60 USD** for everything (smoke included); batch `memgate-hook` capped at
  **0.60 USD**; the smoke on its own batch `memgate-hook-smoke`, capped at **0.05 USD**. Every
  live call goes through `CappedDecider`, which reserves its pessimistic estimate before calling
  and refuses when it does not fit; a call that costs more than its reservation can overshoot by
  the difference. A new request is not started when 0.003 USD (a pair and a fall back) would not
  fit in the room left, the smaller of the batch's cap minus its spend and the ledger's cap
  minus its spend (soft stop). Each hook call also holds the job's own cap (`Thresholds.max_usd`,
  0.10 USD), as installed.
- **What the ledger counts** is the client's estimate (input tokens × the list price), not
  TypeSafe's bill; it is compared with the dashboard after the smoke.
- **Stops are dead**, lot memgate-long's `StopDead`: the first stop refuses every later call
  without making it and drops the pair it hit.
  - **Cap** (a call the cap refuses while the room left no longer holds 0.003 USD): the completed
    pairs are the run; `run-scored.jsonl` is written from them and the verdict is read on them.
    A refusal with more room left is a ledger fault, read as a pause.
  - **Pause** (HTTP 401, 402, 403, 429 or 5xx, no connection, an answer from another model, or 3
    failed calls in a row): nothing written, nothing scored, exit 2. A 402 (out of funds) is a
    pause like the others, not an end of the lot: the balance cannot be checked beforehand, so a
    relaunch after a top-up replays every recorded answer free and asks only the rest. The
    shipped client's retries on 429 are off for this lot.
  - A timeout or an HTTP 400 alone is that arm's failure on that request (rule 3), not a stop.
- Answers are recorded per arm in this folder (`smoke-answers-*.jsonl`, `run-answers-*.jsonl`,
  hashed keys, no text). Scored rows hold request ids, record keys, labels, whether each
  candidate changed files, probabilities, what was shown, L's window and fall-back class: no
  text. A scored file of record is frozen: a live run does not ask again.
- `jev-preflight` for jev-1.13.0 (one call, tens of micro-dollars) runs before the first live
  call, off the ledger.

## Before any live call (in code)

`--smoke --live` and `--run --live` check, in this order, and spend nothing on a refusal:

1. the seal: this file, the code, the items file and the launcher match `prereg.sha256`;
2. the hour: not between 02:00 and 08:00 (the machine's update window);
3. HEAD is the commit that last wrote `prereg.sha256`; it has a single parent; and it changed
   nothing but `prereg.sha256` and `prereg.manifest.json` (`git diff --name-only HEAD^ HEAD`);
4. nothing differs from HEAD (staged, unstaged or untracked) except the run's own new files in
   this folder (`*-answers-*`, `*-scored*`, `*-zone.json`, `summary.json`): this file and the
   seal's two files included;
5. for the run, `smoke-scored.jsonl` exists;
6. on a relaunch after a pause, `<smoke|run>-zone.json` already holds the same time zone.

Then the process's time zone (names and offsets), HEAD and HEAD^ are written to
`<smoke|run>-zone.json`, the key is read, and the preflight runs. A re-seal (`--seal --reseal`)
is refused while this file differs from HEAD: it seals a committed prereg.

## Running it

From a `git worktree add --detach` at the sealed commit (`<worktree>`), with the main checkout's
python and `PYTHONPATH=<worktree>\src`, launched outside the session by WMI with the launcher
`C:\sp-runs\memgate-hook\memgate-hook-run.cmd` (`smoke`, then `run`), which is not tracked. The
launcher logs the start, `tzutil /g`, HEAD, its own sha256, the python's version and httpx's,
and refuses to start while its python or its keys file is still a placeholder (`<PYTHON>`,
`<KEYS_ENV_PATH>`). The seal holds it by `memgate_hook_live.launcher_digest`: its sha256 with LF
line ends and those two lines read as their placeholders, so filling them does not break the
seal and changing any other line does. That digest:
`c01d5e64d7e84e75016503ddfbfa7988d3e7428423b14fe63d26130f3eca8c7b`. No local path
goes into anything tracked. 1,318 live calls one at a time, at the 0.3 s median memgate-long
measured for a short call, plus the local hook work: about 15 to 25 minutes.

```
python benchmarks/memgate_hook/memgate_hook.py --build
python benchmarks/memgate_hook/memgate_hook.py --dry
python benchmarks/memgate_hook/memgate_hook.py --seal
memgate-hook-run.cmd smoke      (by WMI)
memgate-hook-run.cmd run        (by WMI)
python benchmarks/memgate_hook/memgate_hook.py
```

The key comes from `TYPESAFE_API_KEY` or the `.env` that `SANCHOPANZA_KEYS_ENV` names, read
inside the process and never printed.

**The replay.** `--run` (or `--smoke`) without `--live` replays the recorded answers through the
hook again, writes `<name>-replay-scored.jsonl` (never over the rows of record) and counts the
rows that differ from them (exit 3 if any). It is refused in a time zone other than the one in
`<name>-zone.json`: L's requests hold each record's local time (`Episode.title`), so a replay
elsewhere would ask different keys. The summary holds the run's UTC offsets (not the zone's
localised names), the commit it ran at and that commit's parent.

## The smoke

The 4 requests of the seeded order the hook would ask first, both arms, on the smoke batch. Seen:
that the live path, the caps and the recording work end to end; nothing in it changes these
rules, and those 4 requests are not in the run.

## Seal

`prereg.sha256` = sha256 over the lines `"<path> <sha256>\n"` of `prereg.manifest.json`: this
file, the runner, its analysis, its live rules, its tests, the modules it imports from lot
memgate-long, lot L4 and `benchmarks/memory_real`, the three selection files, every file of
`src/sanchopanza/**/*.py` (text files hashed with LF line ends), the hash of the built items
file under the home folder (`.cache/sanchopanza/memory-real/items-memgate-hook.jsonl`, with each
first prompt in it), and the launcher's digest (above). A re-seal (`--seal --reseal`) is refused in code once this lot's ledger
holds any spend or any answer is recorded in this folder.

## Known limits, said before the data

- **Not held out, and S is tuned here** (see Data): a reading that favours S.
- **The record's title holds a local time**: the replay must run in the run's time zone (in code).
- **The labels cannot credit a record that changed nothing**: given where nothing is related, it
  counts as a false alarm in both arms alike; the guard's split shows how much of it is that.
- **A component effect.** v5 found the touch already gives the records the first-prompt recall
  finds; a gain here is a gain of the prompt step, not of the hook with its touch.
- **Not measured:** jev-1.14.0, the long-context header (no request needs it here), answers or
  outcomes downstream of what is given.
