# Pre-registration: a lexical screen and one in-context call in place of a five-call tournament

Written 2026-09-28 before any live call of this run. Hash in `prereg.sha256` (sha256 of this
file with line endings normalised to LF). `benchmarks/lateral/screen/run.py` refuses `--live`
unless the hash matches.

## Claim

`triage_many` on 100 pages runs a tournament: four groups of 25 at 0.18, then the survivors
together at 0.40, five Jev calls, most of their cost in the four round-one calls
(`docs/results/2026-09-27-hierarchy/`: 96.5 % of 200 held-out questions keep both supporting
pages, 3.1 % of the text). Round one only has to be lenient, and a lenient first round is what
lexical retrieval does cheaply when the crowd is off-topic. **SCREEN**: BM25 keeps the 30 pages
it ranks highest (30 = `chunks.PAGE_MAX`, what one call holds), and one `Squire.triage_pages`
call judges those 30 together at the shipped 0.40. One call instead of five, each signal doing
what the other does badly: BM25 is blind to bridge pages but cheap over a crowd; the in-context
call separates the question's own ten pages but cannot hold a hundred.

The claim is **only** for crowds that are lexically far from the question. It is not expected to
hold on a single long document, and the boundary is stated before the run (below).

## Data

The 300 questions of `docs/results/2026-09-27-hierarchy/` (HotpotQA distractor, validation,
CC BY-SA 4.0), built by that run's `build` (its own 10 pages plus 90 paragraphs of other
questions, shuffled, seed 2029). **Only the 200 held-out questions** are screened and scored; the
first 100 fixed the tournament's round-one cut. SCREEN has nothing to derive: 30 and 0.40 are
fixed above. The tournament replays from `fixtures/hierarchy.jsonl`.

Already known before registration, and therefore not a prediction: BM25's top 30 contains both
supporting pages in 99.0 % of the 300 questions (computed without any call). What is unknown is
how one call judges 30 pages of which about 20 are off-topic but lexically close.

## Arms (held-out 200)

- **SCREEN**: BM25 top 30, then one `triage_pages` call, kept at p >= 0.40 (unanswered kept).
- **TOUR**: the tournament as published (replayed).
- **FLAT**: the published groups-alone arm (replayed), descriptive.
- **CEILING**: BM25 top 30 alone, descriptive.

## Metrics

Both supporting pages kept (Wilson 95 %), text kept (share of characters, mean over questions),
pages kept, calls per question. SCREEN against TOUR paired: bootstrap difference and McNemar.

## Criteria

- **S1**: SCREEN both-kept >= TOUR both-kept minus 1 point, **and** SCREEN text kept <= TOUR
  text kept plus 1 point.
- **S2**: the paired bootstrap 95 % lower bound of SCREEN minus TOUR is at least -3 points.

Both = **confirmed** (one call does the tournament's work on off-topic crowds); otherwise **not
confirmed**, reported as it falls.

## The boundary, stated in advance (descriptive, free)

On the 217 QASPER papers of 2026-09-27 with more than 30 paragraphs, BM25's top 30 contains all
evidence paragraphs in 82.0 % of questions (computed before registration), so SCREEN cannot
exceed 82 % there, where the tournament's recorded keep reaches about 95 %. The run reports both
on the same questions. **If S1 and S2 hold, the proposed use is a screen for heterogeneous pools
(search results, many documents) and the tournament for one long document**, not a replacement.

## Prediction

SCREEN 95-98 % at 3-4 % of the text; S1 and S2 hold with about 70 % confidence (the risk is text:
twenty lexically close strangers in one call may keep a page or two more than the tournament).

## Cost and caps

200 calls of 30 pages, about 490 millionths each (25-page calls averaged 408 in
`fixtures/hierarchy.jsonl`): about 0.10 USD. Hard cap in code: 0.12 USD on the squire, and
`benchmarks/lateral/ledger.py` refuses the run if the Jev spend of every lateral run plus 0.12
USD would pass 1.00 USD. 12 calls a second, at most 4 attempts per call.
