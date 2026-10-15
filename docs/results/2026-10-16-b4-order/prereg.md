# B4: order the approved paragraphs that do not fit by a four-level Score (pre-registration, DRAFT)

Status: **draft, not sealed.** Sealing = `python benchmarks/passage_fit/run.py seal` after an
independent review against the code; the paid step refuses to run unless `prereg.sha256`
matches this file. Instrument commit: to be written here at sealing.

## Question

When the passages `Squire.select_passages` keeps from one long document are longer than the
caller can deliver, does ordering the delivered paragraphs by a four-level Score (one Score per
paragraph, all in view, `passages.fit_questions`) and cutting in that order keep more answer
sentences than the free orders? Roadmap B4: an agent with its own harness orders its approved
paragraphs this way; a second Truth pass did not discriminate there.

## The option under test (opt-in, default unchanged)

`select_passages(..., fit_chars=B)` (`src/sanchopanza/squire.py`, `points/passages.py`): when
the kept sentences add up to more than `B` characters, the delivered paragraphs are ordered by
(Score desc, best sentence probability desc, tournament probability desc, page order) and taken
in that order while they fit; one that does not fit is skipped and the next is tried; the rest
become `None`; output stays in page order. `fit_score=False` is the same order without the
Score (no call). `fit_chars=None` (default) changes nothing: every published mask replays
unchanged (`tests/test_select_passages_bench.py`, `tests/test_passages.py`).

## Data (all recorded; nothing re-asked except the Score)

- QASPER test split (CC BY 4.0), local export.
- Derivation set: the 261 questions of `docs/results/2026-09-27-longdocs/` (tournament and
  sentence calls in `fixtures/longdocs.jsonl`, `fixtures/longdocs-sentences.jsonl`).
- Confirmation set: the 219 questions of `docs/results/2026-09-28-lateral-wholedocs/`
  (`fixtures/lateral-wholedocs.jsonl`).
- The shipped document rule (GW: gate 0.75, cut 0.28, window 2) gives each question's mask.
- **Budget B = 3,400 characters**: the median delivered size over the 261 derivation
  questions, rounded down to 100 (`orders.budget_from`). It reads no gold label.
- **Population: the questions whose delivered text exceeds B**: 131 derivation + 102
  confirmation = **233**, pooled (primary). Questions that fit are identical in every arm.

## Arms (`benchmarks/passage_fit/orders.py`)

| arm | order of the delivered paragraphs | calls |
|---|---|---|
| PAGE | page order: what a caller cutting today's output in reading order gets | 0 |
| BM25 | BM25 of the delivered text against the question | 0 |
| PROB | tournament probability | 0 |
| FREE | `fit_score=False`: best sentence probability, then tournament | 0 |
| **L4** | `fit_score=True`: the four-level Score first, then FREE's order | 355 |
| GOLD | paragraphs holding answer sentences first (ceiling, descriptive only) | 0 |

The L4 calls are `passages.fit_questions` over the delivered text of each paragraph (900
characters each, 12 per call), point `passage_fit`, `jev-1.13.0`, asked once and recorded in
`fixtures/b4-order/recording.jsonl`; a paragraph whose score is missing or failed goes after
every scored one (scored 0 included), in FREE's order among the unscored.

## Metric

Primary: mean over questions of the share of the question's answer sentences delivered under
B (gold = the QASPER evidence spans located as in the 2026-09-27 runs). Secondary: every answer
sentence delivered (all-gold), McNemar exact. Paired bootstrap, 2,000 replicas, seed 7
(`eval.stats.bootstrap_difference`).

## Verdict rule (applied by `run.py report`, as written)

Let lo(X-Y) be the lower bound of the 95 % paired bootstrap interval of the recall difference
on the 233 pooled questions.

1. **L4 confirmed** (the Score pays over the free orders) iff lo(L4-PAGE) > 0,
   lo(L4-BM25) > 0, lo(L4-FREE) > 0 and lo(L4-PROB) > 0.
2. **L4 no better than the free orders** iff lo(L4-PAGE) > 0 and lo(L4-BM25) > 0, and the
   smaller of lo(L4-FREE), lo(L4-PROB) is above -0.02 without 1 holding: the Score is not
   worth its calls; `fit_score=False` is the candidate.
3. Otherwise **L4 not confirmed**.

By set (derivation, confirmation) and all-gold are reported, not voted.

## Already known before this run (free, from the recordings; `free.json`)

| 233 pooled overflowing | recall | all-gold |
|---|---|---|
| PAGE | 65.1 % | 59.7 % |
| BM25 | 64.8 % | 57.9 % |
| PROB | 79.3 % | 72.5 % |
| FREE | 78.7 % | 71.7 % |
| GOLD (ceiling) | 92.8 % | 88.8 % |

FREE - PAGE +13.6 points (95 % CI +7.1 to +20.2); PROB - PAGE +14.2 (+7.9 to +20.8); BM25 -
PAGE -0.3 (-7.0 to +6.3); FREE - PROB -0.5 (-5.0 to +3.8). On each set alone FREE and PROB
beat PAGE too (confirmation +18.0 and +16.1; derivation +10.2 and +12.7). The headroom left
for L4 over the free orders is about 14 points (GOLD).

## Power

The paired sd of a recall difference between two orders is about 0.34 (from FREE - PROB on
the 233). At n = 233, alpha 0.05 two-sided, 80 % power: a difference of about 6 points is
detectable; the headroom is 14.

## Cost and caps

355 calls. At the median real request (71 micro-USD): **0.025 USD**; pessimistic estimate
(`CappedDecider`, 3 characters per token): **0.074 USD**. Hard cap **0.10 USD** in the ledger
(`$SANCHOPANZA_B4_RUN/ledger.jsonl`, default `~/.cache/sanchopanza/b4-order`); the runner
refuses a plan whose higher estimate does not fit, asks only what the recording lacks, one
call per query and no re-ask of a failed query (the Jev client itself retries an HTTP 429 or
529 up to 3 times inside one call), and stops at the first refusal, failure or empty answer.
`jev-preflight` first (one call, about 13 micro-USD, outside the ledger). A call cut by a
transport error settles at 0 in the ledger though Jev may bill it: the cap has 0.026 USD of
room over the pessimistic estimate for that.

## Launch (owner's decision)

    python benchmarks/passage_fit/run.py dry      # free: 355 to ask, 0.025 / 0.074 USD
    python benchmarks/passage_fit/run.py seal     # after review
    python benchmarks/passage_fit/run.py paid     # Jev, capped, once
    python benchmarks/passage_fit/run.py report   # free: analysis.json and the verdict
