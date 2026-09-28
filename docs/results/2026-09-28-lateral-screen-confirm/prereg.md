# Pre-registration: the lexical screen, confirmed on questions nothing was chosen on

Written 2026-09-28, before any live call of this run. Hash in `prereg.sha256` (sha256 of this
file with line endings normalised to LF). `benchmarks/lateral/screen/confirm.py` refuses `--live`
unless the hash matches. **Not run yet.**

## Why

`docs/results/2026-09-28-lateral-screen/` found that BM25's top 30 of 100 pages followed by one
`Squire.triage_pages` call matched the five-call tournament (96.0 % against 96.5 % of 200
questions keeping both supporting pages, 3.4 % against 3.1 % of the text) at 28 % of its Jev
cost. Those 200 questions were the held-out half of the hierarchy run, and the tournament was
replayed from that run's recordings: the screen was measured once, on a set whose tournament
answers were already known. It holds its registered text bound exactly at the edge. Before it
ships as the screen for search results, it is measured again on questions no earlier run drew.

## Data

HotpotQA distractor, validation (CC BY-SA 4.0), the same local export. 200 questions drawn by
`hierarchy.build(seed=2030, n=200, exclude=...)`, excluding every id any earlier HotpotQA run of
this repository used: both triage-set samples, the chunk confirmation, and the 300 of the
hierarchy run (the script asserts the sets are disjoint). Each question keeps its own 10
paragraphs plus 90 paragraphs of other unused questions, shuffled, exactly as the hierarchy run
built its pools. Distractor paragraphs may repeat ones used as distractors before; no question,
and no gold page, does.

## Arms, both live, on the same 200

- **SCREEN**: BM25 top 30 (`chunks.PAGE_MAX`), one `triage_pages` call, kept at p >= 0.40
  (`Thresholds.pages_in_context`), unanswered kept.
- **TOUR**: the tournament with the shipped cuts: groups of at most 30 at 0.18
  (`Thresholds.pages_first_round`), survivors together at 0.40.
- **CEILING**: BM25 top 30 alone, descriptive.

Nothing is derived; every number above ships in `Thresholds` today.

## Harness check, already run (free)

`confirm.py --replay-published` runs this file's code on the published 200 from the recordings:
SCREEN 96.0 % at 3.43 % of the text, TOUR 96.5 % at 3.10 %, difference -0.5 points (95 % CI -3.0
to +2.0), S1 and S2 true, as published. The harness is the one that produced the result.

## Metrics and criteria (unchanged from the first run)

Both supporting pages kept (Wilson 95 %), text kept (mean share of characters), pages kept,
calls per question; SCREEN against TOUR paired: bootstrap difference and McNemar.

- **S1**: SCREEN both-kept >= TOUR both-kept minus 1 point, **and** SCREEN text kept <= TOUR
  text kept plus 1 point.
- **S2**: the paired bootstrap 95 % lower bound of SCREEN minus TOUR is at least -3 points.

Both: **confirmed**, and the screen can be proposed for heterogeneous pools (search results,
many documents), with the tournament kept for one long document. Otherwise **not confirmed**,
reported as it falls, and the first result is described as not replicated.

## Prediction

SCREEN 94-98 %, TOUR 95-98 %; S1 and S2 both hold with about 60 % confidence. The risk is the
same as before, text kept: the first run held S1's text bound at the edge.

## Cost and caps

About 1,200 Jev calls: 200 for SCREEN, about 1,000 for TOUR (five per question in the first
run; the fake-decider dry run counts 1,601, an upper bound because a hashed probability keeps
more pages past the first round than Jev did). At the recorded averages (0.49 thousandths USD a
SCREEN call, 1.76 thousandths a question for TOUR): **about 0.45 USD**. Hard cap in code: 0.50
USD of Jev per invocation; an interrupted run resumes from `fixtures/screen-confirm.jsonl` and
pays only for what is missing. This is outside the 1.00 USD total that `ledger.py` keeps for the
lateral runs of 2026-09-28 (0.64 already spent), because it would not fit; the owner approves
this bar before `--live`.
