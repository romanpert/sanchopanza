# Pre-registration, confirmatory: pages judged in context, on 300 fresh questions

Written 2026-09-27 after the first chunk run (`prereg.md`: P15 missed by 0.3 points, P16
failed, P17 held) and before any call of this one. Hash in `prereg-confirm.sha256`.

## Why

Read descriptively on the first run's held-out set, arm C (every page asked in one call with
the others in view) kept every supporting page in 99.0 % of questions at 39.6 % of the text,
where one call per page (arm A) keeps 93.3 % at 52.4 %. The registered rule had picked an
aggressive cut (0.77) that did not hold out. Those curves were read on held-out data; this run
tests the reading on questions nothing was chosen on.

## Fixed here

- **Data**: 300 new HotpotQA distractor validation questions with 10 paragraphs, drawn with
  `random.Random(2028).sample` from those with 10 paragraphs minus the 600 already used.
- **Cuts, derived on all 600 earlier questions, never tuned again**:
  - A: page contribution, cut 0.28 (unchanged since the confirmed triage run).
  - C: the smallest kept share reaching **page joint recall >= 0.97** on the 600.
  - B: the smallest kept share reaching **sentence joint recall >= 0.90** on the 600.
  - CB, secondary: a sentence is kept when C keeps its page and B's p >= the cut derived the
    same way (sentence joint >= 0.90) on the 600.
- Sentences past the 40-sentence cap of a page are kept unjudged, as in the first run.

## Criteria, on the 300 new questions

- **P18**: C reaches page joint recall >= 0.95 with kept share <= 0.45.
- **P19**: C's page joint recall >= A's on the same questions, at a kept share lower than A's,
  with one call per question against A's ten.
- **P20** (secondary): B reaches sentence joint recall >= 0.88 at kept share <= 0.36.

Verdict: P18 and P19 = **confirmed**; otherwise **not confirmed**.

## Cost

A 3,000 calls, B 3,000, C 300: about 0.3 USD of Jev.
