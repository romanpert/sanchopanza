# The `sources` Stop hook on free FRAMES tasks: a development pilot (80 sessions)

The selection study (`2026-10-03-browse-free`) ended on one idea it could not test offline: ask
the agent itself, at the Stop hook, to show the source of every condition of the question for its
answer, and let the model that holds the evidence do the composed judgement. `sanchopanza install
--sources` wires that hook (`sanchopanza.harness.sources_hook`): no model, no decision; at the
first Stop of a session that used the web it blocks once with the request (each condition, the URL
and the exact sentence that meets it, look for a missing one or say it is unsourced, repeat the
ANSWER line). This pilot measures it the way people use Claude Code, on tasks the earlier sets
could not supply: fresh, checkable, with mixed outcomes.

## Set-up

`benchmarks/browse/free_frames.py` (commit 9310457). FRAMES (Krishna et al., 2024), test split,
cached locally only: 20 seeded tasks with "Multiple constraints" among their reasoning types, an
answer of at most four words and two to four Wikipedia links, half with that type alone and half
with numerical or temporal reasoning as well. Only the ids are here (`frames-ids.txt`); no
question, answer or quote is written in this folder. Each session gets the question, the ANSWER
instruction and Claude Code's normal tools (`free_e2e.one_session`), WebFetch denied to the hosts
that serve the set. Four arms, interleaved by task, one run each, Claude Code 2.1.287:

| arm | model | cap (USD) | hook |
|---|---|---|---|
| SONNET | `claude-sonnet-5` | 1.50 | - |
| SONNET-SRC | `claude-sonnet-5` | 1.05 (70 %) | `sources` |
| HAIKU | `claude-haiku-4-5` | 0.60 | - |
| HAIKU-SRC | `claude-haiku-4-5` | 0.42 (70 %) | `sources` |

A -SRC cap is 70 % of its base: the calibration found a stop there costs no right answer, so the
hook's extra turn was meant to be paid out of money the base spends on wrong sessions. **20.31
USD** of subscription at list price for the 80 sessions; no 429, no session lost.

## Results (hand grades)

Every final ANSWER, and every ANSWER given before the block in the -SRC arms, was read by hand
against the gold (`free_frames_hand.py`, `frames-hand.json`). `frames.json` is the runner's
provisional report, kept as it was written.

| arm | right (hand) | right (runner) | mean / median USD | at cap | at 90 % of cap | hook fired | leaks |
|---|---|---|---|---|---|---|---|
| SONNET | **16/20** | 14 | 0.225 / 0.168 | 0 | 0 | - | 0 |
| SONNET-SRC | **16/20** | 15 | 0.344 / 0.266 | 0 | 2 | 15 | 0 |
| HAIKU | **16/20** | 14 | 0.202 / 0.130 | 0 | 2 | - | 0 |
| HAIKU-SRC | **13/20** | 13 | 0.245 / 0.190 | 5 | 5 | 18 | 0 |
| SONNET cut at 70 % | 16/20 | | 0.225 / 0.168 | | | | |
| HAIKU cut at 70 % | 16/20 | | 0.187 / 0.130 | | | | |

The cut rows replay `free_cut.cut_at` (`budget`, f = 0.7) on each base session's recorded cost
trajectory: a session that crossed 70 % of its cap before its last call counts as wrong and costs
what it had spent there. No Sonnet session reached 1.05 USD, so nothing is cut; on Haiku two are,
both wrong, and one right session crossed 0.42 only in the call that gave its answer (at 0.408
before it), so it keeps it.

**Before and after the block** (sessions where the hook fired):

| | right -> right | right -> wrong | wrong -> right | wrong -> wrong |
|---|---|---|---|---|
| SONNET-SRC (15) | 11 | 0 | 0 | 4 |
| HAIKU-SRC (18) | 12 | **1** | 0 | 5 |

**Paired by task** (exact McNemar): Sonnet, SRC against base and against base cut, 0 discordant
tasks, p = 1. Haiku, 3 tasks right in the base alone (FR187, FR633, FR524) and none in SRC alone,
p = 0.25, against the base and against the base cut alike. Of those three, one is the hook (FR187,
the right -> wrong above); FR633 never reached the hook (the SRC session spent its 0.42 cap on
fifteen searches without stopping, where the base answered at 0.30); FR524 was already wrong
before the block (the base answered it right). Counting FR187's withdrawn answer as right, HAIKU-SRC
is 14/20, 2-0, p = 0.5.

**The hook's cost, separated.** SONNET-SRC spent 0.227 USD per session before the block (the base:
0.225) and 0.116 after it: the whole difference is the hook's turn, +52 %, of which 11 of the 15
blocks went to sessions already right. HAIKU-SRC spent 0.163 before the block (less than the base
only because the lower cap truncates) and 0.082 after.

**The owner's bar** - with sanchopanza, cheaper and at least as many right as the harness without
it, model by model - is not met. Sonnet: as many right as the base cut (16), 52 % dearer. Haiku: 3
fewer right than the base cut (13 against 16), 31 % dearer (0.245 against 0.187).

### Checked twice

- **The runner's grade favoured the hook by one on Sonnet** (15 against 14); by hand it is 16 and
  16. The runner is wrong in seven of 80 sessions: one task's gold string appends a year to the
  name every arm answered (four false negatives); one Sonnet base answer names the gold career as
  the activity rather than the job title; one Haiku base answer is the gold exactly but the gold is
  made of dots and dashes, which the normaliser reduces to an empty string; and one HAIKU-SRC
  answer passes because its ANSWER line names the gold while withdrawing it (below). The last two
  cancel in the HAIKU-SRC count, so its 13 is right for the wrong reason. Its before/after matrix
  missed the one right -> wrong.
- **One gold is disputed** (FR633): the answer is computed from six figures, and two sources give
  a different value for one of them. The gold follows one; both Sonnet arms (base and SRC) followed
  the other, and SONNET-SRC said why after the block. Graded wrong, flagged. Counting it right moves
  both Sonnet arms to 17 and changes no comparison.
- **Leaks: none.** The runner marked none; a wider scan (the set's hosts and names in every tool
  input and result, main agent and subagents, all 80 sessions) finds none, and no session opened
  the browser. Sonnet answered four (base) and five (SRC) tasks with no tool call at all, all right:
  the model's own knowledge of Wikipedia facts, not a leak, and the hook never fires there.
- The hook did not fire on two HAIKU-SRC sessions that used the web: FR633 (the cap came before any
  Stop) and FR107, where the main agent delegated the research to a subagent - the hook counts web
  calls in the main transcript only, so the delegated session was never asked.

## What the agents did after the block (read by hand)

**Sonnet (15 blocks).** In every one it re-fetched the pages it cited (2 to 7 WebFetch calls) to
pull verbatim sentences, and wrote a list of conditions with URL and quote. No answer went from
right to wrong or back; four gained a caveat.
In the four wrong sessions it found and named its own weak step, and kept the answer with a caveat:
a share computed from figures it could not quote (FR370), a value on which two sources disagree
(FR633, the disputed gold), a count from lists with no official total (FR186), and an ordinal it
counted itself down a list whose post changes title partway (FR524). In all four the error is in a
step that no page states - a derivation, a choice between sources, a count, a reading of the list -
and a source per condition does not reach it.

**Haiku (18 blocks).** It opened a page in only two sessions (WebFetch, after the block in both; the
base arm never fetched a page). Its "exact sentences" come from the WebSearch tool's summary. In
seven sessions it answered the block with no new tool call (about 0.008 USD each), restating the
summaries as sources. In eleven it searched again (1 to 10 searches):

- FR187, **right -> wrong**: one condition is a score that sits in a results table Haiku never
  opened; nine more searches did not surface it in a summary, and Haiku replaced its right answer
  with an ANSWER line saying it cannot provide a fully sourced answer.
- FR370, FR368, FR186, FR524: already wrong; each searched again and ran into the 0.42 cap
  mid-check (0.66 USD after the block across the four), still wrong or with no answer.
- FR3: wrong before the block from a misreading of the moment the question anchors on; Haiku
  listed the conditions as it had misread them, sourced each correctly, and kept the wrong answer.
  The request lists conditions as the agent understood them, so it cannot catch a misreading.

## What it says, plainly

- **On these tasks the hook does not pay, on either model.** Sonnet: no grade changed in 15 blocks,
  +52 % spend. Haiku: one right answer withdrawn, four sessions pushed into the cap, none fixed.
- **The base is right in 16 of 20 on both models**, so the headroom is four tasks per model; of the
  nine wrong sessions the hook reached, asking for a source fixed none. They failed on derived
  steps (a share, a count, an ordinal), on conflicting sources (the disputed gold), on a misread
  question or two entities taken for one, and, for Haiku, on no answer within the cap.
- **What a next iteration would have to change** (not measured): never let the block cost an answer
  ("keep your best answer on the ANSWER line; list what stays unsourced above it"); count web calls
  in subagents too; stand aside when the session has spent most of its cap; and ask about the step
  no page states - each value derived, counted or chosen between sources, with the page it was read
  from opened - rather than a source per condition the agent has already met in a search summary.
  A pilot of that needs tasks where the base fails more often than one in five.
- Development, one run per arm and task, 20 tasks: a p of 0.25 is no evidence of harm by itself;
  what the pilot shows is the mechanism, read session by session.

## Pilot 2: version 2 of the hook, on twenty new tasks (80 sessions)

### What changed in the hook

`SANCHOPANZA_SOURCES_VERSION=2` (`sanchopanza.harness.sources_v2`; version 1 stays the default and
unchanged) does what the first pilot asked for:

- web calls are counted in the subagents' transcripts too (`<session>/subagents/*.jsonl`), and what
  they read counts as read;
- with `SANCHOPANZA_SOURCES_CAP_USD` set, it stands aside once the session's estimated list spend
  passes 60 % of it. The estimate prices each API call in the transcripts once at list rates and
  adds 0.022 USD per WebSearch or WebFetch for the reader those tools run, which no transcript
  shows (fitted on the first pilot's 80 sessions: 0.020-0.025 per call). On those sessions it is
  0.57 to 1.28 times the recorded spend at the stop, median 1.00;
- it blocks only on a deterministic sign of a weak reply: **number** (a number in the ANSWER line
  that no tool result and not the question shows: computed or counted), **doubt** (words such as
  likely, unclear, could not, assuming, estimate, conflicting), **no_answer** (no ANSWER line when
  the question asked for one);
- the request is new and short: keep the best answer, never withdraw it; name each step no page
  states (each value calculated, counted or chosen between conflicting sources) and check it by
  opening its page; end with the ANSWER line. The signs found are appended as the reason.

### The trigger, replayed for free on the first pilot

`free_frames_trigger.py` cuts each of the first pilot's 80 sessions at its first stop (the -SRC
arms before the block, subagents by timestamp) and runs the hook's own code on it, with the -SRC
caps (1.05 / 0.42). Graded by hand at that stop (`frames-trigger.json`). Web sessions only (71):

| arm | fires on right | fires on wrong | silent right | silent wrong | no cap check: fires right / wrong |
|---|---|---|---|---|---|
| SONNET | 0 | 2 | 12 | 2 | 0 / 3 |
| SONNET-SRC | 1 | 1 | 10 | 3 | 1 / 3 |
| HAIKU | 1 | 0 | 15 | 4 | 2 / 3 |
| HAIKU-SRC | 1 | 1 | 13 | 5 | 1 / 3 |
| all | **3** of 53 | **4** of 18 | 50 | 14 | **4 / 12** |

By sign, all arms: number 4 right / 5 wrong; doubt 0 / 9; no_answer 0 / 3. Version 1 fired on 33
of the 35 -SRC sessions with web calls, 24 of them right. The signs alone separate well (4 of 53
right sessions, 12 of 18 wrong ones); **the 60 % cap check takes out 8 of those 12 wrong fires**,
because the wrong sessions are the expensive ones. One adjustment was made after looking: "about"
and "around" were left out of the doubt words (prepositions in right answers); nothing else was
tuned. The six wrong sessions no sign reaches are a misread question (FR3, both Haiku arms), an
ordinal counted down a list into a name (FR524, three arms) and a session with no stop (FR633).

### Set-up

`free_frames2.py`: twenty FRAMES test tasks drawn (seed 20261006) from the 240 with an answer of at
most four words and three or more reasoning types or four or more Wikipedia links, none of the
first pilot's, by metadata only (`frames2-ids.txt`). Same arms, caps, deny rules, pinned Claude
Code 2.1.287 and runner as pilot 1; the -SRC2 arms get the hook with `SANCHOPANZA_SOURCES_VERSION=2`
and their cap in `SANCHOPANZA_SOURCES_CAP_USD`, through each session's `--settings`. The runner's
grader now passes a gold with a year or a parenthesis appended and a gold of symbols alone (the
first pilot's misses). Smoke of two -SRC2 sessions (0.77 USD; the hook fired in both), then the
80 sessions: **19.59 USD**, 20.36 with the smoke, at list price on the subscription, under a 32
USD ceiling that counted the smoke. No 429, no session lost, no leak (runner and wide scan).

### Results (hand grades, `free_frames2_hand.py`, `frames2-hand.json`)

| arm | right (hand) | right (runner) | mean / median USD | at cap | hook fired | fired on right / wrong | silent: over 60 % of cap |
|---|---|---|---|---|---|---|---|
| SONNET | **16/20** | 15 | 0.281 / 0.145 | 0 | - | - | - |
| SONNET-SRC2 | **15/20** | 15 | 0.280 / 0.198 | 1 | 6 | 4 / 2 | 1 |
| HAIKU | **15/20** | 13 | 0.230 / 0.147 | 1 | - | - | - |
| HAIKU-SRC2 | **15/20** | 14 | 0.189 / 0.150 | 1 | 3 | 0 / 3 | 4 (1 with a sign) |
| SONNET cut at 70 % | 16/20 | | 0.264 / 0.145 | | | | |
| HAIKU cut at 70 % | 13/20 | | 0.211 / 0.147 | | | | |

**Before and after the block** (hand): SONNET-SRC2 right -> right 4, wrong -> right **1**, wrong ->
wrong 1, right -> wrong 0; HAIKU-SRC2 wrong -> right **1**, wrong -> wrong 2, right -> wrong 0. The
two fixes are the same task (FR363) on both models: a difference computed from a figure the agent
had wrong; asked to check the computed step, each opened the page, found the right figure and
gave the gold. No answer was withdrawn and no session was pushed into its cap by the block. The
block cost 0.046 USD per Sonnet session of the arm (0.92 in all; version 1 cost 0.116 per session
on pilot 1) and 0.008 per Haiku session.

**Paired by task** (exact McNemar): Sonnet, SRC2 against base and against base cut, 2 tasks right in
the base alone (FR139, FR55) and 1 in SRC2 alone (FR2), p = 1. Haiku, against the base 1-1 (FR347;
FR774), p = 1; against the base cut 1-3 (FR347; FR139, FR774, FR142), p = 0.625. None of these
discordant tasks is the hook's doing: in all of them the answer at the first stop already decided
the grade (FR139 and FR347: silent over 60 % of the cap; FR55, FR142: no sign; FR2 and FR774 right
in SRC2 before any block).

**Runner against hand**: wrong in 4 of 80, all false negatives - initials run together, a leading
article in the gold, the law under its short name, and two items named with a third as the cause
of death. No gold disputed.

**The owner's bar** (cheaper and at least as many right, model by model): Haiku meets it against
the base (15 = 15, 0.189 against 0.230) and against the base cut (15 against 13, 0.189 against
0.211); Sonnet does not (15 against 16, 0.280 against 0.264 cut). With 20 tasks and one run, p = 1
both ways: the arms differ by run-to-run variance in tasks the hook never touched.

### What it says

- **Version 2 does what version 1 did not**: 9 blocks in 40 sessions instead of 33, 5 of them on
  wrong answers, 2 fixed (the same computed step, both models), none harmed, none pushed into the
  cap; 0.046 USD per Sonnet session of the arm against 0.116 (each block still costs about 0.15).
- **The number sign over-fires on Sonnet**: 4 of its 6 blocks went to right sessions where Sonnet
  had computed a right number (a sum, a span of years) from operands on a page. Doubt and no_answer
  never fired on a right session in either pilot.
- **Most wrong answers carry no sign**: of the 10 wrong -SRC2 sessions, 5 were never asked - two
  stood aside over the cap (one with a sign), two had no sign (a law named for the wrong case, an
  extra item in a list), one hit the cap before any stop. They fail on the entity or the reading,
  which no deterministic sign of the reply sees.
- **The tasks were not much harder**: the metadata filter left the base at 16 and 15 of 20.

### Next fix (not measured)

Quiet the number sign when the reply shows the arithmetic and every operand of it is in a tool
result (the four right Sonnet blocks), so it fires on a number whose source step is missing; and
replay the 60 % cap share against 0.8 for free before moving it, since on pilot 1 it silenced 8 of
12 wrong fires.

## v2.1 offline: the number sign with shown work, and the cap share, on both pilots (160 sessions)

### What changed in the hook

Version 2 runs as measured unless one of two new settings is set (`sources_v2`, `sources_work`):

- `SANCHOPANZA_SOURCES_SHOWN_WORK=1`: the number sign no longer counts a number in the ANSWER
  line that the reply computes in writing (`a - b = c`, `a + b + c = d`, `a / b = c%`), when the
  arithmetic is right to the precision written and every operand is a number some tool result
  (main agent or subagents) or the question shows, or the result of another such step. No model:
  a regular expression for the steps and an evaluator for + - x /.
- `SANCHOPANZA_SOURCES_CAP_SHARE`: the share of the cap past which the hook stands aside (0.6
  when unset or not a share in (0, 1]).

### The replay

`free_frames_variants.py` cuts all 160 sessions of the two pilots at their first stop, as
`free_frames_trigger.py` did for pilot 1, and runs the hook's code with each variant; grades are
the hand grades at that stop. A session reaches a stop unless it ended at its cap without one or,
in a base arm, spent more than the -SRC cap (1.05 / 0.42), which a -SRC session would have hit
first. On the 40 -SRC2 sessions the replay of v2 at 60 % fires exactly where the live hook fired
(40 of 40). Output: `frames-variants.json` (ids, booleans, sign names, dollars).

The bound on the gain is deliberately generous: every block on a wrong session fixes it at pilot
2's rate (2 of 5) and no block harms (0 of 9 on pilot 2). Each block is priced at what pilot 2's
blocks cost after the block: 0.154 USD on Sonnet, 0.056 on Haiku (the 0.046 and 0.008 per session
of the arm, divided by 6 and 3 blocks in 20 sessions).

80 sessions per model (both pilots, base and hook arms; the same task appears four times, so these
are not 80 independent draws). Sonnet: 63 with a web call, 18 wrong at the stop. Haiku: 80 and 21.

| variant | Sonnet fires right / wrong | wrong tasks reached | bound, right per 100 | USD per session | USD per right answer | Haiku fires right / wrong | wrong tasks reached | bound, right per 100 | USD per session | USD per right answer |
|---|---|---|---|---|---|---|---|---|---|---|
| v2, 60 % (as measured) | 9 / 7 | 5 | +3.5 | 0.031 | 0.88 | 3 / 5 | 4 | +2.5 | 0.006 | 0.22 |
| v2, 80 % | 10 / 9 | 6 | +4.5 | 0.037 | 0.81 | 4 / 7 | 5 | +3.5 | 0.008 | 0.22 |
| v2, no cap check | 10 / 10 | 6 | +5.0 | 0.038 | 0.77 | 4 / 8 | 6 | +4.0 | 0.008 | 0.21 |
| v2.1, 60 % | 7 / 4 | 3 | +2.0 | 0.021 | 1.06 | 0 / 4 | 3 | +2.0 | 0.003 | 0.14 |
| v2.1, 80 % | 8 / 6 | 4 | +3.0 | 0.027 | 0.90 | 0 / 5 | 3 | +2.5 | 0.004 | 0.14 |
| v2.1, no cap check | 8 / 7 | 4 | +3.5 | 0.029 | 0.82 | 0 / 6 | 4 | +3.0 | 0.004 | 0.14 |
| v2 + list (exploratory), 60 % | 22 / 9 | 7 | +4.5 | 0.060 | 1.32 | 5 / 5 | 4 | +2.5 | 0.007 | 0.28 |

**Why a wrong session is not asked** (v2 at 60 %): Sonnet, 7 of 18 asked; 6 carry no sign, 3 are
past 60 % of the cap, 2 reach the cap with no stop. Haiku, 5 of 21 asked; 7 no sign, 6 no stop, 3
past the share. With no cap check at all the hook reaches 10 of 18 and 8 of 21: the largest loss
is the wrong answer with no sign in the reply, then (Haiku) the session that never stops.

### What the replay says

- **Shown work quiets the right blocks and loses the only fix.** It silences 2 of Sonnet's 9
  right fires and all 3 of Haiku's, but also the wrong fires on FR363 on both models, the one task
  where a block fixed an answer in pilot 2: there the wrong operand was on a page (a search
  tool result carried the wrong figure), so "every operand is on a page" holds for a wrong answer
  too. Of the four right Sonnet blocks of pilot 2 it quiets one (FR2); the other three rest on a
  number no tool result shows at all (a year or a count the model supplied from memory), which the
  rule cannot reach and the sign is right to flag. Its cost per right answer looks lower in the
  table only because the table applies pilot 2's fix rate, which came from the task it no longer
  reaches. **Not adopted: `SHOWN_WORK` stays off by default.**
- **Moving the cap share from 0.6 to 0.8** adds 2 wrong fires per model (FR370 and FR186 on Sonnet,
  FR370 and FR686 on Haiku: three tasks) and 1 right one. The extra blocks land on sessions between 60 % and 80 % of their cap, where
  version 1's extra turn pushed four Haiku sessions into the cap; that risk is not measured. The
  default stays 0.6.
- **One more sign for a wrong entity or an extra item: none that is deterministic and simple.**
  The wrong sessions with no sign are a misread anchor or a character taken for an actor (FR3,
  FR774), the wrong alumnus or the wrong case (FR368, FR142), an ordinal counted down a list
  (FR524), a count that happens to match a number on a page (FR347), and one item too many in a
  list (FR55). Tried on all 160: an ANSWER line of three or more items fires on 16 right and 2
  wrong Sonnet sessions and on 2 right and 5 wrong Haiku ones, whose wrong hits are four tasks,
  two sessions of them FR55; a proper name in the answer that no tool result shows fires on 10
  right and 2 wrong Sonnet sessions and 1 wrong Haiku one; an ordinal or "how many" in the question does not separate
  (6 right / 6 wrong and 8 / 6 on Sonnet). The list sign is in the table as exploratory and is not
  wired: on Sonnet it more than doubles the right fires, on Haiku it adds no wrong one at 60 %.
- **Over-fitting.** The fix rate rests on one task (FR363, both models). Each variant reaches 3 to
  7 wrong tasks per model, and the gain from 0.8 or from the list sign comes from one or two
  tasks. None of these rows is evidence that the variant pays; they bound what it could pay.

### Against the bar (cheaper and at least as many right as Claude Code alone, model by model)

- **Sonnet: out of reach on price for every variant.** The hook adds 0.021 to 0.038 USD per
  session; the -SRC cap at 70 % saves 0.009 per session against the base (the cut replay: 0.000 on
  pilot 1, 0.017 on pilot 2, on a base mean of about 0.25). The gain bound is +2 to +5 right
  answers per 100 sessions, under one task per 20.
- **Haiku: cheaper, but the gain is below the noise.** The hook adds 0.003 to 0.008 USD per
  session, under the 0.017 the cap saves (0.015 on pilot 1, 0.019 on pilot 2). The bound is +2 to
  +4 per 100 sessions, against a cap cut that loses 2 of 40 right Haiku answers in replay (pilot 2;
  none on pilot 1) and run-to-run differences of two or three tasks in 20 between arms that the
  hook never touched. Pilot 2 met the bar on Haiku; nothing here says it would again.
- **Where the price is.** On both pilots about half of the Sonnet base arms' spend is billed to
  Haiku: the readers that WebSearch and WebFetch run (2.20 of 4.51 USD on pilot 1, 2.71 of 5.62
  on pilot 2; 160 searches and 61 fetches in 40 sessions). That cost does not depend on telling a
  right answer from a wrong one.

## Substitution: fetch by passages

The last line above names where the money is. This section asks whether a deterministic tool can
take the place of one of those readers: `fetch_passages` downloads the page itself, cuts it into
chunks under their headings and returns the ones BM25 ranks highest for the purpose the agent
declares, with no model at all (`sanchopanza.webpage`, `sanchopanza.harness.fetch_tool`, reusing
the package's one BM25 in `sanchopanza.text`). What Indagis learned applies: once the reader is
gone, the model that asked reads what arrives at its own price, so the tool must hand over little
and good text.

### Phase A: where the readers' money goes (free, `free_fetch_offline.py`, `fetch-offline.json`)

Per session, the readers' cost is `modelUsage` less the transcript's own calls priced at list
rates; it is split between WebSearch and WebFetch by least squares on their call counts (no
intercept; the 18 sessions with no web call have no gap). Only WebFetch calls that returned 200
count.

| sessions | per WebSearch | per WebFetch (200) |
|---|---|---|
| FRAMES, both pilots (160) | 0.0227 USD (0.010 fee + 0.0127 tokens) | **0.0241 USD** |
| search-only sessions (138) | 0.0231 | - |
| calibration, AssistantBench and BrowseComp (60) | 0.0240 | 0.0067 |

The calibration's fetches are cheaper: a third of them are JSON APIs, some of which Claude Code
returned raw with no reader, and its pages are shorter.

| FRAMES arms | sessions | list USD | readers | searches -> USD | of it, the fee | fetches (200) | fetch readers (share of spend) |
|---|---|---|---|---|---|---|---|
| SONNET (both pilots) | 40 | 10.12 | 4.91 | 160 -> 3.63 | 1.60 | 54 | **1.30 (12.9 %)** |
| SONNET-SRC + SRC2 | 40 | 12.47 | 6.21 | 153 -> 3.48 | 1.53 | 131 | 3.16 (25.3 %) |
| HAIKU (both pilots) | 40 | 8.63 | 6.36 | 279 -> 6.34 | 2.79 | 0 | 0 |
| HAIKU-SRC + SRC2 | 40 | 8.68 | 6.33 | 272 -> 6.18 | 2.72 | 9 | 0.22 (2.5 %) |

- **WebSearch** is most of the readers' money (36 % of the Sonnet base spend, 73 % of Haiku's)
  but has no deterministic substitute here: replacing it needs a search backend, and the 0.010
  USD fee alone is 16 % of the Sonnet base spend. Out of scope for this phase.
- **WebFetch** is a lever on Sonnet only: 12.9 % of the base arms' spend at most, 25 % in the
  -SRC arms (the hook made them reopen pages). Haiku almost never fetches (9 pages in 80 sessions).
- **Break-even.** A result enters the context once as a 1-hour cache write (what Claude Code
  writes, measured on pilot 2) and is read again by every later call of that agent (4.16 later
  calls per fetch, mean). On Sonnet that is 4.0 + 0.2 x 4.16 = 4.83 USD per million tokens, so a
  fetch's 0.0241 buys about **5,000 tokens** of passages beyond the reader's summary (140 tokens,
  mean); on Haiku about 9,900.

### Phase A: what the tool would have returned (free, same script)

Every WebFetch of the FRAMES sessions that returned 200 and whose URL still serves HTML today (187
of 194; each URL downloaded once and cached outside the repository), cut by `sanchopanza.webpage`
for the `prompt` the agent gave WebFetch, against the reader's summary in the transcript. Gold:
the task's answer under the grader's rule; facts: the numbers and capitalised names of the summary
that are on the page. Tokens are characters / 4.

| | tokens, mean (p90) | gold, of the 71 pages that hold it | summary facts kept, of 2,509 | net USD per fetch on Sonnet | fetches that lose money |
|---|---|---|---|---|---|
| reader's summary | 140 | 22 | (all) | - | - |
| whole page as clean text | 4,266 (8,558) | 71 | 2,509 | 0.0044 | 41 |
| passages, 4,000 characters | 843 (1,021) | 55 | 1,942 | 0.0208 | 0 |
| **passages, 8,000 (default)** | **1,467 (2,036)** | **67** | **2,347 (94 %)** | **0.0179** | **0** |
| passages, 16,000 | 2,317 (4,008) | 68 | 2,452 | 0.0140 | 4 |

At the default the passages hold the gold three times as often as the summary (67 against 22),
in every page where the summary had it, at under a third of the break-even size, and save 74 % of
the reader's cost per fetch. The whole page as clean text is already far smaller than what the
reader is fed (WebFetch's Markdown keeps every link), but a long page wipes out the saving. One
rule was set after looking at a live page: the lead kept first is the first chunk of 200
characters or more (a skip link is not a lead); it moved the gold from 66 to 67. The calibration's
54 HTML fetches are weaker ground (the gold is on 6 pages; the summary had it in 3, the passages
in 4, but they miss 2 of the summary's 3; 0.0023 USD net a fetch, because its reader was cheap).

The replay measures what reaches the agent, not what the agent then does: whether it opens fewer
or more pages with passages than with summaries is a question for live sessions.

### Phase B: the tool and the hook

- `sanchopanza fetch-mcp`: an MCP server, `sanchopanza-fetch`, with one tool,
  `fetch_passages(url, purpose, budget=8000)`. Standard-library download, http and https only,
  every address the host resolves to must be public (no loopback, private, link-local or metadata
  address), each redirect checked again, 6 MB and 20 s limits, `SANCHOPANZA_FETCH_DENY_HOSTS` for
  hosts never fetched. A page is kept 15 minutes, so a second purpose on it costs no download. A
  PDF or other binary page is not read: the reply says to WebFetch it. No model; Jev is not needed.
- `sanchopanza install --fetch` wires `sanchopanza fetch-hook` on `PreToolUse` WebFetch (owned by
  the flag, like the others) and prints the `claude mcp add` line for the server. The hook denies a
  URL's first WebFetch in a session with one line naming the tool, and lets a second WebFetch of
  the same URL run (a PDF, a page that needs a browser, a session without the server). Off by
  default.
- The page's text reaches the main model with no reader in between; `--scan-content` with the tool
  among the content tools is the existing control for that.

### Smoke: two live sessions (Sonnet, 1.50 USD cap each, 0.70 USD)

The two FRAMES tasks whose SONNET base sessions fetched the most pages and were right (FR347,
FR139), one run each with the pilots' runner and Claude Code 2.1.287, the server in the session's
MCP config and the hook in its `--settings` (`free_fetch_smoke.py`). Graded by hand.

| task | right (base / fetch) | list USD (base / fetch) | Haiku USD (base / fetch) | Sonnet USD (base / fetch) | calls (base / fetch) |
|---|---|---|---|---|---|
| FR347 | yes / yes | 0.582 / 0.342 | 0.392 / 0.048 | 0.190 / 0.294 | 3 searches, 10 fetches / 2 searches, 2 denied, 2 passages |
| FR139 | yes / yes | 0.451 / 0.360 | 0.243 / 0.136 | 0.208 / 0.224 | 9 searches, 4 fetches / 6 searches, 2 denied, 2 passages |

The path works end to end: the server starts, the hook denies, the agent loads the deferred tool
with ToolSearch and calls it (once with a budget of its own, 12,000 characters), no fallback to
WebFetch was needed, no leak. The deny costs one round trip per batch of fetches and a ToolSearch.
Two sessions on trajectories unlike their base runs measure nothing: the base FR347 spent most of
its money opening ten pages.

### What it says

- The offline margin is real on Sonnet, on HTML pages: about 0.018 USD a fetch, at most a tenth of
  a Sonnet session's spend at the pilots' rate of fetching, with the answer reaching the agent
  more often than through the reader. On Haiku there is nothing to save, because it almost never
  fetches; its money is WebSearch.
- Not measured: whether sessions open more or fewer pages with passages, and what the deny's
  extra round trip costs over a session. Loading the tool up front (`alwaysLoad`) would remove the
  ToolSearch.

## Fetch pilot: fetch by passages in free sessions, Sonnet and Haiku (80 sessions)

### Set-up

Twenty FRAMES test tasks none of the earlier pilots ran, chosen by metadata alone (an answer of at
most four words and three or more Wikipedia links, so the question touches more pages; seeded;
`fetch-pilot-ids.txt`). The first pilots' runner otherwise: the question and the ANSWER line,
Claude Code 2.1.287 with its normal tools, Bash denied, WebFetch denied to the hosts that serve the
set. Four arms, interleaved by task: SONNET and SONNET-FETCH (cap 1.50 USD each), then HAIKU and
HAIKU-FETCH (0.60 each), the Haiku pair only because the Sonnet pair left room under the 20 USD
ceiling. A -FETCH arm adds the `sanchopanza-fetch` server and `fetch_hook` through the session's
own MCP config and `--settings` (`free_fetch_pilot.py`). Same cap within a model: the question is
the same answers for less, not a tighter budget. Hand grades in `free_fetch_pilot_hand.py` and
`fetch-pilot-hand.json`; the runner's report in `fetch-pilot.json`.

The server is registered with `alwaysLoad`. Checked for free before any session: Claude Code's
first request, captured on a local endpoint that answers 400, offers `fetch_passages` with its
schema and not behind ToolSearch when the key is set, and does not offer it without the key
(`--check-load`). With tool search on, WebSearch and WebFetch themselves are deferred, so in a
-FETCH arm the page tool is the only web tool the model sees at the start. `install --fetch` now
prints the `claude mcp add-json` line with the key.

### Results (hand grades)

| arm | right | mean USD | median USD | readers USD / session | WebSearch | WebFetch (denied, back) | fetch_passages (unread) | passage tokens / read | ToolSearch |
|---|---|---|---|---|---|---|---|---|---|
| SONNET | 19/20 | 0.175 | 0.117 | 0.072 | 57 | 10 (-, -) | - | - | 18 |
| SONNET-FETCH | 19/20 | 0.105 | 0.110 | 0.034 | 30 | 0 (0, 0) | 3 (0) | 1,992 | 12 |
| HAIKU | 16/20 | 0.147 | 0.101 | 0.104 | 92 | 1 (-, -) | - | - | 22 |
| HAIKU-FETCH | 16/20 | 0.147 | 0.081 | 0.074 | 61 | 2 (2, 0) | 79 (7) | 1,833 | 10 |

Readers: `modelUsage` less the transcripts' own calls at list rates (the Haiku inside WebSearch
and WebFetch). 80 sessions, 11.49 USD, plus 0.23 for two smoke sessions. No leak (the wider scan:
0 of 80). Five verdicts differ from the runner's (the gold's yes and its item without a detail
the gold adds, three times; a number without its unit, twice); one gold is disputed and left as it
is (FR502: the question reads two ways, and both Sonnet arms gave the other reading's item).

Paired by task, exact McNemar: Sonnet 0 against 0 (p = 1); Haiku 3 against 3 (p = 1).

### Read by hand: every number that favours FETCH, every FETCH miss

- **Sonnet's lower mean is one session.** On FR644 the base ran a subagent through 28 searches and
  7 fetches (1.43 USD); the -FETCH session answered from memory with no tool (0.05). Without that
  task the means are 0.109 and 0.108 and the readers 0.036 and 0.035 a session. Sonnet answered
  6 (base) and 7 (-FETCH) tasks with no tool at all; on the 13 tasks where both arms used the web,
  12 right each, mean 0.135 against 0.137. The tool was called in one Sonnet session (FR314: three
  pages, no search, right, 0.105 against the base's 0.146), and Sonnet never reached for WebFetch,
  so the hook never fired. On these tasks Sonnet searches and stops: there was little reader money
  to take.
- **Haiku changes how it works.** With the page tool loaded and search deferred, Haiku opened pages
  in 16 of 20 sessions and in 11 never searched: it guessed the Wikipedia URL. Those 11 cost 0.89
  against 1.08 USD and got 9 right against 10; without FR31 (below) 0.56 against 0.98. The 5
  sessions that mixed search and pages cost 1.18 against 0.49 (FR231 hit the cap in a 16-search
  loop the page tool did not cause; FR502 searched 8 times). The -FETCH session was cheaper on 13 of
  20 tasks (median paired difference -0.022 USD), and the arm's total equal to the base's (2.94 and
  2.95): the passages move money from the reader to the main model (0.073 against 0.044 a session
  outside the readers).
- **Haiku's three gains.** FR419 is the tool's: the passages of two pages led, link by link, to
  what the question asks for, where the base settled on a guess from search snippets. FR285 is not
  (no page fetched; the base looped through 23 searches into the cap). FR502 is mostly not (the
  answer came from searches and from reading the question the gold's way, not from the one page
  read).
- **Haiku's three losses.** FR450: no search, two guessed pages, passages that held what it
  needed, and a wrong step in the date logic (it took the event after the one the question anchors
  on). FR110: on one page, for a purpose that named a section, the passages kept the section's
  heading and a reference title but not the prose sentence or the table row that state the fact;
  a second page stated it too, and the agent answered no. FR644: no page fetched, a 21-search loop
  to a wrong answer (noise).
- **A loop the tool makes cheap.** FR31: 28 pages, one per candidate of a list, about 50,000
  tokens of passages, 0.334 USD against the base's 0.099 for three searches; right in both.
- Wikipedia pages under the budget come back whole, with the language list, "Jump to content" and
  "[edit]" marks (FR314, FR110): words the agent pays for and BM25 can rank.

### Against the bar (cheaper and at least as many right as Claude Code alone, model by model)

- **Sonnet: not met.** Same answers; the cost difference is one session that did not use the tool.
  On these tasks Sonnet fetches too little for the tool to matter (10 WebFetch calls in 20 base
  sessions, 7 of them in FR644).
- **Haiku: not met.** Same answers (3 against 3, two of each side not the tool's doing) and the same
  total; the median session is 20 % cheaper because Haiku trades searches for pages, but a page
  loop (FR31) and a wrong guessed page (FR450) give it back. Phase A said Haiku had nothing to save
  on fetches; live, the tool did not save on fetches but replaced searches, which is where Haiku's
  money is.

### Next fix (not measured)

From the misses, in order:

1. Section-aware passages: when a heading matches the purpose (a table of works, a list), keep
   that section's rows together, and do not let a heading or a reference title stand in for
   the body (FR110).
2. Strip a page's chrome before cutting: language lists, skip links, edit marks (FR314, FR110).
3. A fetch budget per session for the small model: past N pages with no search, the tool's reply
   says to search first (FR31, and the guessed page of FR450). The pages-instead-of-searches
   pattern is the lever on Haiku, so it is worth keeping and bounding, not removing.

## fetch v2: passages by sections, chrome stripped, a page budget (Haiku, 40 sessions)

### What changed (behind settings; version 1 stays as measured)

- `SANCHOPANZA_FETCH_VERSION=2` (`sanchopanza.webpage_v2`, used by `fetch_passages`): an element
  whose role, id or class names navigation, a menu, a language list, a skip link, an edit mark, a
  navigation box, a category list or a citation mark is dropped with its contents before the page
  is cut, and so are left-over `[edit]` and `[12]` marks; a heading carries its parents
  (`Filmography > Television`); a table cut into pieces repeats its header row; a section whose
  heading shares a word with the purpose is kept together up to three quarters of the budget (its
  first chunk and its best chunks when it does not fit), so a heading never stands in for its body;
  references, notes, external links and further reading only when the purpose names them; a 404
  says the address may be a guess and to search first; a disambiguation page says so.
- `SANCHOPANZA_FETCH_MAX_PAGES=N` (`fetch_hook`, on `PreToolUse` WebSearch and `PostToolUse`
  `fetch_passages` and WebFetch): pages since the session's last search are counted, and from page
  N + 1 on one line after each page says to search first. It never blocks. Off when unset. Not
  wired by `install --fetch` until it is measured to do something.

### Offline: version 1 against version 2 on the same pages (free, `free_fetch_offline.py`)

| pages | calls | gold on the page | tokens v1 mean / median / p90 | tokens v2 | gold v1 | gold v2 | v1 only / v2 only |
|---|---|---|---|---|---|---|---|
| WebFetch pages of both FRAMES pilots, 8,000 characters, the WebFetch prompt as purpose | 187 | 71 | 1,467 / 1,826 / 2,036 | 1,313 / 1,407 / 2,044 | 67 | 62 | 5 / 0 |
| `fetch_passages` calls of the fetch pilot, each with its own purpose and budget (`--collect-pilot`) | 75 | 50 | 1,800 / 1,960 / 2,042 | 1,702 / 1,953 / 2,062 | 28 | 24 | 6 / 2 |

Read by hand, every one of the 11 v1-only matches is the gold string inside a reference entry, a
citation mark (`[1]` against a gold of 1), a language count, a maintenance or browser notice, or a
table of a reference section: none is the page's text about the subject. The two v2-only matches
(FR31) are the name in an infobox row and in a lead. The automatic gold count punishes version 2
for dropping noise; it found no real loss. One real loss came up and was fixed before the live
run: a "See also" list was the only place a gold stood (FR248), so "See also" stays in.

FR110, by hand: the table row that states the fact is on two of the pages the session read.
Version 1 gave it on neither (one page's table cut before it, behind 46 language names; on the
other, the Filmography heading with no body, the case this fix was for). Version 2 gives it on
both, each actor's filmography whole under its subsection headings; 2,390 -> 2,522 and 2,391 ->
1,810 tokens. The first page now fits whole: 9,902 characters of text against 19,704.

### The page budget, replayed for free (`--replay-budget`, `fetch2-budget-replay.json`)

The hook's own `handle` over the web calls of the fetch pilot's 40 -FETCH sessions. N of 7 or less
notes FR419 (8 pages in a row: the tool's one gain) and, below 5, more right sessions; N = 8 notes
only FR31 (the 28-page loop: 20 pages) and the last page of FR110; 9 and above, FR31 alone. N = 8.

### Set-up

Twenty FRAMES test tasks none of the earlier pilots ran (frames, frames2, fetch pilot), drawn by
metadata alone as in the fetch pilot with a new seed (`fetch2-pilot-ids.txt`). HAIKU (Claude Code
alone) against HAIKU-FETCH2 (the server at version 2, `alwaysLoad`, the WebFetch deny, the page
budget at 8), interleaved by task, cap 0.60 USD a session in both, a hard ceiling of 10 USD in
code, settings only through the session's `--settings` and MCP config, Claude Code 2.1.287 pinned
first on the PATH of the run (`free_fetch2_pilot.py`). Checked for free before any session: the
first request offers `fetch_passages` up front (`--check-load`), and a session against a scripted
local Messages endpoint, with the budget at 0, sends the page's passages and the budget's line in
the request after the tool result (`--check-note`). Started outside the session (WMI, a new
process group) at 17:37, ended at 18:05; no 429, no weekly limit. 40 sessions, 5.81 USD.

### Results (hand grades, `free_fetch2_pilot_hand.py`, `fetch2-pilot-hand.json`)

| arm | right | mean USD | median USD | readers USD / session | WebSearch | fetch_passages (unread) | passage tokens / read | page-budget lines | 404 lines | disambiguation lines | hit the cap |
|---|---|---|---|---|---|---|---|---|---|---|---|
| HAIKU | 15/20 | 0.177 | 0.098 | 0.129 | 97 | - | - | - | - | - | 2 |
| HAIKU-FETCH2 | 16/20 | 0.114 | 0.055 | 0.052 | 31 | 92 (6) | 1,240 | 34 (one session) | 3 | 14 (12 wrong) | 1 |

Three verdicts differ from the runner's: the gold's number in digits (FR444), without its unit
(FR321), and in digits where the question asks for words (FR30, a judgement call: 15/20 if it is
counted wrong). Paired by task, exact McNemar: 2 against 1, p = 1 (2 against 2 with FR30 wrong).
No leak (the wider scan: 0 of 40). Same tasks for both arms; there is no version 1 arm, so this
pilot does not separate version 2 from the task mix (the fetch pilot ran other tasks).

### Read by hand: every number that favours FETCH2, every FETCH2 miss

- **The mean is helped by two base loops.** On FR444 the base ran 22 searches into the cap with no
  answer (0.675); on FR1, 16 searches to a wrong rank (0.595); FR388 hit the cap in both arms.
  Without those three tasks: 17 tasks, mean 0.098 against 0.065 USD (-34 %), median 0.093 against
  0.049, FETCH2 cheaper on 12 of 17. On all 20 it is cheaper on 14 (median paired difference
  -0.037). The money moves as in the fetch pilot: readers 0.129 -> 0.052 a session, the main model
  0.048 -> 0.062. Eleven FETCH2 sessions never searched (guessed Wikipedia URLs): 0.77 against 1.81
  USD on those tasks, 9 right against 8.
- **The two gains.** FR1 is the tool's: one long ranking table, asked three times with three
  purposes, came back in row pieces each under its header, and the rank was read off it. FR444 is
  only partly: 42 pages in a row, one per event of a series, and the right count at half the base's
  money; the page budget's line came after 34 of those pages and was ignored every time, and here
  following it would have been wrong.
- **The loss.** FR690: no page fetched (8 searches), a wrong reading of what the question asks;
  not the tool's. FR388, FR205 and FR436 are wrong in both arms.
- **The page budget and the 404 line did nothing.** The budget's line: one session, 34 pages,
  never followed by a search. The 404 line: 3 times, each followed by another guessed URL.
- **The disambiguation line was a bug.** 14 lines, 12 on ordinary articles: the parser took a
  hatnote's link to a disambiguation page (class `mw-disambig`) for the page's own mark. Of the six
  sessions it touched, five kept the base's verdict and FR444 was right in FETCH2 only. Fixed after
  the pilot, in the next commit; this pilot measured the bug.

### Against the bar (cheaper and at least as many right as Claude Code alone)

- **Haiku: met on this development pilot**, not confirmed: 16 against 15 right (15 against 15
  strict), mean -36 %, median -44 %, -34 % without the three loop tasks; n = 20, p = 1. What did
  the work is what the fetch pilot already showed (pages instead of searches) plus passages that
  hold the rows: 1,240 tokens a read against 1,833 in the fetch pilot, and the one clear gain is a
  table read with its header. The page budget, the 404 line and the disambiguation line contributed
  nothing or were wrong.
- Not run on Sonnet: on the fetch pilot it fetched too little for the tool to matter.

### Next fix (not measured)

1. The disambiguation mark from the page's own markers only (the next commit, with the live case
   as a test). Done: on the 13 pages behind the 14 lines, downloaded again, only the two real
   disambiguation pages are flagged.
2. Drop the page budget's line or make it act: as additional context Haiku ignored it 34 times,
   and the one long run it fired on was the right work.
3. To separate version 2 from the task mix: a sealed run with three arms (HAIKU, HAIKU-FETCH at
   version 1, HAIKU-FETCH2) on new tasks.
