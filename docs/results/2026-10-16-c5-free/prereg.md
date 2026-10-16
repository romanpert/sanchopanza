# C5: the free order against page order on QASPER questions nobody has looked at (pre-registration, DRAFT)

Status: **draft, not sealed.** Before the seal: an independent `revisor-prereg` review against
the code, then `python -I benchmarks/passage_fit/free_confirm.py seal` writes `prereg.sha256`
(the sha256 of this file and of `c5-free-run.cmd`, its two local values read as placeholders).
Instrument commit: `ba632bc7ba2fbbdf2a5dc60d7377c8bad5009462`.

## Question

When what `Squire.select_passages` keeps from one paper is longer than the caller can deliver,
does cutting it in the free order (`select_passages(fit_chars=B, fit_score=False)`: the delivered
paragraphs by best sentence probability, then tournament probability, then page order, taken
while they fit) keep more answer sentences than cutting it in page order? In B4
(docs/results/2026-10-16-b4-order/), exploring on QASPER test questions whose recordings already
existed, it kept **+13.6 points [+7.1, +20.2]** more (233 questions). The budget, the
population and the tiebreak were fixed there alongside the result. Here all three are fixed
before any answer, on questions no run of this package has read.

## The option under test (opt-in, default unchanged)

`select_passages(..., fit_chars=3400, fit_score=False)` (`src/sanchopanza/squire.py`,
`points/passages.py`), exactly as shipped since B4; no code of the option changes for this run.
`fit_chars=None` (the default) is what every published run used.

## Data

- QASPER validation split (CC BY 4.0), `allenai/qasper`, the parquet of the
  `refs/convert/parquet` branch (`qasper/validation/0000.parquet`, sha256
  `089781b91c337d348dd9e8b57cc8adc100ed2d9cab84a6127402bcccf1559222`), exported row by row to JSON
  lines by `free_confirm.py export` (sha256
  `1824533661cc2f8b4c442a9444ea62ac87b56c99b0aee1782f7c41464da1ab29`, LF; the recipe rebuilds the
  test export's content exactly). `paid`, `dry` and `report` refuse another file.
- **Questions:** every question of a paper whose first answer is answerable with evidence
  paragraphs present in the paper (`longdocs.run.eligible`), each distinct question of a paper
  once: 718; the answer sentences located from the first answer's highlighted evidence
  (`longdocs.sentences.enrich`): 69 not located; 3 where those sentences are not
  `select_passages`' own (`text.split_sentences`) excluded: **646 questions in 257 papers**.
  Pages as the 2026-09-27 runs built them (section, paragraph). The questions are asked in an
  order shuffled with seed 20261018 (`SEED`); the order changes nothing but which calls are in
  flight together.
- Labels by construction: an answer sentence is a sentence overlapping QASPER's highlighted
  evidence. No label comes from a model.

## Arms

jev-1.13.0 (`DEFAULT_MODEL`), shipped thresholds and limits. Per question, `select_passages`
runs twice through one asker, the second answered entirely from the first's calls:

| arm | what is delivered under B = 3,400 characters | calls |
|---|---|---|
| PAGE | `select_passages` without a budget, its delivered paragraphs taken in page order while they fit (`passages.fit`): what a caller cutting today's output gets | the run's |
| **FREE** | `select_passages(fit_chars=3400, fit_score=False)` | none more |
| BM25 | the same delivered paragraphs by BM25 of their kept text against the question | none |
| GOLD | answer paragraphs first (ceiling, descriptive) | none |

**B = 3,400 characters** is B4's registered budget (the median delivered size on its 261
derivation questions), not recomputed here. **Population:** the questions whose delivered text
(the unbudgeted run's kept sentences) exceeds B; on the others every arm delivers the same.

## Metrics

Primary: per question, the share of its answer sentences delivered (recall), averaged over the
population. Secondary: every answer sentence delivered (all-gold), exact McNemar. Intervals:
paired bootstrap over papers (10,000 resamples, seed 20261015, `l4_stats`), since a paper can hold
several questions; item-bootstrap intervals reported, not voted.

## Verdict rule (applied by `free_confirm.py report`, `verdict`, as written)

With lo and hi the 95 % cluster-bootstrap bounds of FREE − PAGE recall on the population,
**unrounded** (`recall_ci95_cluster_exact`; the rounded pair is for reading):

0. **Incomplete.** Once no launch is left, any call unanswered: **"no verdict: incomplete, N
   calls unanswered"**. An unanswered tournament group keeps its paragraphs and an unanswered
   sentence call keeps its sentences (the package's rule: in doubt, text enters), so FREE and
   PAGE cut the same oversized text and the difference is pulled toward zero. The readings
   without every question an unanswered call touched are then reported as a sensitivity
   (`sensitivity_without_affected`), not a verdict. Nothing recorded at all is the same rule.
1. lo > 0: **"FREE confirmed: it keeps more answer sentences than page order at 3,400
   characters"**.
2. hi < 0: **"FREE loses to page order"**.
3. Otherwise **"not confirmed: FREE and page order not told apart"**.

What each licenses. Rule 1 makes `select_passages(fit_chars=..., fit_score=False)` a measured
option at B = 3,400 on scientific papers, jev-1.13.0: a caller that must cut should cut in the
free order, not page order. It says nothing of other budgets, of other documents, or of the
Score (`fit_score=True`, not run here; B4 did not show it pays). Rules 2 and 3 leave the free
order a candidate. Reported, not voted: BM25 − PAGE, GOLD − PAGE, the characters each arm
delivers, the population's size.

## Power

From B4, the paired standard deviation of a FREE − PAGE recall difference is about 0.51. B4's
population was 49 % of its questions; at that share, about 315 of the 646 overflow (the number is
known only after the run). At 315 questions, alpha 0.05 two-sided, normal approximation, with
the standard error widened by a fifth for clustering by paper (2.5 questions a paper): power
about 0.98 for B4's +13.6, 0.83 for +10, 0.64 for +8 (without the widening: 1.00, 0.94, 0.80).

## Cost and caps

The free dry run (`free_confirm.py dry`, B6's stub): 7,116 calls (1,976 tournament, 5,140
sentence), **1.28 USD** at `CappedDecider`'s pessimistic reservation. The stub sends 7.96
paragraphs a question to the sentence stage, about what Jev sent on QASPER test (1,766 calls
over 219 questions, 8.06), so the count is not inflated. At the QASPER whole-papers run's
ledger rate (0.537 USD over 5,132 calls) the 7,116 calls come to **about 0.74 USD expected**;
1.30 USD is the pessimistic end. Ledger dollars are each call's input tokens x 0.042 USD per
million, not TypeSafe's bill; a call cut by a timeout settles at its reservation. Check the
TypeSafe balance by hand before the launch. Claude: 0.

**One ledger for the round.** C4, C5 and C6 share the round's Jev budget in one ledger file,
`C:/sp-runs/w17-jev/ledger.json` (`benchmarks/w17_round.py`; no variable moves it): **6.00 USD
over the three lots**, and this lot's batch `c5-free` capped at **2.00 USD** in it
(`SpendLedger` refuses any call past either). The launches are logged in
`~/.cache/sanchopanza/c5-free/launches.jsonl`. The `jev-preflight` call (about 13 micro-USD) is
outside the ledger.

**Duration.** At B6's pace (11,202 calls in 14.4 minutes, 4 in flight) about 10-20 minutes;
launched before 23:00 it ends well before midnight, and the launcher refuses to start between
00:00 and 08:00.

`paid` refuses, before the key is read, unless: it was started from `c5-free-run.cmd` or a copy
differing only in its two local values; the export has its sha256; the dry run's pessimistic
estimate fits in what this batch and the round have left (`paid_once.room`); the seal matches
this file and the launcher; HEAD descends from the instrument commit and `src/`,
`benchmarks/passage_fit/`, `benchmarks/b6_es/`, `benchmarks/paid_once.py`,
`benchmarks/jev114/l4_stats.py`, `benchmarks/longdocs/`, `benchmarks/triage_sets/run.py` and
`benchmarks/w17_round.py` are identical to it, nothing uncommitted under them (the launcher is
not an instrument path: the seal fixes it, its two local values read as placeholders, so a copy
filled in place passes); the launch rule allows a launch; on a first launch no recording
exists; no other `paid` of the lot holds its lock. Then, in one event loop: `jev-preflight`,
the live client (`JevDecider`, jev-1.13.0, long context and images off, its own retries of 429
and 529 turned off) built inside it, every call through `CappedDecider`, recorded in
`fixtures/c5-free/recording.jsonl` (hashed keys, no text), at most 4 in flight, never asked
twice: a call that failed answers every later identical request of the run with the same
failure (`Asker(memo_failures=True)`). The first cap refusal, 401/402/403/429, 5xx or loss of
connection stops every later call; three failures in a row of any kind do too; an answer from
another model halts the run as a stop of kind "model" (`Asker(model_halts=True)`), written in
`launches.jsonl`.

**Launch rule.** One launch and at most one relaunch (`paid_once.may_launch`), none after an HTTP
402, a 429, the cap or an answer from another model; a relaunch replays what was recorded and
asks the rest. While a relaunch is allowed, `report` refuses with calls unanswered; after it,
rule 0 applies.

**Launch.** From a `git worktree add --detach` at the seal commit, by WMI in its own process group
(`CreateFlags=512`), outside any Claude Code session, before 23:00 (the launcher refuses 00:00-08:00);
the export is made first (free) if it is not already there with its sha256. Stopped only by PID.
