# Jev 1.14 answering alone above 0.6, Sonnet 5.5 elsewhere, on 162 fresh LongBench v2 tasks (lot lb162)

**The result.** On long-document multiple-choice questions, the hybrid is **no worse than
Sonnet 5.5 alone** under the sealed −10-point rule.
- **Verdict:** "no peor". Hybrid minus Sonnet is **+1.2 points**, 95 % CI **[−3.1, +5.6]**,
  over 162 tasks.
- **The product claim** also needed coverage ≥ 20 %. Jev covered **37 %** (60 of 162), so it
  holds: **"sustituye"**.
- **On the covered tasks:** Jev was right on 31 of 60, Sonnet on 29. McNemar 8 against 6,
  p 0.79. The tie seen post hoc in L6 holds on fresh tasks.
- **Cost:**
  - Jev cost 0.874 USD for all 162 tasks; Sonnet 5.757 USD on the 60 covered.
  - Sonnet's cost on the other 102 tasks was not measured. Estimated at 0.123 USD a task,
    the hybrid saves about **27 % of Sonnet's cost** (4.88 of an estimated 18.30 USD).

**What the margin allows.** Over all 162 tasks, −10 points at 37 % coverage means Jev could
have been up to **27 points** less accurate than Sonnet on the tasks it answers. The measured
CI is far inside that: on the covered tasks it is about [−8, +15] points.
- Under L6's original −2-point rule the result would be "no concluyente": the lower bound is
  −3.1.
- The −10 margin is the owner's product decision, fixed before the data.

The setup:
- **Arms:**
  - Jev `jev-1.14.0`, with the long-context header and up to 900,000 characters of the
    document (the long window, L6's j14-L cell);
  - Sonnet 5.5 (`claude-sonnet-5-5`) in clean Claude Code 2.1.287 (arm N of the 2026-10-06
    confirmation).
- **Pre-registration:** `prereg.md`, sealed at c483beb (`prereg.sha256` 01de9ff5…). It was
  reviewed twice by `revisor-prereg` before the seal.
- **The run:** live on 2026-10-15 from a detached worktree of the sealed commit.
- **Reproducibility:** a free replay of phase J from the recorded answers reproduces
  `jev-scored.jsonl` byte for byte. Recomputing gives the same `sonnet-rows.jsonl` and
  `summary.json`.

## Design

- **Tasks.** The 162 LongBench v2 tasks outside the 60 drawn on 2026-10-06, in the same
  domains: Single- and Multi-Document QA, contexts over 100,000 characters.
  - Chosen by metadata only and frozen before any answer (`ids.txt`, sha256 da7d37d3…).
  - Length bands: 38 short, 88 medium, 36 long. Difficulty: 50 easy, 112 hard.
  - 134 documents fit the 900,000-character window whole; 28 were middle-cut.
- **Phase J.** One Choice A-D per task over the document. A refused call is asked again at
  0.8 and then 0.64 of the window.
- **The cut.** A task is covered when Jev's top-choice probability is ≥ 0.6.
- **Phase S.** One clean Claude Code session per covered task, graded by LongBench v2's
  official `extract_answer`. Sonnet's answer stands on the uncovered tasks, so they add 0 to
  hybrid minus Sonnet.
- **Statistics.** Paired bootstrap over the 162 tasks (10,000 draws, seed 20261015, all kept)
  and exact McNemar on the covered disagreements.

## Primary result

| | Value |
|---|---|
| Tasks (n) | 162, none left unasked, none failed |
| Covered at 0.6 | 60 (**37.0 %**; L6: 27 of 50, 54 %) |
| Sonnet sessions on them | 60 of 60 |
| Jev right on the covered tasks | 31 of 60, **51.7 %** (Wilson 39.3-63.8 %) |
| Sonnet right on the same tasks | 29 of 60, **48.3 %** |
| Disagreements | 14: Jev only 8, Sonnet only 6 (McNemar p 0.79) |
| Hybrid minus Sonnet | **+1.2 points**, 95 % CI **[−3.1, +5.6]** (normal approximation [−3.3, +5.8]) |
| Verdict at −10 points | **no peor** |
| Product claim (also coverage ≥ 20 %) | **sustituye** |

**Sensitivity reading** (registered): no Sonnet session ended in an infrastructure error. So
counting such sessions as wrong changes nothing: +1.2 points, [−3.1, +5.6], "no peor".

**Jev alone.** Jev alone gets 64 of 162 right (39.5 %), and 33 of the 102 it did not cover
(32 %). Sonnet was not asked on those 102, so its accuracy on all 162 is not known.

**Descriptive, not registered:** Jev's precision rises with the cut.
- 0.5: 40 of 82;
- 0.7: 21 of 41;
- 0.8: 17 of 27;
- 0.9: 9 of 12.

## By band (descriptive)

| Length | Tasks | Covered | Jev right / Sonnet right on them | Hybrid minus Sonnet |
|---|---|---|---|---|
| Short | 38 | 18 (47 %) | 11 / 9 | +5.3 points |
| Medium | 88 | 35 (40 %) | 16 / 17 | −1.1 |
| Long | 36 | 7 (19 %) | 4 / 3 | +2.8 |

| Difficulty | Tasks | Covered | Jev right / Sonnet right on them | Hybrid minus Sonnet |
|---|---|---|---|---|
| Easy | 50 | 19 (38 %) | 13 / 12 | +2.0 points |
| Hard | 112 | 41 (37 %) | 18 / 17 | +0.9 |

- Jev covers long documents least: 7 of 36. Of the 28 middle-cut documents, 7 were covered.
- The bands are small; none is a finding on its own.

## Cost and time

| | USD | |
|---|---|---|
| Jev, all 162 tasks (shorter retries included) | 0.874 | measured; plan expected 0.92 |
| Jev smoke (one dev task, outside the 162) | 0.001 | measured |
| Sonnet 5.5, the 60 covered tasks | 5.757 | measured: 0.096 a session (median 0.058, max 0.39) |
| Sonnet 5.5, the 102 uncovered tasks | 12.55 | **estimate**, at 0.123 a task (Sonnet's mean on 2026-10-06) |
| Sonnet alone on all 162 | 18.30 | **estimate** (measured plus estimated) |
| Hybrid on all 162 | 13.42 | **estimate** (Jev plus Sonnet on the uncovered tasks) |
| Saving of Sonnet's cost | 4.88, **26.7 %** | **estimate** |

- **Jev:** 0.875 USD in all, under the lot's 1.20 cap. Three tasks needed a shorter retry.
  20.8 M input tokens.
- **Sonnet:** 60 sessions under the 18 USD ceiling. None hit its 3.00 cap, none errored, all
  gave a letter. 4.7 turns on average.
- **Wall time:**
  - Phase J: 1 minute 25 seconds (4 calls in flight).
  - Phase S: 20 minutes 33 seconds, one session at a time; median 15 s, mean 20.5 s,
    longest 84 s.

## What this licenses, and what it does not

**It licenses** a router for **long-document multiple-choice questions**, in the conditions
measured:
- Jev 1.14 reads up to 900,000 characters with the long-context header.
- It answers alone when its top choice is ≥ 0.6.
- Sonnet 5.5 answers the rest.

On LongBench v2 that saved about a quarter of Sonnet's cost (estimated) at no measurable loss
of accuracy.

**It does not license:**
- Jev as a general Sonnet substitute.
- Open-ended answers: these were four-option questions, graded by the letter.
- Other document kinds: Single- and Multi-Document QA only.
- Other models: Sonnet 5.5 only. No Opus 5.5 arm was run.
- A saving measured end to end: the uncovered part of Sonnet's cost is estimated.

**Limits of the evidence:**
- **One draw:** coverage moved from 54 % in L6 to 37 % here, and Jev's precision on the
  covered tasks from 63 % to 52 %.
- **Hard tasks for both models:** Sonnet was right on only 48 % of the covered ones.
- **The tie is not a measured "better":** the CI includes small losses, and a −2-point rule
  would not decide.

## Recommendation

**What would ship.** An opt-in point that answers a multiple-choice question over a long
document with Jev and says when to escalate, in the shape of `navigate`'s `escalate_below`:
- returns Jev's letter and its probability when the top choice is ≥ 0.6;
- otherwise a flag telling the caller to ask its own model.

Its shape:
- In `src/sanchopanza/points/`, with the long-context header and a 900,000-character middle
  cut.
- Off by default and not in `install`. Nothing in `policy.py` or `DEFAULT_MODEL` changes: the
  cut is this lot's, on 1.14.

**What to measure next:**
1. Sonnet on the 102 uncovered tasks (about 12.5 USD), to turn the saving from an estimate
   into a measurement.
2. The same router with Opus 5.5 as the expensive model.
3. A long-document set graded on free-text answers, where the letter-only grading here does
   not apply.

## Files

- `prereg.md`, `prereg.manifest.json`, `prereg.sha256`: the sealed registration.
- `ids.txt`, `ids.sha256`: the 162 ids.
- `jev-answers-j14-L.jsonl`: Jev's answers with hashed keys, no text; a relaunch replays them
  free.
- `jev-scored.jsonl`: one row per task, with id, gold and chosen letters, probabilities, cost
  and bands.
- `smoke-*`: the one dev task.
- `covered-ids.txt`: the 60 covered tasks in the seeded order phase S ran them.
- `sonnet-rows.jsonl`: per session, the letter, grade, cost, time and how it ended. No text.
- `sonnet-stop.json`: how phase S ended (`done`).
- `summary.json`: the analysis.

Reproduce for free (needs the LongBench v2 cache):

```bash
PYTHONPATH=src python benchmarks/jev114/lb162.py --run      # replays phase J
PYTHONPATH=src python benchmarks/jev114/lb162.py            # summary.json from the rows
```
