# The compaction guard: carrying what Claude Code's summary drops

## Summary

Run through our own evaluation harness, inside Claude Code 2.1.282 (headless, Haiku 4.5), and
offline on the recorded sessions. Numbers are not directly comparable with numbers obtained
through the API. Pre-registered: `prereg.md` (end-to-end, amendment A2 below its hash lines) and
`prereg-prompt-recall.md` (offline, amendments 1-5); every hash in the matching `.sha256`.

The guard does not replace Claude Code's native summary, which beat every replacement we built
(`../2026-09-28-context-lean/`). It adds to it: a note to the summariser (`PreCompact`), and,
after the summary, the recorded lines of outputs that cannot be had again, the person's requests
verbatim and the trail of files changed (`SessionStart`, source `compact`).

**End to end, Haiku 4.5, the 7 tasks whose facts can reach the model** (paired by phase A; the
other 3 are lost to a task defect, below):

| | N: native summary | G: + guard, rule | GJ: + guard, first decider | **K: + guard, cascade** |
|---|---|---|---|---|
| tasks finished (all hidden tests) | **2/7** | **5/7** | 6/6 | **6/7** |
| probe code and tolerance in context after the last compaction | 1/7 (summary) | 7/7 (guard; summary 4) | 6/6 (guard) | 7/7 (guard; summary 1) |
| `probe` fact passed | 2 | 6 | 6 | 6 |
| `limit` (re-readable control) passed | 7 | 5 | 6 | 7 |
| phase-B cost, sum (list price) | 2.28 USD | 1.51 USD | 1.41 USD (6 tasks) | 1.68 USD |

- **H1 holds** (G >= N + 2): 5 against 2; paired, G alone 4, N alone 1 (McNemar exact p = 0.375:
  n = 7 does not make it significant). **H2 holds**: one-shot facts 25 against 20, no single fact
  lower by more than 1. **H3 fails**: G passed the re-readable `limit` twice fewer than N (5
  against 7, the rule allowed 1); it cost less (0.66x, paired difference [-0.20, -0.03] USD per
  task). **H4 holds** (GJ 6 of 6 against G 5), but GJ's decider was never asked: its pool fit.
  **H6 holds**: K 6 of 7 against G 5.
- **What the native summary loses is the probe**, not the rule: it kept the release token and
  the person's rule in 7 of 7, and the probe's code and tolerance in 1 of 7. Without them N
  compacted more and spent more looking (2.28 against 1.51 USD).
- The failures that remain are not lost context: in t10 G stopped after 4 turns asking to run
  PowerShell (not an allowed tool); N and K wrote the probe's drift where its tolerance goes,
  with the tolerance in K's guard block. t09 G failed the `limit` control.

**Publishable sentence:** inside Claude Code, the guard keeps what the native summary drops:
**5 of 7 tasks finished with the free rule and 6 of 7 with the cascade, against 2 of 7 with
the summary alone** (Haiku 4.5, pre-registered, n = 7, not significant on its own).

**What the decider adds, measured offline.** When 400 characters must be chosen from the ~3,600
of one-shot output of a phase A, with the next prompt as the question (28 recorded sessions):

| condition (28 units, 400 characters) | recent | BM25 | rule | first decider questions | **cascade (`keep`)** |
|---|---|---|---|---|---|
| literal prompt, original output | 0 | 27 | 7 | 26 | **28** |
| oblique prompt, values reworded (seen) | 0 | 0 | 7 | 7 | **28** |
| JSON records, prompt sharing no word (new) | 0 | 0 | 0 | 26 | **28** |
| "Carry on with the remaining steps" (new) | 0 | 0 | 7 | 28 | **28** |

P5 and P6 hold (the cascade beats BM25 and the rule by far more than 20 points on the new
conditions); **P7 fails**: on the two new conditions the first decider questions already found
54 of 56, so the redesign's own gain there is 2 units. Most of the jump from the earlier run
came from fixing how the question was asked, not from a better model call (below).

## The negatives first

- **The first decider questions never read the request.** `chunks.*_questions` cut `purpose` to
  400 characters and the guard's preamble took 301 of them: about 95 characters of each prompt
  reached Jev. In the oblique condition the half asking for the probe's limit was never sent
  (probe 0 of 20). The earlier run's "the decider fails at the frontier" (amendment 4, 0/9 on
  test) was this defect, not a limit of the model.
- **The first cascade was worse than the decider alone** at a tight budget (19/28 against 26/28
  on the literal prompt): the rule's lines took the room before the decider's.
- **The rewrite is not blind.** Amendment 5 was designed after reading where the decider failed;
  its criteria describe the kinds of value these tasks plant (an identifier issued once, a
  failure's limit and reference), with examples from other domains. The new conditions were
  written before any decider answer on them, but a one-shot value of another kind (a port, a
  random seed, a line of a diff) is not tested.
- **The native summary cannot be the decider's context at a compaction.** Read from the 2.1.282
  binary and seen in the run: `SessionStart` hooks run before `PostCompact`, and the summary is
  written to the transcript after them; `PostCompact` can only show a message. So the guard
  cannot ask with the summary in view before the first call after the compaction. The `notes`
  field is fed the task list (`TodoWrite`) when there is one; unmeasured here (these sessions had
  no task list).
- **A task defect cost three of ten tasks.** Claude Code keeps the first and last 5,000
  characters of a shell result that exits with an error; the build log is 20-22 KB and exits 1.
  On the three tasks whose failing check sits in the middle (t02, t05, t08) no arm ever saw it,
  native included. The same defect sat in `../2026-09-28-context-lean/` (corrected there): its
  native 5/7 was 5 of 5 deliverable. The guard now says when an output was cut before it was
  seen (`guard.clipped_of`).
- **Public trajectories: no advantage** (`offline/public.json`): on 40 OpenHands trajectories what
  was needed from shell output could be re-run; the guard's lines held a needed token for 30 %
  against 43 % for the most recent results (every interval crosses 0). The claim is limited to
  values that cannot be had again.
- The offline replay of 31 recorded compactions (token, probe code and tolerance in 18 of 18 by
  the guard against 15, 13 and 14 in the native summary) was tuned on that data: not evidence.

## End to end (`prereg.md`, amendments A2 and A3)

Claude Code 2.1.282 headless, one phase A per task (no hooks), forked into every arm; the
native auto-compaction fires in the middle of phase B (`CLAUDE_CODE_AUTO_COMPACT_WINDOW`
100000, `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE` 63). 36 valid rows, none invalid. The run was
stopped by the owner after t08 to measure the decider offline (amendments 4 and 5), then
resumed: t09 and t10 in N, G and K, then K on the five measurable tasks left. K replaced GJ
for what remained (GJ's decider was never asked). Sonnet 5 was not run: the money left after
K would have bought n = 2, which decides nothing.

Across all 10 tasks: N 2/10, G 5/10, GJ 6/9. K's decider cost 0.0145 USD over 7 sessions (8
compactions, about 0.002 each); in 7 of 8 compactions its `notes` were empty (the summary is
written after the hook runs; the one with notes read the previous compaction's summary).

Declared: G on t09-t10 ran code changed after t01-t08 (the one-shot fix, the note about cut
outputs); K ran with that code throughout.

## The cascade (`context.keep`, questions in `points.keep`)

1. **Plumbing** (`guard.pieces_of`): every line of every output that cannot be read again,
   chosen by tool (not file reads or edits, not test runs, not web or MCP by default). If it
   fits, it all goes and nothing is asked.
2. **The rule** (free): errors, words shared with the requests, rare line shapes. What stands
   when the decider fails or times out.
3. **Jev** (`jev-1.13.0`), only when the pool does not fit: a Score of four levels per block of
   output (at most 900 characters, titled by its command, up to 12 per call, all in view), then
   a Score per line of the best four blocks, each line read in its block. The requests go in
   full in their own field; the levels describe situations (nothing needed / background or
   re-readable / a value that might be used / an exact value the requests point to that exists
   only here). Lines at 2.0 or more go first, then the rule's, then lines at 1.5 or more.
   About 5 calls and 0.002 USD per compaction.

Why Score and not yes/no: inside a budget the order among kept lines decides, and a four-level
score gives a position (the same fix Indagis measured on long documents).

## Defects found and fixed, each with a test

`tests/test_context_guard.py`, `tests/test_context_guard_review.py`, `tests/test_context_keep.py`:
secrets in `KEY=value` lines masked; web and MCP output out by default and fenced when in; the
decider's request truncated (above); a one-shot tool whose first run also failed lost its output
when re-run (`guard.latest_only`); a line printed twice took room twice; outputs cut by the
harness are named in the block.

## Cost

- End to end: 12.66 USD of subscription at list price by the runner, plus about 0.25 USD of a
  t09 session cut off before it wrote a row: about 12.9 of the 18 approved.
- Decider (`jev-1.13.0`): 0.374 USD of the 0.40 approved: the offline runs 0.183 (amendments
  1-4) and 0.175 (amendment 5), one hook check 0.002, K in the run 0.0145.

## Files

- `prereg.md`, `prereg-prompt-recall.md` and their `.sha256`; `tasks.py` (seed, digest in
  `tasks.sha256`); `arms.py`, `run.py`, `guard_wrapper.py`, `dry.py`, `analyze.py`.
- `runs.jsonl`, `phase-a.jsonl`, `analysis.json` (end to end); transcripts under
  `~/.cache/sanchopanza/context-guard/` (not published: they hold local paths).
- `offline/prompt_recall.py` (`prompt_recall.json`: amendments 1-4; `prompt_recall_keep.json`:
  amendment 5; decisions replayable from the recordings). After the review fixes (secrets
  masked before a line is cut, a null provider counted as a failure) the replay,
  `prompt_recall_keep.replay.json`, reproduces `keep` exactly on all 112 registered rows; three
  rows of other arms differ only in characters used, by ties (BM25 was unified in the package
  since), no hit changes; t10's phase A now exists and has no recordings. `offline/replay.py`,
  `offline/public.py`.
