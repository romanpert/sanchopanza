# B4: order the approved paragraphs that do not fit by a four-level Score (pre-registration, DRAFT)

Status: **draft, not sealed.** Sealing: write the instrument commit below, then
`python benchmarks/passage_fit/run.py seal` after an independent review against the code. The
seal (`prereg.sha256`) holds the sha256 of this file and of `b4-order-run.cmd` (its two local
values read as placeholders). Instrument commit: to be written here at sealing, as
`` Instrument commit: `<40 hex>` ``.

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

- QASPER test split (CC BY 4.0), local export, sha256 (raw bytes)
  `4e71660ba0da787d9c78c6949abe52e67f36db6135f8fea3b96b591e73d5fce1`; `paid` refuses another.
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

**Unanswered Score calls.** One launch and at most one relaunch (`paid_once.may_launch`), none
after an HTTP 402, a 429 or the cap. Within a launch a failed call is not re-asked: the launch
stops; a relaunch asks only what the recording lacks. While a relaunch is still allowed,
`report` refuses to score with calls missing; after it (or after a stop that allows none),
every paragraph of a call still without an answer is unscored (placed as above), and the number
of such calls is reported (`score_calls_unanswered`).

## Metric

Primary: mean over questions of the share of the question's answer sentences delivered under
B (gold = the QASPER evidence spans located as in the 2026-09-27 runs). Secondary: every answer
sentence delivered (all-gold), McNemar exact. Paired bootstrap, 2,000 replicas, seed 7
(`eval.stats.bootstrap_difference`).

## Verdict rule (applied by `run.py report`, as written)

Let lo(X-Y) be the lower bound of the 95 % paired bootstrap interval of the recall difference
on the 233 pooled questions, **unrounded** (`recall_ci95_low_exact`).

1. **L4 confirmed** (the Score pays over the free orders) iff lo(L4-PAGE) > 0,
   lo(L4-BM25) > 0, lo(L4-FREE) > 0 and lo(L4-PROB) > 0.
2. **L4 no better than the free orders** iff lo(L4-PAGE) > 0 and lo(L4-BM25) > 0, and the
   smaller of lo(L4-FREE), lo(L4-PROB) is above -0.02 without 1 holding: the Score is not
   worth its calls at this size.
3. Otherwise **L4 not confirmed**.

What each licenses. The interval's half-width for a difference between two orders is about
0.044 here, wider than the -0.02 margin, so rule 2 holds only when L4's point gain over the
stronger free order (the one giving the smaller lower bound, the minimum of the two) is roughly
+2.4 to +4.4 points without reaching significance: "not worth its
calls" means "a gain this run cannot separate from zero", not "equal". Rule 3 covers a gain
under about +2.4 points, a tie or a loss; it says the Score is not shown to help, and nothing
about the free orders. Neither rule 2 nor rule 3 licenses shipping `fit_score=False` as a
measured option: the free orders' standing rests on the exploratory result below, which needs
its own confirmation on questions nobody looked at. By set (derivation, confirmation) and
all-gold are reported, not voted.

## Already known before this run: EXPLORATORY (free, from the recordings; `free.json`)

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

**This is exploration, not a test.** The budget rule, the population and FREE's tiebreak were
fixed alongside it, on the same recorded questions: the free arms were first run on the 219
alone; the best-sentence order then looked better than the tournament order (+2.0 points there,
not significant) and became FREE's (and L4's) tiebreak; the 261 were then pooled in for power,
where the two orders came out -0.5 apart. Only B = 3,400 was ever computed: no other budget was
tried. The paid verdict does not rest on any of this: B reads no gold label, and no Score answer
has been seen.

## Power

The paired sd of a recall difference between two orders is about 0.34 (from FREE - PROB on
the 233). At n = 233, alpha 0.05 two-sided, 80 % power: a difference of about 6 points is
detectable; the headroom is 14.

## Cost and caps

355 calls of up to 12 paragraphs of up to 900 characters each. What the ledger settles is the
computed cost of each call (its input tokens x 0.042 USD per million). The `CappedDecider`
estimate counts 3 characters per token: 0.074 USD. These calls run at about 3.1-3.9 characters
per token (real cost 0.76-0.95 of that estimate), so the expected spend is **about 0.056-0.070
USD**; the median real request (71 micro-USD, 0.025 USD here) underestimates calls this long.
Hard cap **0.10 USD** in the ledger at a fixed path, `~/.cache/sanchopanza/b4-order/ledger.jsonl`
(no variable moves it; `dry` and `paid` print it), with the launches beside it in
`launches.jsonl` (HEAD and why each stopped). A call cut by a transport error settles at 0 in
the ledger though Jev may bill it: the cap has 0.026 USD of room over the estimate for that.
On a relaunch, what the ledger already holds is added to the estimate before the cap check.

`paid` refuses, before the key is read, unless: the estimate plus what the ledger holds fits
under the cap; the seal matches this file and the launcher (and this file names the instrument
commit: `seal` refuses otherwise); HEAD descends from the instrument commit and `src/`,
`benchmarks/paid_once.py`, `benchmarks/passage_fit/`, `benchmarks/lateral/wholedocs/`,
`benchmarks/lateral/ledger.py`, `benchmarks/longdocs/`, `benchmarks/triage_sets/run.py`,
`benchmarks/thresholds.py` and the three recordings above are identical to it, with nothing
uncommitted under them; the QASPER export has its hash; the launch rule allows a launch; on the
first launch, no recording exists yet; no other `paid` of the lot holds its lock. The key loader
and the live client live in `paid_once.py` (sealed with the instrument); nothing from another
lot is imported. Then, in one event loop: `jev-preflight` (one call, about 13 micro-USD, outside
the ledger), the live client (`JevDecider`, jev-1.13.0, long context and images off) built inside
that loop, every call once, in order, and the first refusal, failure, empty answer or answer
from a model other than jev-1.13.0 stops it. Only lines answered by jev-1.13.0 count as recorded,
in `paid`, `dry` and `report` alike. The Jev client itself retries an HTTP 429 or 529 up to 3
times inside one call. `tests/test_passage_fit_bench.py` checks, on both sets, that
`select_passages(fit_chars=3400, fit_score=True)` asks exactly these 355 queries (202 + 153,
same keys, same order) and that without the Score it cuts exactly as FREE.

The key arrives through the file `SANCHOPANZA_KEYS_ENV` names (never printed, never in this
repository); `b4-order-run.cmd` sets it and the python, as placeholders here, filled only in
the sealed worktree's copy.

**Clock.** About 3-5 minutes for 355 calls, one at a time. Launch attended, outside 02:00-08:00
(Windows Update restarts).

## Launch (owner's decision)

    python benchmarks/passage_fit/run.py dry      # free: 355 to ask, about 0.06-0.07 USD
    python benchmarks/passage_fit/run.py seal     # after review, with the commit written above
    b4-order-run.cmd                              # from the sealed worktree, by WMI: paid, report
