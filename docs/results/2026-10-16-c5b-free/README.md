# The free order against page order on fresh QASPER train questions (C5b)

**The result:** when what `select_passages` keeps from a paper is longer than 3,400 characters,
cutting it in the free order keeps more answer sentences than cutting it in page order.
**Confirmed by the sealed rule.** The free order is `select_passages(fit_chars=3400,
fit_score=False)`.
- **Recall:** FREE **78.3 %**, page order **61.9 %**, **+16.4 points, cluster 95 % CI [+11.0,
  +21.9]**, on the 348 questions (216 papers) whose kept text exceeds the budget.
- **Text:** both deliver the same amount, 3,214 against 3,218 characters.
- **Every answer sentence kept:** 72.1 % against 56.3 %, McNemar 81 against 26.

This is the confirmation C5 could not give. C5's runner cut 1,437 of FREE's decisions with its
own budget, so its sealed reading did not measure the option
(docs/results/2026-10-16-c5-free/). C5b runs the same design with that runner fixed, on
questions no run of this package had read.

Pre-registered in `prereg.md`, a delta on C5's sealed prereg:
- instrument commit `3386caa`, sealed in `adc03c2`;
- `prereg.sha256` holds the hash of `prereg.md` (`9fa14258…`) and of `c5b-free-run.cmd`;
- reviewed by `revisor-prereg` against the code before the seal.

Run on 2026-10-16 from a detached worktree at the seal commit, started outside the session (WMI
at 21:13:45). The paid step ended at 21:39:07 and the report at 21:39:52. Jev (`jev-1.13.0`)
answered **8,869 of 8,869** calls on the first launch, with no relaunch, no unanswered call and
no refusal. The round's shared ledger settled **1.3710 USD** for this batch, under its 2.00 cap.
Claude: 0.

## What changed from C5

Only what the delta prereg lists:
- **Questions:** QASPER train (CC BY 4.0), never read by this package before. Of its 888 papers,
  1,653 questions were built by C5's builder. A paper-wise draw with seed 20261019 took **646
  questions in 300 papers**, none of them in the validation split C5 used.
- **The runner's squire has no cap of its own.** The caps are the ledger's.
- **Lot `c5b-free`:** its own recording, launcher and batch cap.

Everything else is C5's, word for word:
- the option, B = 3,400 characters, and the arms PAGE, FREE, BM25 and GOLD;
- the population: questions whose delivered text exceeds B;
- the metric, the cluster bootstrap over papers, and the rules.

## The verdict, by the sealed rule

| Condition (prereg) | Measured |
|---|---|
| Rule 0: calls unanswered | **0** |
| Rule 1: lower bound of FREE − PAGE recall, unrounded, > 0 | **+0.10987** |

**"FREE confirmed: it keeps more answer sentences than page order at 3,400 characters"**

## The arms (348 overflowing questions, 216 papers)

| arm | recall | all answer sentences | characters delivered |
|---|---|---|---|
| PAGE | 61.9 % | 56.3 % | 3,218 |
| BM25 | 61.6 % | 54.3 % | 3,248 |
| **FREE** | **78.3 %** | **72.1 %** | 3,214 |
| GOLD (ceiling) | 92.9 % | 89.9 % | 3,219 |

| pair | recall difference [cluster 95 % CI] | item CI | all-gold: only first / only second | McNemar p |
|---|---|---|---|---|
| **FREE − PAGE** | **+16.4 [+11.0, +21.9]** | [+10.9, +21.9] | 81 / 26 | < 0.001 |
| BM25 − PAGE | −0.3 [−6.1, +5.6] | [−5.9, +5.3] | 50 / 57 | 0.56 |
| GOLD − PAGE | +31.0 [+26.3, +35.7] | [+26.5, +35.6] | 117 / 0 | < 0.001 |

- **The free order only reorders the delivered text.** It keeps the same characters as page
  order and more of the sentences that answer.
- **BM25 over the delivered text** is not told apart from page order.
- **The ceiling** (answer paragraphs first) leaves 14.6 points above the free order.

## Against the earlier readings (context, not part of the verdict)

| reading | data | FREE − PAGE recall |
|---|---|---|
| B4, exploratory | QASPER test, 233 questions, recorded answers | +13.6 [+7.1, +20.2] |
| C5, post-data amendment (the squire's cap lifted) | QASPER validation, 346 questions | +12.0 [+6.7, +17.0] |
| **C5b, sealed** | QASPER train, 348 questions | **+16.4 [+11.0, +21.9]** |

The three readings come from three disjoint QASPER splits and agree in direction and size. Only
C5b's is a sealed confirmation: B4 chose its budget and tiebreak on its own data, and C5's
figure is a post-data amendment of a run whose sealed reading failed.

## What it licenses

By the prereg's rule 1 (C5's, inherited):
- **Licensed:** `select_passages(fit_chars=..., fit_score=False)` is a measured option at
  B = 3,400 on scientific papers, at jev-1.13.0. A caller that must cut what `select_passages`
  keeps should cut in the free order, not in page order.
- **Not licensed:**
  - other budgets, other kinds of document, or other models;
  - any change to `select_passages`' defaults. `fit_chars=None`, no fitting, stays the default.
- **About `fit_score`'s default (True, the four-level Score):** this run did not test the
  Score. B4 did not confirm it over the free order: +2.3 [−1.5, +6.2], at the cost of its calls.
  Making `fit_score=False` the default for callers that set `fit_chars` is a separate decision,
  which this rule does not license. The owner took it after this run, on C5b with B4: since 0.3.2
  `fit_score` defaults to `False` (`9abb025`); `fit_chars=None` is unchanged.

## Cost and clock

- **Cost:** 1.3710 USD on the round's shared ledger (batch `c5b-free`, cap 2.00), inside the
  prereg's expected 1.3-1.4. That is 8,869 calls (2,829 tournament, 6,040 sentence) and
  32,643,307 input tokens at 0.042 USD per million: the ledger's figure, not TypeSafe's bill.
  The preflight call is outside it. The dry run had predicted 7,379 calls.
- **Clock:** 25 minutes from launch to the end of the paid step, 26 to the report; median latency 437 ms.

## Reproducing

    python -I benchmarks/passage_fit/free_confirm_b.py export <train parquet>   # once
    python -c "import gzip,shutil; shutil.copyfileobj(gzip.open('fixtures/c5b-free/recording.jsonl.gz'), open('fixtures/c5b-free/recording.jsonl', 'wb'))"
    python -I benchmarks/passage_fit/free_confirm_b.py report

`analysis.json` is the report the sealed run wrote; the replay at the seal commit reproduces it byte for byte (from a later checkout only `head` differs). The
recording ships gzipped (`fixtures/c5b-free/recording.jsonl.gz`, 8,869 lines; keys, token
counts, costs and answers, no text). `tests/test_c4_c5_published.py` checks its hash and, where
the train export is present, replays the report. `launches.jsonl` holds the launch's lines.
