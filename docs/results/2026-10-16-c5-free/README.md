# The free order against page order on fresh QASPER questions (C5)

**The result:** the sealed rule reads **"FREE loses to page order"** (−6.9 points, cluster 95 %
CI [−13.4, −0.6]). That reading does not measure the option.
- **What went wrong in the reading.** The sealed runner capped its own squire at 2.00 USD of
  decisions. Each time the memo or the recording answered a decision, the squire counted it
  again. In the sealed report 1,437 of FREE's decisions, in 292 of the 646 questions (1,138 of
  them in 182 of the 346 that count), came back as the package's default ("budget exhausted")
  and were never asked.
- **Where FREE was not cut** (164 questions): it kept **78.0 %** of the answer sentences, against
  page order's 59.8 %.
- **The same recorded answers with the squire's cap lifted** (a post-data amendment, labelled
  as such; it does not replace the sealed verdict): FREE **75.6 %** against page order's
  **63.6 %**, **+12.0 points [+6.7, +17.0]**, in line with B4's exploratory +13.6 [+7.1,
  +20.2], post-data.

The sealed verdict is what the rule produced; the defect means it does not measure the
option, and the post-data reading does not replace it. **B4's +13.6 was not refuted**: what the
sealed rule read as a loss is the runner cutting FREE's runs. The confirmation came from C5b,
the same design on a fresh QASPER train draw with the runner fixed: **+16.4 points [+11.0,
+21.9]**, confirmed by the sealed rule (docs/results/2026-10-16-c5b-free/).

Pre-registered in `prereg.md`:
- instrument commit `319ee79`, sealed in `3a201f0`;
- `prereg.sha256` holds the hash of `prereg.md` (`8b22ed29…`) and of `c5-free-run.cmd`;
- reviewed twice by `revisor-prereg` against the code before the seal.

Run on 2026-10-16 from a detached worktree at the seal commit, started outside the session
(WMI). Jev (`jev-1.13.0`) answered every call it was asked, with no refusal and no failed call.

| launch | when | calls | outcome |
|---|---|---|---|
| first | 18:42:39-19:06:42 | 7,956 | all answered; `report` refused: 246 calls never asked |
| relaunch | 19:09:24-19:11:09 | 246 | all answered; report written |

The relaunch is the sealed procedure for a recording that lacks calls: it replays what was
recorded and asks the rest. The 246 calls (all sentence calls) were missing for the same reason
as above. On the first launch the squire's meter reached 2.00 partway, and the decisions after
that never reached Jev. The ledger settled **1.2220 USD** for 8,202 calls, under the batch's
2.00 cap. Claude: 0.

## The question

When what `Squire.select_passages` keeps from one paper is longer than the caller can deliver,
does cutting it in the free order keep more answer sentences than cutting it in page order?
The free order is `select_passages(fit_chars=3400, fit_score=False)`: paragraphs by best
sentence probability, then tournament probability, taken while they fit. B4 found +13.6 points,
exploring, on QASPER test questions; here the budget, the order and the comparison were fixed
before any answer.

## What ran

- **Questions:** QASPER validation (CC BY 4.0), never read by this package before. Every
  question whose first answer has evidence paragraphs: 646 questions in 257 papers.
- **Per question:** the shipped `select_passages` without a budget (PAGE cuts that output in
  page order) and with `fit_chars=3400, fit_score=False` (FREE). The second run's calls are the
  first run's, answered from the memo.
- **Budget:** B = 3,400 characters, B4's. **Population:** the 346 questions (191 papers) whose
  delivered text exceeds B.

## The sealed reading (`analysis.json`)

| arm | recall | all answer sentences | characters delivered |
|---|---|---|---|
| PAGE | 63.6 % | 58.4 % | 3,192 |
| BM25 | 67.1 % | 60.1 % | 3,209 |
| FREE | 56.6 % | 52.0 % | **2,396** |
| GOLD (ceiling) | 94.1 % | 91.9 % | 3,197 |

FREE − PAGE −6.9 [−13.4, −0.6], all-gold 51 against 73 (McNemar p 0.059). By the sealed rule,
"FREE loses to page order". BM25 − PAGE +3.6 [−2.2, +9.0].

## Why that reading does not measure the option

FREE delivers 800 characters less than page order, under the same budget, from the same kept
text. The free order only reorders what is kept; it cannot shrink it. So the shortfall points at
the runner.

- **The cause.** The runner built its squire with `max_usd` equal to the batch cap, 2.00. A
  squire charges every decision's cost to its own meter, including a decision the memo or the
  recording answers. FREE's run repeats PAGE's calls, so the meter counted the run about twice:
  2.44 USD over the 646 questions.
- **What it did.** Past 2.00, the squire returned its default without asking: "budget
  exhausted". In the report, 1,437 decisions were cut, all in FREE's runs: 375 tournament calls
  and 1,062 sentence calls, in 292 questions. PAGE's run is identical with or without the cap.
- **What the default does to FREE.** A paragraph or sentence without an answer is kept whole
  (in doubt, text enters). A cut run therefore delivers whole paragraphs with no probabilities,
  and fewer of them fit under 3,400 characters.

| overflowing questions | n | PAGE recall | FREE recall, sealed | FREE recall, cap lifted | FREE characters, sealed | FREE characters, cap lifted |
|---|---|---|---|---|---|---|
| FREE's run cut | 182 | 66.9 % | **37.4 %** | 73.3 % | **1,669** | 3,236 |
| not cut | 164 | 59.8 % | 78.0 % | 78.0 % | 3,203 | 3,203 |

`free_confirm.py report` replays the sealed setting (`SEALED_SQUIRE_CAP_USD`) and reproduces
`analysis.json` exactly. The runner now gives its squire no cap of its own (`SQUIRE_CAP_USD`);
the caps are the ledger's. A test fails under the sealed setting and passes now. C6's runner had
the same setting and is fixed too.

## The same answers with the cap lifted (`analysis-postdata.json`, post-data amendment)

| arm | recall | all answer sentences | characters delivered |
|---|---|---|---|
| PAGE | 63.6 % | 58.4 % | 3,192 |
| BM25 | 67.1 % | 60.1 % | 3,209 |
| **FREE** | **75.6 %** | **69.4 %** | 3,220 |
| GOLD (ceiling) | 94.1 % | 91.9 % | 3,197 |

FREE − PAGE **+12.0 [+6.7, +17.0]** (item bootstrap [+7.1, +16.9]); all-gold 66 against 28,
McNemar p 0.0001. Every answer comes from the sealed recording: nothing was asked again. What
changed after the data is one line of the runner. By the project's rule, an amendment written
after the data is labelled as such and does not replace the sealed verdict.

## What it implies

- **`fit_score=False` stays opt-in, as a candidate.** That is what the sealed rule licenses: its
  rule 2 ("FREE loses") leaves the free order a candidate as rule 3 does (`prereg.md`, "What each
  licenses"). It should not be retired: B4 (exploratory) and this lot's post-data reading both
  favour it over page order, by +13.6 and +12.0.
- **C5b has since measured it:** on 646 fresh QASPER train questions with the runner fixed,
  FREE kept 78.3 % against page order's 61.9 %, +16.4 [+11.0, +21.9], confirmed by the sealed
  rule (docs/results/2026-10-16-c5b-free/).
- **BM25 over the delivered text** is not told apart from page order (+3.6 [−2.2, +9.0]).
- **The ceiling** (answer paragraphs first) is 94.1 %, +30.5 points over page order [+25.5,
  +35.4]; post-data, 18.5 points above the free order.

## Cost and clock

- **Cost:** 1.2220 USD on the round's shared ledger (batch `c5-free`, cap 2.00; the round's
  6.00 over C4, C5 and C6). That is 8,202 calls and 29,095,050 input tokens at 0.042 USD per
  million: the ledger's figure, not TypeSafe's bill. The preflight calls are outside it.
- **Clock:** 24 minutes for the first launch, 2 for the relaunch; median latency 421 ms.

## Reproducing

    python -I benchmarks/passage_fit/free_confirm.py export <validation parquet>   # once
    python -c "import gzip,shutil; shutil.copyfileobj(gzip.open('fixtures/c5-free/recording.jsonl.gz'), open('fixtures/c5-free/recording.jsonl', 'wb'))"
    python -I benchmarks/passage_fit/free_confirm.py report     # the sealed reading
    python -I benchmarks/passage_fit/free_confirm.py postdata   # the cap lifted

The recording ships gzipped (`fixtures/c5-free/recording.jsonl.gz`, 8,202 lines; keys, token
counts, costs and answers, no text). `tests/test_c4_c5_published.py` checks its hash and, where
the QASPER export is present, replays both files. `launches.jsonl` holds both launches' lines.
