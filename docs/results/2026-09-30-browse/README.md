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

**A hook that prunes snapshots inside a real Claude Code session: with Playwright MCP it came out cheaper in every registered phase, with playwright-cli it rarely has anything to cut.** Registered results, each on tasks the hook was not fixed on. With Playwright MCP: 12.9 % cheaper on six tasks (3d, interval below zero), about 7 % on twelve (3f, crossing zero), 12.4 % on twelve (3h, crossing zero), 13.4 % on twelve (3j, below zero), 8 % on twelve more (3l, below zero) and 3 % on twelve more (3n, crossing zero). It pays where a large snapshot arrives inline: **17 % cheaper on twelve tasks chosen that way (3p, registered, below zero, every answer right)**; a page past Claude Code's own limit was already cheap without it. With playwright-cli: about 5 % on twelve tasks (3g, below zero) and nothing on 48 more (3i, 3k, 3m, 3o): page content is about 16 % of such a session, the agent narrows with `find` and `grep` itself, and on an output Claude Code saves both arms see 2,000 characters. It stays opt-in. Questions about position ("the first quote listed") cost answers in 3h and 3i; since they pass through uncut (or, on a saved output, come back in page order), 3j to 3m answered all 54 such runs in both arms. Every fault the phases found was in the hook, none in the ranking.

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

## Phase 3q: registered, not met: 16 % cheaper, and one table read wrong three times (`prereg-e2e-t.md`)

Eleven new inline pages that are data tables (eight from endoflife.date, IANA's status code
registry, Python's devguide, PHP's supported versions), each question one cell of one row. The
hook at 890d3f1 (a kept cell brings its whole row and the column headers). Claude Code 2.1.287
in every session (2.1.285 in 3n-3p).

| | Success | List USD / session | Cuts | LEAN minus PLAIN |
|---|---|---|---|---|
| PLAIN | 33/33 | 0.1160 | | |
| LEAN | 30/33 | 0.0962 (+0.0012 Jev) | 26 | -0.0185 [-0.0284, -0.0097] |

**The rule is not met: the cost would pass, the answers do not** (30 against at least 31). The
checks: the hook cut in 26 of 33 runs (check 1 met); LEAN used `Grep` or `Read` in 13 runs, PLAIN
in 12 (check 2 met: the row now comes with the cut); LEAN answered 30 of 33 (check 3 not met).
All three misses are T4, Django 5.2: every LEAN run answered "03 Dec 2025", the end of Active
Support, for Security Support (30 Apr 2028). What the model was shown held the header row and the
whole 5.2 row, in order and right; but the second header has no name (only a link "Python"
inside it), and with five named headers against six cells the model slid one column. Shown the
whole table, the other rows let it line them up, and PLAIN answered all three. 7.21 USD at list
price, 0.040 USD of Jev.

The fix (`_row_label`, on the `browse-row-labels` branch until merged): a row the cut brings whole
carries one YAML comment beside it pairing each cell with its header, a header with no name
named by what it holds (`# 5.2 (LTS): Release: 5.2 (LTS) | Python: 3.10 - 3.14 ... | Active
Support: ... (03 Dec 2025) | Security Support: ... (30 Apr 2028) | ...`), and none when cells and
headers do not pair up. Not yet measured on new tasks.

## Phase 3p: registered, passed: 17 % cheaper on pages whose snapshot arrives inline (`prereg-e2e-v.md`)

Twelve new tasks chosen for the claim read across 3j, 3l and 3n: each page's snapshot measured
beforehand at 11,000-75,000 characters, inline but large. Playwright MCP, the hook at 5dead40
(with the Jev position judge), three runs per task and arm.

| | Success | List USD / session | Cuts | LEAN minus PLAIN |
|---|---|---|---|---|
| PLAIN | 36/36 | 0.1270 | | |
| LEAN | 36/36 | 0.1042 (+0.0015 Jev) | 29 | **-0.0213 [-0.0334, -0.0096]** |

**The rule is met: 17 % cheaper, every answer right in both arms.** The checks: the hook cut in
27 of the 30 LEAN runs of the ten tasks that are not about position (the three it did not cut
are V7, where the agent asked `browser_find` and never took a snapshot); on V4 and V5, the two
position questions the word rule missed ("the third chapter in the tutorial's contents", "the
link right after Install"), Jev judged them a place, the hook cut none of the six runs and all
twelve answered; and the ten tasks saved -0.026 USD a session on average, half the -0.047 read
after the fact from 3j, 3l and 3n, as a confirmation on new tasks should expect. Nine of the ten
were cheaper, by 0.008-0.053 a session (V7 with nothing cut, so by chance); V9 cost +0.008: PostgreSQL's version table was cut from 14,000 to
5,400 characters and the row for version 14 was left out, so the agent `Grep`ped the archive
for it (one or two more turns, the answer right). 8.54 USD at list price, 0.055 USD of Jev.

So the hook is worth turning on with Playwright MCP when the pages a session reads give large
snapshots that still fit inline; on pages past Claude Code's limit, and with playwright-cli, it
has little to do.

## Phases 3n and 3o: twelve new tasks after the card, nearest-row and position-word fixes (`prereg-e2e-u.md`)

The hook at 4416aa4, a warm-up session first, three runs per task and arm, both tools at once.

| Tool | Success PLAIN / LEAN | List USD / session PLAIN / LEAN | Cuts | LEAN minus PLAIN |
|---|---|---|---|---|
| Playwright MCP (3n) | 36/36 / 36/36 | 0.1163 / 0.1114 (+0.0017 Jev) | 12 | -0.0033 [-0.0104, +0.0028] |
| playwright-cli (3o) | 36/36 / 36/36 | 0.1096 / 0.1116 (+0.00005 Jev) | 2 | +0.0021 [-0.0023, +0.0071] |

**The rule is not met with either tool.** With Playwright MCP the estimate is again negative (3
% cheaper; every MCP phase since 3d, six of them, has a negative estimate, three below zero), but
the interval crosses zero. The checks: infobox and cards (U1-U6) 18 of 18 in both arms with both
tools; position (U7-U9) 9 of 9 likewise; U2 ("the first ascent") was cut with Playwright MCP
(check 3 met) and never reached the hook with playwright-cli, where every run asked `find "First
ascent"`, the agent's own search, which is never cut (check 3 not met, and not for the reason it
tests). No session was NOT RUN. 8.53 and 8.36 USD at list price, 0.062 USD of Jev.

**Where it pays, read across the last three MCP phases (3j, 3l, 3n; development, not
registered).** Grouping their 36 tasks by what the hook received:

| What the hook got (LEAN) | Tasks | LEAN minus PLAIN, USD / session |
|---|---|---|
| A snapshot under 100,000 characters, inline | 6 | **-0.047** (all six cheaper) |
| A snapshot past Claude Code's limit (400,000-620,000 characters) | 8 | +0.001 |
| Nothing to cut | 22 | -0.005 |

The hook saves where the page arrives inline: there it cuts 30-40 % of a session (Y1, Y2, Z7, Z8,
U5, U10). On a page past Claude Code's limit the unhooked agent already pays little: Claude Code
saves the result and shows a notice, the agent `Grep`s the file, and the hook's 18,000 pruned
characters (13,700 in 3j, 16,700 in 3l, 17,800 in 3n, as the infobox rows and card facts were
added) cost about what the extra turn did. 3n drew four such pages and two inline ones, so its
total is small; how much the hook saves depends on how many pages a user's tasks meet that fit
inline and are large.

**Why playwright-cli leaves nothing to cut (development, the 144 sessions of 3k and 3m, `cli_cost.py`).**
Priced per turn at list rates (reproducing 15.10 of 15.24 USD): a session spends about 75 % on
Claude Code's own prefix (written once, then read back on every turn), 16 % on page content
(`find` 8.9, `snapshot` 2.4, the rest under 1.2 each) and 4 % on the model's output. Everything a
pruning hook could touch is that 16 %, and the agent already narrows with `find`; the smallest
effect 72 pairs can see is about 6 % (paired SD 0.0185 USD). U8 (+0.023) in 3o is the agent, not
the hook: in two LEAN runs it opened the category and asked for the whole snapshot, which the hook
rightly left whole (a question about the bottom of the page), where PLAIN's runs used `grep`.

## Phases 3l and 3m: twelve new tasks after the infobox and page-order fixes (`prereg-e2e-z.md`)

The hook at 0138a2d, a warm-up session first, three runs per task and arm, both tools at once.

| Tool | Success PLAIN / LEAN | List USD / session PLAIN / LEAN | Cuts | LEAN minus PLAIN |
|---|---|---|---|---|
| Playwright MCP (3l) | 36/36 / 36/36 | 0.1235 / 0.1124 (+0.0012 Jev) | 12 | **-0.0098 [-0.0219, -0.0011]** |
| playwright-cli (3m) | 35/35 / 34/34 | 0.1088 / 0.1080 (no Jev) | 9 | -0.0005 [-0.0043, +0.0032] |

**With Playwright MCP the rule is met again**, 8 % cheaper: it cut on the Nile's infobox (Z1,
-0.017 a session), the two GitHub pages (Z7 -0.026, Z8 -0.064) and the RFC (Z12, +0.005). The
infobox and position checks hold: 12 of 12 in each arm for both. **With playwright-cli the rule
is not met**, and this time the hook acted: nine page-order previews of saved outputs (the
agent's own `find` on Z4 and Z8, the position questions Z5 and Z9), the first time that path ran
end to end; no answer was lost and nothing was saved, because the agent narrows with `find` and
`grep` itself and on a saved output both arms see 2,000 characters. Z5's +0.013 is one LEAN run
that tried `snapshot | grep | awk`, was refused for approval and fetched the whole snapshot.
**The subscription's weekly limit was reached during 3m's last task:** three sessions of Z12 (run
2 LEAN, run 3 both arms) returned the limit notice instead of running; they are left out above.
Counted as recorded, 35/36 and 34/36, -0.0024 [-0.0072, +0.0022]: the same conclusion. 8.71 and
7.65 USD at list price, 0.045 USD of Jev.

## Which questions ask for a position (`benchmarks/browse/position.py`)

Phase 3l's Z2 ("in which year was the first ascent") counted as a position, so the hook left
Mont Blanc's page uncut; and the rule also read the agent's own step, where "First I'll open the
page" would have counted too. The rule now reads the request only and needs a word of listing
beside the ordinal ("listed", "table", "page", "there", "the first one"...). Written on the 66
task questions (right on all 66), then scored once on 30 goals labelled by hand and sealed
before the change (2e2cf73):

| Rule | Precision | Recall | False positives | Missed |
|---|---|---|---|---|
| 0138a2d | 0.50 | 0.80 | 12 | 3 |
| now | **0.86** | 0.80 | 2 | 3 |

A false positive only costs a saving (the page is left uncut). The three missed are worse, since a
cut can drop what was asked for: "the latest release listed at the top", "the final chapter",
"the top answer", none with an ordinal. So a second set of 24 goals was sealed (c75a1dd) before
fixing them on the first: "final", "penultimate", "top", "most recent" count as ordinals, "at
the top/bottom" counts alone, and "according to the page" is a source, not a list. Scored once
on the second set:

| Rule | Precision | Recall | Wrong |
|---|---|---|---|
| d2a6fda | 1.00 | **0.25** | 9 missed |
| now | 0.92 | **0.92** | "the final year of the war given on the page" (false positive), "the 2nd link in the sidebar" (missed) |

What the model sees (below) is unchanged by either: 173 of 239.

**The word rule does not carry to new goals; a question to Jev does**
(`benchmarks/browse/position_jev.py`, `position-jev.json`). A third set of 28 goals, sealed
(d69ce09) with an ordinal on a link, tab or card and no word of listing, and with ordinals of
time or of a name ("the final year", "last name", "top speed", "the first president"), scored
the rule at 0.30 / 0.20. Rather than add words again, one Truth question to Jev per request
(does it pick an element by its place on the page?) was written, tried on the three sets it had
seen (82 of 82, its criteria name set 3's examples, so that proves nothing), frozen with its cut
of 0.5 (6d3bbe5), and then scored once on a fourth set of 28 goals sealed after it (14085fe),
in words it does not use:

| On the fourth set | Precision | Recall | Wrong |
|---|---|---|---|
| word rule (da4711d) | 0.50 | 0.31 | 13 |
| Jev, one Truth per request | **0.93** | **1.00** | "the second-tallest building ... according to the table" (p 0.78) |

The bar fixed at the freeze was 0.85 for both. 0.002 USD of Jev for all 110 goals. The hook
uses it on the `browse-position-jev` branch (one call per request and session, cached; the
word rule without a provider), not yet in any registered phase.

## What the model sees, replayed (`benchmarks/browse/visible.py`, development)

Every large snapshot the PLAIN sessions of Phases 3-3k received (239, never touched by a hook) is
replayed through a version of the hook, ranked by BM25 (free), and scored by what Claude Code
would show the model: whether every required answer of the task is in it.

| Hook | Answer in what the model sees (239) | Saved `Bash` outputs (20) |
|---|---|---|
| none | 143 | 1 |
| a31edd3 (before 2026-10-01's fixes) | 152 | 1 |
| 07f6a72 (saved output ranked whole) | 154 | 3 |
| 0138a2d (infobox rows; page order for position and search) | 173 | 15 |
| now (nearest infobox rows first; a kept element's card) | **177** | **15** |

None of the 152 is lost. The 21 gained: 14 saved `Bash` outputs (questions about position and the
agent's own `find`, which used to pass through and show the model the first 2,000 raw
characters) and 7 MCP snapshots of infoboxes (Everest, Guido van Rossum, France) whose values are
plain text. Of the 5 saved outputs still missed, 3 do not hold the answer at all (W9) and 2 are
React's page, which BM25 misses and Jev finds. Designed on these snapshots, so it claims nothing;
Phases 3l and 3m measure it on new tasks (`visible-dev-*.json`).

**Ranked by Jev** (`visible.py score OUT --jev`, as the hook ranks; 0.25 USD of Jev a run), the
hook at 0138a2d shows the answer in 185 of 239 (`visible-dev-jev.json`), saved `Bash` outputs 17
of 20. Of the 17 snapshots it cut without the answer in view, 13 do not hold it (a step before
the page that does). The other four were two faults, fixed since: the Danube's "Length" was the
23rd of 52 infobox rows and the 3,000-character budget ran out in page order, so the rows nearest
the kept one now come first; and Y12's price "£17.44" sat beside the kept link "The Stranger" in
its product card, so a kept element now brings up to four lines that say something from its
list item, article or row (when the card has at most 24 lines; star glyphs say nothing). By BM25:
177, the four gained, none lost; three marginal cuts of T1 now pass through whole.

## Phases 3j and 3k: twelve new tasks after the saved-output and position fixes (`prereg-e2e-y.md`)

The hook at 07f6a72, a warm-up session first, three runs per task and arm, both tools at once.
Five of the twelve tasks ask for a position.

| Tool | Success PLAIN / LEAN | List USD / session PLAIN / LEAN | Cuts | LEAN minus PLAIN |
|---|---|---|---|---|
| Playwright MCP (3j) | 36/36 / 36/36 | 0.1339 / 0.1147 (+0.0013 Jev) | 10 | **-0.0179 [-0.0357, -0.0025]** |
| playwright-cli (3k) | 36/36 / 36/36 | 0.1080 / 0.1062 (no Jev) | 0 | -0.0018 [-0.0082, +0.0033] |

**With Playwright MCP the rule is met**: 13.4 % cheaper with the interval below zero. The hook cut
on the four large pages (Y1-Y4) and saved where it cut on GitHub (Y1 -0.087, Y2 -0.055 a session,
all six runs); LEAN was also cheaper on three tasks it never touched (Y8, Y9, Y12), which is noise
between sessions. It lost on Y4 (the Danube, +0.022): the cut kept the infobox's "Mouth" row,
whose header is a link, and dropped "Length 2,850 km", which is plain text the ranking never sees
and shares no word with "how long"; the agent searched the archive after reading a 16,000-character
cut. **With playwright-cli the rule is not met, and the hook did nothing**: in 36 LEAN sessions the
agent took five snapshots, all on positional tasks, which pass through, and its large outputs came
from `find` (the agent's own search, passed through by design), once chained after `open`. 3k is
in effect an A/A comparison: two identical arms differ by up to 0.03 USD on a task. The fix for
large `Bash` outputs was not exercised. Position check, both tools: no cut on Y5 and Y8-Y11, and
15 of 15 right in each arm. 9.25 and 7.81 USD at list price, 0.046 USD of Jev.

## Phase 3i: playwright-cli on the same twelve tasks: no saving (`prereg-e2e-x.md`)

| Arm | Success | List USD / session | Turns | Cuts |
|---|---|---|---|---|
| PLAIN | 36/36 | 0.1210 | 5.22 | |
| LEAN | 34/36 | 0.1218 (+0.0006 Jev) | 5.47 | 16 |

LEAN minus PLAIN per task: **+0.0014 USD a session [-0.0067, +0.0109]**; the rule **is not met**
(success is within it, cost is not). Phase 3g's saving with playwright-cli does not repeat here.
Both LEAN failures are X12, the positional question again: two runs named Steve Martin. 8.84 USD
at list price, 0.02 of Jev.

The losses on X2 (React's GitHub page, +0.031) and X4 (France, +0.032) are one fault of the hook
with playwright-cli. Past 30,000 characters Claude Code saves a `Bash` output to a file, hands the
hook only its first 30,000 characters, and shows the model the first 2,000 of the hook's reply
(probed with a recording hook, one session). So the hook ranked a prefix (128 of France's 3,569
elements), archived that prefix as the whole page, and the model saw the note and a few
navigation lines; it searched the archive, found nothing (the infobox's currency and GitHub's
language bar were past the prefix) and went back to the page. The same three LEAN sessions of X2
and run 3 of X4. X4's other two LEAN runs cut nothing and differ by the agent alone. Fixed: the
hook reads the whole saved output (from its own session's folder only), ranks all of it,
archives all of it, writes the cut to a file it names, and replies with what fits in 2,000
characters, the ranked elements first. Replayed on the two saved pages with Jev, the reply holds
Paris and the euro, and the MIT license and JavaScript 49.5 %. Phase 3k did not exercise it:
its agent took no large snapshot outside the positional tasks.

In Phase 3h, X4 run 1 and X8 run 1 cost more in LEAN with nothing cut; X1 run 2 kept the
"Languages" heading of a page whose snapshot has no percentages and the agent went for a
screenshot, while X1's other LEAN runs were cheaper than PLAIN.

**After 3h and 3i the hook does not cut for a question about position** (`asks_for_position`:
"the first one", "the 3rd book", "the last entry", but not "when did it first appear"). It cost
answers in 3h and 3i and extra turns in 3c and 3f. Measured in 3j and 3k: 30 of 30 right in each
arm, no cut.

## Phase 3h: Playwright MCP after 3f's fixes, twelve new tasks (`prereg-e2e-x.md`)

The hook at fccc06a (huge pages shortlisted before Jev; a matching heading keeps its section),
a warm-up session first, three runs per task and arm.

| Arm | Success | List USD / session | Turns | Cuts |
|---|---|---|---|---|
| PLAIN | 36/36 | 0.1289 | 5.69 | |
| LEAN | 35/36 | 0.1114 (+0.0015 Jev) | 5.39 | 25 |

LEAN minus PLAIN per task: **-0.0160 USD a session [-0.0409, +0.0044]**: 12.4 % cheaper on
average, the interval still crossing zero, so the rule **is not met**. 8.77 USD at list price
with the warm-up, 0.06 of Jev. Both fixes did their part: France's 1,001,580-character snapshot
(3,569 elements) cost 0.0075 USD of Jev instead of about 0.035; GitHub's React page saved 0.051 a
session and the Poetry several-step task 0.131.

What kept it from passing is the one fault left from 3c and 3f, and here it cost an answer:
**a question about position**. X12 asks for the author of the first quote tagged "humor"; the cut
kept the elements to act on and dropped the first quote, one run answered "Steve Martin" (the
answer is Jane Austen) and another cost 0.233 USD going back for it (X12: +0.046). Nothing in a
snapshot line says it comes first.

## Phases 3f and 3g: twelve more tasks; playwright-cli passes, Playwright MCP does not (`prereg-e2e-wide.md`, amendment)

The reviewed hook (1476d12) on twelve new tasks, five of them several steps long, three runs per
task and arm, both tools at once. Amendment 1, written before any analysis: the rule must also
hold without the first, cache-warming run (`warmup.py`).

| Tool | Success PLAIN / LEAN | List USD / session PLAIN / LEAN | LEAN minus PLAIN, all | without the warm-up run |
|---|---|---|---|---|
| playwright-cli (3g) | 35/36 / 36/36 | 0.1143 / 0.1044 | **-0.0094 [-0.0189, -0.0019]** | **-0.0058 [-0.0115, -0.0012]** |
| Playwright MCP (3f) | 36/36 / 36/36 | 0.1253 / 0.1114 | -0.0090 [-0.0321, +0.0099] | -0.0061 [-0.0257, +0.0101] |

**With playwright-cli the hook passes both versions of the rule** (5 % cheaper without the
warm-up run, 8.7 % with it); the one failure is a PLAIN run that opened the wrong book. **With
Playwright MCP it does not pass on this wider sample**: big savings on W1 (-0.088) and W9
(-0.089), losses on W2 (+0.035), W12 (+0.021), W4 (+0.017) and W7 (+0.014). 8.52 and 7.87 USD at
list price, 0.18 and 0.02 of Jev.

What the transcripts of the losing tasks show:

- **On huge pages Jev cost more than the cut saved.** W4 (Spain, 951,684 characters) and W7 (the
  tallest buildings, 561,045): LEAN's sessions were as cheap or cheaper in tokens, but ranking
  2,000-3,000 elements is 60-100 Jev calls, 0.02-0.035 USD a snapshot. Fixed: past
  `BROWSE_MAX_ELEMENTS` (600) BM25 shortlists what Jev ranks, about 21 calls at most.
- **A section the question points at lost its body.** W2 (the VS Code repository): the cut kept
  the heading "Languages" and dropped "TypeScript 95.6%" under it, a list item with no word of
  the question; the agent grepped the archive, asked for a targeted snapshot and fell back to
  `evaluate` (+0.05-0.07 a session). Fixed: a heading that shares a word with the goal (a plural
  `s` aside) brings up to 12 lines of its section.
- **A positional answer, again** (W12, the first book on catalogue page 3), as M6 in Phase 3c. Not
  fixed: nothing in a line says it is first.

Both fixes were designed on these tasks, so they are measured next on new ones.

Re-reading the earlier phases for the warm-up (`warmup.json`): 3d does not move (-0.0143
[-0.0266, -0.0025]); 3e shrinks from -0.0094 to -0.0037 [-0.0066, -0.0004], still below zero, so
its 8.6 % was mostly the first session's cache write and the honest figure is about 3 %.

## Phase 3e: registered, passed, with a caveat: playwright-cli (`prereg-e2e-cli-new.md`)

The fixed hook with `playwright-cli` (Phase 3's setup) on Phase 3d's six new tasks, four runs per
task and arm.

| Arm | Registered success | List USD / session | Turns | Snapshots cut |
|---|---|---|---|---|
| PLAIN | 20/24 | 0.1097 | 4.25 | |
| LEAN | 19/24 | 0.0999 (+0.0004 Jev) | 4.21 | 8 |

LEAN minus PLAIN per task: **-0.0094 USD a session [-0.0184, -0.0036]**; by task N1 -0.031, N5
-0.009, N2 -0.006, N4 -0.005, N3 -0.003, N6 -0.002. The rule (success at least PLAIN's minus one,
interval below zero) **is met**. Every registered failure in both arms is Phase 3's artefact: the
agent answered, closed the browser as asked, and ended on "Done - browser closed."; the grader
reads the final message only. **The caveat:** the hook cut only on N4 and N5 (quotes.toscrape
8,732 characters to about 3,350; the Poetry category about 29,000 to 5,900), yet LEAN was also
cheaper on tasks it never touched (N1 by 0.031, where one PLAIN run cost 0.231), so part of the
8.6 % is noise between sessions; what the hook itself did is on N4 and N5. 5.03 USD at list price,
0.01 of Jev.

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

## Phase 1e: registered, passed: the description is the default (`prereg-hints-reask.md`)

Phase 1d could not tell the description from the noise of asking Jev again. Phase 1e keeps
DESCRIBED as it was and builds a control, REASK, on the reading without the description, where
the 1,684 calls DESCRIBED replayed are replayed too and the other 1,045 are asked again live
(0.36 USD of Jev), so both arms carry the same noise on the same groups:

| Arm | R@1 | R@5 | R@10 | R@20 | R@30 |
|---|---|---|---|---|---|
| REASK (no description, asked again) | 41.5 % | 76.1 % | 82.4 % | 88.0 % | 90.8 % |
| DESCRIBED | 45.1 % | 76.1 % | 83.8 % | 88.0 % | 90.8 % |

DESCRIBED minus REASK: R@10 +1.4 [-1.4, +4.2], R@20 0.0 [0.0, 0.0]. **Passed: the description
is `elements_from_html`'s default.** Phase 1d's -1.4 at R@20 was the noise of asking again: the
control without any description fell to the same 88.0 %. A second look at the same 142 steps with
a better control, not a new sample.

## Phase 1d: registered, failed at 20 (`prereg-hints.md`, `hints-jev-confirm.json`)

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
the change. Phase 1e separated it.

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
