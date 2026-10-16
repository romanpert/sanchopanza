# The compaction guard's pointer block against its whole-results block, replayed (2026-10-16)

**The result:** replayed on 10 recorded long sessions of clean Claude Code 2.1.287 with Sonnet
5.5 (98 compactions), the pointer block that the guard attaches by default since 0.3.2 is a
median **7,925 characters** (max 9,470) against **49,473** for the whole-results block
(`install --guard-full`). Carrying it to the next compaction costs **0.19 USD per session instead
of 1.18** on the arm that compacts near 160k (Ne, mean of 5) and **0.35 instead of 1.98** on the
arm that compacts near 67k (Nl, mean of 5): **1.31 USD less per session** on average, 83 % of the
whole-results block's carry cost. On the benefit side, the agent fetched again something the
whole-results block would have held whole in **7 of the 98 compactions** (9 re-fetches, 8 of
them in one session), worth **0.0019 USD per compaction** at best, against the **0.16 USD per
compaction** that block costs to carry.

Free and offline: recorded transcripts, the current guard code, no model, no API. Not
pre-registered: it is the evidence behind a default (the pointer block), not a verdict on quality.

## What was replayed

- **Sessions.** The 10 Sonnet 5.5 sessions of the long-compaction run
  ([2026-10-13-long-compact](../2026-10-13-long-compact/README.md)): chains conan-1, conan-2,
  moto-1, moto-2 and pydantic-1 (long60, 60 bugs fixed in one Claude Code session), each in two
  arms of clean Claude Code with no sanchopanza and no guard: **Ne**
  (`CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000`, compacting near 160k; 18 compactions) and **Nl**
  (`=100000`, near 67k; 80 compactions). Claude Code 2.1.287, `claude-sonnet-5-5` in every
  transcript.
- **At each compaction** (each `compact_boundary`), the transcript up to it went through both
  blocks as the hook builds them today:
  - the whole-results block: `context.parts.split(..., parts=6)` with its defaults (44,000
    characters of whole results, 6 parts of at most 9,500), what `--guard-full` wires;
  - the pointer block: `context.pointers.build`, the requests first, the files changed, the cut
    outputs and pointers, every one-shot output archived; its archive folder a fixed 70-character
    absolute path, the length of a project's `.sanchopanza/archive/<session id>`.
- **Carry cost** of a block: its tokens written once to the cache and read by every later request
  until the next compaction. Requests are counted per segment from the transcript (distinct
  message ids).
- **Re-fetches**: in the segment after a compaction, the first call that fetches again an item
  the whole-results block held whole (a Read of a file whose read or edit it held, with no edit
  of that file earlier in the segment; the same shell command, search or other label). Its cost
  is the request that issued it (its whole context read again, its output) plus its result
  carried to the next compaction: what the block could have saved had the agent trusted it.
- **Rates.** Sonnet 5.5, USD per million tokens: output 10, cache read 0.2, 1-hour cache write
  4, fitted exactly from Claude Code's own session costs in the F2 cell
  ([2026-10-16-memory-f2](../2026-10-16-memory-f2/README.md)). Tokens per character: 0.30, from
  the two guarded compactions of the L-smoke run (6,274 tokens of cache write over 20,850
  characters of guard block).

Code: [`benchmarks/guard_pointers/replay.py`](../../../benchmarks/guard_pointers/replay.py), tests
beside it. Output: [`summary.json`](summary.json) and one row per compaction in
[`compactions.json`](compactions.json) (sessions named by their arm folder only).

## The figures

| Session | Compactions | Requests after them | Whole-results block (median chars) | Pointer block (median chars) | Carry, whole results (USD) | Carry, pointers (USD) | Re-fetches |
|---|---|---|---|---|---|---|---|
| conan-1 Ne | 4 | 345 | 50,598 | 7,776 | 1.28 | 0.20 | 0 |
| conan-1 Nl | 20 | 503 | 48,588 | 7,979 | 2.41 | 0.42 | 0 |
| conan-2 Ne | 4 | 351 | 51,519 | 7,626 | 1.31 | 0.20 | 0 |
| conan-2 Nl | 15 | 428 | 49,761 | 8,175 | 2.03 | 0.35 | 0 |
| moto-1 Ne | 4 | 333 | 50,844 | 8,190 | 1.25 | 0.20 | 0 |
| moto-1 Nl | 15 | 397 | 49,145 | 7,613 | 1.94 | 0.30 | 1 |
| moto-2 Ne | 4 | 310 | 51,584 | 9,099 | 1.20 | 0.20 | 0 |
| moto-2 Nl | 18 | 408 | 47,220 | 7,768 | 1.92 | 0.35 | 0 |
| pydantic-1 Ne | 2 | 241 | 50,542 | 7,812 | 0.85 | 0.13 | 0 |
| pydantic-1 Nl | 12 | 385 | 47,804 | 8,342 | 1.58 | 0.31 | 8 |

- **Per arm, mean of 5 sessions:** Ne 1.18 → 0.19 USD of carry per session (medians 1.25 →
  0.20); Nl 1.98 → 0.35 (medians 1.94 → 0.35). Mean saving 1.31 USD per session, 83.1 % of the
  whole-results block's carry.
- **What the archive takes instead:** a median 44,169 characters of one-shot output per
  compaction is written to disk, read only if the agent asks for it.
- **The benefit side.** 9 re-fetches of items the whole-results block held, in 7 of 98
  compactions (8 Reads and 1 shell command; 8 of the 9 in pydantic-1 Nl), 0.18 USD over all 98,
  0.0019 USD per compaction, against 0.161 USD per compaction of carry for that block. Of 209
  files read for the first time in a segment (before any edit of them), 8 had been read or
  edited in the segment before, and the block held all 8; of 2,669 first shell commands, 1 had
  run in the segment before. In these sessions each segment mostly works on other bugs than the
  last, so what a block holds from before the compaction is rarely what comes next.

## Limits

- **Offline and first-order.** No session was run with either block: the carry cost is the
  block's own tokens through the cache, and the re-fetch saving assumes the agent would trust
  the block perfectly. A block changes what the agent does next (fewer or more calls, another
  summary), and that second-order effect is not here.
- **Quality is not measured.** The replay prices the block; it does not say whether the agent
  solves as many bugs with pointers as with whole results. The guard's re-injection added
  nothing measurable on BrowseComp-Plus ([2026-10-07-h2h-ne](../2026-10-07-h2h-ne/README.md)),
  and the long-compaction run found no quality loss from compacting to recover; neither is a
  measurement of the pointer block.
- **Tokens per character.** 0.30 comes from two compactions of one Haiku session. Code, JSON and
  prose tokenize differently: read every USD figure as ±20 %. The ratio between the two blocks
  does not depend on it.
- **Clean sessions only.** The blocks were built on sessions that never had a guard; a guarded
  session's later segments would differ.
- **One rate card.** Sonnet 5.5 only; Opus 5.5 doubles the write rate and keeps the read rate.
- **Re-fetch matching** is by file (last two path parts) for reads and by the exact label for
  everything else: a re-run with other arguments is not counted, and a read of a file under
  another path ending the same way is.
