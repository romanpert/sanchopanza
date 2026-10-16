# The memory gate with the long window, confirmed on 84 unseen LongMemEval questions (lot memgate-long)

**The result.** The long window's lift holds on questions that did not generate it, and the long
gate now reaches BM25 top 3.

- **Confirmed.** On the 84 LongMemEval S test questions lot L6 did not reach, the memory gate
  reading every session whole in one call raised selection recall from **0.726** to **0.905** on
  jev-1.13.0: **+17.8 points [+10.7, +25.7]**. Under the sealed rule (CI lower bound above 0)
  this is **"confirmado"**. L6 measured +18.5 on its 36 questions.
- **Against BM25 top 3** (0.815 on these questions), the long gate is **+8.9 points
  [0.0, +17.3]**: **"alcanza"**. It misses "bate" because the CI's lower bound is exactly 0, not
  above it. The shipped short gate is −8.9 [−21.4, +2.9]: "no alcanza".
- **Cost of the gain.** The long gate selects 32,900 characters a question against the short
  gate's 20,800 (BM25's 40,900), at precision 0.71 against 0.91 (BM25 0.51). One long call costs
  about 0.0051 USD a prompt against the short path's 0.0010.
- **No failures.** Both cells answered all 84 questions: 0 failed cells, no error of any class.

Pre-registered in `prereg.md`:
- sealed in c8d1da1;
- `prereg.sha256` d29c8d4b…, over the document, the code and the hashes of the external inputs;
- reviewed twice by an independent `revisor-prereg` before the seal, with every point it raised
  fixed in the code and the text before any answer.

Model: **jev-1.13.0** (the production `DEFAULT_MODEL`), asked live on 2026-10-15 from a detached
worktree at the sealed commit. Claude was not called.

## What was measured

The 120 LongMemEval S test questions of `docs/results/2026-09-28-memory-gate`, in L6's seeded
launch order: L6 ran ranks 0-35, this lot ranks 36-119. The runner refused to start unless
L6's ids were the head of that order and the 84 were distinct and disjoint from them and from
the dev slice.

Per question, one `needs_recall` call, then the gate's triage in two windows:

- **S**, the shipped gate: each session as its head plus the best-matching window, 900
  characters, 30 a call, a tournament past that.
- **L**, the long window: the long-context header on, every session whole in one `triage_pages`
  call (about 120k tokens).
- **BM25 top 3**, computed, and the gate **recorded on 2026-09-28** (`rec13-S`), replayed free.

The gate keeps the triage's sessions when `needs_recall` looks and none when it does not.
Recall is pooled over gold sessions. It measures the **selection** of `memory_gate.gate` (the
library call), not what an agent answers with it.

## Results per cell (84 questions)

| Cell | Gate recall | Any-hit | All-hit | Characters selected | Precision | Failed cells | Errors by class |
|---|---|---|---|---|---|---|---|
| BM25 top 3 | 0.815 | 0.940 | 0.762 | 40,850 | 0.508 | — | — |
| gate 1.13, recorded 2026-09-28 (S) | 0.720 | 0.750 | 0.524 | 20,413 | 0.926 | 0 | — |
| gate 1.13, S | 0.726 | 0.750 | 0.536 | 20,750 | 0.912 | 0 | none |
| **gate 1.13, L** | **0.905** | 0.905 | 0.833 | 32,883 | 0.714 | 0 | none |

- The excerpt ceiling on these questions is 115 of 150 evidence turns (77 %). L's recall passes
  it, as in L6: the excerpt is what caps the short gate.
- `needs_recall` looked on 78 of 84 questions (92.9 %). The 6 it skipped are all
  single-session-preference questions, so the gate injects nothing there in either window: both
  windows recall 0.25 on the 8 preference questions, against BM25's 0.62.
- **Descriptive:** the long triage alone, if every question looked, would recall 0.936.
- Recall by type, S → L:
  - knowledge update 0.62 → 1.00 (12 questions);
  - single-session assistant 0.42 → 1.00 (12);
  - single-session user 0.50 → 1.00 (10);
  - multi-session 0.84 → 0.93 (25);
  - temporal reasoning 0.85 → 0.88 (17).
- Per question, L kept more gold sessions than S on 30 questions and fewer on 4.
- The recorded 2026-09-28 gate (0.720) and today's S (0.726) agree on these questions. The
  recorded gate's recall on the 84 could be computed free before the seal; it was not looked at
  until this analysis.

## Verdicts

**Rule 1, the confirmation.** The Holm family has one comparison: recall L − S on jev-1.13.0.
The test is a paired bootstrap over questions (10,000 resamples, seed 20261015).

| Comparison | n | L | S | Difference [95 % CI] | Holm p | Failure gap | Verdict |
|---|---|---|---|---|---|---|---|
| recall L − S, 1.13 | 84 | 0.905 | 0.726 | **+17.8 [+10.7, +25.7]** | <0.001 | 0 | **confirmado** |

Under L6's own rule (`l4_stats.verdict`) the same comparison is "mejora".

**Rule 2, against BM25 top 3** (L6's definitions):

| Cell | Difference [95 % CI] | Bate | Alcanza | Verdict |
|---|---|---|---|---|
| **L** | **+8.9 [0.0, +17.3]** | no: lower bound 0.0, not above 0 | yes | **alcanza** |
| S | −8.9 [−21.4, +2.9] | no | no | no alcanza |

BM25 is weaker on these 84 questions (0.815) than on L6's 36 (0.938). The prereg stated that
before the seal: it is free and deterministic.

## Pooled 36 + 84 = 120 (descriptive, no verdict)

L6's 36 questions generated the hypothesis, so this reading carries no verdict.

| Cell | Recall | Any-hit | All-hit | Characters selected | Precision |
|---|---|---|---|---|---|
| BM25 top 3 | 0.851 | 0.950 | 0.808 | 40,657 | 0.525 |
| gate 1.13, recorded 2026-09-28 (S) | 0.725 | 0.742 | 0.542 | 20,307 | 0.925 |
| gate 1.13, S | 0.725 | 0.742 | 0.542 | 20,377 | 0.915 |
| gate 1.13, L | 0.905 | 0.908 | 0.842 | 32,511 | 0.708 |

On all 120 questions:
- L − S is +18.0 points [+11.6, +24.7].
- L − BM25 is +5.4 [−1.8, +12.5].
- S − BM25 is −12.6 [−22.5, −3.1].

## Spend

From the lot's own ledger (`C:/sp-runs/memgate-long/ledger.json`, cap 1.50 USD), which counts
the client's estimate (input tokens × Jev's list price):

| Part | Batch | USD |
|---|---|---|
| Smoke (2 dev questions) | `memgate-long-smoke` | 0.0123 |
| Run (84 questions) | `memgate-long` | 0.5160 |
| **Total** | | **0.5283** |

- **Prereg estimate:** 0.515 USD for the run.
- **Per question:**
  - the long call: 0.4294 USD in all, 0.0051 a question, 121,600 tokens median;
  - the short triage: 250 calls, 0.0848 USD, 0.0010 a question;
  - `needs_recall`: 0.0018 USD in all.
- **Latency:** the long call took 1.6 s median (2.0 s at most); a short triage call 0.28 s median.
- The `jev-preflight`, one call, is off the ledger. The run took about two minutes. Claude: 0.

## Recommendation

**For `memory_gate.gate`: make the long window the default.** The owner adopted it: the long
window is the library default since 2026-10-16 (merge `c65f021`; `SANCHOPANZA_MEMORY_WINDOW=short`
turns it off). The installed memory hook stays on the short window, as below.

- **The case for it.** The gate's job is to find the memory a prompt needs. The long window now
  has a confirmed +18-point recall gain on unseen questions, and it reaches BM25 top 3 where
  the short window does not.
- **Its price:**
  - about 0.005 USD a prompt against 0.001, and about 0.01 USD at the window's
    750,000-character ceiling;
  - one call of about 1.6 s instead of about 3 short calls;
  - a precision drop from 0.91 to 0.71.
- **Why the precision drop matters less than it looks.** The gate renders at most 10,000
  characters (3,000 a memory), most probable first. The extra sessions it selects cost room in
  that cap, not unbounded context.
- **How the change was made.** The package shipped the mode as an opt-in
  (`SANCHOPANZA_MEMORY_WINDOW=long`, merged in 64bf8c8). Making it the default for
  `memory_gate.gate` flipped that default and kept `short` as the setting that turns it off.
  The short window stays the fallback past Jev's long window, without a long-context decider,
  or past the job's budget.
- **What stays as it is.** The installed memory hook keeps the short window. It judges
  candidate records, not LongMemEval sessions, and this lot does not measure it. The records
  replay on SWE-chat did, on 2026-10-16 ([memgate-hook](../2026-10-16-memgate-hook/README.md)):
  on 905 first requests the long window gave more hits (+12.7 points [+6.3, +19.8]) and more
  false alarms (+3.7 [+1.5, +6.2]; the cluster upper bound 6.3 against the sealed +5), "peor en
  ruido". The hook stays short.
- **Not measured.** Answer accuracy downstream of the gate, jev-1.14.0 on these 84 (L6 found no
  model effect on its 36), and the preference questions `needs_recall` skips.

## Files

- **Runner:** `benchmarks/memgate_long/memgate_long.py`. Analysis: `memgate_long_analysis.py`.
  Tests: `tests/test_memgate_long.py`.
- **Scored rows:** `a7-scored.jsonl`. It holds ids, session indexes, sizes, the look and the
  failed cells' error classes (none here); no text.
- **Answers per cell:** `a7-answers-j13r-S.jsonl` and `a7-answers-j13r-L.jsonl`, hashed keys
  with no text. A relaunch replays them free.
- **Summary:** `summary.json`.
- **Smoke on dev items:** `smoke-*`.

Reproduce for free from the recordings:

```bash
PYTHONPATH=src python benchmarks/memgate_long/memgate_long.py --run
```

This needs the external inputs named in `prereg.manifest.json`, under the home cache. Checked
after the run: the replay rewrites `a7-scored.jsonl` byte for byte and the same `summary.json`.
