# Whole papers under a quarter of the text: move the cut to the paragraph, widen the sentence

Two pre-registered runs on QASPER (test split, CC BY 4.0), both on questions nothing was
derived on. The first confirms a rule that keeps 21 % of a paper with every answer sentence in
87 % of questions; the second shows a second model answers from that 21 % at least as well as
from the whole paper.

## The idea

On 2026-09-27 the shipped two stages (`triage_many`, then `select_sentences` at 0.28) kept 31.5 %
of a paper with every answer sentence in 83.1 % of 261 questions, failing both bars (85 %, 25 %).
What they dropped was the second or third sentence of a multi-sentence answer. Replaying those
recordings showed the two stages were doing each other's job: the sentence cut was compressing
and losing recall, while the paragraph stage kept half the paper. Rearranged, with one knob per
job and no new question to the model:

- **Window (recall).** Keep every sentence within 2 positions of a sentence that clears 0.28, in
  the same paragraph. Alone, at the shipped paragraph cut, it lifts all-gold from 83.1 % to 94.6 %
  on the 261, at 40.6 % of the text.
- **Paragraph gate (compression).** Send to the sentence stage only paragraphs whose final
  tournament probability is at least 0.75. Paragraphs under it need no sentence call.

Both use probabilities the two stages already return. The rule (**GW**: gate 0.75, cut 0.28,
window 2) was fixed by a registered procedure on the 261 recorded questions
(`benchmarks/lateral/wholedocs/rescore.py`, `derivation.json`): the highest all-gold recall at
<= 23 % text over 44 rules. There it scored 86.97 % at 22.51 %; re-derived on 40 random halves it
scored 86.7 % at 22.2 % on the other halves, both bars met on 26 of 40.

## Run 1: confirmed (`prereg.md`, hash in `prereg.sha256`)

219 questions nothing was derived on: all 89 eligible papers the 2026-09-27 run never drew, and
130 second questions, never asked, on papers it did draw. The tournament ran as shipped and
`select_sentences` on every paragraph it kept, so every arm is scored on the same calls.

| arm, 219 questions | all answer sentences kept (95 % CI) | any kept | text kept | sentence calls |
|---|---|---|---|---|
| MS: shipped two stages | 84.0 % (78.6-88.3) | 96.3 % | 30.2 % | 4,277 |
| **GW: gate 0.75, cut 0.28, window 2** | **87.2 %** (82.1-91.0) | 91.3 % | **21.0 %** | **1,766** |
| W: window only (gate 0.40) | 93.2 % (89.0-95.8) | 97.3 % | 39.7 % | 4,277 |
| G: gate only (window 0) | 78.5 % | 90.4 % | 17.3 % | 1,766 |
| BM25 over sentences, GW's text | 43.4 % | 69.0 % | 21.5 % | 0 |

- **Q1 holds**: 87.2 % >= 85 % at 21.0 % <= 25 %.
- **Q2 holds**: GW keeps more (+3.2 points, bootstrap 95 % CI -1.8 to +8.2; 19 questions only GW
  keeps whole, 12 only MS; McNemar p = 0.28) with **9.2 points less text**.
- **Q3 holds**: 43.8 points over BM25 with the same text.

By set: fresh papers GW 87.6 % at 22.2 % (MS 86.5 % at 31.4 %), n = 89; second questions GW
86.9 % at 20.2 % (MS 82.3 % at 29.4 %), n = 130. The prediction (84-88 % at 21-24 %) held.

**What is and is not shown.** The point estimate clears the 85 % bar; its Wilson interval
(82.1-91.0) does not exclude a true rate below it, and the gain over the shipped stages in
recall is not significant. What is robust is the dominance: the same or better recall with 30 %
less text and 59 % fewer sentence calls. And the trade is visible: GW loses *every* answer
sentence in 8.7 % of questions (MS 3.7 %), because the gate drops whole evidence paragraphs that
the tournament scored between 0.40 and 0.75. Run 2 asks whether that costs answers.

**Not for short pages.** On the 300 HotpotQA confirmatory questions (recorded, free) GW keeps
every supporting sentence in 83.3 % against the shipped 90.3 %: with ten short pages the gate
drops supporting pages. The rule is for one long document; the short-page defaults stay.

**The replay.** All scores replay exactly. The call count does not: live, the tournament made
855 calls, the replay 853, because 14 to 19 of its calls re-asked a group already judged in the
same tournament and Jev answered differently. That defect is measured and fixed as a candidate
in `../2026-09-28-lateral-memo/`.

## Run 2: the kept 21 % answers at least as well (`prereg-answers.md`)

Claude Haiku 4.5 through the Claude Code CLI (subscription, no API key), reply forced into one
short field, QASPER answer F1 (maximum over annotators). The first 10 questions were a cost pilot
(0.0256 USD per question for both arms), which fixed N = 146 by the registered rule. Every session
returned a structured answer; nothing was excluded.

| input, 146 questions | answer F1 | exact match | "unknown" | input tokens | list cost |
|---|---|---|---|---|---|
| FULL: the whole paper | 44.5 % | 11.0 % | 11 | 940,699 | 2.84 USD |
| **GW: what the rule keeps** | **48.2 %** | 15.1 % | 15 | 324,948 (34.5 %) | 0.75 USD |

- **A1 holds**: GW is not below FULL minus 3 points; it is 3.7 points above.
- **A2 holds**: paired bootstrap 95 % CI of GW minus FULL is [-0.5, +7.8], lower bound over -6.

The claim is equality within the margin, not gain: the interval includes zero. The prediction
(GW within -3 to +1) was pessimistic. The token share (34.5 %) is above the text share (21 %)
because each session carries the same fixed prompt overhead.

## Proposed library change (not made: `src/` is out of scope for this run)

1. `Squire.select_sentences(..., window: int = 0)`: after the cut, keep every sentence within
   `window` of a kept one (`benchmarks/lateral/wholedocs/rules.py`, `widen`). Default 0 keeps
   every shipped number.
2. `Thresholds.document_paragraphs: float = 0.75` and `Thresholds.document_window: int = 2`, with
   a method for one long document:

```python
async def select_passages(self, *, purpose, pages):
    """One long document: tournament, then sentences with a window in paragraphs >= 0.75."""
    kept = await self.triage_many(purpose=purpose, pages=pages)
    out = []
    for (title, text), (keep, p) in zip(pages, kept):
        if not keep or (p is not None and p < self._t.document_paragraphs):
            out.append(None)                       # paragraph not sent on
            continue
        out.append(await self.select_sentences(purpose=purpose, title=title,
                   sentences=split(text), window=self._t.document_window))
    return out
```

`triage_many` already returns the final probability for every kept page, so nothing else moves.

## Paragraph ready for the paper (5.16) and the README

> **Whole documents, rearranged.** On whole papers the sentence cut was doing the compressing and
> losing the second sentence of an answer. Moving the compression to the paragraph (only
> paragraphs the tournament scores at 0.75 or more reach the sentence stage) and widening each
> kept sentence by two neighbours, both fixed on the 261 recorded questions, kept every answer
> sentence in **87.2 %** of 219 new QASPER questions at **21.0 %** of the text, against 84.0 % at
> 30.2 % for the shipped stages on the same calls, with 59 % fewer sentence calls; Claude Haiku 4.5
> answered from that 21 % with F1 48.2 % against 44.5 % from the whole paper (146 questions, CI of
> the difference -0.5 to +7.8), pre-registered. The rule is for one long document: on ten short
> HotpotQA pages it loses 7 points.

## Cost and reproducing

- Jev: 5,132 recorded calls, **0.537 USD** (`fixtures/lateral-wholedocs.jsonl`: tournament 855
  calls 0.290 USD, sentences 4,277 calls 0.247 USD). The derivation replayed existing recordings.
- CLI: 292 sessions, **3.590 USD** at list price against the subscription, 0 USD against any key
  (`fixtures/cli/lateral-wholedocs-answers.jsonl`).

```bash
python benchmarks/lateral/wholedocs/rescore.py --qasper QASPER-TEST.jsonl --hotpot HOTPOT.jsonl
python benchmarks/lateral/wholedocs/confirm.py --qasper QASPER-TEST.jsonl     # free, replay
python benchmarks/lateral/wholedocs/answers.py --qasper QASPER-TEST.jsonl     # free, CLI cache
```

`tests/test_lateral_wholedocs.py` pins the derivation, the confirmation and the answering run
(needs `SANCHOPANZA_QASPER`; `SANCHOPANZA_HOTPOT` for the transfer check). `analysis.json` is the live run
of record (855 tournament calls); `answers-analysis.json` the answering run.

## Applied (2026-09-28)

The rule ships as `Squire.select_passages` with `Thresholds.document_paragraphs = 0.75` and
`document_window = 2`, and `select_sentences(window=)`. `tests/test_select_passages_bench.py`
replays the 219 confirmation questions through the shipped method and demands the same sentences
kept (87.2 %). Since the tournament memo fix (`../2026-09-28-lateral-memo/`) a replay makes 839
tournament calls where the recording holds 853: the 14 repeats are reused, and every number above
is unchanged.
