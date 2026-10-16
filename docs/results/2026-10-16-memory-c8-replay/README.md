# Memory's C8 gaps, replayed free (2026-10-16)

**What this is.** Free replays of the memory changes that closed ROADMAP C8, run on main's code
(6b4301b). They show what the changed code gives on data already recorded. They are not a new
measurement of quality or cost: **nothing was measured live**. Jev and Claude were not called
(`live_calls: 0` in `replay.json`).

Three sources, kept apart below:
- **F2's recorded decisions, replayed.** The 72 S arms of the F2 night
  ([2026-10-16-memory-f2](../2026-10-16-memory-f2/README.md)): each arm's memory store and hook
  logs as the night left them, with the decider answering from the probabilities the night logged.
- **SWE-chat.** The 909 public first prompts of lot memgate-hook
  ([2026-10-16-memgate-hook](../2026-10-16-memgate-hook/README.md)), read from the local cache.
- **The owner's stored rules.** 280 standing rules stored from his own sessions. Only the count
  is published.

`python benchmarks/memory_c8/replay_c8.py --f2-root <F2 run root> --own-rules <rules file>`
rebuilds `replay.json`. The SWE-chat items are read from the local cache by default. Each part
runs only when its input is given.

## What changed in C8

- **A bare "continue".** A session's very first prompt that only says to go on gets the newest
  record of the newest session not still at work. That record must be at most 7 days old. It is
  given by code: no new decider question, and the decider is asked in the same cases as before.
  - Before C8, a line naming no file a record changed got no record at the prompt.
  - The switches are `SANCHOPANZA_MEMORY_CONTINUE` and `SANCHOPANZA_MEMORY_CONTINUE_DAYS`.
- **A long prompt's record** keeps its head and its tail within the same 1,000 characters,
  instead of the head alone.
- **Plan-shaped sentences.** Examples: "For step 2, cap the discount", "Step 2, in the next
  session: ...". Only those with no lasting word (always, never, must, every, ...) count.
  - They are not asked about at Stop.
  - A plan stored earlier ranks below every rule at a session start and in the audit. Nothing
    stored is dropped.

## F2's recorded decisions, replayed

The F2 night is replayed through `memory_hook.recall` with the continuation off, which is the hook
before C8.
- It gives what the night gave in every arm: 48 of 48 Sonnet arms and 24 of 24 Opus arms.
- The rules rendered as before C8 match the night's too.

As shipped now:

| | Sonnet 5.5 (48 arms) | Opus 5.5 (24 arms) |
|---|---|---|
| session 1's record at session 2's prompt, the night | 36 | 18 |
| the same, now | **48** | **24** |
| decider calls at that prompt, before / now | 36 / 36 | 18 / 18 |
| questions the night did not answer | 0 | 0 |
| rules given at session 2's start, median characters, the night / now | 1,691 / 1,693.5 | 1,681.5 / 1,696 |
| characters given in session 2 (rules, prompt, touch), median, the night / now | 3,895 / 3,899 | 4,774 / 4,733.5 |

- **Which arms changed.** The arms that gain the record at the prompt are the scenes whose
  continue line names no file step 1 wrote: h_loud, h_merge and h_judge, all repetitions.
  - That night those arms got the record at a file touch. On Sonnet, 5 of them got it only
    after their first shell write.
  - Now they get it before any tool call. The record moves from the touch to the prompt, so the
    characters given stay about the same.
- **Rules at the start.** They do not shrink. When a plan ranks lower, an older rule fills its
  place in the 8-rule slot.
- **Plan-shaped sentences in F2.**
  - Of the 118 standing rules the night stored, 16 are plan-shaped by the shipped rule; the
    other 102 stay rules.
  - Of the 72 sentences in the 12 scenes' session-1 prompts, 15 are no longer asked about at
    Stop.
- **Long prompts.** The session-1 prompts are 508 to 751 characters. None is cut, so this
  replay never exercises the head-and-tail record.

## SWE-chat's first prompts

909 first prompts.

**The continuation cue fires on 7.**
- 4 open with a go-on verb, among them three bare "resume".
- 3 ask where the last session left off.
- All 7 are requests to go on.
- The labels by code (from the files the session then changed) call the record given unrelated
  on all 7. In all 7 the pool holds no record those labels call related. Labels from file
  changes cannot credit a record that only carries a plan.
- No item carries a time of its own, so the 7-day bound is not applied. **7 of 909 (0.8 %) is
  the most the cue adds to the hook's records given where nothing is related here.**

**Long prompts.**
- 235 of the 909 prompts are longer than 1,000 characters.
- None has a plan-shaped sentence past the first 1,000 characters by the shipped rule. So these
  data say nothing about the head-and-tail record.

## The owner's stored rules

Of 280 standing rules stored from the owner's real sessions, **0** are plan-shaped by the
shipped rule. None would rank below the others, and none would go unasked.

## What this does not show

- Whether the record at the first turn changes what the agent does. F2's S already finished 48
  of 48 on Sonnet, so these data have no room to show it. Only a paid run can.
- Whether moving a decision about step 2 out of the standing rules costs anything, now that it
  reaches session 2 only through the record. That also needs a paid run.
- Cost. A prompt longer than 1,000 characters now gives Stop's rule extraction different input.
  Its recorded answers do not replay there, and each new sentence is a new decision.

## Files

| file | what it is |
|---|---|
| `replay.json` | every figure above, with F2's per-arm rows: numbers, scene, model and repetition only; no text, session id or path |
| `benchmarks/memory_c8/replay_c8.py` | runs the three parts and writes `replay.json` |
| `benchmarks/memory_c8/f2_replay.py`, `swechat.py`, `own_rules.py` | the three parts |
