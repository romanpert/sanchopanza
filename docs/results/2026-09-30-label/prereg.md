# Label a corpus: pre-registration

Written 2026-09-30 before any model saw these items. Question and policy are
`points.entities.classification_questions` and `decide_classification` (the `classify` point)
at the commit that adds this file; the rubrics are `benchmarks/label/data.py:RUBRICS`.

## Questions

1. How accurate is Jev as a corpus labeller on public labelled sets, at what cost, against a
   general model answering the same typed question (`claude-haiku-4-5`)?
2. A cascade (Jev, and the general model only on what Jev is unsure of): what accuracy at what
   share of the general model's cost?
3. Jev's Choice `confidence` is `(p1 - 1/k)/(1 - 1/k)`, a function of the winning probability
   alone (derived 2026-09-30 on 6,206 recorded answers; TypeSafe's docs state it for k = 3). Does
   the margin `p1 - p2`, which it ignores, separate right from wrong labels better than `p1`?

## Data

AG News (4 topics) and DBpedia-14 (14 types), test splits, 300 items each at evenly spaced
positions (`benchmarks/label/data.py`). Gold labels are the datasets'. `add_other` is off: every
item belongs to a listed class.

## Arms

- **JEV**: `sanchopanza.label.label` over a Jev squire (`jev-1.13.0`), one call per item.
- **HAIKU**: the same questions through `providers.llm.LLMDecider` on `claude -p`
  (`claude-haiku-4-5-20251001`, tool-less, isolated, `--json-schema`), one session per item.
  Answered through our own evaluation harness; list prices; not directly comparable with the API.
- **CASCADE** (offline, from the two arms' answers, no extra calls): Jev's label when its `p1`
  is at or above `tau`, else Haiku's. `tau` is chosen on the first half of each set (items in
  file order) as the smallest value whose Jev-kept accuracy is >= Haiku's accuracy on that half,
  and evaluated on the second half only.

## Metrics

- Accuracy of the argmax label over all items, Wilson 95 %; accuracy and coverage at the shipped
  `Thresholds.classify` (p1 >= 0.60).
- Cost: Jev dollars; Haiku list dollars as the CLI reports them, and the API-equivalent from its
  token counts at list price (1 / 5 USD per MTok in / out); per 1,000 items.
- Question 3: AUROC of `p1` and of `margin` for "Jev's label is right", per set; selective
  accuracy of the two gates at matched coverage (80 % and 60 % of items kept), with a paired
  bootstrap interval of the difference.

## Decision rules, fixed now

- Question 3: `label` gains a margin gate only if margin beats p1 in selective accuracy at both
  coverages on both sets with bootstrap intervals above 0. Otherwise the gate stays on p1 and the
  margin is reported as a column only.
- Question 2: the cascade is recommended in the docs if, on the held-out halves, its accuracy is
  within 2 points of HAIKU at under half of HAIKU's cost. Otherwise both numbers are published
  and nothing is recommended.

## Money

Jev at most 0.10 USD. Haiku through the CLI at most 6.00 USD list, 0.05 USD per session; a pilot
of 5 items per set first to check the prompt and parser, counted in the ceiling, excluded from
the results.
