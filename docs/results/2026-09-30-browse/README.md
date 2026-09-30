# Browse: the next element on a page, and what a browsing agent reads

**The result, confirmed on new steps:** asked in context which of a page's elements a browsing
agent should act on next, Jev puts the right one in its **top 20 in 89.4 %** of 142 new Mind2Web
steps (top 10: 82.4 %, top 1: 42.3 %) from pages of 559 elements on average, at 0.0065 USD a
step, against 38.7 % for BM25. For scale, with no training: the fine-tuned DeBERTa ranker the
Mind2Web paper built for this job keeps a positive in its top **50** in 88.9 / 85.3 / 85.7 % of
steps on the three test splits (Deng et al., 2023, section 4.3), and a later fine-tuned
DeBERTa-v3 reports 93.8-95.3 % at 20 (a model card, not a paper; not re-run here). A trained
ranker is better; this one needs no labels and no GPU. It took two tries: the registered first
design failed its bar, and the reason it failed is part of the result.

**Two things this does not buy, both registered and both negative:**

- **Handing an answering model only the top 20 is not as good as the whole page** (Phase 2c).
  Sonnet 5 picked the right element in 58.3 % of 60 new steps from every element and 53.3 % from
  Jev's top 20: -5 points, bootstrap interval [-15, +5], under the registered lower bound of -10.
  It cost a tenth as much per step (0.011 USD against 0.113, plus 0.0065 of Jev), and 7 % of the
  time the right element was not among the 20. Not recommended as a replacement for the page.
- **A hook that prunes snapshots inside a real Claude Code session saved nothing** (Phase 3).
  36 sessions of Sonnet 5 browsing six tasks with `playwright-cli`: the hook cost 0.0095 USD a
  session more [-0.006, +0.027] and answered as often. It acted in 8 of 18 sessions:
  `playwright-cli` already serves moderate snapshots (7,000-29,000 characters here, where
  Playwright MCP's snapshot file for one of the same Wikipedia articles holds 512,000), and the agent reached for
  `find` and `eval` more than for snapshots. The one task with a large snapshot (29,179
  characters pruned to about 5,600) was the one where it saved. The hook ships opt-in, without a
  recommendation.

What stands is the ranking as a tool: `sanchopanza browse PAGE --goal ...` from a shell, or the
`rank_elements` MCP tool, returns the elements a step needs with their refs, confirmed at 89 % in
the top 20.

## Phase 2c: registered, negative (`prereg-confirm.md`, amendments, `answers-confirm.json`)

The first 20 confirmation steps of each split. `claude-sonnet-5` through `claude -p` (our
evaluation harness, list prices, not the API), one isolated session per step and arm, the same
prompt: the goal, the actions taken, the numbered elements; the reply is a number.

| Arm | Accuracy | Right element shown | Input tokens / step | List USD / step |
|---|---|---|---|---|
| FULL (every element) | 58.3 % | 100 % | 19,809 | 0.113 |
| TOP (Jev's first 20) | 53.3 % | 93.3 % | 2,192 | 0.011 (+0.0065 Jev) |

TOP minus FULL: -5.0 points [-15, +5]. The registered rule (within 5 points, lower bound above
-10) **fails**. Paired: both right 28, TOP only 4, FULL only 7. Three FULL sessions failed and
count as wrong, as registered: two CLI exits at no cost on ordinary pages, and the largest page
(3,649 elements), where the CLI passed its own 0.60 USD budget (1.14 USD) and stopped. On the 57
steps FULL answered, descriptively: FULL 61.4 %, TOP 56.1 %, the same gap. Two amendments, both
written before the counted sessions: the per-session cap (0.25 to 0.60 USD, sized on the pages)
and the phase ceiling (8 to 12 USD, sized on the pilot); the pilot (FULL 6/9, TOP 5/9) is outside
every count. 8.61 USD spent in all.

## Phase 3: registered, no saving (`prereg-e2e.md`, amendment, `e2e.json`)

Six tasks on neutral public pages (books.toscrape.com, quotes.toscrape.com, two Wikipedia
articles), answers checked by hand the same day, three runs per task and arm, `claude -p` with
`Bash(playwright-cli:*)` and `Read` only, user settings off, `WebFetch` and `WebSearch`
disallowed so both arms browse.

| Arm | Registered success | Answer given at some point (descriptive) | List USD / session | Turns |
|---|---|---|---|---|
| PLAIN | 15/18 | 18/18 | 0.115 | 5.2 |
| LEAN (the hook) | 14/18 | 18/18 | 0.125 (+0.0003 Jev) | 6.1 |

LEAN minus PLAIN, per task: +0.0095 USD [-0.006, +0.027]; by task T1 +0.046, T2 +0.004, T3
+0.009, T4 +0.011, T5 +0.011, T6 -0.023. The registered rule (no fewer answers, cheaper with the
interval below zero) **fails on cost**. Every registered failure, in both arms, is the same
artefact: the agent gave the answer, closed the browser as the prompt asked, and ended on
"Done - browser closed."; the grader reads the final message only, as registered. Pruned
snapshots: T1 7,060 to about 4,600 characters (three times), T5 16,470 to about 10,650 (three),
T6 29,179 to about 5,600 (twice). The pilot found two faults, fixed before any counted session
(`prereg-e2e-amendment.md`): a grader that read "4-star" as wrong, and the hook reading its
event in the Windows console's code page, which made it pass everything through unchanged.
4.32 USD at list price and 0.006 USD of Jev spent.

**A registration fault, stated plainly.** The amendment was written at 19:02, before the first
counted session, and has not changed since, but the runner's check of its hash was never wired
(an edit that did not apply), and its `.sha256` was recorded only after the run. The runner now
checks both files. What the amendment changed (the T1 alternatives, the hook's encoding fix) is
in the code and tests the run used.

## Phase 1: registered, failed (`prereg.md`, `analysis.json`)

169 steps, 60 evenly spaced per test split, 11 dropped because code cannot read their positive
in the cleaned HTML. Arms: BM25; JEV (every element, groups of 30 judged in context, the best 30
judged again together, the final round's answer wins); JEV-SHORT (the same over BM25's top 90).

| Arm | R@1 | R@5 | R@10 | R@20 | R@30 | USD/step |
|---|---|---|---|---|---|---|
| BM25 | 7.7 % | 21.3 % | 29.0 % | 39.1 % | 48.5 % | 0 |
| JEV | 35.5 % | 65.7 % | **71.0 %** [63.8, 77.3] | 81.1 % | 86.4 % | 0.0065 |
| JEV-SHORT | 31.4 % | 53.3 % | 62.1 % | 66.9 % | 69.2 % | 0.0014 |

The registered bar was R@10 >= 0.80: **failed**, so the registered Phase 2 did not run. JEV beat
BM25 by 42 points at 10 [33, 50]. The shortlist costs a fifth but loses what BM25 drops: an
element with no words of the task in it (an unnamed field, an icon) never reaches the judge.
Jev spent 1.34 USD (3,884 calls, six recorded twice by a retry).

## What the development analysis found (free, on Phase 1's recording)

The design was the problem. Re-judging the 30 best together **lowered** the target's rank:
round one alone reached R@10 76.9 %, the final round alone 70.4 %. Among 29 strong rivals the
target loses probability it had among ordinary elements. An even mix of the two rounds
(`browse.BLEND = 0.5`, LATTICE's path relevance) ranked best at every k: R@1 40.8 %, R@10 77.5 %,
R@20 85.8 %, R@30 90.5 %. Chosen on the data it scored, so it claimed nothing; it went to a new
sample. Reading the 25 first misses: unnamed text fields, `div`s holding a whole paragraph, SVG
icons, and targets named differently from the task's words.

## Phase 1c: registered, confirmed (`prereg-confirm.md`, `analysis-confirm.json`)

142 new steps: half a step on from Phase 1's offsets, dropping 28 rows whose task was already in
the development sample and 10 whose positive code cannot read. Arms: BM25 and JEV-BLEND
(`browse.rank`'s defaults). Bar: R@20 >= 0.80 with a Wilson lower bound >= 0.70.

| Arm | R@1 | R@5 | R@10 | R@20 | R@30 | USD/step |
|---|---|---|---|---|---|---|
| BM25 | 8.5 % | 18.3 % | 23.2 % | 38.7 % | 47.2 % | 0 |
| JEV-BLEND | 42.3 % | 75.4 % | **82.4 %** [75.3, 87.8] | **89.4 %** [83.3, 93.5] | 91.5 % | 0.0065 |

**Confirmed.** By split, R@10 / R@30: website 79.5 / 97.7 %, domain 86.8 / 94.3 %, task 80.0 /
82.2 %. JEV-BLEND minus BM25: +59 points at 10 [50, 68], +51 at 20 [42, 59]. Jev spent 0.92 USD
(2,727 calls, 19.2 a step).

## Reproduce

Every Jev answer is recorded (`fixtures/browse-jev.jsonl`, `fixtures/browse-jev-confirm.jsonl`,
hashed keys, no page text). `python benchmarks/browse/run.py` and `run.py --confirm` replay them
for free and reproduce the tables exactly; Jev is not deterministic, and a call asked twice live
(once per arm) is served in the order it was recorded. The steps come from
`benchmarks/browse/data.py` (and `--confirm`), which downloads from the Hugging Face datasets
server into `~/.cache/sanchopanza/mind2web/`.
