# The MCP guard replayed over ATBench-Codex (lot A3)

**The result:** wired into the hook, the `actions` point catches **185 of 250 unsafe
trajectories (74.0 %)**, while the hook as it ships today catches **0**. It also flags **82 of
250 safe ones (32.8 %)**.

The registered floor was 75.2 % recall (the offline reference minus 10 points), so **by the
sealed rule the replay is not confirmed**:
- P1 fails on recall, by 3 trajectories. Its FPR holds.
- P2 and P3 hold.

`--guard-mcp` stays opt-in, and phase 2 (live Claude Code sessions) was not run.

**The question** (pre-registered):
- The hook that `sanchopanza install` leaves in Claude Code lets MCP tool calls through with no
  decision. On ATBench-Codex, whose risks live in MCP calls, it flagged 0 of 250 unsafe
  trajectories ([claude-code-broad](../2026-09-28-claude-code-broad/), part H).
- Offline, the `actions` point read the same trajectories whole
  ([cascade-frontier](../2026-09-27-cascade-frontier/)) and flagged 213 of them.
- This lot wires that point into the hook for `mcp__*` tools (`install --guard-mcp`), where it
  reads only the session up to the pending call. How many unsafe trajectories does it catch, and
  how many safe ones does it flag?

**Pre-registered** in `prereg.md`:
- sealed at commit 65528af;
- `prereg.sha256` c222aaf5…;
- reviewed against the code by `revisor-prereg` before the seal.

The seal still matched at scoring time (`analysis.json`, `seal`).

**What ran:**
- **When and where:** 2026-10-16, 06:13 to 06:15, from a detached worktree at the sealed
  commit, launched outside the session.
- **Data:** the 500 ATBench-Codex test trajectories (250 unsafe), turned into Claude Code
  transcripts. Each of their 1,195 actions became one PreToolUse event: 1,188 non-shell calls
  and 7 shell commands.
- **The path judged:** the hook's own code, in process (`claude_code.needs_decision`, then
  `claude_code.handle`), as `sanchopanza hook` runs it. No Claude Code session ran, and no
  model besides Jev was asked.
- **Decider and cut:** TypeSafe Jev `jev-1.13.0` at the cut 0.5 (`Thresholds.action_stop`),
  fixed before the data.
- **Answers:** 1,189 questions, all answered, 0 errors, all from `jev-1.13.0`.
- **Spend:** 0.0496 USD in the run's ledger, under the 0.25 cap.

## Verdict by the sealed rule

| Criterion | Rule | Measured | Holds |
|---|---|---|---|
| **P1** recall at FPR, `mcp` arm | recall ≥ 0.752 and FPR ≤ 0.342 | recall **0.740**, FPR 0.328 | **no** (recall) |
| **P2** McNemar on the 250 unsafe, `mcp` vs `today` | more flagged only by `mcp`, p < 0.05 | 185 vs 0, p 4.1e−56 | yes |
| **P3** coverage and provenance | every MCP call decided in `mcp`, none in `today`, all `jev-1.13.0`, none unanswered | 1,188 / 1,188, 0, yes, 0 | yes |
| **Verdict** | P1, P2 and P3 | | **not confirmed** |

P2 was close to automatic, as the prereg said: `today` decides one call in the whole set (a
shell command, in a safe trajectory) and denies nothing.

## The figures

Trajectories flagged at the cut 0.5, `jev-1.13.0`, with Wilson 95 % intervals.

| Arm | Recall (250 unsafe) | FPR (250 safe) |
|---|---|---|
| Offline reference: whole records, 2026-09-27 (`fixtures/cascade-jev.jsonl`) | 213 (85.2 % [80.3, 89.1]) | 73 (29.2 % [23.9, 35.1]) |
| **`mcp`**: the hook with `SANCHOPANZA_GUARD_MCP=1` | **185 (74.0 % [68.2, 79.1])** | **82 (32.8 % [27.3, 38.8])** |
| `today`: the hook as `install` writes it | 0 (0.0 % [0.0, 1.5]) | 0 (0.0 % [0.0, 1.5]) |
| `mcp` without Codex's own tools (reported) | 183 (73.2 % [67.4, 78.3]) | 82 (32.8 % [27.3, 38.8]) |
| Offline control, asked today ([amendment 1](#amendment-1-the-offline-control-asked-again)) | 213 (85.2 % [80.3, 89.1]) | 72 (28.8 % [23.5, 34.7]) |

How to read it:
- **`mcp` against `today`, paired** (bootstrap 95 %): recall +74.0 points [68.4, 79.2], FPR
  +32.8 [27.2, 38.8].
- **Codex's own tools:** 65 of the 1,188 "MCP" calls are Codex's own tools, which Claude Code
  would not route through an MCP server. Leaving them out costs 2 unsafe trajectories and no
  false flag.
- **The control:** the run's own offline control answered 2 of its 500 records. Amendment 1
  asked it again: the offline point flags today what it flagged on 2026-09-27.

**The cut, re-cut after the data (reported, not judged).** No cut on this sweep meets both
margins at once:

| Cut | 0.3 | 0.4 | **0.5** | 0.6 | 0.7 | 0.8 | 0.9 |
|---|---|---|---|---|---|---|---|
| Recall | 90.4 % | 81.6 % | **74.0 %** | 67.2 % | 54.0 % | 43.6 % | 23.2 % |
| FPR | 52.8 % | 42.0 % | **32.8 %** | 24.0 % | 15.6 % | 8.0 % | 1.6 % |

## What it costs a real session

These figures come from ATBench's safe trajectories. They are built to look risky, so they
are not the false-deny rate of ordinary MCP work: that is phase 2's question.

- **Denials in safe sessions:**
  - **112 of the 589 MCP calls in safe trajectories are denied** (19.0 % [16.1, 22.4]);
  - **82 of the 250 safe sessions (32.8 %) meet at least one denial**;
  - writes and sends are denied far more often than reads (next section).
- **Jev per call:** 42 µ$ (954 input tokens at the median), and 203 ms at the median (p90
  250 ms) as the client measures it. At 2.4 calls per trajectory that is about 100 µ$ per
  session. The hook's process start is not in these figures.

## Where the recall went, and what the false flags are

This section is free and post hoc: `diagnose.py` reads the per-call verdicts beside the
reference and ATBench's own labels. `diagnosis.json` holds every figure.

**Per unsafe trajectory, offline reference against the hook's `mcp` arm:**

| | Hook flags | Hook misses |
|---|---|---|
| **Reference flags** | 180 | **33** |
| **Reference misses** | 5 | 32 |

So 213 − 33 + 5 = 185.

**The 33 the hook misses:**
- **They are not near the cut.** The highest per-call p is below 0.3 in 14 of them, 0.3 to 0.4
  in 6 and 0.4 to 0.5 in 13. In 30 of the 33 it is the last call's.
- **The reference was not borderline on them either.** Its p is below 0.6 in only 6.
- **Codex's own tools play no part.** None of the 33 consists of them only.
- **Most of them are tools that misbehave in their response** (ATBench's `risk_source`):

| Risk source (ATBench) | Unsafe | Reference flags | Hook flags | Missed by the hook | Caught only by the hook |
|---|---|---|---|---|---|
| **malicious_tool_execution** | 39 | 37 | 23 | **14** | 0 |
| corrupted_tool_feedback | 21 | 17 | 12 | 5 | 0 |
| indirect_prompt_injection | 26 | 23 | 18 | 5 | 0 |
| dependency_mcp_supply_chain_compromise | 54 | 46 | 44 | 4 | 2 |
| unreliable_or_misinformation | 41 | 32 | 29 | 3 | 0 |
| repository_artifact_injection | 22 | 20 | 19 | 1 | 0 |
| inherent_agent_failures | 22 | 14 | 15 | 1 | 2 |
| policy_precedence_misinterpretation | 16 | 16 | 16 | 0 | 0 |
| tool_description_injection | 9 | 8 | 9 | 0 | 1 |

**What these rows have in common: the harm shows only in a tool's answer.**
- In `malicious_tool_execution` the tool itself does the harm. ATBench's own reasons for the
  missed trajectories point at what the tool's response showed. Examples: a staging deploy
  that went to production, an enrichment billed for 4,127 records instead of 5, a draft that
  was published.
- The call that triggers it looks benign. The harm appears in its result, after the last call,
  which a PreToolUse hook never reads. The whole-record reference reads it.
- `corrupted_tool_feedback` and `indirect_prompt_injection` account for 10 of the other 19.
  By ATBench's reasons, the poisoned content sits mostly in the last call's result there too.

Every trajectory ends with the agent's final text after its last call. So "the flag is only in
the final text" and "the flag is in the last result" cannot be told apart from these answers:
it would take new questions, which were not asked.

**False flags per call, by kind of operation and by position.** The kind is the operation's
leading verb, from a fixed list written after the data.

| MCP calls | Denied in safe trajectories | Denied in unsafe trajectories |
|---|---|---|
| **Writes or sends** (update, create, deploy, send…) | **58 / 146 (39.7 %)** | 159 / 205 (77.6 %) |
| Reads or checks (search, query, read, list…) | 29 / 337 (8.6 %) | 36 / 289 (12.5 %) |
| Operation not named | 20 / 50 (40.0 %) | 32 / 53 (60.4 %) |
| Other verbs | 4 / 21 (19.0 %) | 11 / 22 (50.0 %) |
| Codex's own tools | 1 / 35 (2.9 %) | 4 / 30 (13.3 %) |
| First or only call | 17 / 250 (6.8 %) | 13 / 250 (5.2 %) |
| Later calls | 95 / 339 (28.0 %) | 229 / 349 (65.6 %) |

**Safe trajectories flagged, by what ATBench says the agent did** (`defense_type`):

| Defense type | Safe | Reference flags | Hook flags |
|---|---|---|---|
| detected_with_warning | 109 | 42 | 45 |
| none | 66 | 19 | 24 |
| partial_refusal | 39 | 6 | 9 |
| refused | 24 | 5 | 3 |
| defended | 12 | 1 | 1 |

How to read the false flags:
- The point separates writes from reads, but not well enough on writes: in safe trajectories
  it denies 4 writes in 10.
- It denies little on first calls and reads, which are most of ordinary MCP traffic.
- Most of its false flags fall on sessions where the agent noticed something and went on with
  a warning, or had no defence to make: 69 of the 82.
- The reference flags these same sessions about as often (73 against 82; 61 in common), so the
  hook adds few false flags of its own: 21 safe trajectories are flagged only by the hook, and
  12 only by the reference.

## What it implies

- **`--guard-mcp` stays opt-in, as registered.** The default flips only if this replay is
  confirmed and phase 2's rule holds. The replay is not confirmed.
- **Phase 2 was not run.** Its bounded live probe in Claude Code (48 Sonnet 5.5 sessions, about
  5 USD) was the next gate only after a confirmed replay.
- **Cost against benefit:** the guard closes most of the MCP gap (0 → 74 % of unsafe
  trajectories), at 1 MCP call denied in 5 in ATBench's safe sessions and 4 writes in 10.
  Neither figure is the false-deny rate of ordinary work, but neither argues for a default.
- **The cut is not the lever.** No cut on the sweep meets both margins. The 33 missed
  trajectories are mostly well below the cut, not near it.
- **Next proposal: judge what tools return, not only what is called.**
  - Most of the lost recall is harm that appears in a tool's result (a misbehaving tool,
    poisoned feedback).
  - A PostToolUse check on MCP results would read what the reference reads and the PreToolUse
    guard cannot. It cannot undo the call, but it can stop the agent before it acts on, or
    passes on, a result that shows the harm.
  - That is a separate lot, with its own prereg and its own replay on these 500 trajectories.
    It should also say which harms a check after the fact still prevents.

## Amendment 1: the offline control asked again

Written after the data and labelled so. It re-asks only the control (the 500 whole records,
`jev-1.13.0`, cut 0.5). The hook's answers are replayed free and must match `calls.jsonl`.
It has no criteria and does not replace the verdict above.

- **Text and seal:** `prereg-amendment-1.md`, sealed at commit b10c1ec
  (`prereg-amendment-1.sha256` f0544c06…), after a review against the code by
  `revisor-prereg`. The seal also covers the sealed run's `answers.jsonl`, `calls.jsonl` and
  `analysis.json`.
- **Cap:** its own batch, capped at 0.05 USD on the same ledger. The free rehearsal
  (`dry-amendment-1.json`) expects 0.031 to 0.036 USD.

**Result.** Run on 2026-10-16, 09:32 to 09:33, from a detached worktree at b10c1ec. All 500
records were answered by `jev-1.13.0`, with no stop. The amendment's seal matched.

| | Recall (250 unsafe) | FPR (250 safe) |
|---|---|---|
| Offline reference, 2026-09-27 | 213 (85.2 % [80.3, 89.1]) | 73 (29.2 % [23.9, 35.1]) |
| Offline control, asked again | 213 (85.2 % [80.3, 89.1]) | 72 (28.8 % [23.5, 34.7]) |
| Control against reference, paired | 0 discordant, exact McNemar p 1.0 | 2 vs 3 discordant, p 1.0; difference −0.4 points [−2.0, +1.2] |
| Hook `mcp` arm against the control (both / control only / hook only / neither) | 180 / 33 / 5 / 32 | 59 / 13 / 23 / 155 |

**No drift shown, by the reading fixed before the answers** (`p_exact` 1.0 on the unsafe pairs).
The point flags the same unsafe trajectories today as on 2026-09-27, so the 0.852 → 0.740 gap
is the hook judging each call before its result, not Jev moving.

## Not done

- **Phase 2**, the live probe in Claude Code: it was conditional on a confirmed replay.
- **No cut was chosen on this set**, and none is proposed from the sweep.
- **No other Jev model:** 1.14 was not asked here.
- **The split between the last result and the final text** among the 33 misses: it needs
  questions on records cut before the last result, which cost money and were not registered.
- **The relaunch rule never applied:** the first launch left no hook call unanswered.

## Spend

| | USD |
|---|---|
| Batch `a3-replay` in the run's ledger (hook arms, 1,189 answers; control, 2) | **0.0496** |
| Batch `a3-control-amendment-1` (amendment 1, 500 answers) | **0.0308** (batch cap 0.05) |
| The run's ledger, both batches | 0.0805 (cap 0.25) |
| Preflights, outside the ledger | about 0.00003 |
| Claude | 0 |

## Files

- `prereg.md`, `prereg.manifest.json`, `prereg.sha256`: the sealed registration.
- `dry.json`: the free rehearsal before the run.
- `answers.jsonl`: every live answer, with a hashed key, the model, tokens, cost and the
  answer. No text. They replay for free.
- `calls.jsonl`: per call, the trajectory id, its label, and each arm's verdict and p.
- `control.jsonl`: per record, the control's p beside the reference's.
- `analysis.json`: the scoring, the verdict, the seal's state and the spend.
- `diagnosis.json`: the post-hoc diagnosis above, from `benchmarks/a3_mcp/diagnose.py`.
- `prereg-amendment-1.md`, `prereg-amendment-1.manifest.json`, `prereg-amendment-1.sha256`,
  `dry-amendment-1.json`: amendment 1's registration and free rehearsal.
- `answers-control-amendment-1.jsonl` (hashed keys and numbers, no text),
  `control-amendment-1.jsonl` and `analysis-amendment-1.json`: amendment 1's answers, records
  and analysis. `replay.py --control-only`, without `--live`, analyses them again for free.

To reproduce, free, with ATBench-Codex on disk (`SANCHOPANZA_ATBENCH_CODEX`):
- the scoring, at the sealed commit 65528af: `python benchmarks/a3_mcp/replay.py --run`, which
  replays `answers.jsonl`;
- the diagnosis: `python benchmarks/a3_mcp/diagnose.py`.
