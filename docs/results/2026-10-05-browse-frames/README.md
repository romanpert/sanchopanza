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
