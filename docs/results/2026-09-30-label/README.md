# Labelling a corpus: Jev against Haiku, and whether the margin says more than p1

**The result:** as a corpus labeller on two public labelled sets, Jev is **as accurate as
`claude-haiku-4-5` or better, at 1/70 to 1/95 of its cost**: 89.3 % against 83.0 % on AG News,
98.0 % against 98.0 % on DBpedia-14, at 0.02-0.03 USD per thousand items against 1.89 USD (Haiku
through the API, from its token counts) or 2.93 USD (as `claude -p` billed it). The margin
`p1 - p2`, which Jev's Choice `confidence` ignores, separates right labels from wrong ones **no
better than p1 does**, so the abstention gate stays on p1. Escalating Jev's doubts to Haiku buys
nothing on these sets, because Haiku is not better than Jev on them.

Pre-registered in `prereg.md` (sealed before any item was labelled; sha256 in `prereg.sha256`).
Jev spent 0.0142 USD; Haiku 1.76 USD at list price through the subscription, under the 0.10 and
6.00 caps. Every Jev answer is in `fixtures/label-jev.jsonl` and every Haiku session in
`fixtures/cli/label-haiku.jsonl`; `python benchmarks/label/run.py` replays them for free.

## Data

- AG News (4 topics) and DBpedia-14 (14 entity types), test splits, 300 items each at evenly
  spaced positions (DBpedia's test split is sorted by class; the sample is balanced: 73-76 per
  topic, 21-22 per type). Gold labels are the datasets'.
- The rubrics are each dataset's class names with a one-line description written before any
  model saw an item (`benchmarks/label/data.py:RUBRICS`). No `other` option: every item belongs.

## Registered results (`analysis.json`)

| | AG News | DBpedia-14 |
|---|---|---|
| Jev, argmax | **89.3 %** [85.3, 92.3] | 98.0 % [95.7, 99.1] |
| Jev at the shipped `classify` gate (p1 >= 0.60): coverage / accuracy | 98.3 % / 90.2 % | 99.7 % / 98.3 % |
| Haiku 4.5, same questions | 83.0 % [78.3, 86.8] | 98.0 % [95.7, 99.1] |
| Jev USD per 1,000 items | 0.020 | 0.028 |
| Haiku USD per 1,000 items (API-equivalent / `claude -p` list) | 1.89 / 2.93 (both sets) | |

Wilson 95 % intervals in brackets. On AG News most errors of both arms are the same one: a
Sci/Tech article (typically about a tech company) labelled Business, 17 of Jev's 32 errors and
31 of Haiku's 51. That boundary is the dataset's loosest.

### Question 3: does the margin say more than p1?

| | AG News | DBpedia-14 |
|---|---|---|
| AUROC for "Jev is right": p1 / margin | 0.723 / 0.722 | 0.903 / 0.902 |
| Accuracy of the 80 % most confident, by p1 / by margin | 94.6 % / 94.6 % | 99.6 % / 99.6 % |
| Accuracy of the 60 % most confident, by p1 / by margin | 94.4 % / 94.4 % | 99.4 % / 99.4 % |

The registered rule wanted the margin ahead at both coverages on both sets with its interval
above zero. It is not ahead anywhere (every bootstrap interval is [0, 0]): **the gate stays on
p1**, and `label` reports the margin as a column only. Jev puts nearly all of an answer's mass
on one or two options, so the runner-up adds almost nothing to the winner. That is why the
fact behind the question matters less than it looked: Jev's Choice `confidence` is
`(p1 - 1/k)/(1 - 1/k)` (TypeSafe documents it for k = 3; we measured it on 6,206 recorded
answers), so it is p1 in other units and never a second signal, but on this model the signal it
ignores is empty too. Two consequences stand: a Choice gate on `confidence` shifts with the
number of options (adding an option asks for a different p1), and `confidence` is not a
calibrated probability; p1 is the number to threshold.

### Question 2: the cascade

`tau` was chosen on each set's first half as the smallest p1 at which Jev's kept accuracy
reached Haiku's; on both sets that is below every item, so nothing escalates on the held-out
halves (AG News: 93.3 % for the cascade, which is Jev alone, against 86.7 % for Haiku; DBpedia:
100 % both). The registered rule (within 2 points of Haiku at under half its cost) holds, but
only in the trivial way: **use Jev alone on sets like these**. A cascade earns its place when the
expensive stage is better than the cheap one, which on these sets would take a stronger model
than Haiku; that is not measured here.

## What this does not show

- Two sets with clean, well-known taxonomies. A rubric of your own, with overlapping labels,
  can do worse; measure it (the bench takes any labelled `.jsonl` and rubric).
- Haiku answered one item per session through `claude -p`; batching several items per request
  would lower its cost per item. The API-equivalent column is the fairer comparison.
- Jev is not deterministic; a re-run can move a few labels.
