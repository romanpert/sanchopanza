# Jev 1.14 against 1.13 with the long window (lot L6: LongBench v2, QASPER, LongMemEval)

**The result.** The long window changes one verdict. The model's one significant difference is
1.6 points less QASPER text kept.

- **A7, memory gate.** Reading every LongMemEval session whole lifts the gate's recall from
  0.72 to **0.91** on 36 questions, for both 1.13 and 1.14. Under the sealed rule this is
  "mejora" (+18.5 points, Holm p 0.03). It ends 3.1 points under BM25 top 3 (0.94 on these
  questions), with 19-21 % fewer characters injected and better precision (0.66-0.69 against
  0.56). It misses "alcanza" by 0.08 of a point.
- **B3, LongBench v2.** Jev alone with the whole document (up to 900,000 characters) does not
  replace Sonnet at the registered cut. Jev answers 21-22 of 50 right; Sonnet got 31. At 0.9
  Jev is sure on 7 of 50 tasks (14 %, the bar was 20 %) and gets 6 right (86 %, the bar was
  90 %). Sonnet got the same 6 right. Verdict: **"no sustituye"** in all four cells.
- **A6, QASPER.** One call with every paragraph whole keeps **more** text than the tournament
  (51-53 % of the paper against 49 %). It keeps the evidence slightly more often (97.0 %
  against 94.7 %). P28 (<= 25 % of the text) **fails** in every cell.
- **Model effect.** No difference between 1.14 and 1.13 is significant anywhere, except that
  1.14 keeps 1.6 points less of a QASPER paper. Every gain here is the window's, and the window
  works the same on 1.13.

Pre-registered in `prereg.md`:
- sealed in dd46e67;
- `prereg.sha256` 373313eb…, over the document, the code and the hashes of the external
  inputs;
- reviewed by `revisor-prereg` before the seal. Its blocking point, a failure counter shared
  by concurrent items, was fixed before any data.

Both models were asked live on 2026-10-15, interleaved item by item on the same inputs, through
the shared ledger.

- **Jev:** 1.4822 USD in the batch, under the 1.50 cap:

  | Part | USD |
  |---|---|
  | Smoke (dev items) | 0.0207 |
  | B3 | 0.5810 |
  | A6 | 0.4380 |
  | A7 | 0.4425 |

- **Ledger after this lot:** 2.6025 of 4.50.
- **Claude:** 0. Sonnet's answers are the ones recorded on 2026-10-06.

## B3: LongBench v2, Jev alone against Sonnet's recorded answers

The 50 confirmation tasks of `2026-10-06-h2h-longdoc`, with contexts of 104k to 2M characters.
Each task is one Choice A-D over the document.

- **S** shows 100,000 characters: the first and last halves, under 32k tokens.
- **L** shows up to 900,000 characters with the long-context header; 44 of the 50 documents fit
  whole.
- **Sonnet 5.5** (clean Claude Code 2.1.287, arm N) got **31/50 right** at 6.13 USD, 0.123 a task.

| Cell | Right / 50 | AUC (confidence, right vs wrong) | Tokens a task | Jev USD |
|---|---|---|---|---|
| 1.13, S | 18 | 0.720 | 27k | 0.057 |
| 1.14, S | 20 | 0.718 | 27k | 0.057 |
| 1.13, L | 22 | 0.710 | 109k | 0.229 |
| 1.14, L | 21 | 0.763 | 109k | 0.239 |

**Failures.** One task (`6703f57b…`) failed in every cell at all three lengths: dense text,
over the token limit even at 64,000 characters. Four other tasks needed a shorter retry, which
was asked of both models. The runner does not record whether a failed attempt was an HTTP 400
or a timeout, and the ledger settles both at 0.

**Position bias.** Jev chose D 17-23 times and A 5-11 times, against a gold of 21 D and 3 A.
That is no first-option bias.

### Substitution: Jev answers where it is sure, Sonnet elsewhere

The registered cut is tau = 0.9, and the primary cell is 1.14 L. "Sustituye" needed all
three of:
- coverage >= 20 %;
- precision >= 90 %;
- hybrid minus Sonnet with a CI lower bound > -2 points.

| Cell, tau 0.9 | Covered | Jev right on them | Sonnet right on them | Hybrid | Net saving of Sonnet's cost | Verdict |
|---|---|---|---|---|---|---|
| **1.14, L** | 7 (14 %) | 6 (86 %; Wilson 49-97 %) | 6 | 31/50 | 1.5 % | **no sustituye** |
| 1.13, L | 8 (16 %) | 7 (88 %) | 7 | 31/50 | 2.8 % | no sustituye |
| 1.14, S | 7 (14 %) | 6 (86 %) | 6 | 31/50 | 4.6 % | no sustituye |
| 1.13, S | 8 (16 %) | 6 (75 %) | 7 | 30/50 | 6.9 % | no sustituye |

Where Jev is sure, Sonnet is right too. So substituting there costs nothing in accuracy, but
it saves almost nothing either: those are short, cheap Sonnet sessions.

**The sweep is descriptive, not a verdict.** The cuts below were registered as descriptive.
Any cut chosen from this table would be post hoc.

| 1.14 L, cut | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | 0.95 |
|---|---|---|---|---|---|---|
| Coverage | 64 % | 54 % | 44 % | 24 % | 14 % | 10 % |
| Precision | 59 % | 63 % | 64 % | 58 % | 86 % | 80 % |
| Hybrid / 50 | 30 | **31** | 30 | 30 | 31 | 31 |
| Hybrid − Sonnet [95 % CI] | −2 [−14, +10] | 0 [−12, +12] | −2 [−10, +6] | −2 [−6, 0] | 0 | 0 |
| Net saving | 61 % | **57 %** | 22 % | 8 % | 1.5 % | −0.4 % |

At 0.6 the hybrid matched Sonnet's 31/50 at 43 % of its cost. On those 27 tasks Jev and
Sonnet were each right on 17. The CI of ±12 points does not show "no peor", and the cut was
not registered. This is a hypothesis for a confirmation on fresh LongBench tasks, not a
result. It was taken up: [b3conf](../2026-10-15-jev114-b3conf/README.md) found that 50 fresh
tasks with Jev alone decide about 4 % of the time, [lb162](../2026-10-15-lb162/README.md) ran
162 fresh tasks with the cut fixed at 0.6 (no worse than Sonnet at −10 points, "sustituye"),
and [lb162x](../2026-10-16-lb162x/README.md) measured the saving and the hybrid against Opus 5.5.

### Model and window (family B3, Holm over six)

| Comparison | n | New | Old | Difference [95 % CI] | Holm p | Verdict |
|---|---|---|---|---|---|---|
| accuracy 1.14 − 1.13, S | 49 | 40.8 % | 36.7 % | +4.1 [0.0, +10.2] (2 won, 0 lost) | 1.0 | no peor |
| accuracy 1.14 − 1.13, L | 49 | 42.9 % | 44.9 % | −2.0 [−12.2, +6.1] | 1.0 | no concluyente o peor |
| accuracy L − S, 1.13 | 49 | 44.9 % | 36.7 % | +8.2 [−4.1, +20.4] (7 won, 3 lost) | 1.0 | no concluyente o peor |
| accuracy L − S, 1.14 | 49 | 42.9 % | 40.8 % | +2.0 [−6.1, +10.2] | 1.0 | no concluyente o peor |
| AUC 1.14 − 1.13, S | 49 | 0.718 | 0.720 | −0.001 [−0.124, +0.112] | 1.0 | no concluyente o peor |
| AUC 1.14 − 1.13, L | 49 | 0.763 | 0.710 | +0.053 [−0.083, +0.188] | 1.0 | no concluyente o peor |

With 50 tasks, nothing here is resolved (prereg, Power). The window adds 2 to 8 points of
accuracy, not significantly.

## A6: QASPER, every paragraph whole in one call

The 300 papers of `2026-09-27-longdocs`, scored at the production cut (0.40), with 0 failed
papers.

- **S** is the published tournament, the recorded 1.13 run replayed. Re-asking it was outside
  the cap, so the window comparison spans two days and two draws of 1.13.
- The "25 % budget" column ranks paragraphs by probability and keeps them up to 25 % of the
  paper. It is the reading of P28 without a threshold.

| Cell | All evidence kept | Text kept | Paragraphs kept | P28 | All evidence in a 25 % budget | Mean AUC per paper |
|---|---|---|---|---|---|---|
| tournament, 1.13 recorded (S) | 94.7 % | 48.9 % | 21.2 | fails | 81.0 % | 0.934 |
| **one call, 1.13 (L)** | **97.0 %** | 53.1 % | 23.4 | fails | 83.7 % | 0.940 |
| **one call, 1.14 (L)** | 95.3 % | 51.5 % | 22.8 | fails | 82.3 % | 0.941 |

Family A6, Holm over six. Text saved = old share minus new share; positive means less text.

| Comparison | Difference [95 % CI] | Holm p | Verdict |
|---|---|---|---|
| model: all evidence, 1.14 − 1.13 | −1.7 [−3.7, +0.3] (2 won, 7 lost) | 0.40 | no concluyente o peor |
| model: all evidence in a 25 % budget | −1.3 [−4.0, +1.3] | 0.45 | no concluyente o peor |
| model: text saved by 1.14 | **+1.6 [+0.7, +2.4]** | **0.005** | **mejora** |
| window (cross-day): all evidence, one call − tournament | +2.3 [+0.7, +4.3] (8 won, 1 lost) | 0.16 | no peor |
| window (cross-day): all evidence in a 25 % budget | +2.7 [−0.3, +5.7] | 0.40 | no peor |
| window (cross-day): text saved by one call | −4.2 [−5.2, −3.1] | <0.001 | no concluyente o peor (it keeps more) |

**Reading.**
- Seeing the whole paper at once ranks a little better: mean AUC 0.940 against 0.934, and 83-84 %
  against 81 % within the 25 % budget.
- At the 0.40 cut, one call keeps more paragraphs, not fewer. The compression failure of
  2026-09-27 was the cut and the question, not the window.
- No cell reaches 85 % within 25 % of the text.
- The lateral-wholedocs rule GW, measured on sentences (87.2 % at 21.0 %), stays the
  long-document recipe.
- One call costs about 0.0007 USD a paper, against the tournament's 5 calls.

## A7: the memory gate with every session whole

The LongMemEval S test questions in the seeded order. The soft stop before rank 36 left
**36 questions**, all complete in all four cells, with 0 failures.

- **S** is the shipped gate: 900 characters a session, a tournament.
- **L** is every session whole in one call, about 120k tokens and 0.005 USD a model.
- The excerpt ceiling on these questions is 42 of 60 evidence turns (70 %).

| Cell | Gate recall | Any-hit | All-hit | Characters injected | Precision |
|---|---|---|---|---|---|
| BM25 top 3 | 0.938 | 0.972 | 0.917 | 40,207 | 0.565 |
| gate 1.13, recorded 2026-09-28 (S) | 0.738 | 0.722 | 0.583 | 20,060 | 0.923 |
| gate 1.13, S | 0.723 | 0.722 | 0.556 | 19,507 | 0.922 |
| gate 1.14, S | 0.723 | 0.722 | 0.556 | 20,135 | 0.887 |
| **gate 1.13, L** | **0.908** | 0.917 | 0.861 | 31,644 | 0.694 |
| **gate 1.14, L** | **0.908** | 0.917 | 0.889 | 32,612 | 0.663 |

Family A7, Holm over four:

| Comparison | Difference [95 % CI] | Holm p | Verdict |
|---|---|---|---|
| recall 1.14 − 1.13, S | 0.0 [−4.3, +4.6] | 1.0 | no concluyente o peor |
| recall 1.14 − 1.13, L | 0.0 [−4.3, +4.6] | 1.0 | no concluyente o peor |
| **recall L − S, 1.13** | **+18.5 [+5.7, +32.8]** | **0.028** | **mejora** |
| **recall L − S, 1.14** | **+18.5 [+4.4, +32.9]** | **0.034** | **mejora** |

Against BM25 top 3 (the original criterion 1, and "alcanza" at −3 points):

| Cell | Difference | Bate | Alcanza |
|---|---|---|---|
| S, either model | −21.5 (1.13 [−37.5, −8.1], 1.14 [−37.7, −6.9]) | no | no |
| L, either model | **−3.08** (1.13 [−14.8, +8.1], 1.14 [−15.9, +8.6]) | no | no, by 0.08 of a point |

**Reading.**
- The registered reading of 2026-09-28 holds: the excerpt capped the gate. With the whole
  session, recall (0.91) passes the excerpt ceiling (0.70). The gains are where the evidence is
  one line in a long session (single-session user and assistant 0.5-0.6 → 1.0, knowledge update
  0.6 → 0.9-1.0) and in multi-session (0.75 → 1.0).
- Temporal reasoning does not move (0.85-0.88).
- The two preference questions stay at 0 in every gate cell (BM25 finds both).
- BM25 is unusually strong on these 36 questions: 0.94, against 0.85 on all 120.
- n = 36 resolves only large effects. The window's +18.5 is one; the −3 against BM25 is not
  resolved either way.

## Recommendation

- **Does Jev with the long window replace a Claude call with enough quality? Not on this
  evidence.**
  - On LongBench v2, at the registered cut, Jev is sure on 14 % of the tasks. Those are tasks
    Sonnet also gets right, cheaply. The substitution saves 1.5 % of Sonnet's cost.
  - Alone, Jev answers 42-44 % against Sonnet's 62 %.
  - The only promising number is post hoc: at 0.6 the hybrid tied Sonnet at 43 % of its cost.
    It deserves one confirmatory run on 50 fresh LongBench v2 tasks, with the cut fixed at 0.6
    beforehand, about 0.3 USD of Jev and 0 of Claude. It is not a product claim today. What
    followed: b3conf, lb162 and lb162x, as under B3 above.
- **Where the long window does pay is inside a component: the memory gate.** Whole sessions
  in one call lift recall by 18.5 points, to within 3 of BM25, with less text injected and
  higher precision. It costs about 0.005 USD a prompt against 0.001.
  - Candidate change: a memory-gate mode with the long-context header and `Limits(page_chars`
    large, `pages_per_call` large`)`. Confirm it on the remaining 84 test questions first
    (about 1 USD for one model). Done in [memgate-long](../2026-10-15-memgate-long/README.md):
    +17.8 points [+10.7, +25.7] on jev-1.13.0. The long window is the library gate's default
    since 2026-10-16; the installed hook stays short
    ([memgate-hook](../2026-10-16-memgate-hook/README.md)).
  - This mode works on 1.13. It is not a reason to switch models.
- **QASPER triage:** do not replace the tournament with one call. It keeps more text, and P28
  still fails.
- **Model.** 1.14 is no better than 1.13 on long context here. Its one significant
  difference is 1.6 points less text on QASPER, with recall −1.7 (not resolved).
  - Nothing in this lot argues for moving `DEFAULT_MODEL`.
  - No threshold needs recalibrating for 1.14 on these points. The cuts were not exercised
    against a 1.14 shift: S recall is identical for both models.

## Files

- **Runner:** `benchmarks/jev114/l6.py`. Analysis: `l6_analysis.py`. Tests:
  `tests/test_jev114_l6.py`.
- **Scored rows:** `b3-scored.jsonl`, `a6-scored.jsonl`, `a7-scored.jsonl`. They hold ids,
  letters, masks and probabilities, no text.
- **Answers per cell:** `*-answers-<cell>.jsonl`, hashed keys with no text. A relaunch replays
  them for free.
- **Summary:** `summary.json`.
- **Smoke on dev items:** `smoke-*.jsonl` and `*-dev-answers-*`.

Reproduce for free from the recordings:

```bash
PYTHONPATH=src python benchmarks/jev114/l6.py --run --sets b3,a6,a7
```

This needs the external inputs named in `prereg.manifest.json`, under the home cache. Checked
after the run: the replay rewrites the three scored files byte for byte and the same summary.
