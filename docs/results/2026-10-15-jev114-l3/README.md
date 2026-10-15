# Labelling a corpus: Jev 1.14 against 1.13, in English and in five other languages

**The result:** with the closed rubrics of 2026-09-30, `jev-1.14.0` labels **as accurately as
`jev-1.13.0`**. Both versions were asked today, on the same items, back to back.

- On **AG News, DBpedia-14 and SIB-200 outside English**, the difference is at most 0.2 points,
  and every interval sits inside ±1.3 points. The registered verdict is **"no peor"** on all
  three.
- **Outside English**, 1.14 shows **no measurable extra gain**. Its gain minus its gain in
  English is +1.8 points, but the interval runs from -0.3 to +4.1.
- **At the shipped gate** (`classify`, p1 >= 0.60), coverage and accuracy do not move by any
  registered amount, so nothing calls for recalibration.
- By the registered rule, **`label` can move to 1.14**. This batch changes neither
  `DEFAULT_MODEL` nor `policy.py`.

Pre-registered in `prereg.md` (sha256 in `prereg.sha256`, instrument at commit `67bfa66`),
sealed before any 1.14 answer on these items. An independent review against the code ran in
two rounds before the seal.

**Cost:** Jev spent **0.1512 USD** in the batch ledger for 6,448 calls (3,224 per arm, 0.0756 USD
each), under the batch's 0.20 cap. The two preflights cost another 0.00004 USD, outside the
ledger. Nothing was spent on Claude.

**Replay:** 1.14's answers are in `fixtures/jev114/label-jev.jsonl` and today's 1.13 answers in
`fixtures/jev114/label-jev113r.jsonl`. `python benchmarks/label/jev114.py` replays them for free.

## Data and arms

- **AG News** (4 topics) and **DBpedia-14** (14 types), test splits, 1,000 items each. They are
  the 300 items of 2026-09-30 plus 700 evenly spaced over the rest. The rubrics are
  unchanged (`benchmarks/label/data.py`).
- **SIB-200** (topic classification of FLORES-200 sentences, 7 topics, CC BY-SA 4.0): the whole
  test split, 204 sentences, in English, Spanish, French, German, Chinese (simplified) and
  Arabic, so 1,224 items. The sentences are translations of each other. The rubric is the same
  in every language: the dataset's seven topic names with a one-line English description each
  (`benchmarks/label/data114.py`).
- **Arms:** 13r is `jev-1.13.0` and 14 is `jev-1.14.0`. Both use the `classify` point's question
  and policy (`label.label_one`), with no Danger Zone header. Each item got its two calls back to
  back, with the first arm alternating, and at most 4 requests were in flight. No answer was
  missing, no call was retried into a second answer, and no answer came from a model other than
  the arm's.

## Registered results (`analysis.json`)

Accuracy is the argmax label's, with Wilson 95 % intervals. Differences are 1.14 minus 1.13,
with 95 % paired bootstrap intervals: by item, or in SIB-200 by sentence with all its languages.
McNemar p is Holm-adjusted across the three families.

| | AG News | DBpedia-14 | SIB-200, 5 languages outside English |
|---|---|---|---|
| Items | 1,000 | 1,000 | 1,020 (204 sentences) |
| 1.13 today, argmax | 88.8 % [86.7, 90.6] | 98.5 % [97.5, 99.1] | 89.1 % [87.1, 90.9] |
| 1.14, argmax | 88.7 % [86.6, 90.5] | 98.6 % [97.7, 99.2] | 88.9 % [86.9, 90.7] |
| **Difference, points** | **-0.1 [-0.8, +0.6]** | **+0.1 [0.0, +0.3]** | **-0.2 [-1.3, +0.9]** |
| Only 1.14 right / only 1.13 right; Holm p | 6 / 7; 1.0 | 1 / 0; 1.0 | 10 / 12; 1.0 |
| **Verdict** (non-inferiority at -2 points) | **no peor** | **no peor** | **no peor** |
| At p1 >= 0.60, coverage: 1.13 / 1.14 | 97.9 % / 97.5 % | 99.5 % / 99.4 % | 96.1 % / 95.4 % |
| At p1 >= 0.60, accuracy: 1.13 / 1.14 | 89.5 % / 89.9 % | 98.8 % / 99.0 % | 90.6 % / 90.4 % |
| Coverage difference at 0.60, points | -0.4 [-1.2, +0.4] | -0.1 [-0.6, +0.4] | -0.7 [-2.3, +0.8] |
| Without a threshold, AUROC of p1 for "right": 1.13 / 1.14 | 0.727 / 0.777 | 0.853 / 0.875 | 0.848 / 0.844 |
| AUROC difference | **+0.050 [+0.019, +0.083]** | +0.021 [-0.034, +0.101] | -0.003 [-0.028, +0.024] |
| Labels identical between versions | 98.6 % | 99.7 % | 97.8 % |

### The registered recommendations

- **Move `label` to 1.14: yes.** All three families are "no peor".
- **Recalibrate `classify` for 1.14: no.** No family's coverage at 0.60 moves by more than 2
  points with its interval off zero, and no accuracy at 0.60 has its interval below zero.
- **Claim that 1.14 gains more outside English: no.** The difference in differences is
  +1.8 points [-0.3, +4.1].

### Per language (SIB-200, argmax accuracy, 204 sentences each)

| | English | Spanish | French | German | Chinese | Arabic |
|---|---|---|---|---|---|---|
| 1.13 | 89.2 % | 89.2 % | 90.2 % | 90.7 % | 87.7 % | 87.7 % |
| 1.14 | 87.3 % | 87.7 % | 89.2 % | 89.7 % | 88.2 % | 89.7 % |

The two versions are close in every language. 1.14 is a little lower in the Latin-script
languages and a little higher in Chinese and Arabic, which is where the small, non-significant
difference in differences comes from.

In SIB-200 English, reported apart as the reference for the gap, 1.14 is 2.0 points lower
[-4.4, 0.0]: 1 item right only for 1.14, 5 only for 1.13, McNemar p 0.22. At the gate its
accuracy is 2.9 points lower [-5.4, -0.9], with 1.5 points more coverage. That is on 204
sentences, and the registered rule does not count this set as a family. Read it as a reason to
watch English topic labels after a switch, not as a measured regression.

### Noise: today's 1.13 against the 2026-09-30 recording

On the 300 items per English set that both runs have, today's 1.13 gives the same label as the
recording on 99.7 % (AG News) and 100 % (DBpedia) of them: 89.0 % against 89.3 %, and 98.0 %
against 98.0 %. A rerun of 1.13 moves about one label in 300 on these sets. The difference
between versions (1.4 %, 0.3 % and 2.3 % of labels changed) is larger than that, but it moves
right and wrong labels about equally.

## What this shows and what it does not

- **The vendor's claim.** On these sets, 1.14 is a drop-in replacement for 1.13 as a labeller,
  at the same price per token (both versions read the same number of input tokens). The
  vendor's "largest gain in multilingual" does not show up here: in five languages with an
  English rubric, the two versions label alike.
- **Ranking at AG News.** 1.14 orders its confidence better on AG News: its AUROC of p1 rises
  by 0.05, with an interval off zero. This metric is reported, but no rule rests on it. It does
  not appear on the other two sets.
- **The errors are the same ones.** The largest share on AG News is still the Sci/Tech-labelled-
  Business boundary: 51 items, the same for both versions. On SIB-200 it is geography taken as
  science/technology (25 items for 1.14) and entertainment taken as travel (16).
- **Not measured:**
  - Languages outside these six, and low-resource ones. SIB-200 has 205 languages; this run
    took six widely spoken ones.
  - Rubrics written in the item's own language.
  - Rubrics with overlapping labels.
  - Latency.
  - Jev is not deterministic, and each version was asked once per item.
