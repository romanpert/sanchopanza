# Ordering approved paragraphs that do not fit by a four-level Score (B4)

**The result:** when the passages `select_passages` keeps from one paper are longer than a
3,400-character budget, ordering them by a four-level Score before cutting keeps 81.0 % of
the answer sentences, against 65.1 % for page order (+15.9 points). But it is **not confirmed
under the sealed rule**: against the two free orders it gains +2.3 and +1.8 points, and
neither difference is told apart from zero. The Score is not shown to add anything over what
the tournament and sentence probabilities already give for free.

Pre-registered in `prereg.md`:
- instrument commit `92107d2`, sealed in `7f8bca6`;
- `prereg.sha256` holds the hash of `prereg.md` and of `b4-order-run.cmd`;
- reviewed by `revisor-prereg` before the seal.

Run on 2026-10-16 from a detached worktree at the seal commit, started outside the session
(WMI). The paid step ran from 09:46:56 to 09:48:33 and the report finished at 09:48:42. Jev
(`jev-1.13.0`) answered **355 of 355** Score calls on the first launch, with no relaunch, no
unanswered call and no refusal. Spend was **0.0617 USD** under the 0.10 cap (1,469,013 input
tokens; median latency 250 ms). Claude: 0.

## The question

When the paragraphs that pass `select_passages` exceed what the caller can deliver, does
ordering them by a four-level Score (one per paragraph, all in view, `passages.fit_questions`)
keep more answer sentences than the free orders? An agent with its own harness orders its
approved paragraphs this way, and a second Truth pass did not discriminate there (roadmap B4).

## What ran

- **Questions.** QASPER test split (CC BY 4.0): the 261 derivation questions of
  `2026-09-27-longdocs` and the 219 confirmation questions of `2026-09-28-lateral-wholedocs`.
  The tournament and sentence calls were replayed from their recordings. Each mask comes from
  the shipped document rule (gate 0.75, cut 0.28, window 2).
- **Budget.** B = 3,400 characters: the median delivered size on the 261, rounded down to 100.
  It reads no gold label.
- **Population.** The 233 questions whose delivered text exceeds B: 131 derivation and 102
  confirmation, pooled. The other questions are identical in every arm.
- **The Score.** One four-level Score per delivered paragraph, 12 per call: 202 calls on the
  derivation set and 153 on the confirmation set. A test checks that these are exactly the
  calls `select_passages(fit_chars=3400, fit_score=True)` makes, with the same keys in the same
  order.

## The arms (233 pooled overflowing questions)

| Arm | Order of the delivered paragraphs | Answer-sentence recall | All answer sentences kept [95 % CI] |
|---|---|---|---|
| PAGE | page order (what cutting today's output gives) | 65.1 % | 59.7 % [53.2, 65.8] |
| BM25 | BM25 of the delivered text against the question | 64.8 % | 57.9 % [51.5, 64.1] |
| PROB | tournament probability | 79.3 % | 72.5 % [66.5, 77.9] |
| FREE | `fit_score=False`: best sentence probability, then tournament | 78.7 % | 71.7 % [65.6, 77.1] |
| **L4** | `fit_score=True`: the Score, then FREE's order | **81.0 %** | **74.2 %** [68.3, 79.4] |
| GOLD | answer paragraphs first (ceiling, descriptive) | 92.8 % | 88.8 % [84.2, 92.3] |

Every arm delivers about 3,215 characters on average.

## The pairs (recall difference, paired bootstrap 95 % CI; all-gold McNemar)

| Pair | Recall difference [95 % CI] | All-gold: only first / only second | McNemar p |
|---|---|---|---|
| **L4 − PAGE** | **+15.9 [+9.2, +22.3]** | 51 / 17 | < 0.001 |
| **L4 − BM25** | **+16.2 [+10.2, +22.5]** | 52 / 14 | < 0.001 |
| **L4 − FREE** | +2.3 [−1.5, +6.2] | 17 / 11 | 0.34 |
| **L4 − PROB** | +1.8 [−2.3, +5.7] | 16 / 12 | 0.57 |
| FREE − PAGE | +13.6 [+7.1, +20.2] | 46 / 18 | < 0.001 |
| PROB − PAGE | +14.1 [+7.9, +20.8] | 48 / 18 | < 0.001 |
| BM25 − PAGE | −0.3 [−7.0, +6.3] | 30 / 34 | 0.71 |
| FREE − PROB | −0.5 [−5.0, +3.8] | 18 / 20 | 0.87 |

By set, reported but not voted:
- **Confirmation (102):** L4 − FREE +2.4 [−3.2, +8.6]; L4 − PROB +4.3 [−1.1, +10.6].
- **Derivation (131):** L4 − FREE +2.3 [−3.0, +7.5]; L4 − PROB −0.2 [−5.9, +5.2].

## The verdict, by the sealed rule

- Rule 1 needs all four lower bounds above zero. L4 − PAGE (+0.092) and L4 − BM25 (+0.102)
  pass. L4 − FREE (−0.015) and L4 − PROB (−0.023) do not.
- Rule 2 needs the smaller of the last two above −0.02. It is −0.0233 (unrounded), so it misses
  by 0.003.
- Rule 3 applies: **L4 not confirmed.**

What this licenses, as the prereg wrote it before the run:
- The Score is not shown to help over the free orders. The gain of about +2 points cannot be
  separated from zero with 233 questions, and the run does not show the Score to be worse.
- It says nothing new about the free orders.
- `select_passages(fit_chars=..., fit_score=True)` stays opt-in, as a candidate. No default
  changes.

## The free order against page order

The free order is significantly better than page order: FREE − PAGE +13.6 [+7.1, +20.2] and
PROB − PAGE +14.1 [+7.9, +20.8]. Cutting today's output in reading order loses about a seventh
of the answer sentences that ordering by probabilities the two stages already return keeps.

But this comparison was **exploratory**. The budget rule, the pooled population and FREE's
tiebreak were fixed alongside it, on these same recorded questions. Its numbers are those of
`free.json`, written before any Score was asked, and the paid run did not change them. Only
B = 3,400 was ever computed. The paid verdict does not rest on this comparison; nothing here
licenses shipping `fit_score=False` as a measured option.

## Cost and clock

- **Cost.** 0.0617 USD in the ledger: 355 calls at 4,138 input tokens on average, × 0.042 USD
  per million. That is inside the prereg's realistic range (0.056-0.070) and under its 0.074
  pessimistic estimate.
- **Clock.** The paid step took about 1.6 minutes, under the 3-5 minutes planned.

## What remains

- **Confirm `fit_score=False` on fresh data before changing anything.** This means questions
  nobody has looked at, with the budget rule, the order and the comparison against page order
  fixed in advance. The 219 already took every eligible QASPER test paper the first run left.
  What remains is third questions on used papers, the validation split, or a long document
  outside English scientific papers (which would also cover roadmap B6).
- **Whether the Score is worth asking at all.** At this spread, a gain of +2.3 points would need
  about three times the questions to separate from zero, at about 0.0003 USD per question.
  Before asking: do consumers deliver under budgets where the cut bites as often as here (102
  of 219)?

## Not done

- No library default moved. `fit_chars` stays `None` and `fit_score` stays opt-in.
- No test of other budgets, other answering models, or answer quality from the cut text (as
  the `2026-09-28` run did with Haiku).
- No second recording of the Score, so its run-to-run variation is unmeasured.

## Reproducing

    python benchmarks/passage_fit/run.py report   # free, from fixtures/b4-order/recording.jsonl

This needs the local QASPER test export (sha256 in `prereg.md`). `analysis.json` is the
report the sealed run wrote. `fixtures/b4-order/recording.jsonl` holds keys, token counts,
costs and scores only, no text.
