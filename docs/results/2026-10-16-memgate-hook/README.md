# The installed memory hook with the long window, on 905 SWE-chat first requests (lot memgate-hook)

**The result.** Reading each candidate record whole lets the installed hook give a related
earlier record more often at a session's first prompt, but it also gives records more often
where nothing is related, past the sealed margin. By the sealed rule: **"peor en ruido"**. The
installed hook stays on the short window.

- **Hits, the primary (126 hittable requests).** The hook gave a related record on 45 with the
  long window (L) against 29 with the shipped short window (S): **35.7 % against 23.0 %, +12.7
  points [+6.3, +19.8]** (group bootstrap [+6.3, +19.2]); 18 requests only L got, 2 only S got;
  exact McNemar p = 0.0004.
- **False alarms, the guard (483 requests with no related candidate).** L gave something on 42,
  S on 24: **8.7 % against 5.0 %, +3.7 points [+1.5, +6.2]** (group bootstrap [+1.3, +6.3]); 27
  only L, 9 only S; p = 0.004. The guard reads the wider upper bound, **6.3 points against the
  sealed +5**: it fails by 1.3 points. The net condition of "mejora" fails too: L's 16 extra hits
  are fewer than its 18 extra false alarms.
- **Cost of the long window here:** 0.113 USD for L's 659 calls against 0.065 for S's (4,190
  input tokens median against 2,480), at the same latency (0.22 s median). No call failed, none
  fell back, and both arms saw the same candidates on every request.

Pre-registered in `prereg.md`:
- sealed in 211227c (`prereg.sha256` cc075dd3…), over the document, the code (instrument commit
  ccebeff), the items file with every first prompt, and the launcher;
- reviewed twice by an independent `revisor-prereg` before the seal, with what it raised fixed in
  the code and the text before any answer.

Model: **jev-1.13.0** (the production `DEFAULT_MODEL`, which the installed hook asks), live on
2026-10-16 from a detached worktree at the seal commit. Claude was not called.

## What was measured

The installed hook's recall at a session's first prompt (`memory_hook.recall`, as `sanchopanza
install` leaves it: decider mode, the v5 name gate, 5 BM25 candidates, the 0.8 cut, the 6,000
character cap), replayed through its own code on the first request of every later session of
the three SWE-chat sets of `docs/results/2026-10-01-memory-real`: 909 first requests, 4 in the
smoke, **905 in the run**, of which the hook asked the decider on **659**. Two arms on the same
requests, back to back, the first arm alternating:

- **S**: nothing set, the hook's default: each candidate as its 880-character page.
- **L**: `SANCHOPANZA_MEMORY_WINDOW=long`: each candidate whole (`Episode.text()`), on the same
  decider (no request came near Jev's short window, so no long-context header).

Labels by code from the transcripts (`lineage`: the request rewrites a line the record wrote;
`file`: it changes a file the record changed). A request is **hittable** when a related
candidate passes the name gate: only there can either arm give a related record. Of the 176
asked requests with a related candidate, 126 are hittable and 50 are blocked by the gate in both
arms alike. **These sets are not held out**: the hook's K, cut, gate and cap were tuned on them,
on the short window, which favours S.

## Verdict (the sealed rule, in its order)

| Step | Reading | Result |
|---|---|---|
| 1. n | 126 hittable, 483 without a related candidate (both ≥ 30) | passes |
| 2. computable | both differences and their CIs | passes |
| 3. failures | 0 in S, 0 in L | passes |
| 4. guard | false alarms L − S, wider 95 % upper bound **+6.3** > +5 | **fails: "peor en ruido"** |
| 5. "mejora" (not reached) | McNemar p 0.0004 and group CI above 0 hold; 16 extra hits < 18 extra false alarms | would fail |

**The false alarms, by what was given** (the same 483 requests; one request can count in both):

| Record given where nothing is related | S | L | L − S [95 % CI] | Only L / only S |
|---|---|---|---|---|
| any | 5.0 % | 8.7 % | +3.7 [+1.5, +6.2] | 27 / 9 |
| one that changed files | 1.2 % | 2.9 % | +1.7 [+0.4, +3.1] | 9 / 1 |
| one that changed nothing (a question, an investigation) | 3.7 % | 6.0 % | +2.3 [+0.2, +4.4] | 19 / 8 |

About three fifths of L's extra false alarms are records that changed nothing. The labels can
never credit such a record, so some of them may be useful context the metric cannot see; the
rule counts them, as sealed. Records given where nothing is related: 29 in S, 55 in L.

## Descriptive, over all 905 first requests (the prompt alone, no touch)

| Arm | Recall (requests with a related record in the pool given one) | Precision (records given that are related) | Noise (requests with nothing related given anything) | Records given |
|---|---|---|---|---|
| S | 0.131 | 0.432 | 0.031 | 74 |
| L | 0.204 | 0.368 | 0.054 | 133 |

`lineage` hits on the hittable requests: 15 in S, 28 in L.

## Power against what came out

The prereg gave the primary test 80 % power when L alone hits on about 11.5 % of the hittable
requests with S alone on 2 %. It came out at 14.3 % (18 of 126) and 1.6 % (2 of 126): the gain on
hits was there to see, and was seen. The guard decided the lot, not the primary.

## What it implies

- **The installed hook stays on the short window** (`SANCHOPANZA_MEMORY_WINDOW` unset). The long
  window there finds more of what is related, and gives more of what is not, by more than the
  margin fixed before the data. It stays an opt-in (`=long`) for whoever prefers recall at a
  session's start to a cleaner one.
- **The library gate's default does not change from this.** `memory_gate.gate` reads memory
  files, and its long window was confirmed on LongMemEval
  (`docs/results/2026-10-15-memgate-long`: recall 0.726 to 0.905), a different population for
  three reasons:
  - there the evidence sat deep inside long sessions that the 900-character excerpt cut away;
    here a record is bounded by code to about 1,000 characters a section, and its page already
    shows most of it;
  - there every question has gold sessions to find and the gate is behind `needs_recall`; here
    73 % of the asked requests (483 of 659) have nothing related, so a false alarm is the common
    case the guard is about;
  - there the gate renders at most 10,000 characters of what it keeps; here what is kept goes
    into a session's first prompt as whole records.
  This lot does not measure the library gate, and its rule does not reach it. Both lots show the
  same direction, more kept at lower precision (memgate-long: precision 0.91 to 0.71).

## Spend

From the lot's own ledger (`C:/sp-runs/memgate-hook/ledger.json`, cap 0.60 USD), the sum of the
settled amounts: the client's estimate (input tokens × Jev's list price), not TypeSafe's bill.

| Part | Batch | Calls | USD |
|---|---|---|---|
| Smoke (4 requests) | `memgate-hook-smoke` | 8 | 0.0011 |
| Run (905 requests) | `memgate-hook` | 1,318 | 0.1783 |
| **Total** | | 1,326 | **0.1794** |

- Prereg estimate: 0.19 USD pessimistic for the run.
- By arm: S 0.0653, L 0.1130.
- The two `jev-preflight` calls are off the ledger.
- Smoke 11:22:46-11:22:56, run 11:32:19-11:40:49 on 2026-10-16, both exit 0. Claude: 0.

## Test-retest (descriptive, free)

S's probabilities against the answers v5's passes cached for the same request and candidates
(`score.ANSWERS`): **1,840 records** matched. Mean absolute difference 0.018, median 0.010, and
99.4 % of them fall on the same side of the 0.8 cut. The short arm reads as it did in v5.

## Not done

- jev-1.14.0; Jev's long-context header (no request needed it here).
- Whether a session uses what is given, or what it costs downstream: this measures selection.
- The hook with its touch: v5 found the touch already gives what first-prompt recall finds, so
  a gain here is a gain of the prompt step alone.
- A long window with a stricter cut or without change-less records: that would be designed on
  these data and would need fresh requests to confirm.

## Files

- **Runner:** `benchmarks/memgate_hook/memgate_hook.py`; analysis `memgate_hook_analysis.py`;
  live conditions `memgate_hook_live.py`. Tests: `tests/test_memgate_hook.py`.
- **Scored rows:** `run-scored.jsonl`: request ids, record keys, labels, whether each candidate
  changed files, probabilities, what was shown, L's window; no text.
- **Answers per arm:** `run-answers-S.jsonl` and `run-answers-L.jsonl`, hashed keys with no text.
- **Summary:** `summary.json`, with the run's UTC offsets, its commit and that commit's parent.
- **Zone files:** `run-zone.json` and `smoke-zone.json` hold the zone names too; the replay
  compares them.
- **Smoke:** `smoke-*`.

Reproduce for free from the recordings, in the run's time zone, with the items built from the
SWE-chat cache (`--build`):

```bash
PYTHONPATH=src python benchmarks/memgate_hook/memgate_hook.py --run
```

Checked after the run: the replay rebuilds `summary.json` exactly and every record shown in both
arms. On 15 rows a probability differs by a few hundredths: 11 requests repeat within the run,
Jev was asked each time, and the replay answers every repeat from one recording.
