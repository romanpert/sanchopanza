# W17: the default install at user scope against clean Claude Code, Sonnet 5.5 and Opus 5.5 (2026-10-16 and 2026-10-17)

**Verdict, by the sealed rule:**
- **Lot S, Sonnet 5.5: "S' better than N0; no gana (cost)". Scoreboard: "no gana".**
  - Claude Code with the default sanchopanza install at user scope (S') continued a two-step
    feature correctly in 48 of 48 pairs. Clean Claude Code (N0) did so in 9 of 48 (39 to 0).
  - The same held when session 2's line named nothing ("Let's continue."): 24 of 24 against 3 of
    24.
  - S' cost a median 1.187x N0 per pair [1.148, 1.244], above the sealed bound of 1.10.
- **Lot O, Opus 5.5: "not determined". Scoreboard: "no gana".**
  - S' cost the same as N0: a median 0.999x per pair [0.965, 1.055]. The sealed O1 needs the
    upper bound at 1.05 or below; it is 1.05549 unrounded, 0.0055 above.
  - S' kept the plan in 34 of 36 pairs, N0 in 31 of 36 (3 to 0). Not worse by the sealed margin
    (O2 holds), and not shown to be better: one-sided McNemar p = 0.125.

**Lot S** is sealed by `prereg.sha256` `49b86f8b873f7260bf5855664bdc237ef12411bbe3d4fe9bb11fb54c13e01cdc`
at commit 5d416fa (instrument f31caf8; prereg.md sha256 `2d01db77…53742`, launcher
`memlot-night-run.cmd` `9114f138…ef9ec`).
- An independent review of the prereg against the code ran before sealing. Its findings were
  fixed before the seal.
- Lot S ran from a detached worktree at 5d416fa with clean Claude Code 2.1.287 (pinned). It was
  started by WMI at 20:07:51 and ended at 22:06:07 with exit 0: 48 pairs, 96 arms.
- Nothing in lot S was resumed, amended or retried.
- `src/` is cbfd932 (memory's C8 fixes and the lean install; unreleased at the time of the run).

**Lot O** is the run of the prereg's Amendment 1 (`prereg.md`, its last section). A first Opus
run, started on 2026-10-16, was interrupted before it ended; it was discarded whole, and none of it
is read for any figure here. The amendment, written and sealed before the repeat's data, repeats
lot O whole and clean with the same arms, scenes, call and run caps, criteria and analysis.
- Sealed by `prereg.sha256` `d4e379a528fefc8822a9925c66c6de330d3bed9693975e99d6a5f9b7f0b024bc`
  at commit 941c9a9 (instrument 9fe1fcf; prereg.md sha256 `fb3ba33f…ba74c`, launcher
  `memlot-night-run.cmd` `085985fe…bd599`), after an independent review of the amendment
  against the code.
- Lot O ran from a detached worktree at 941c9a9 with clean Claude Code 2.1.287 (pinned), model
  `claude-opus-5-5`. It was started by WMI on 2026-10-17 at 09:09:55 and ended at 10:58:53 with
  exit 0: 36 pairs, 72 arms.
- Nothing in lot O was resumed or retried.
- `src/` is cbfd932 plus the amendment's change 1, which changes how state files are written,
  not what they hold; S' installs the same files as in lot S.

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
- **bare:** "Let's continue.", naming nothing: repetitions 3-4 on Sonnet, repetition 3 on Opus.

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

## Result, Opus 5.5

| | N0 | S' |
|---|---|---|
| pairs run | 36 | 36 |
| **kept all** | **31** | **34** |
| task / fact (C) / decision (D) | 31 / 31 / 31 | 34 / 34 / 34 |
| intact (step 1) | 36 | 36 |
| repository tests pass | 36 | 36 |
| kept all, named stratum (24 pairs) | 21 | 22 |
| kept all, bare stratum (12 pairs) | 10 | 12 |

| sealed criterion | result |
|---|---|
| "costs extra" first: the cost ratio's lower bound above 1.00 | lower bound 0.965: **no** |
| O1 (primary). the cost ratio's upper bound <= 1.05 | median 0.999, 95 % interval [0.965, 1.055] (upper bound 1.05549 unrounded): **fails** |
| O2. kept all not worse: one-sided 95 % Tango lower bound above -12.5 points | 3 to 0, +8.3 points, lower bound +0.8: **holds** |
| O3. no harm: S' tests within floor(0.125 x 36) = 4 pairs of N0's | 36 vs 36: **holds** |
| O3. no harm: S' sessions 2 sent back by another rule <= 5 % | 0: **holds** |
| scoreboard: headroom (N0 failing in more than 1 of 36 pairs) | N0 failed 5 of 36: there is room |
| scoreboard: "gana (coste)" (upper bound below 1.00) or "gana (éxito)" (McNemar p < 0.05 within 1.05) | upper bound 1.055; 3 to 0, p = 0.125: **neither** |

**The difference in success is not shown.** S' kept all in 3 pairs where N0 did not, and N0 in
none where S' did not: one-sided exact McNemar p = 0.125. By stratum: named 22 against 21 (1 to
0, p = 0.5), bare 12 against 10 (2 to 0, p = 0.25). By scene, S' kept all more often in 2 of 12
scenes (`h_semicolon` 3 and 1, `h_judge` 1 and 0) and tied in 10.

**Cost is at parity**, within the bootstrap's interval of about 3.5 % below to 5.5 % above N0.
The prereg's power section expected "not determined" if S' truly costs the same as N0: O1 holds
with probability 0.25 at 1.00x over 36 pairs.

**Every miss, in either arm, was step 2 not done.** Wherever a session built step 2 it kept C
and followed D. As in F2, `h_judge` (an urgency verdict with no cutoff given, which its C forbids
the code to pick) holds both S' misses and 3 of N0's 5; N0's other 2 are `h_semicolon`
(repetitions 1 and 3).

**Claude Code's own auto memory saved after every Opus session 1, in both arms**
(`native_after_1` 36 of 36 in N0 and in S'), as it did in every F2 Opus arm. That is why N0
keeps 31 of 36 on Opus and S' has little to add.

## What S' gave, and when

- **Session 2, at the prompt, in every S' arm** (`given_in_S` 48 of 48 on Sonnet, 36 of 36 on
  Opus), in both strata. Memory's continuation cue gave session 1's record at the first prompt,
  by code, for the bare line too. In F2 the record came at the prompt in 36 of 48 Sonnet arms and
  18 of 24 Opus arms, through the file-touch path in the others.
- **S' ran as S' in every arm.** Its memory hook answered both SessionStarts in all 84 S' arms
  (`hook_starts_below_2` 0 in both lots), and every S' session listed the `sanchopanza-code`
  skill.
- **Jev:** Sonnet 281 decisions (164 named, 117 bare), 0 failed, 0.009 USD; Opus 227 decisions
  (168 named, 59 bare), 0 failed, 0.007 USD. Each lot's preflight answered HTTP 200 on
  `jev-1.13.0`.
- **Send-backs:** none in either lot. The Stop audit is off by default and stayed off.

## Cost and tokens

**The cost ratio** is, per pair, S's cost (its sessions' own `total_cost_usd` plus its Jev
decisions) over N0's; its statistic is the median over pairs and its interval the sealed
percentile bootstrap (10,000 draws, seed 20261017, pairs in (scene, repetition) order).

| S' / N0 | pairs | median | 95 % interval |
|---|---|---|---|
| **Sonnet 5.5, all (the sealed S2)** | 48 | **1.187** | **[1.148, 1.244]** |
| Sonnet 5.5, named stratum | 24 | 1.155 | [1.021, 1.246] |
| Sonnet 5.5, bare stratum | 24 | 1.217 | [1.179, 1.329] |
| Sonnet 5.5, session 1 only (the same prompt and work in both arms; an overhead of the install is not shown) | 48 | 1.052 | [0.961, 1.079] |
| **Opus 5.5, all (the sealed O1)** | 36 | **0.999** | **[0.965, 1.055]** |
| Opus 5.5, named stratum | 24 | 0.999 | [0.962, 1.057] |
| Opus 5.5, bare stratum | 12 | 1.000 | [0.957, 1.162] |
| Opus 5.5, session 1 only (the same prompt and work in both arms) | 36 | 1.088 | [1.056, 1.120] |

- **Cost per arm run, median (Jev included):** Sonnet N0 0.1016 USD, S' 0.1235 USD; Opus N0
  0.2937 USD, S' 0.2892 USD.
- **Per session, median:** Sonnet session 1 N0 0.0582, S' 0.0627 USD; session 2 N0 0.0417, S'
  0.0620 USD. Opus session 1 N0 0.1210, S' 0.1311 USD; session 2 N0 0.1736, S' 0.1632 USD.
- **On Opus the install's overhead shows in session 1**, where both arms do the same work: S'
  cost 1.088x N0 [1.056, 1.120]. Over the pair it is offset in session 2 (medians 0.1632
  against 0.1736 USD); why is not measured here.
- **Where the extra cost comes from** (descriptive, post hoc, not part of the verdict):
  - Sonnet: in the 39 pairs where only S' kept all, the ratio's median is 1.225; in the 9 pairs
    where both arms kept all, 0.896. S' costs more mostly because it builds step 2 where N0
    stops, which a cheaper install cannot remove. The prereg expected this: "no gana on cost".
  - Opus: in the 31 pairs where both arms kept all, 0.986; in the 3 where only S' did, 1.300; in
    the 2 where neither did, 1.202.

**Tokens per arm run, median** (input / output / cache read / cache write):

| | N0 | S' |
|---|---|---|
| Sonnet 5.5 | 14 / 1,947.5 / 145,784.5 / 12,860 | 14 / 2,780 / 152,350.5 / 15,692.5 |
| Opus 5.5 | 20 / 4,878 / 217,063 / 18,859.5 | 18 / 4,467.5 / 198,567 / 20,027.5 |

**Wall time:** session 2 median 26.95 s (N0) and 35.3 s (S') on Sonnet, 40.95 s and 44.9 s on
Opus. Lot S took 1 h 58 min, lot O 1 h 49 min.

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

| Opus 5.5, named line | F2, S at project scope (24 triples) | W17, S' at user scope (24 named pairs) |
|---|---|---|
| S kept all | 22 of 24 | 22 of 24 |
| N0 kept all | 21 of 24 | 21 of 24 |
| S / N0 cost, median [interval] | 1.105 [1.011, 1.158] | 0.999 [0.962, 1.057] |
| record given at session 2's prompt | 18 of 24 | 24 of 24 |

On Opus the named line gave the same counts in both installs. F2's interval lies above 1 and
W17's reaches below it, but the two overlap (different nights and seeds, as above): this is no
measured cost difference between the installs.

## Exclusions and items reported whatever the result

- **NOT RUN: none.** 48 of 48 Sonnet pairs and 36 of 36 Opus pairs ran. No timeout, session
  error, usage limit, cap stop, charged session, subagent or midnight crossing in either lot.
- **init, all 192 Sonnet and 144 Opus sessions:** Claude Code 2.1.287, `claude-sonnet-5-5` or
  `claude-opus-5-5`, `apiKeySource` `none` (the subscription's OAuth token), no MCP server. Every
  N0 session listed 3 plugins, 19 skills and 5 agents, all Claude Code 2.1.287's own built-ins;
  every S' session the same plus `sanchopanza-code`.
- **Permission mode:** session 1 `auto`, session 2 `default`, in both arms alike (as in F2).
- **Folders the agent touched** (`handoff_call.TOUCH`): Claude Code's configuration folder
  (`claude-config`), that is Claude Code's own memory at work, as in F2. On Sonnet N0 named it in
  9 sessions 1 and 19 sessions 2, and no S' session named any harness file or folder. On Opus N0
  named it in 36 sessions 1 and 36 sessions 2, S' in 36 and 34. No session of either arm in
  either lot named `..\..`, another arm's folder, the run's key or Jev files, S's store or logs,
  `.claude/`, `.mcp.json` or `carry_hook`.
- **Secrets:** no token or TypeSafe key in any published file.

## Spend

- **Lot S: 11.18 USD at Claude Code's list price, through the subscription.** Claude Code 11.173
  plus Jev 0.009 plus the preflight. The run cap was 17 USD; the dearest session cost 0.118
  against its 0.50 cap.
- **Lot O: 21.32 USD at list price, through the subscription.** Claude Code 21.308 plus Jev
  0.007 plus the preflight. The run cap was 33 USD; the dearest session cost 0.261 against its
  0.80 cap.
- **The interrupted first Opus run:** about 7.2 USD (Amendment 1, "Caps and cost"), not used
  for any figure.
- **The lot in all: about 39.7 USD** (11.18 + 7.2 + 21.32).

## What it means for the product

- **On Sonnet 5.5, the default install carries the plan across sessions, also from a bare
  "Let's continue."**: 48 of 48 against Claude Code alone's 9 (24 of 24 against 3 on the bare
  line), with no request beyond the line and no harm.
- **On Sonnet it is not a "gana":** it cost 1.19x Claude Code alone per pair [1.15, 1.24], above
  the sealed 1.10. Descriptively and post hoc (above), the extra cost sits in the pairs where S'
  did the next step and Claude Code alone did not do it; on the same work in session 1 an
  overhead of the install is not shown: 1.05x [0.96, 1.08].
- **On Opus 5.5 it costs the same as Claude Code alone and is not shown to do better:** 0.999x
  [0.965, 1.055] per pair, 34 of 36 against 31 (p 0.125), no harm. Claude Code saved its own
  auto memory after every Opus session 1, in both arms, and alone kept the plan in 31 of 36. "No extra cost"
  would have needed the upper bound at 1.05; it is 1.055: "not determined", not a "gana".
- **Next:** a "gana" on Sonnet needs a cost rule that compares equal work, sealed before its data,
  or scenes where N0 also builds. On Opus the lever is the install's own overhead, seen in
  session 1 (1.09x [1.06, 1.12] on the same work): a cheaper first session could move the pair's
  ratio below 1, which "gana (coste)" asks for. At a true parity, 36 pairs show "no extra cost"
  with probability 0.25 (the prereg's power), so parity alone needs more pairs.

## What this does not show

- **Scenes written by us**, F2's twelve, with F2's note on the checks a natural implementation may
  pass without knowing C or D (`h_loud`, `h_nomutate`, `h_batch`, `h_merge`). No session lost C or
  D, so the scenes did not test that.
- **Headless, one prompt per session.** A session 2 that asks a question counts as not done; in
  real use the person answers, and N0 would recover part of its misses.
- **Repetitions are correlated:** by scene the evidence is 12 scenes (Sonnet: S' ahead in 11,
  tied in 1; Opus: S' ahead in 2, tied in 10), not 48 or 36 independent trials.
- **Sonnet 5.5 and Opus 5.5 only, clean Claude Code 2.1.287 only.** Later releases may change
  auto memory.

## Files

| file | what it is |
|---|---|
| `prereg.md`, `prereg.manifest.json`, `prereg.sha256` | the sealed pre-registration with its Amendment 1, and the amendment's seal (lot S's seal files are in commit 5d416fa) |
| `w17-sonnet-table.json`, `w17-opus-table.json` | the sealed analysis (`handoff_pairs.analyse`) of each lot's rows |
| `rows-w17-sonnet.json`, `rows-w17-opus.json` | every arm's row with numbers and flags only: no text the agent or the model wrote, no session id, no path |
| `costs.json` | what each lot spent |

`python benchmarks/memory_carry/handoff_publish.py <lot S's folder> <this folder> w17-sonnet` and
`python benchmarks/memory_carry/handoff_publish.py <lot O's folder> <this folder> w17-opus`
rebuild these files; each keeps the other lot's entry in `costs.json`. Each checks that the
analysis gives the same text from the full rows and from the public rows, and that it equals, in
every field, the table the night wrote.
