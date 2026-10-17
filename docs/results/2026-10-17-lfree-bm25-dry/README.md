# A free BM25 prefilter before Jev's page tournament (∞Bench En.QA dev, dry)

**Status: dry and free. No call was made: every number below is a replay of the dev's recorded
Jev calls, B6's dry-run stub, or arithmetic on them. Nothing here is a measured result of the
prefilter; it sizes a small paid probe for the owner to approve or not.**

## The question

The longdoc-free dev (`../2026-10-16-longdoc-free/`) found Jev's passage selection cost
0.039 USD a question, 0.037 of it the page tournament (68 calls a question over novels of a
median 805 pages of 900 characters), more than the about 0.030 USD that sending covered
questions to Haiku 4.5 instead of Sonnet 5.5 saves. Would a free BM25 shortlist of the K pages
that best match the question, before the tournament, bring Jev well under that, and what would
it drop?

## Setup

- Option `prefilter_k` in `benchmarks/longdoc_free/jev_phase.py` (`ask`, `dry`, and
  `--prefilter-k` for the dry run only), default off: `pages.bm25_shortlist` keeps the K pages
  BM25 (`text.BM25Index`) scores best for the question, in the novel's order; only those enter
  `select_passages`; every other page is not kept. With the option off, or K at least the
  novel's page count, the output and calls are byte-identical to the sealed path (tested).
- `benchmarks/longdoc_free/bm25_dry.py`, three offline replays of the 41 dev questions:
  - **real**: the dev's recording (`fixtures/longdoc-free/jev-dev.jsonl.gz`) through the sealed
    path; it reproduces the published rows exactly (gate p and kept characters, 41 of 41) and
    gives each call's billed cost and each page's p round by round;
  - **stub**: B6's dry-run Stub, with and without the prefilter;
  - **oracle**: the tournament over the shortlist, each page answering with its own real p in
    each round; sentence calls and the gate from the recording when the identical call was
    recorded, else 0.5. Without the prefilter it reproduces the real tournament calls of every
    question exactly.
- Dollars: each call's size estimate (`estimate_usd`) times the dev's billed/estimate ratio per
  decision point (tournament 0.772, sentences 0.889, gate 0.766). Two cost estimators per K:
  stub calls times that question's own real/stub ratio, and the oracle.

## The dev as recorded

| | |
|---|---|
| Jev a question | 0.0392 USD (1.6072 over 41) |
| Tournament calls | 2,787 (68.0 a question), 0.000542 USD a call (dearest 0.000607) |
| Sentence calls | 27.8 a question (most 182), 0.000078 USD a call |
| Stub's tournament calls | 1,967: real/stub pooled 1.417, per question median 1.615, from 0.589 to 2.474 |
| Gold answer string in Jev's kept text | 21 of 41 (in the novel at all, normalised, 27) |

The stub's error is not a constant: it ranks the lines of a call's page list, and a page with a
paragraph break spans several lines, so its ranks land on the wrong page ids. A flat 1.39
correction is right on the total and wrong on any one question.

## Recall and cost by K (41 questions)

Kept pages: pages with at least one sentence in Jev's real kept text. Gold: ∞Bench's normalised
reference found in the text. "Masked": Jev's real kept text with the pages outside the top K
removed (no new page enters: conservative). "Oracle": the oracle's kept text.

| K | Kept pages surviving (mean) | Questions with all kept pages | Gold page in top K (of 27) | Gold in kept, masked (of 21) | Gold in kept, oracle | Tournament calls, stub × ratio | Tournament calls, oracle | Tournament ceiling (calls) |
|---|---|---|---|---|---|---|---|---|
| 30 | 31.0 % | 3 / 37 | 20 | 14 | 15 | 1.5 | 1.0 | 4 |
| 60 | 38.6 % | 3 / 37 | 22 | 16 | 16 | 4.5 | 4.8 | 8 |
| 90 | 45.4 % | 4 / 37 | 24 | 17 | 17 | 8.2 | 7.9 | 12 |
| 120 | 54.5 % | 6 / 37 | 24 | 18 | 18 | 9.7 | 10.9 | 16 |
| 150 | 59.1 % | 7 / 37 | 24 | 19 | 19 | 11.5 | 13.6 | 20 |
| **200** | 70.1 % | 9 / 37 | 25 | 19 | 19 | 18.1 | 18.7 | 28 |
| 300 | 79.1 % | 12 / 37 | 26 | 21 | 21 | 24.1 | 26.4 | 40 |
| 400 | 84.2 % | 18 / 37 | 27 | 21 | 21 | 34.8 | 35.0 | 56 |
| none | 100 % | 37 / 37 | 27 | 21 | 21 | 68.0 (real) | 68.0 | — |

| K | Jev a question, stub × ratio (USD) | Jev a question, oracle (USD) | 90th percentile (oracle / stub × ratio) | Tournament ceiling (USD) |
|---|---|---|---|---|
| 30 | 0.0012 | 0.0010 | 0.0014 / 0.0018 | 0.0024 |
| 60 | 0.0028 | 0.0029 | 0.0042 / 0.0041 | 0.0049 |
| 90 | 0.0046 | 0.0047 | 0.0063 / 0.0064 | 0.0073 |
| 120 | 0.0059 | 0.0064 | 0.0090 / 0.0081 | 0.0097 |
| 150 | 0.0072 | 0.0081 | 0.0115 / 0.0099 | 0.0121 |
| **200** | **0.0102** | **0.0108** | 0.0148 / 0.0146 | 0.0170 |
| 300 | 0.0144 | 0.0157 | 0.0221 / 0.0202 | 0.0243 |
| 400 | 0.0193 | 0.0202 | 0.0262 / 0.0265 | 0.0340 |
| none (real) | 0.0392 | 0.0392 | | |

The ceiling holds whatever Jev answers: the tournament makes at most 3 pruning rounds and a final
one, each of ceil(K / 30) calls, each priced here at the dev's dearest tournament call.

## Reading

- **Cost.** The two estimators agree within 12 % from K = 60 on (20 % at K = 30, a call or two
  a question). At K = 200, Jev comes to about
  0.010-0.011 USD a question (a quarter of the dev's 0.039); its tournament cannot exceed 28
  calls, 0.017 USD.
- **What it drops.** Of the 21 questions whose gold string Jev's kept text held, K = 200 loses 2
  by both measures; K = 300 loses none (0.014-0.016 USD a question). Jev's kept text itself
  changes more: only 70 % of its kept pages survive at K = 200 (all of them for 9 of the 37
  questions where it kept any). Of 27 questions whose gold string is in the novel at all, BM25 puts a page
  holding it in the top 200 for 25.
- **The oracle's blind spot.** It takes a page's p as its own; real Jev judges each page among
  29 others, and a shortlist where every page matches the question may pass more of them to
  later rounds. That is why the range below goes to 1.5 times the higher estimate, and why only
  a real probe can settle it.

## Recommendation (a projection, not a measurement)

**K = 200.** Jev a question: **0.0105 USD** central (0.0102 stub × ratio, 0.0108 oracle), range
**0.010 to 0.016** (1.5 times the higher), ceiling about 0.031 (the tournament's 0.017 plus the
dev's largest sentence stage, 182 calls, 0.014). Against the dev's substitution saving (0.80 ×
(0.069 − 0.031) ≈ 0.030 a question, or 0.022 on the questions actually covered) that leaves
0.014-0.020 (0.006-0.012 on the covered basis), where the dev was 25 % worse. K = 300 is the
quality-safe alternative at 0.014-0.024. Nothing here says the router's F1 holds: the gate's p
and the coverage would move with the passages.

## The probe it would take (not run; the owner's decision)

- **What:** Jev only, `select_passages` and the gate at K = 200 on 3 dev questions, chosen to
  span the predicted cost: id 0 (oracle 0.0199 USD, the dearest), id 375 (0.0111, the median,
  the longest novel of 1,552 pages) and id 7 (0.0056, the cheapest). Their full-novel real Jev
  was 0.041, 0.068 and 0.070 USD, so each question's saving is read directly.
- **Cost:** expected 0.037 USD (the oracle), 0.055 with 1.5 times; the ceiling of three
  questions is 0.094.
- **Hard cap: 0.10 USD** in its own `paid_once` lot (ledger, recording, sealed prereg), behind
  `jev-preflight`. It needs a new lot and a `paid` path that takes the prefilter: the dry run
  is the only path that takes it today, on purpose.
- **Rule to seal before it runs:** a new dev is worth preparing only if the 3 questions' mean
  real Jev is at most 0.015 USD and none exceeds 0.031; real tournament calls against the
  oracle's are reported per question.

## Files

`bm25-dry.json` (every number above; per question: ids, novel keys, page and call counts,
costs; no question, answer or novel text). Code: `benchmarks/longdoc_free/bm25_dry.py`,
`pages.bm25_shortlist`, `jev_phase.ask(prefilter_k=...)`.
