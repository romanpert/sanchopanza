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

**Handing an answering model only the top 20 or 30, in page order, chooses as well as the whole
page** (Phase 2d, registered, 82 new steps): 52.4 % and 50.0 % against 51.2 %, both within the
registered bound, at an eighth of the cost. The first try (Phase 2c) showed them in rank order
and lost 5 points; in 6 of its 7 lost steps the target was among those shown, and the fix was
the order and a note on repeated lines, not the ranking.

**A hook that prunes snapshots inside a real Claude Code session with Playwright MCP makes it 12.9 % cheaper** (Phase 3d, registered, 48 sessions on six new tasks): -0.0144 USD a session [-0.0270, -0.0025], 24 of 24 answers in both arms. It took four phases. With `playwright-cli` (Phase 3) and in its first Playwright MCP run (3b) it saved nothing, and reading the transcripts found five faults of the hook, not of the ranking: Claude Code replaces a large MCP result with a notice before any hook runs, the hook cut the agent's own searches and narrowed reads, its goal lost the user's question, and its note sent the agent to read the whole archive. With them fixed it passed on tasks it was never fixed on.

What stands is the ranking as a tool: `sanchopanza browse PAGE --goal ...` from a shell, or the
`rank_elements` MCP tool, returns the elements a step needs with their refs, confirmed at 89 % in
the top 20.

## Phase 2d: registered, passed (`prereg-present.md`, `present-confirm.json`)

Phase 2c's loss was the presentation, not the ranking. `diagnose.py` (free, replays 2c) found the
target **among the 20 shown in 6 of the 7 steps TOP lost**: two were identical lines ("View
more", an unnamed phone field) that the page's order tells apart and a ranked list does not;
three were picks from the first three rows of a list sorted by Jev's score; one picked a `div`
holding the right `span`. Only one lost step had the target outside the 20 (it was 28th).
`browse.in_page_order` now shows the kept elements in the page's order, and a line repeated on
the page says which of the alike it is and what precedes it (`2nd of 2 alike, after label "Max
price"`). `render`, and so `sanchopanza browse` and `rank_elements`, use it.

Development, on 2c's own 60 steps (seen data, claims nothing): FULL 58.3 %, PAGE20 58.3 %, PAGE30
61.7 %. Registered confirmation on the **82 Phase 1c steps 2c never used**, with 2c's rule:

| Arm | Accuracy | Minus FULL [95 %] | Right element shown | List USD / step |
|---|---|---|---|---|
| FULL (every element) | 51.2 % | | 100 % | 0.097 |
| PAGE30 (primary) | 50.0 % | -1.2 [-9.8, +7.3] | 89.0 % | 0.015 |
| PAGE20 | 52.4 % | +1.2 [-7.3, +9.8] | 86.6 % | 0.012 |

**Both pass** (difference at least -5 points, lower bound above -10); PAGE30 only just (-9.76).
Showing Sonnet the top 20 or 30 in page order chooses as well as the whole page within the
precision 82 steps allow, at an eighth of the cost. Three FULL sessions ended in a CLI exit at
no cost, as in 2c, and count as wrong. 10.12 USD at list price spent (FULL 7.94, the two PAGE arms
2.18), no Jev.

**A registration fault, stated plainly.** The runner used two harness clients (a 0.10 cap for
PAGE sessions, 0.60 for FULL), each with the registered 15 USD ceiling, so the phase as a whole
was not held to 15 by code; and each client starts from the cache's total, so its reported
`cli_spent_usd` (14.99) counts the development run twice and imputes 0.60 to each failed session.
What was spent is the sum of the sessions' own costs, 10.12 USD, within the registration.

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

## Phase 3d: registered, passed: 12.9 % cheaper on six new tasks (`prereg-e2e-mcp-new.md`)

The hook with Phase 3c's two further faults fixed (0e8f5fd: what the agent narrowed passes, and
the note points recovery at `Grep`), on six tasks it was never fixed on: a GitHub repository
(Flask), two Wikipedia infoboxes (the Eiffel Tower, Guido van Rossum), the Python `json` docs,
quotes.toscrape and a books.toscrape category. Same design and rule as 3b and 3c.

| Arm | Success | List USD / session | Turns | Cache write / session |
|---|---|---|---|---|
| PLAIN | 24/24 | 0.1114 | 4.75 | 17,673 |
| LEAN | 24/24 | 0.0954 (+0.0016 Jev) | 4.58 | 14,133 |

LEAN minus PLAIN per task: **-0.0144 USD a session [-0.0270, -0.0025]**, the whole interval below
zero; by task N1 -0.035, N5 -0.032, N3 -0.017, N4 -0.008, N6 -0.001, N2 +0.006. **The rule is
met: the hook is recommended with Playwright MCP.** 14 cuts: GitHub's 32,685-character snapshot to
about 7,100 (all four runs), a 96,917-character Wikipedia snapshot to about 9,400, one of 350,134
to 11,791 that Claude Code would have replaced with its notice. 4.96 USD at list price, 0.04 of Jev.

What it took, in order: Phase 3 (playwright-cli) and 3b (Playwright MCP) found nothing; reading
their transcripts found five faults of the hook, not of the ranking (Claude Code hides a large MCP
result behind a notice before any hook runs; the agent's own searches were cut; the goal lost the
question; narrowed reads and targeted snapshots were cut; recovery read the whole archive); 3c
measured the first three fixed on the same tasks (-8.5 %, interval crossing zero); 3d measured all
five on new tasks. Six tasks is a small sample and the interval is over six task means.

## Phase 3c: registered, 8.5 % cheaper but not yet below zero (`prereg-e2e-mcp-fixed.md`)

Phase 3b's design again, same day, with the three faults fixed (a17dc5b). The hook now acts where
it could not: 14 cuts, ten of them `browser_snapshot` results Claude Code had replaced with its
notice (72,192 characters to 11,842 on GitHub; 859,973 to 13,464 on Mount Everest).

| Arm | Success | List USD / session | Turns | Cache write / session |
|---|---|---|---|---|
| PLAIN | 24/24 | 0.1362 | 6.17 | 20,169 |
| LEAN | 24/24 | 0.1209 (+0.0037 Jev) | 6.25 | 16,183 |

LEAN minus PLAIN per task: **-0.0116 USD a session [-0.0466, +0.0154]**; by task M1 -0.090 (39 %
cheaper, all four runs), M3 -0.025, M5 -0.004, M2 +0.008, M6 +0.009, M4 +0.034. The rule
(interval below zero) **fails**; no answer was lost. 6.17 USD at list price, 0.09 of Jev.

What the transcripts of the tasks that cost more show:

- **The hook cut what the agent had already narrowed.** M4 run 1 `Read` the snapshot file with
  `limit: 150`; the hook halved that chunk, and the agent grepped twice, read the archive twice
  and fell back to `evaluate` (0.167 USD against PLAIN's 0.095). M4 run 2 asked for a snapshot of
  one element (`target: e166`, the infobox) and the hook cut that too.
- **A positional answer is not a next action.** M6 asks for the first book listed; the cut kept
  the elements to act on and dropped the first title, and in run 1 the agent then read the whole
  33,541-character archive.
- **On pages past Claude Code's limit that the agent greps (M2, M4), the cut is neutral**: without
  the hook the saved file plus one `Grep` is already cheap.

## Phase 3b: registered, no saving, and three faults found (`prereg-e2e-mcp.md`, `e2e-mcp.json`)

The same question with what most people install: Playwright MCP 0.0.83, `Read`/`Grep`/`Glob`,
no instruction about tools, six tasks on ordinary pages (a GitHub repository, two Wikipedia
articles, the Python docs, npm, books.toscrape), four runs per task and arm.

| Arm | Success | List USD / session | Turns | Snapshots cut |
|---|---|---|---|---|
| PLAIN | 24/24 | 0.1268 | 6.54 | |
| LEAN | 24/24 | 0.1255 (+0.0004 Jev) | 6.83 | 8 |

LEAN minus PLAIN per task: -0.0009 USD [-0.0185, +0.0126]; by task M1 -0.042, M2 +0.014, M3
+0.021, M4 -0.004, M5 +0.003, M6 +0.001. The rule (cheaper, interval below zero) **fails**. 6.06
USD at list price (the pilot 0.64 more), 0.01 of Jev.

Reading the transcripts found why, and none of it is the ranking:

- **Claude Code hid every large snapshot from the hook.** An MCP result past its token limit
  (72,000 characters for the GitHub page, 505,000 and 860,000 for the Wikipedia articles) is
  replaced by a notice ("exceeds maximum allowed tokens. Output has been saved to ...") **before**
  `PostToolUse` runs: a recording hook, 2026-09-30, received the 1,617-character notice, never
  the snapshot. The model then reads the saved file in chunks or greps it. The hook never cut a
  `browser_snapshot`. It cut the `.yml` files the agent `Read` (M1, M6), and on M1 that paid:
  -0.042 USD a session, a quarter.
- **The hook cut the agent's own searches.** Four `browser_find` results were pruned (M2, M3),
  and after three of them the agent read the whole archive: it pays twice. M2 and M3 are the two
  tasks where LEAN cost more.
- **The goal lost the question.** The hook ranked for `purpose_of`'s summary, which keeps the
  first 130 characters of the request; a request that opens with a URL and instructions ends
  with its question. A probe asking for the license kept 20 elements without the license link.

Fixed, each with a test (`harness/browse_hook.py`): the hook reads the saved result behind
Claude Code's notice (only from its own session's `tool-results` folder, since a page can print
a fake notice) and returns it pruned in its place, which a live probe confirmed Claude Code
accepts; `browser_find` and a browser CLI's `find` pass untouched; the goal is `browse_goal`,
the request's start and end with URLs cut to their host, plus the agent's last step. Not yet
measured again.

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

## Phase 1d: registered, failed at 20, opt-in (`prereg-hints.md`, `hints-jev-confirm.json`)

Five of the 23 development targets Jev ranked below 20 (`misses.py`) were unnamed SVG icons whose
classes said what they do (`add-wishlist-new__icon`; `save-icon-favorite` inside a "Save"
button). `elements_from_html(..., describe_unnamed=True)` adds, to an element with no name, the
useful words of its classes and the name of the element holding it. Development (169 seen steps,
0.42 USD of Jev): R@10 +3.0 [0.0, +5.9], R@20 +0.6; the wishlist and Save icons went from
outside the top 50 to 1st and 2nd. Confirmation on the 142 Phase 1c steps (0.36 USD of Jev):

| Arm | R@1 | R@10 | R@20 |
|---|---|---|---|
| BEFORE (Phase 1c) | 42.3 % | 82.4 % | 89.4 % |
| DESCRIBED | 45.1 % | 83.8 % | 88.0 % |

R@10 +1.4 [-1.4, +4.2] passes; **R@20 -1.4 [-3.5, 0.0] fails** the registered -3 bound, so the
description stays opt-in. Where it described the target (6 steps) it lifted or kept 5 (the
unnamed "$ Max" field of Phase 2c's Amy Grant step went from 6th to 1st); the two steps that fell
out of the top 20 (20th to 23rd, 19th to 26th) were ones whose target it did not touch: Jev asked
again about a group where another line changed, which is noise this design cannot separate from
the change. A cleaner test would hold every unchanged call fixed, and is not run.

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
