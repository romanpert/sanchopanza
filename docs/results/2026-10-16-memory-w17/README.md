# W17: the default install at user scope against clean Claude Code, Sonnet 5.5 (2026-10-16)

**Verdict, by the sealed rule:**
- **Lot S, Sonnet 5.5: "S' better than N0; no gana (cost)". Scoreboard: "no gana".**
  - Claude Code with the default sanchopanza install at user scope (S') continued a two-step
    feature correctly in 48 of 48 pairs. Clean Claude Code (N0) did so in 9 of 48 (39 to 0).
  - The same held when session 2's line named nothing ("Let's continue."): 24 of 24 against 3 of
    24.
  - S' cost a median 1.187x N0 per pair [1.148, 1.244], above the sealed bound of 1.10.
- **Lot O, Opus 5.5: not run to completion; no verdict.** No Opus result is reported here.

The lots are sealed by `prereg.sha256` `49b86f8b873f7260bf5855664bdc237ef12411bbe3d4fe9bb11fb54c13e01cdc`
at commit 5d416fa (instrument f31caf8; prereg.md sha256 `2d01db77…53742`, launcher
`memlot-night-run.cmd` `9114f138…ef9ec`).
- An independent review of the prereg against the code ran before sealing. Its findings were
  fixed before the seal.
- Lot S ran from a detached worktree at 5d416fa with clean Claude Code 2.1.287 (pinned). It was
  started by WMI at 20:07:51 and ended at 22:06:07 with exit 0: 48 pairs, 96 arms.
- Nothing in lot S was resumed, amended or retried.
- `src/` is cbfd932 (memory's C8 fixes and the lean install; unreleased at the time of the run).

## The question and the arms

F2 (`docs/results/2026-10-16-memory-f2`) found that S, the install at **project** scope, finished
the next step from a plain "let's continue with ..." line in 48 of 48 triples against N0's 4, at
1.23x N0's cost. W17 asks whether the default install at **user** scope keeps that gain, also on a
line that names nothing, and whether it now wins without losing on cost.

The scenes and checks are F2's: 12 two-step features, each with a constraint C and a decision D
stated in passing in session 1, and step 2 to be done in session 2 (`scenes_handoff.py`).

| arm | what it is | session 2's prompt |
|---|---|---|
| N0 | clean Claude Code 2.1.287 | the pair's line |
| S' | N0 plus `sanchopanza install --scope user --memory --write` into the arm's own `CLAUDE_CONFIG_DIR`, as it ships: memory on, Jev deciding (`jev-1.13.0`), the `sanchopanza-code` skill, no MCP server, 7 decoy rules in the store | the pair's line |

**Session 2's line, two strata.**
- **named:** the scene's F2 line ("Let's continue with the shipping labels."), repetitions 1-2.
- **bare:** "Let's continue.", naming nothing, repetitions 3-4.

**Kept all** means the step 2 work (`task`), C held (`fact`) and D followed (`decision`), each
checked by code in the repository.

## Result, Sonnet 5.5

| | N0 | S' |
|---|---|---|
| pairs run | 48 | 48 |
| **kept all** | **9** | **48** |
| task / fact (C) / decision (D) | 9 / 9 / 9 | 48 / 48 / 48 |
| intact (step 1) | 48 | 48 |
| repository tests pass | 48 | 48 |
| kept all, named stratum (24 pairs) | 6 | 24 |
| kept all, bare stratum (24 pairs) | 3 | 24 |

| sealed criterion | result |
|---|---|
| S1. S' better than N0 on kept all, one-sided exact McNemar p < 0.05 | 39 to 0, p = 1.8e-12; +81.3 points, one-sided 95 % Tango lower bound +70.4: **holds** |
| S2. the cost ratio's upper bound <= 1.10 | median 1.187, 95 % interval [1.148, 1.244]: **fails** |
| S3. no harm: S' tests within floor(0.125 x 48) = 6 pairs of N0's | 48 vs 48: **holds** |
| S3. no harm: S' sessions 2 sent back by another rule <= 5 % | 0: **holds** |
| sealed secondary: the bare stratum alone, McNemar p < 0.05 | 21 to 0, p = 4.8e-7: **holds** ("the continuation path works on a line that names nothing") |
| scoreboard: headroom (N0 failing in at least 5 % of pairs) | N0 failed 39 of 48: there is room |

The named stratum alone: 18 to 0, p = 3.8e-6. By scene, S' kept all more often than N0 in 11 of
12 scenes and tied in one (`h_nomutate`, 4 and 4).

**Every N0 miss was step 2 not done**, as in F2. Wherever a session built step 2, in either arm,
it kept C and followed D.

**N0 kept all exactly when Claude Code's own auto memory saved the plan in session 1:** in 9 of
those 9 pairs, and in none of the other 39. S' never saved Claude Code's auto memory
(`native_after_1` 0 of 48); memory carried the plan instead.

## What S' gave, and when

- **Session 2, at the prompt, in all 48 S' arms** (`given_in_S` 48), in both strata. Memory's
  continuation cue gave session 1's record at the first prompt, by code, for the bare line too.
  In F2 the record came at the prompt in 36 of 48 Sonnet arms and through the file-touch path in
  the other 12.
- **S' ran as S' in every arm.** Its memory hook answered both SessionStarts in all 48 S' arms
  (`hook_starts_below_2` 0), and every S' session listed the `sanchopanza-code` skill.
- **Jev:** 281 decisions (164 named, 117 bare), 0 failed, 0.009 USD. The preflight answered HTTP
  200 on `jev-1.13.0`.
- **Send-backs:** none. The Stop audit is off by default and stayed off.

## Cost and tokens

**The cost ratio** is, per pair, S's cost (its sessions' own `total_cost_usd` plus its Jev
decisions) over N0's; its statistic is the median over pairs and its interval the sealed
percentile bootstrap (10,000 draws, seed 20261017, pairs in (scene, repetition) order).

| | pairs | S' / N0, median | 95 % interval |
|---|---|---|---|
| **all (the sealed S2)** | 48 | **1.187** | **[1.148, 1.244]** |
| named stratum | 24 | 1.155 | [1.021, 1.246] |
| bare stratum | 24 | 1.217 | [1.179, 1.329] |
| session 1 only (the same prompt and work in both arms; an overhead of the install is not shown) | 48 | 1.052 | [0.961, 1.079] |

- **Cost per arm run, median:** N0 0.1016 USD, S' 0.1235 USD (Jev included).
- **Per session, median:** session 1 N0 0.0582, S' 0.0627 USD; session 2 N0 0.0417, S' 0.0620 USD.
- **Where the extra cost comes from** (descriptive, post hoc, not part of the verdict): in the 39
  pairs where only S' kept all, the ratio's median is 1.225; in the 9 pairs where both arms kept
  all, 0.896. S' costs more mostly because it builds step 2 where N0 stops, which a cheaper
  install cannot remove. The prereg expected this: "no gana on cost".

**Tokens per arm run, median** (input / output / cache read / cache write):

| | N0 | S' |
|---|---|---|
| Sonnet 5.5 | 14 / 1,947.5 / 145,784.5 / 12,860 | 14 / 2,780 / 152,350.5 / 15,692.5 |

**Wall time:** session 2 median 26.95 s (N0) and 35.3 s (S'). The run took 1 h 58 min.

## Against F2's project-scope S (descriptive, not part of the verdict)

| Sonnet 5.5 | F2, S at project scope (src 3fb53f1) | W17, S' at user scope (src cbfd932) |
|---|---|---|
| S kept all | 48 of 48 | 48 of 48 |
| N0 kept all | 4 of 48 | 9 of 48 |
| S / N0 cost, median [interval] | 1.226 [1.141, 1.261] | 1.187 [1.148, 1.244] |
| record given at session 2's prompt | 36 of 48 | 48 of 48 |
| session 1, S / N0, median per pair | 1.077 | 1.052 |

Different nights, different seeds for the interval (F2's was descriptive, seed 20261016) and a
different N0 draw (Claude Code saved its auto memory after 9 sessions 1 here, 4 in F2). S' loads
no MCP server and a shorter skill listing. The two intervals overlap; this is no measured cost
difference between the installs.

## Exclusions and items reported whatever the result

- **NOT RUN: none.** 48 of 48 pairs ran. No timeout, session error, usage limit, cap stop,
  charged session, subagent or midnight crossing.
- **init, all 192 sessions:** Claude Code 2.1.287, `claude-sonnet-5-5`, `apiKeySource` `none`
  (the subscription's OAuth token), no MCP server. Every N0 session listed 3 plugins, 19 skills
  and 5 agents, all Claude Code 2.1.287's own built-ins; every S' session the same plus
  `sanchopanza-code`.
- **Permission mode:** session 1 `auto`, session 2 `default`, in both arms alike (as in F2).
- **Folders the agent touched** (`handoff_call.TOUCH`): N0 named Claude Code's configuration
  folder (`claude-config`) in 9 sessions 1 and 19 sessions 2: Claude Code's own memory at work,
  as in F2. No S' session named any harness file or folder, and no session of either arm named
  `..\..`, another arm's folder, the run's key or Jev files, S's store or logs, `.claude/`,
  `.mcp.json` or `carry_hook`.
- **Secrets:** no token or TypeSafe key in any published file.

## Spend

- **Lot S: 11.18 USD at Claude Code's list price, through the subscription.** Claude Code 11.173
  plus Jev 0.009 plus the preflight. The run cap was 17 USD; the dearest session cost 0.118
  against its 0.50 cap.
- **Lot O:** 6.56 USD recorded in its ledger before it stopped (below).

## Lot O, Opus 5.5: not run to completion

The Opus run started at 22:10:40 and did not run to completion. It has no verdict and no result
is read from it.

## What it means for the product

- **On Sonnet 5.5, the default install carries the plan across sessions, also from a bare
  "Let's continue."**: 48 of 48 against Claude Code alone's 9 (24 of 24 against 3 on the bare
  line), with no request beyond the line and no harm.
- **It is not a "gana":** it cost 1.19x Claude Code alone per pair [1.15, 1.24], above the sealed
  1.10. Descriptively and post hoc (above), the extra cost sits in the pairs where S' did the next
  step and Claude Code alone did not do it; on the same work in session 1 an overhead of the
  install is not shown: 1.05x [0.96, 1.08].
- **Next:** a "gana" on Sonnet needs a cost rule that compares equal work, sealed before its data,
  or scenes where N0 also builds. Opus answers the cost question once its run is completed.

## What this does not show

- **Scenes written by us**, F2's twelve, with F2's note on the checks a natural implementation may
  pass without knowing C or D (`h_loud`, `h_nomutate`, `h_batch`, `h_merge`). No session lost C or
  D, so the scenes did not test that.
- **Headless, one prompt per session.** A session 2 that asks a question counts as not done; in
  real use the person answers, and N0 would recover part of its misses.
- **Repetitions are correlated:** by scene the evidence is 12 scenes (S' ahead in 11, tied in 1),
  not 48 independent trials.
- **Sonnet 5.5 only, clean Claude Code 2.1.287 only.** Later releases may change auto memory.

## Files

| file | what it is |
|---|---|
| `prereg.md`, `prereg.manifest.json`, `prereg.sha256` | the sealed pre-registration and its seal |
| `w17-sonnet-table.json` | the sealed analysis (`handoff_pairs.analyse`) of lot S's rows |
| `rows-w17-sonnet.json` | every arm's row with numbers and flags only: no text the agent or the model wrote, no session id, no path |
| `costs.json` | what lot S spent |

`python benchmarks/memory_carry/handoff_publish.py <lot folder> <this folder> w17-sonnet`
rebuilds these files. It checks that the analysis gives the same text from the full rows and from
the public rows, and that it equals, in every field, the table the night wrote.
