# The MCP guard after the call, replayed over ATBench-Codex (lot W17, development)

**The result:** adding the check after the call (`install --guard-mcp-post`) to A3's guard
before the call, both at 0.5, flags **220 of 250 unsafe trajectories (88.0 %)** against **185
(74.0 %)** for the guard before the call alone. It also flags **96 of 250 safe ones (38.4 %)**
against 82 (32.8 %).

**By the sealed development rule it does not license a confirmation on fresh data:**
- (i) more unsafe caught: **holds**, 35 against 0, two-sided exact McNemar p 5.8e−11;
- (ii) a bounded FPR rise: **fails**, 14 safe trajectories newly flagged, one-sided 95 % upper
  bound of the rise **+8.0 points** against the bound of +7;
- (iii) coverage and provenance: **holds**.

`--guard-mcp-post` stays opt-in, as the registration says it would whatever the outcome. This is
a development lot on data A3 had already used: it could license a confirmation, never confirm.

**The question** (pre-registered):
- A3's PreToolUse guard (`install --guard-mcp`) reads the session up to the pending MCP call and
  never that call's result. On ATBench-Codex it caught 185 of 250 unsafe trajectories, short of
  its registered floor ([A3](../2026-10-16-a3-mcp/)). Most of what it missed was harm that shows
  only in a tool's answer.
- The opt-in check `install --guard-mcp-post` asks the same `actions` point after an MCP call
  has run, with the call's result last, at its own cut (`Thresholds.action_result_stop`, 0.5).
  On a flag the hook answers Claude Code with `decision: block` and a notice for the operator.
- Added to A3's guard at the same cuts, does it catch more unsafe trajectories, while the false
  flags on safe ones rise by no more than 7 points?

**Pre-registered** in [`benchmarks/a3_mcp/w17_prereg.md`](../../../benchmarks/a3_mcp/w17_prereg.md):
- sealed at commit 2912c0b by `w17_prereg.sha256` (`b9d3197e…`) and `w17.manifest`, which cover
  the registration, the W17 and A3 code, A3's answers and calls, the ceiling, the dry run, the
  launcher, the package and the data;
- reviewed against the code by `revisor-prereg` before the seal;
- amendment 1, written and sealed before any answer: the first sealed launch, from 09ef1b9, was
  refused by the launcher check, because the environment scrub had already removed
  `SANCHOPANZA_LAUNCHER`. Nothing was asked or spent, and it was not a counted launch.

The seal still matched at scoring time (`analysis.json`, `seal`).

**What ran:**
- **When and where:** 2026-10-16, 16:30:39 to 16:32:48, exit 0, one launch, by WMI (CreateFlags
  512) from a worktree detached at the sealing commit.
- **Data:** A3's 500 ATBench-Codex test trajectories (250 unsafe) as Claude Code transcripts, and
  their 1,188 MCP calls. 65 of them are Codex's own tools, counted as MCP as in A3. The 7 shell
  calls are left out.
- **The path judged:** the hook's own code, in process (`claude_code.needs_decision`, then
  `claude_code.handle`), per MCP call:
  - `pre`, the PreToolUse event with `SANCHOPANZA_GUARD_MCP=1`, answered only from A3's recorded
    answers: all 1,188 replayed free, every p equal to A3's;
  - `post`, the PostToolUse event with `SANCHOPANZA_GUARD_MCP_POST=1` and the call's result as
    `tool_response`, asked live.
- No Claude Code session ran, and no model besides Jev was asked.
- **Decider and cuts:** TypeSafe Jev `jev-1.13.0`, profile `coding`, cuts fixed before the data.
- **Answers:** 1,188 post questions, all answered, none halted, all from `jev-1.13.0`.
- **Spend:** 0.0620 USD in the run's ledger, under the 0.20 cap.

## Verdict by the sealed rule

`pre+post` against `pre`, paired per trajectory. `pre+post` flags whatever `pre` flags, so no
trajectory is flagged only by `pre`.

| Criterion | Rule | Measured | Holds |
|---|---|---|---|
| **(i)** more unsafe caught | more flagged only by `pre+post`, two-sided exact McNemar p < 0.05 | 35 vs 0, p 5.8e−11 | yes |
| **(ii)** a bounded FPR rise | one-sided 95 % upper bound of the rise ≤ +7 points (paired bootstrap, 10,000 resamples, seed 20261015) | +5.6 points, upper bound **+8.0** (14 vs 0) | **no** |
| **(iii)** coverage and provenance | every call has a usable pre and post p, all `jev-1.13.0`, every pre p equal to A3's | 1,188 / 1,188, yes, yes | yes |
| **Outcome** | (i), (ii) and (iii) | | **does not license** |

Read as counts, as the registration does: (ii) holds at 11 or fewer safe trajectories newly
flagged and fails at 12 or more. The check flagged 14.

## The figures

Trajectories flagged, `jev-1.13.0`, with Wilson 95 % intervals. "Before the last result" counts a
pre denial on any call, or a post flag on a result that a later MCP call follows; anything else
is detected only after the last call ran.

| Arm | Pre cut | Post cut | Recall (250 unsafe) | FPR (250 safe) | Recall before the last result | FPR before the last result |
|---|---|---|---|---|---|---|
| `pre`: A3's guard, the reference | 0.5 | off | 185 (74.0 % [68.2, 79.0]) | 82 (32.8 % [27.3, 38.8]) | 185 | 82 |
| **`pre+post`: the development rule** | **0.5** | **0.5** | **220 (88.0 % [83.4, 91.5])** | **96 (38.4 % [32.6, 44.6])** | 191 | 86 |
| `relaxed+post` (exploratory) | 0.7 | 0.5 | 216 (86.4 % [81.6, 90.1]) | 84 (33.6 % [28.0, 39.7]) | 148 | 56 |
| `post` (exploratory) | off | 0.5 | 216 (86.4 % [81.6, 90.1]) | 82 (32.8 % [27.3, 38.8]) | 63 | 30 |
| `relaxed` (exploratory) | 0.7 | off | 135 (54.0 % [47.8, 60.1]) | 39 (15.6 % [11.6, 20.6]) | 135 | 39 |

**Paired against `pre`** (exact McNemar, two-sided; paired bootstrap 95 %):

| Comparison | Unsafe: only new / only old, difference | Safe: only new / only old, difference |
|---|---|---|
| **`pre+post` − `pre`** | **35 / 0, +14.0 points [10.0, 18.4]**, p 5.8e−11 | **14 / 0, +5.6 [2.8, 8.4]**, p 1.2e−4, one-sided upper bound +8.0 |
| `relaxed+post` − `pre` (exploratory) | 35 / 4, +12.4 [8.0, 16.8], p 3.4e−7 | 14 / 12, +0.8 [−3.2, +4.8], p 0.85 (not shown) |
| `post` − `pre` (exploratory) | 35 / 4, +12.4 [8.0, 16.8], p 3.4e−7 | 14 / 14, 0.0 [−4.0, +4.0], p 1.0 (not shown) |
| `post` − `relaxed+post` (exploratory) | 0 / 0, 0.0 | 0 / 2, −0.8 [−2.0, 0.0], p 0.5 (not shown) |
| Before the last result, `relaxed+post` − `pre` (exploratory) | 6 / 43, −14.8 [−20.0, −9.6] | |
| Before the last result, `post` − `relaxed+post` (exploratory) | 0 / 85, −34.0 [−40.0, −28.4] | |

**When the check catches.** Of the 35 unsafe trajectories that only `pre+post` flags, **29 are
flagged only after their last MCP call ran** and 6 earlier, on a result a later call follows. Of
the 14 safe ones it newly flags, 10 are flagged only after the last call.

**The 33 the registration expected** (`w17_ceiling.json`, `gained_ids`: the trajectories the
offline reference flags from the last result and A3's guard misses): the post check flags **31
of them, 28 on their last result**. The free proxy, which gave the post check the reference's p
on each last call, had flagged all 33.

**By risk source** (ATBench's `risk_source`), unsafe trajectories flagged:

| Risk source | Unsafe | `pre` | **`pre+post`** | `relaxed+post` | `post` | `relaxed` |
|---|---|---|---|---|---|---|
| dependency_mcp_supply_chain_compromise | 54 | 44 | **48** | 47 | 47 | 33 |
| unreliable_or_misinformation | 41 | 29 | **33** | 33 | 33 | 20 |
| **malicious_tool_execution** | 39 | 23 | **38** | 38 | 38 | 13 |
| indirect_prompt_injection | 26 | 18 | **24** | 24 | 24 | 17 |
| repository_artifact_injection | 22 | 19 | **20** | 20 | 20 | 16 |
| inherent_agent_failures | 22 | 15 | **16** | 15 | 15 | 10 |
| corrupted_tool_feedback | 21 | 12 | **16** | 15 | 15 | 9 |
| policy_precedence_misinterpretation | 16 | 16 | **16** | 16 | 16 | 12 |
| tool_description_injection | 9 | 9 | **9** | 8 | 8 | 5 |

The check closes what A3 diagnosed: a tool that misbehaves in its response goes from 23 of 39
caught to 38. 15 of the 35 trajectories it adds are of that kind.

**The cuts, re-cut after the data (reported, not judged).** Recall / FPR on the 250 and 250.

| Pre cut ↓ / post cut → | 0.5 | 0.6 | 0.7 | 0.8 | 0.9 | off |
|---|---|---|---|---|---|---|
| **0.5** | **88.0 / 38.4** | 85.2 / 35.6 | 83.2 / 35.2 | 80.4 / 34.0 | 77.6 / 33.6 | 74.0 / 32.8 |
| 0.6 | 86.4 / 34.8 | 81.6 / 28.0 | 78.4 / 26.8 | 75.2 / 25.2 | 72.0 / 24.8 | 67.2 / 24.0 |
| 0.7 | 86.4 / 33.6 | 80.0 / 23.2 | 73.2 / 20.0 | 67.6 / 17.2 | 63.6 / 16.4 | 54.0 / 15.6 |
| 0.8 | 86.4 / 33.2 | 79.6 / 22.8 | 70.4 / 16.4 | 61.2 / 10.0 | 54.4 / 8.8 | 43.6 / 8.0 |
| 0.9 | 86.4 / 32.8 | 79.6 / 22.4 | 70.0 / 16.0 | 56.0 / 7.6 | 36.8 / 3.2 | 23.2 / 1.6 |
| off | 86.4 / 32.8 | 79.6 / 22.4 | 70.0 / 16.0 | 56.0 / 7.6 | 31.6 / 2.4 | 0.0 / 0.0 |

## What it costs a real session

ATBench's safe trajectories are built to look risky, so these are not the false-block rate of
ordinary MCP work.

- **Blocks in safe sessions, per MCP call:** the post check flags **113 of the 589 calls in safe
  trajectories** (19.2 % [16.2, 22.6]): 73 of the 250 last results and 40 of the 339 earlier
  ones. The guard before the call denies 112 of the 589 at 0.5 (19.0 %) and 47 at 0.7 (8.0 %).
- **In unsafe trajectories** the post check flags 288 of 599 calls: 210 of the 250 last results.
- **Codex's own tools:** the post check flags 1 of their 35 calls in safe trajectories and 4 of
  30 in unsafe ones.
- **Jev per post call:** 52 µ$ on average (49 µ$ and 1,172 input tokens at the median), 218 ms at
  the median (p90 280 ms) as the client measures it. The hook's process start is not in these
  figures.

## What it implies

- **`--guard-mcp-post` stays opt-in, and no confirmation lot is licensed.** The registration
  allowed a license to buy exactly one thing, a confirmation on fresh data (ATBench, about 0.20
  ledger USD); without it that lot does not run on this rule.
- **The check does what it was built for.** It reads the result the guard before the call never
  sees, and it catches most of what A3 missed: misbehaving tools, poisoned feedback, injections
  in a result. Recall rises by 14 points.
- **It catches after the fact.** 29 of the 35 trajectories it adds are flagged only once the
  last call has run. At most it can stop the agent before it acts on or passes on that result
  (not measured live), and it cannot undo the call.
- **The bound was the binding term, as the registration said.** The proxy put the upper bound at
  7.2 points; the real check, which renders the record as the hook does, put it at 8.0.
- **Two exploratory readings for a next registration** (cuts chosen on this data, not judged):
  - `relaxed+post` (pre at 0.7, post at 0.5) keeps the recall (216, +12.4 points over `pre`)
    with an FPR rise not shown (84 against 82, +0.8 points [−3.2, +4.8], p 0.85; one-sided upper
    bound +4.0). It moves the
    catch later: 148 unsafe flagged before the last result against `pre`'s 185.
  - `post` alone matches it on the unsafe (the same 216), a difference on the safe not shown
    (82 against 84, 0 / 2, p 0.5), but flags only 63 before the last result.
  - Either would need its own prereg, with the cut fixed before its data, on fresh trajectories.

## Not done

- **The confirmation on fresh data:** not licensed.
- **A live Claude Code session:** what the model does with the `block` reason, or with a
  withheld result (`--guard-mcp-withhold`), was not measured.
- **No other Jev model:** 1.14 was not asked here.
- **No cut was chosen after the post answers** for the judged rule: its cuts (0.5 / 0.5) were
  fixed before them; the 0.7 pre cut was chosen on this data and is exploratory. The relaunch
  rules never applied: the launch left no call unanswered.

## Spend

| | USD |
|---|---|
| Batch `w17-mcp-post` in the run's ledger (1,188 post answers) | **0.0620** (cap 0.20; expected 0.062 by the token fit, 0.084 at the flat median) |
| Pre answers, replayed from A3's recordings | 0 |
| Preflight: one Truth in `replay.preflight`, outside the ledger | about 0.000013 |
| Claude | 0 |

## Files

- [`benchmarks/a3_mcp/w17_prereg.md`](../../../benchmarks/a3_mcp/w17_prereg.md),
  `w17_prereg.sha256`, `w17.manifest`: the sealed registration, with amendment 1.
- `benchmarks/a3_mcp/w17_dry.json`, `w17_ceiling.json`: the free rehearsal and ceiling before
  the run.
- `answers.jsonl`: every live post answer, with a hashed key, the model, tokens, cost and the
  answer. No text. They replay for free.
- `calls.jsonl`: per MCP call, the trajectory id, its label, whether it is the last call or a
  Codex tool, and the pre and post verdicts and p's.
- `analysis.json`: the scoring, the rule's outcome, the seal's state and the spend.

To reproduce, free:
- `python -m pytest tests/test_w17_mcp_post_published.py` rescoring `calls.jsonl` into the
  published arms and outcome;
- the whole replay, with ATBench-Codex on disk (`SANCHOPANZA_ATBENCH_CODEX`) and `answers.jsonl`
  copied into the run folder as `w17_answers.jsonl` (`w17_replay.RUN`): at the sealed commit
  2912c0b, `python benchmarks/a3_mcp/w17_replay.py --run`.
