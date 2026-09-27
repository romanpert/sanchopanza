# Pre-registration: whole papers under a quarter of the text, by moving the cut to the paragraph and widening the sentence

Written 2026-09-28 before any live call of this run. Hash in `prereg.sha256` (sha256 of this
file with line endings normalised to LF). `benchmarks/lateral/wholedocs/confirm.py` refuses
`--live` unless the hash matches.

## Claim

On whole scientific papers, the shipped two stages (`triage_many` at 0.18 / 0.40, then
`select_sentences` at 0.28) keep 31.5 % of the text and every answer sentence in 83.1 % of
questions (`docs/results/2026-09-27-longdocs/`, both bars failed). The loss is the second or
third sentence of a multi-sentence answer. One rule with one new knob per job, applied to the
same probabilities the two stages already return:

- **window 2**: a sentence is kept if any sentence within two positions of it, in the same
  paragraph, clears the shipped sentence cut 0.28 (the recall half);
- **paragraph gate 0.75**: only paragraphs whose final tournament probability is at least 0.75
  go to the sentence stage (the compression half; the paragraphs under it need no sentence call).

The claim is that this rule (**GW**: gate 0.75, cut 0.28, window 2) keeps every answer sentence
in at least 85 % of questions with at most 25 % of the text, on questions nothing was derived on.

## How the rule was fixed (already done, free, on the recordings)

`benchmarks/lateral/wholedocs/rescore.py` replays the 261 questions of 2026-09-27 (1,569 +
5,308 recorded calls) and scores a family of 44 rules: gate in {0.40, 0.45, ..., 0.90}, window
in {0, 1, 2, 3}, sentence cut fixed at the shipped 0.28. The registered procedure: the highest
all-gold recall with text kept at most 23 % (two points under the bar), ties to less text, then
the smaller window, then the lower gate. It picked gate 0.75, window 2: 86.97 % at 22.51 % on
the 261 (shipped: 83.14 % at 31.48 %). `derivation.json` holds every rule's score.

**Disclosure.** Before writing the family down, the author explored these 261 questions freely:
products of the two probabilities, sentence cuts from 0.05 to 0.60, a "rescue" branch for
paragraphs under the gate, windows on one side only. The family registered here is the simplest
one that did as well. All of that exploration touched only the 261; the confirmation sets below
were never scored, and no Jev answer exists for them.

Out-of-sample estimate from the recordings: re-deriving on 40 random halves of 130 and scoring
the other 131 gives a mean of 86.7 % at 22.2 % held out, both bars met on 26 of 40 halves,
worst half 80.9 %. The HotpotQA confirmatory set (300 short-page questions, recorded) scored
under GW falls from 90.3 % to 83.3 %: **the rule is for long documents only** and nothing here
licenses changing the short-page defaults.

## Data (never used for any derivation)

QASPER test split (CC BY 4.0), converted row by row from the `allenai/qasper` parquet, the same
file as 2026-09-27. Eligibility and gold marks exactly as 2026-09-27 (`benchmarks/longdocs/`):
first annotator answerable, every evidence paragraph found in the text, every highlighted span
located in its paragraph (`sentences.enrich`).

- **Fresh papers**: every eligible paper the 2026-09-27 run did not draw (92), one question
  drawn as that run draws it; 89 remain after span location.
- **Second questions**: for each of the 300 papers of 2026-09-27, a question other than the one
  asked there, drawn with `Random(f"2031-{paper_id}")` among eligible ones; 218 remain after span
  location; sorted by id and shuffled with `Random(2032)`; the first 130 are used (a cost
  limit). The paper was seen by the earlier run; this question and its gold were not.

219 questions in all. The primary analysis pools them; each set is also reported alone.

## Arms (all from the same calls)

- **GW** (registered): gate 0.75, cut 0.28, window 2.
- **MS** (shipped two stages): gate 0.40 (the tournament's own), cut 0.28, window 0.
- **W** (window only, descriptive): gate 0.40, cut 0.28, window 2.
- **G** (gate only, descriptive): gate 0.75, cut 0.28, window 0.
- **BM25** over sentences with at least GW's text per question (as 2026-09-27).

Calls: `Squire.triage_many`-identical tournament (shipped cuts) on every question, and
`select_sentences` on **every** paragraph the tournament keeps, so that MS can be scored; GW
itself needs the sentence calls only of paragraphs at or above its gate, which is reported.

## Metrics

All-gold (every highlighted sentence kept), any-gold, text kept (share of paragraph characters,
mean over questions), exactly as `benchmarks/longdocs/sentences.py`. Wilson 95 % intervals;
GW against MS paired: McNemar and bootstrap difference.

## Criteria (pooled, 219 questions)

- **Q1**: GW all-gold >= 85 % **and** GW text kept <= 25 %.
- **Q2**: GW all-gold >= MS all-gold **and** GW text kept at least 5 points below MS.
- **Q3**: GW all-gold at least 10 points above BM25 with GW's text.

Verdict: all three hold = **confirmed**; otherwise **not confirmed**, reported as it falls.

## Prediction

GW 84-88 % at 21-24 % of the text; MS 81-85 % at 30-33 %; Q1 is the uncertain one (the halves
put it near 65 %), Q2 and Q3 should hold. Sentence calls needed by GW: about 45 % of MS's.

## Cost and caps

Tournament: about 5 calls per question at about 340 millionths each (2026-09-27), about 0.39
USD; sentences: about 20 calls per question at about 57 millionths, about 0.25 USD. Hard caps in
code: 0.45 USD on the tournament squire, 0.32 USD on the sentence squire, and
`benchmarks/lateral/ledger.py` refuses the run if the recorded Jev spend of every lateral run
plus 0.77 USD would pass 1.00 USD. One throttle for both stages (12 calls a second), at most 4
attempts per call, no other retry. A cap reached means an incomplete run: nothing is scored.
