# The lexical screen did not confirm on fresh questions: retired

Pre-registered in `prereg.md` (hash in `prereg.sha256`, registered before the live run). 200
HotpotQA distractor questions (validation, CC BY-SA 4.0) that no earlier run of this repository
drew, each with 100 pages: its own ten and 90 paragraphs of other unused questions, shuffled.
Both arms ran live on the same 200 with the cuts that ship; nothing was derived.

- **SCREEN**: BM25's top 30, one `Squire.triage_pages` call, kept at 0.40.
- **TOUR**: the tournament (`triage_many`), groups at 0.18, survivors together at 0.40.
- **CEILING**: BM25's top 30 alone, descriptive.

## Result: not confirmed

| arm, 200 fresh questions | both supporting pages kept (95 % CI) | text kept | pages kept | Jev calls per question |
|---|---|---|---|---|
| SCREEN | 96.5 % (92.9-98.3) | 3.8 % | 4.5 | 1 |
| **TOUR** | **97.5 %** (94.3-98.9) | **3.3 %** | 3.9 | 5.0 |
| CEILING (BM25 top 30) | 97.0 % (93.6-98.6) | 31.9 % | 30 | 0 |

- **S1 holds**: 96.5 % against 97.5 % (bar: at most 1 point below; it is exactly 1), with 3.8 %
  of the text against 3.3 % (bar: at most 1 point above).
- **S2 fails**: SCREEN minus TOUR is -1.0 point, paired bootstrap 95 % CI **[-4.0, +2.0]**; the
  bar was a lower bound of at least -3 points. The arms disagree on 10 questions (4 kept only by
  the screen, 6 only by the tournament; McNemar p = 0.75).

As registered: **not confirmed**, and the first result (`../2026-09-28-lateral-screen/`, S2 held
at exactly -3.0) is described as **not replicated**. The prediction (SCREEN 94-98 %, TOUR 95-98 %)
held for both arms; the joint criterion, given about 60 %, did not.

## Where the screen loses

The lexical stage, not the call. BM25's top 30 held both supporting pages in 97.0 % of these
questions, against 99.0 % on the first set: **6 of the screen's 7 misses** are questions where
BM25 had already dropped a supporting page before any call, and the tournament kept every one
of those 6. No in-context call can recover a page the screen did not pass it. On a crowd that
is off topic by construction, BM25 still costs 3 points on one set in two; with harder
distractors, or on one long document (82 % on QASPER, `../2026-09-28-lateral-screen/`), it
costs more. The saving it buys is four Jev calls a question, about 1.3 thousandths of a dollar.

## What changed

The screen is retired as a candidate: removed from the README's open items, the paper (5.16)
and the CHANGELOG, each replaced by one line pointing here. It was never in `src/`, so no code
path is removed. `benchmarks/lateral/screen/` and both result folders stay as the record.

## Cost and reproducing

1,201 Jev calls, **0.451 USD** (SCREEN 200 calls, 0.099 USD; TOUR 1,001 calls, 0.352 USD), mean
latency 277 ms a call, recorded in `fixtures/screen-confirm.jsonl`. Inside the registered 0.50
USD cap.

```bash
python benchmarks/lateral/screen/confirm.py --replay-live --hotpot HOTPOT.jsonl   # free
```

reproduces `analysis.json` exactly from the recording; `tests/test_screen_confirm.py` pins it
(needs `SANCHOPANZA_HOTPOT`).

## Limits

- 200 questions: a 1-point difference is inside the noise either way. The claim that fails is
  non-inferiority at a 3-point margin, not a proof that the screen is worse.
- Jev is not deterministic; a live rerun is a new sample. The numbers above are the recorded run.
