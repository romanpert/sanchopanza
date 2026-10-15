# The installed memory hook with the long window, on SWE-chat records (lot memgate-hook): pre-registration

**DRAFT, not sealed.** Written 2026-10-15, before any answer of either arm on these requests.
To be reviewed against the code by an independent `revisor-prereg` agent before the seal.
`prereg.sha256` will hold the hash of this file together with the code and inputs it names
(`prereg.manifest.json`, written by `python benchmarks/memgate_hook/memgate_hook.py --seal`).
The sealing commit's message carries the hash.

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
**909 first requests**. Labels by code from the transcripts, as `build.py`: a record is
`lineage` when the request rewrites a line it wrote, `file` when the request changes a file it
changed, none otherwise. Public data and public code: anyone with the dataset rebuilds them.

These sets were used to design and confirm the hook's touch and its first-prompt recall (v3 to
v6), always on the short window; the aggregate numbers of the short window's first-prompt
recall on them are published there. The long window has never been run on them. The hypothesis
comes from LongMemEval, not from these records.

## Arms (`benchmarks/memgate_hook/memgate_hook.py`)

Each request goes through the installed hook's own recall (`memory_hook.recall`) twice, in an
environment where every memory variable is unset except: decider mode, recall at the first
prompt, the store and log in a temporary folder, the working-tree snapshot off (no cwd). The
prompt is the session's first prompt whole, read from its transcript (`replay_v5.first_prompt`).
The pool is saved to the store as the hook would hold it. A fresh squire per call
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
requests in both arms, with the same candidates.

One model: **jev-1.13.0** (the production `DEFAULT_MODEL`, which the installed hook asks),
pinned (`JevDecider(model="jev-1.13.0", long_context=False, images=False)`, 30 s a request). An
answer served by another model is not recorded and pauses the run. No request of either arm
needs Jev's long-context header here: the largest L request in the dry run is 26,345
characters, under the 190,000 of `SHORT_WINDOW_CHARS`. So this lot measures whole records on the
same decider, not the long-context header.

**Order.** The 909 requests in a seeded order (seed 20261016 over the sorted request ids). The
first 4 the hook would ask (a BM25 candidate passes the name gate; free to check) are the smoke
and are out of the run: **905 requests** in the run, **659** of which the hook asks. Both arms
back to back per request, S first at even positions and L first at odd ones, one call at a time.

## Metrics

On the requests the hook asks in both arms where neither arm failed (complete cases). A
request is **related** when one of the candidates the decider was shown is labelled `lineage`
or `file`. The dry run counted **176** related requests and **483** without a related candidate.

- **Primary, hit (L against S):** on related requests, whether the hook gave at least one
  related record at the prompt. Paired binary.
- **Guard, false alarm (L against S):** on requests without a related candidate, whether the
  hook gave anything at the prompt. Paired binary.
- **Descriptive**, per arm, over all 905 first requests, v5's first-request reading for the
  prompt alone (no touch): recall (requests with a related record in the pool given one),
  precision (records given that are related), noise (requests with nothing related in the pool
  given anything), records given, failed requests, L's fall backs by class, long-call dollars.

A failed arm on a request: it asked and got no probability at all (after any fall back), or the
hook's decider time ran out.

## Statistics

Lot L4's (`l4_stats.paired_binary`): exact two-sided McNemar on the discordant pairs; the
difference's 95 % CI by a paired bootstrap over requests (10,000 resamples, seed 20261015,
percentile), and a second CI by a bootstrap over the groups the requests come from (one person
on one repository), reported beside it. No multiplicity correction: one primary test; the guard
is a condition, not a second claim.

## Verdict rule (decided now, in this order)

1. **"no concluyente (n bajo)"**: fewer than 30 complete related requests, or fewer than 30
   complete requests without a related candidate.
2. **"no medido"**: no difference computable.
3. **"no medido (fallos)"**: L failed on more than 2 % more of the asked requests than S.
4. **"peor en ruido"**: the false-alarm difference L − S has a 95 % CI upper bound above
   **+5 points** (L may give unrelated records more often), whatever the hit result.
5. **"mejora"**: exact McNemar p < 0.05 on hits with L ahead.
6. **"no peor"**: the hit difference's 95 % CI lower bound at or above **−5 points**.
7. **"peor"**: otherwise.

Only **"mejora"** supports proposing the long window as the installed hook's default; the owner
decides. Every other reading keeps the hook on the short window: "no peor" shows no gain to pay
for (L's requests are larger, about 1.6 times S's characters at the median).

## Power

From the dry run's 176 related requests (`memgate_hook_analysis.power_table`, exact): the
primary test reaches 80 % power when L alone hits on about **9.5 %** of related requests and S
alone on 2 %. By scenario (L-only, S-only): 0.10/0.02 → 0.86; 0.08/0.02 → 0.67; 0.06/0.02 →
0.38; 0.05/0.01 → 0.49; 0.15/0.05 → 0.82. So this lot sees a net gain of about 7 points or more
and can miss a smaller one: a "no peor" here does not rule out a gain of a few points.

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
    failed calls in a row): nothing written, exit 2. A relaunch replays every recorded answer
    free and asks the rest. The shipped client's retries on 429 are off for this lot.
  - A timeout or an HTTP 400 alone is that arm's failure on that request (rule 3), not a stop.
- Answers are recorded per arm in this folder (`run-answers-S.jsonl`, `run-answers-L.jsonl`,
  hashed keys, no text). Scored rows hold request ids, record keys, labels, probabilities, what
  was shown, L's window and fall-back class: no text. A scored file of record is frozen: a live
  run does not ask again.
- `jev-preflight` for jev-1.13.0 (one call, tens of micro-dollars) runs before the first live
  call, off the ledger.

## Running it

From a `git worktree add --detach` at the sealed commit, with the main checkout's python and
`PYTHONPATH=<worktree>\src`, launched outside the session, never between 02:00 and 08:00 (the
machine's update window). 1,318 live calls one at a time, at the 0.3 s median memgate-long
measured for a short call, plus the local hook work: about 15 to 25 minutes.

```
python benchmarks/memgate_hook/memgate_hook.py --build
python benchmarks/memgate_hook/memgate_hook.py --dry
python benchmarks/memgate_hook/memgate_hook.py --seal
python benchmarks/memgate_hook/memgate_hook.py --smoke --live
python benchmarks/memgate_hook/memgate_hook.py --run --live
python benchmarks/memgate_hook/memgate_hook.py
```

The key comes from `TYPESAFE_API_KEY` or the `.env` that `SANCHOPANZA_KEYS_ENV` names, read
inside the process and never printed. The live paths check the seal before reading the key and
spend nothing if anything changed.

## The smoke

The 4 requests of the seeded order the hook would ask first, both arms, on the smoke batch. Seen:
that the live path, the caps and the recording work end to end; nothing in it changes these
rules, and those 4 requests are not in the run.

## Seal

`prereg.sha256` = sha256 over the lines `"<path> <sha256>\n"` of `prereg.manifest.json`: this
file, the runner, its analysis, its tests, the modules it imports from lot memgate-long, lot L4
and `benchmarks/memory_real`, the three selection files, every file of `src/sanchopanza/**/*.py`
(text files hashed with LF line ends), and the hash of the built items file under the home
folder (`.cache/sanchopanza/memory-real/items-memgate-hook.jsonl`). A re-seal (`--seal
--reseal`) is refused in code once this lot's ledger holds any spend or any answer is recorded
in this folder.

## Known limits, said before the data

- **The record's title holds a local time.** `Episode.text()` heads each record with its time in
  the machine's time zone, so L's requests, and the recording keys, depend on it. A free replay
  must run in the same time zone as the live run.
- **The labels cannot credit a record that changed nothing** (a question, an investigation):
  it is labelled none. The name gate lets such records through to the decider, so a hit on one
  counts as a false alarm in both arms alike.
- **A component effect.** v5 found the touch already gives the records the first-prompt recall
  finds; a gain here is a gain of the prompt step, not of the hook with its touch. The
  descriptive reading is of the prompt alone.
- **Not measured:** jev-1.14.0, the long-context header (no request needs it here), answers or
  outcomes downstream of what is given.
