# Benches

JSON-lines files, one labelled case per line, comments with `#`. Content is Spanish, except
the AgentDojo-derived material, which is English; keys and labels are English.

| File | Cases | Points | Labels |
|---|---|---|---|
| `benches/core.jsonl` | 74 | routing 20, search 18, triage 16, citation 20 | one annotator |
| `benches/safety.jsonl` | 106 | injection 28, command 32, unsourced 22, numeric_citation 24 | one annotator; adversarial cases written, not harvested |
| `benches/graph.jsonl` | 65 | entity 24, facts 20, dependency 20, plan 1 (56 pairs) | one annotator |
| `benches/memory.jsonl` | 46 | memory_write 16, memory_collision 16, recall 14 | one annotator, 2026-09-24 |
| `benches/graph-build.jsonl` | 36 | extract_gate 16, edge 20 | one annotator, 2026-09-24 |
| `benches/retrieval.jsonl` | 16 | redundant_page 16 | one annotator, 2026-09-24 |
| `benches/loop.jsonl` | 26 | goal_met 14, repeats_check 12 | one annotator, 2026-09-24 |

Added after 0.2.0, each with the report that ran it:

| File | Cases | Points | Report in `docs/results/` |
|---|---|---|---|
| `benches/{loop,memory,graph-build,retrieval}-b.jsonl` | 212 | the six binary points to 50 each | `2026-09-24-fifty/`; a blind generative second annotator on the same cases |
| `benches/memory-c.jsonl`, `benches/retrieval-c.jsonl` | 125 | memory_write 50, redundant_page 75 | `2026-09-24-third-batch/` |
| `benches/graph-c.jsonl`, `benches/memory-d.jsonl` | 94 | facts 30, edge 30, memory_collision 34 | `2026-09-24-fourth-batch/` |
| `benches/memory-collision-toward-branch.jsonl` | 52 | memory_collision, built toward the branch that acts | `2026-09-24-collision/` |
| `benches/steerability.jsonl` | 28 | 14 flipped pairs | `2026-09-24-steerability/` |
| `benches/agentdojo-injection.jsonl` | 273 | injection, harvested from AgentDojo v1.2.2: 124 with a payload, 149 without | `2026-09-24-agentdojo/` |
| `benches/memory-{e,f,g}.jsonl` | 108 | memory_write, written before the `common` question was measured | `2026-09-25-window/memory.md` |
| the 50 `facts` cases, asked in three option orders | 150 decisions | option-order sensitivity of a Choice, with the shipped order re-asked the same day to separate drift | `2026-09-25-order/` |
| the 100 `memory_write` cases and the six binary points, replayed | 0 decisions | how much of the policy-model gap the policy's shape explains; Platt scaling leave-one-out | `2026-09-25-policy-shape/` |

The tool-selection and tool-window numbers are not in a `benches/` file: their cases are
AgentDojo's own tasks, replayed through its `FunctionsRuntime`, and the needed groups are
derived from the suite's ground truth rather than labelled. Their recordings are
`fixtures/tools-window.jsonl` (97 trajectories and 40 three-task sessions) and
`fixtures/parts.jsonl` (the parts-against-groups bench), reported in
`docs/results/2026-09-25-window/`; `tests/test_window_bench.py` pins the window figures
without needing AgentDojo installed. The end-to-end run with a real agent keeps its Jev
decisions in `fixtures/e2e-window.jsonl` and one row per task in
`docs/results/2026-09-25-e2e/runs-*.jsonl`.

The page and sentence selection numbers are not in a `benches/` file either. Their cases are
HotpotQA distractor questions (validation split, CC BY-SA 4.0), whose `supporting_facts` mark
the paragraphs and sentences an answer needs, so the labels come by construction. The dataset
is not redistributed: point `SANCHOPANZA_HOTPOT` at a local copy. Recordings:
`fixtures/triage-sets.jsonl`, `fixtures/chunks.jsonl` and `fixtures/chunks-confirm.jsonl`
(ten pages per question, `docs/results/2026-09-25-triage/` and `2026-09-27-chunks/`), and
`fixtures/hierarchy.jsonl` (100 pages per question, `2026-09-27-hierarchy/`). The answering
runs through the Claude Code CLI keep their sessions in `fixtures/cli/`
(`2026-09-27-answers/`); free-length replies through the CLI are not comparable with answers
through the API, and with the reply forced into one short field the path check agrees (67.0 %
against 67.7 %). Whole documents come from QASPER (test split, CC BY 4.0, not redistributed:
point `SANCHOPANZA_QASPER` at a local JSONL), recorded in `fixtures/longdocs.jsonl`
(`2026-09-27-longdocs/`, replayed with the fixed `triage_many`), with the sentence stage in
`fixtures/longdocs-sentences.jsonl`. The permission cascade's confirmation reads ATBench-Codex
(Apache-2.0, not redistributed: point `SANCHOPANZA_CODEX` at a local `test.json`); Jev's answers are
in `fixtures/cascade-jev.jsonl` and Opus 5's CLI sessions in `fixtures/cli/cascade-opus.jsonl`
(`2026-09-27-cascade-frontier/`). The fifth batch of `edge` and `facts` is
`benches/graph-d.jsonl` and `graph-e.jsonl`, recorded in `fixtures/fifth-batch/`.

The four files added in 0.2.0 replay from `fixtures/new-points-v2.jsonl` and are weaker
evidence than the first three: fewer cases per point, one sitting, and three labels revised
on the question's own criteria after the run (the revisions and their reasons are in the file
headers). `docs/paper.md` Section 5.10 reports the replay of that fixture under the shipped
policy (`memory_write` 14/16 at its derived cut, `redundant_page` 15/16, 82 of 88 on the six
binary points);
`docs/results/2026-09-24-new-points/summary.md` is the first recording of the same benches,
`fixtures/new-points.jsonl`, made under the policy in force that day.

The 298 closed-vocabulary classifications reported in the paper are not published: they are
the register of a real investigation.

## Format

```json
{"id": "rt-01", "point": "routing", "input": {"task": "...", "brief": "..."}, "expected": "light"}
```

| Point | Input keys | Expected |
|---|---|---|
| routing | task, brief | light / default / deep |
| search | query, previous, brief | cut / cheap / full |
| triage | purpose, title, url, text | keep / drop |
| citation, numeric_citation | claim, section | supported / contradicted / unsupported |
| injection | purpose, text | true / false |
| command | command | true / false |
| unsourced | task, result | true / false |
| entity | a, context_a, b, context_b | true / false |
| facts | fact_a, fact_b | agree / conflict / unrelated |
| dependency | a_title, a_goal, b_title, b_goal | true / false |
| plan | lines [{id, title, goal}], edges [[a, b], ...] | evaluated as a whole |
| classify | field, text, options, context | one option name |

## Running

```
sanchopanza bench benches/core.jsonl benches/safety.jsonl benches/graph.jsonl \
    --provider recorded --fixture fixtures/public-benches.jsonl
sanchopanza bench benches/*.jsonl --provider jev --record fixtures/mine.jsonl --out results/today
```

The first command replays the public run (`docs/paper.md` Section 5.9) from its recording, for
free. Each further bench replays from its own fixture, listed in Appendix A of the paper; a
bench replayed against a fixture that does not hold its cases is scored on defaults, not on
recorded answers. The second command is a live run that records what it asks.

The runner sends each case through the same `Squire` methods production uses, with
`allow_upgrade=True` so all three routing tiers are reachable, and reports agreement when
deciding, coverage, Wilson 95 % intervals, median latency, AUC / Brier / ECE for binary
points, agreement by confidence band, calibration by primitive, and for `plan` the raw and
cleaned precision / recall with the parallel waves against the reference.

`results.json` holds one row per case with the raw probability, so everything is
recomputable with `sanchopanza.eval.stats`.

Agreement is scored with the thresholds the policy applies, not at a plain 0.5 cut: the loop
points speak from `saturated`, injection flags only above `injection`, and
`tests/test_policy_in_force.py` checks that every scored row matches what the policy would
do. The "correct at 0.5" column, where a report shows one, measures the model's ordering and
is labelled as such.

## Quote from the recording, never from a live rerun

The provider is not deterministic across a day, even with the version pinned: the same
states asked of `jev-1.13.0` again moved by up to 0.09 within a day, enough to move answers
that sit just above a cut to just below it (`docs/results/2026-09-25-window/README.md`,
section 7). So:

- **Every published number comes from a recording** (`--record`), and a replay test pins it.
  A live rerun of the same bench is a new sample, not a reproduction.
- **A decision within about 0.1 of its cut is a coin flip between runs.** A count should say
  how many of its decisions sit that close.
- The five-repetition stability result of the paper (Section 5.5) holds within a session and
  does not extend across one.

## The rule

A threshold moves when a point has 50 cases, two annotators with reported agreement, and the
band table justifies the move, or when it is derived to a stated target on one set and
judged on another. Until then a threshold in `Thresholds` stays where it was fixed before the
September 2026 runs. Derived so far: `adds_nothing` (below); `remember` / `derivable`, one cut
of 0.54 on the weakest margin, derived on half of the 100 `memory_write` cases to an 80 %
precision target and judged on the other half and on the 108 cases of `memory-{e,f,g}`
(`docs/results/2026-09-27-memory-write-cut/`); and the HotpotQA selection cuts, among them
`pages_first_round` (0.18), each derived to a recall target on its own derivation questions.

Deriving a knob needs positives as well as cases. `Thresholds.window_add` has 13 positives in
4,268 observe answers, and no cut clears even a 50 % precision target at its Wilson lower
bound, so it stays equal to `Thresholds.tools`, with the derivation attempt written beside it
in `policy.py` (`docs/results/2026-09-25-window/README.md`, section 6). Page redundancy's
`adds_nothing` is the knob that could be derived: 0.59 to a 90 % precision target, 100 %
precision held out (`docs/results/2026-09-24-third-batch/`).

## Contributing cases

Real material beats written material; hard negatives beat easy ones; a second annotator
beats a bigger bench. Do not include identifiable private individuals. Keep the content
language: the point of these benches is that the instructions are in English and the
content is not.
