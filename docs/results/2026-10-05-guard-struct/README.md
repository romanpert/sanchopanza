# The compaction guard keeps whole tool results by structure (`struct`)

A product change to the compaction guard (`sanchopanza install --guard`), decided on an offline
replay of recorded sessions on 2026-10-05. The Jev scores below come from one recorded run;
everything else is a free replay.

## What changed

`SANCHOPANZA_GUARD_CHOOSER=struct` is the default chooser (`context.structural`). Over every
tool result since the previous compaction, re-readable ones included:

1. results on files edited since the previous compaction (the edits, and reads, searches and
   commands naming one of those files);
2. the rest, by recency;
3. of the reads and edits of one file, only the latest.

Inside each tier, output that cannot be had again (a one-shot command, a subagent's report) goes
first, newest first. Results are kept whole while they fit. A re-readable result left out gets a
pointer (file and line range, the search, the command), within `GUARD_POINTER_CHARS` (1,500); a
one-shot result left out is lost, as it would be without the guard. Web and MCP output is only
pointed to unless `GUARD_WEB=1`. No decider runs on this path, and any error gives the rule's
block. `rule`, `keep`, `judge` and `decider` can still be chosen.

## Why the decider is out of the ranking

On the public set (99 compaction points from 82 public benchmark sessions, compaction at 100k
or 150k tokens; 88 points on Haiku 4.5, 11 on Sonnet), Jev's block scores separated the results
the work needed next from the rest worse than plain recency:

| arm | Jev block scores, within-point AUC | recency, within-point AUC |
|---|---|---|
| plain Claude Code | 0.58 | 0.60 |
| Claude Code with sanchopanza | 0.56 | 0.61 |

The shipped cascade (`keep`) proposes lines of one-shot output only, so it could not keep what
was needed most: in the plain arm at 100k it kept 126 of 494 needed `Bash` results and none of
the 375 needed `Read` or 225 needed `Edit` results. The Jev calls for the 99 points cost 1.63 USD
at list price (0.71 for the cascade as shipped, 0.92 for the block scores).

## What structure keeps

On the owner's Claude Code sessions (135 sessions, 344 compaction points at 200k tokens; 335 on
Opus 5.5 or Opus 5), with a median of 97 candidate results and 34 needed ones per point. A read
superseded by a newer kept read of the same file counts as kept. Share of needed results kept,
at-risk ones (output that cannot be had again) in brackets:

| budget, characters (tokens) | this order (`struct`) | without the at-risk step | recency | oracle |
|---|---|---|---|---|
| 3,000 (1,364) | .15 (.17) | .21 (.13) | .15 (.12) | .39 (.27) |
| 11,000 (5,000) | .28 (.30) | .36 (.26) | .25 (.21) | .65 (.55) |
| 22,000 (10,000) | .44 (.43) | .52 (.40) | .38 (.33) | .79 (.74) |
| 44,000 (20,000) | .64 (.61) | .67 (.59) | .56 (.51) | .91 (.89) |

The guard's rule-only path keeps .12 (.17) at its 3,000 characters. Keeping the last ten results
whole keeps .47 at 44,000 characters. The at-risk step costs a few points of the total and buys
the outputs that cannot be read again; it is kept.

## The budget and what reaches the model

`GUARD_STRUCT_CHARS` defaults to 44,000 characters (about 20k tokens), the budget measured at
.64-.67.

Claude Code keeps a hook's `additionalContext` inline only up to 10,000 characters. Past that it
writes the text to a file, and the model sees a `<persisted-output>` notice with the first 2,000
characters and the path (read in the 2.1.282 and 2.1.287 binaries). The guard therefore caps the
whole block at `GUARD_INLINE_CHARS` (9,500; 0 turns the cap off). Results get the room the
requests, the trail and the pointers leave under it: about 3,900 characters with 2,500 of
requests and 20 changed files, up to 7,000 with a short request. In Claude Code today the block
therefore sits between the 3,000 and 11,000 rows above: about .15 to .28 of needed results,
against .12 for the rule. The contexts of several `SessionStart` hooks are capped one by one and
then concatenated, so the measured 44,000 can only arrive split across several hook commands.

The split is on main since 2026-10-06 (merge `cb0062e`, `context.parts`): `PreCompact` splits the
block into up to six parts under 9,500 characters each, part 1 holding the requests, the work so
far, the pointers and the results that rank first, and each `SessionStart` command prints one
part. In 2.1.287 each command's context is persisted on its own past 1e4 (`Pde`), the
`SessionStart` contexts are collected in one list with no aggregate cap, and they reach the
model as one message joined by newlines, in the order the hooks finish (`Promise.race`), so each
part names itself "part i of N". Offline on 18 one-shot outputs of 2,500 characters, run as
Claude Code runs hooks: 6 parts of 5,700 to 8,200 characters, 17 of 18 results kept.

**Live probe, passed (2026-10-06, merge `cb0062e`).** `benchmarks/guard_split/probe.py --run`
(`--model` sonnet and opus) inside Claude Code on Sonnet 5.5 and Opus 5.5: all 6 parts
arrived inline, with no `<persisted-output>`, delivered out of order, and the model answered the
marker taken from part 2 exactly. This checks delivery, not what the kept results are worth to
the work.

## Caveats

- "Needed" is a proxy: a later tool input or assistant text naming the result's file, or a
  distinctive token first seen in it.
- The public set is mostly Haiku 4.5; the owner's sessions are one person's work, mostly on one
  model.
- The ranking figures are offline. Inside Claude Code only the split's delivery was probed
  (above); this folder does not measure what the structural keep is worth to a session there.
- Characters per token are about 2.2 in these sessions; the token columns use that rate.

## Reproduce

The replay scripts (`real.py`, `iterate.py`, `iterate_credit.py`, `budget.py`, `fails.py`) ran
over private transcripts and are not published. The code is tested in
`tests/test_context_structural.py`: tiers, dedupe, pointers, the budget, the inline cap, masking,
`since`, the default, a 400k-token transcript through both hooks in under 2 s, the fail-safe and
install wiring.
