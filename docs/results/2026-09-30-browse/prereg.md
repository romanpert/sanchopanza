# Browse: the next element on a page, pre-registration

Written 2026-09-30 before any model saw these pages. The question and criteria are
`sanchopanza.points.browse.NEXT` at the commit that adds this file.

## Question

A browsing agent reads the whole page on every step (a Playwright MCP snapshot, the HTML) to
pick one element to act on. Can a decision model rank the page's elements so that the one the
agent needs is among the first few, at a small fraction of the text, and does an answering
model choose as well from those few as from the whole page?

## Data

Mind2Web (osunlp/Multimodal-Mind2Web, test splits `test_website`, `test_domain`, `test_task`),
60 steps per split at evenly spaced row offsets (`benchmarks/browse/data.py`, no seed, no
choice). A step is dropped only when its positive candidate is not in the cleaned HTML (code
cannot read it); the count dropped is reported. Elements are every candidate of the step
(positive and negative), read from the cleaned HTML by `browse.elements_from_html`. The goal is
`confirmed_task`; `done` is the step's previous `action_reprs`.

## Phase 1: ranking (Jev, no answering model)

Arms:

- **BM25**: `browse.rank` with no squire. Free.
- **JEV**: `browse.rank` with a Jev squire over every element: groups of 30 in page order, the
  best 30 judged again together. `jev-1.13.0`.
- **JEV-SHORT**: the same over the 90 BM25-best elements only.

Metric: Recall@k, the share of steps with a positive among the first k (k = 1, 5, 10, 20, 30),
with Wilson 95 % intervals; paired difference JEV minus BM25 at k = 10 with a bootstrap
interval. Cost per step (Jev dollars, calls), and elements per step.

Published reference, not re-run: MindAct's fine-tuned DeBERTa ranker keeps a positive in its
top 50 in about 86-89 % of steps on these splits (Deng et al., 2023, Table 2).

Decision rule, fixed now:

- JEV Recall@10 >= 0.80 (point estimate) and above BM25 at k = 10 (bootstrap interval above 0):
  the ranking goes into Phase 2 and into the Claude Code hook as an opt-in.
- Below: reported as measured, the hook is not built on it, and nothing is claimed.

Money: Jev at most 1.50 USD for the phase (runner refuses past it).

## Phase 2: does the answering model choose as well from the top k? (claude -p, subscription)

Only if Phase 1 passes. 20 steps per split (the first 20 of each split's sample, in file order),
`claude-sonnet-5` through `claude -p` (tool-less, isolated, `--json-schema`), one session per
step and arm:

- **FULL**: every element line of the page, numbered, with the goal and previous actions.
- **TOP**: the JEV arm's first 20 lines only, same prompt.

The model returns the number of the element to act on next. Metric: element accuracy (a
positive chosen), paired difference TOP minus FULL with a bootstrap interval; input tokens and
list cost per step in each arm.

Decision rule: TOP is recommended when its accuracy is within 5 points of FULL (interval lower
bound above -0.10) at a lower total cost counting Jev. Otherwise the result is published as a
negative.

Money: 6.00 USD at list price for the phase, sessions capped at 0.25 USD each; a pilot of 3
steps per arm first to check the prompt and the parser, excluded from the counts.

## What would make this wrong

- Mind2Web's candidate lists come from cleaned HTML, not from Playwright's accessibility tree;
  a snapshot names elements differently. Phase 3 (a real Claude Code session with Playwright
  MCP) is the check, and it is not part of this registration.
- One positive per step: when a page offers two equivalent ways, a "wrong" pick may be right.
  Counted as wrong, the same in every arm.
