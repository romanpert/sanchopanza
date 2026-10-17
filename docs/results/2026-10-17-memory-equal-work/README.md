# Equal work: the default install at user scope against clean Claude Code told once to go on, Sonnet 5.5 (2026-10-17)

**Verdict, by the sealed rule: "gana (éxito)"** (Sonnet 5.5, clean Claude Code 2.1.287).
- Claude Code with the default sanchopanza install at user scope (S') continued a two-step
  feature correctly in 48 of 48 pairs. Clean Claude Code told once "Yes, go ahead." when its
  session 2 left step 2 undone (N0⁺) did so in 3 of 48 (45 to 0, one-sided exact McNemar
  p = 2.8e-14).
- S' cost a median 1.005x N0⁺ per pair [0.949, 1.063]: within the sealed 1.10, not below 1.00.
  No harm.

**What the "gana" rests on.** N0 left step 2 undone after session 2 in 45 of 48 pairs and was
nudged in those 45. **The nudge finished step 2 in 0 of the 45.** It cost N0 a median 0.0232 USD
(1.10 USD over the 45), and that extra round, which did not help, brought N0's cost per pair up to
S's. S' did not get cheaper: it costs what N0 costs when a person tells it to go on, and does the
work N0 then still does not do. On the same rows without the nudge (W17's reading, a sealed
secondary) S' costs 1.247x N0 [1.178, 1.295]: "no gana (cost)", as in W17.

**Which person this models.** The nudge is a person who answers whatever session 2 said with the
same blind "Yes, go ahead.", without repeating the task. A person who repeated it (named step 2,
its constraint and its decision) would be doing memory's work by hand; this lot does not measure
that person.

**Sealed** by `prereg.sha256` `9751680c20b825183f68ab691b8e980635a16a243c800509157718dfe6306b6e`
at commit d1c39af (instrument 1be6051; prereg.md sha256 `09081962…d19cfb`, launcher
`ew-night-run.cmd` `fe91643b…fc40b2`).
- The owner approved the lot (rule R3, 48 Sonnet pairs) and its 22 USD cap on 2026-10-17, before
  any of its data. Independent reviews of the prereg against the code ran before sealing; their
  findings were fixed before the seal, and the sealing commit holds only the seal.
- The lot ran from a detached worktree at d1c39af with clean Claude Code 2.1.287 (pinned), model
  `claude-sonnet-5-5`. It started at 14:43:39 and ended at 16:39:03 with exit 0: 48
  pairs, 96 arms, 45 nudges.
- Nothing was resumed, amended or retried.
- `src/` is as on main 4c143e1 (last changed at 88f5400). The user-scope install it writes is
  byte for byte W17's.

## The question and the arms

W17 (`docs/results/2026-10-16-memory-w17`) found S' continuing a two-step feature in 48 of 48
Sonnet pairs against clean Claude Code's 9, at 1.187x the cost [1.148, 1.244]: "no gana (cost)".
Most of that extra cost was work N0 did not do: an N0 session 2 that did not build step 2 mostly
stopped to ask, and nobody answered. This lot asks the same question at equal work: when a person
answers a session that left step 2 undone with "Yes, go ahead.", does S' still do better without
costing more?

The scenes and checks are F2's (`docs/results/2026-10-16-memory-f2`): 12 two-step features, each
with a constraint C and a decision D stated in passing in session 1, and step 2 to be done in
session 2 (`scenes_handoff.py`).

| arm | what it is | session 2's prompt | the nudge |
|---|---|---|---|
| N0⁺ (`N0` in the rows) | clean Claude Code 2.1.287 | the pair's line | once, when `task` failed after session 2 |
| S' (`S` in the rows) | N0 plus `sanchopanza install --scope user --memory --write` into the arm's own `CLAUDE_CONFIG_DIR`, as it ships: memory on, Jev deciding (`jev-1.13.0`), the `sanchopanza-code` skill, no MCP server, 7 decoy rules in the store; W17's arm | the pair's line | the same rule |

**The nudge (rule R3).** After session 2 the scene's checks ran on a copy of the repository. If
and only if `task` failed (step 2 not in the repository), session 2 was resumed once,
`claude -p --resume <session 2 id> "Yes, go ahead."`, on the tree exactly as session 2 left it,
under the same 0.25 USD call cap. The checks after it decide. Everything arbitrary in the rule
favours N0: the person knows exactly when step 2 is missing, costs nothing, and S' controls
neither the trigger nor the text.

**Session 2's line, two strata, as W17:** named ("Let's continue with the shipping labels."),
repetitions 1-2; bare ("Let's continue."), repetitions 3-4. 24 pairs each.

**Kept all** means the step 2 work (`task`), C held (`fact`) and D followed (`decision`), each
checked by code in the repository. The `task` check imports step 2 by the name and signature
session 1 gave it.

## Result, Sonnet 5.5

| | N0⁺ | S' |
|---|---|---|
| pairs run | 48 | 48 |
| kept all after session 2 | 3 | 48 |
| nudged (task failed after session 2) | 45 | 0 |
| kept all after the nudge, of those nudged | 0 of 45 | — |
| **kept all (the primary)** | **3** | **48** |
| task / fact (C) / decision (D) | 3 / 3 / 3 | 48 / 48 / 48 |
| intact (step 1) | 48 | 48 |
| repository tests pass | 48 | 48 |
| kept all, named stratum (24 pairs) | 2 | 24 |
| kept all, bare stratum (24 pairs) | 1 | 24 |

| sealed rule, in order | result |
|---|---|
| 1. "sin veredicto" with fewer than 40 pairs | 48 pairs: **no** |
| 2. "sin margen" when N0 failed kept all after session 2, before its nudge, in fewer than 5 % of the pairs | N0 failed 45 of 48: **there is room** |
| 3. "gana (coste)": the cost ratio's upper bound below 1.00, Tango's lower bound above −12.5 points, no harm | upper bound 1.063: **fails** (Tango +83.4 and no harm hold) |
| 4. "gana (éxito)": one-sided exact McNemar p < 0.05, the cost ratio's upper bound at most 1.10, no harm | 45 to 0, p = 2.8e-14; median 1.005, 95 % interval [0.949, 1.063] (1.06315 unrounded); no harm: **holds** |
| no harm: S' tests within floor(0.125 x 48) = 6 pairs of N0's | 48 vs 48: **holds** |
| no harm: S' sessions 2 (the nudge included) sent back by another rule in at most 5 % of pairs | 0: **holds** |

S' − N0⁺ on kept all: +93.8 points, one-sided 95 % Tango lower bound +83.4.

**By scene,** S' kept all in 4 of 4 pairs in every scene; N0⁺ in 1 of 4 in `h_nomutate`,
`h_weeks` and `h_pages`, and in none elsewhere: S' ahead in 12 of 12 scenes.

**Every N0⁺ miss was step 2 not done**, as in F2 and W17. Wherever a session built step 2, in
either arm, it kept C and followed D.

**N0's 3 successes came in session 2, with no nudge,** in the three pairs where Claude Code's own
auto memory saved after session 1 (`native_after_1`), and in none of the other 45 (`h_nomutate`
and `h_pages` repetition 1, named; `h_weeks` repetition 4, bare). This is W17's pattern again (9
of 9 there). S' saved Claude Code's auto memory after 1 session 1 of 48.

**Strata** (sealed secondaries, not deciding):

| stratum | pairs | kept all S' / N0⁺ | McNemar | N0 nudged, kept after | cost S' / N0⁺, median [95 %] |
|---|---|---|---|---|---|
| named | 24 | 24 / 2 | 22 to 0, p = 2.4e-7 | 22, 0 | 0.949 [0.908, 1.019] |
| bare | 24 | 24 / 1 | 23 to 0, p = 1.2e-7 | 23, 0 | 1.072 [0.959, 1.089] |

On the named line, that S' costs less than N0⁺ is not shown (the interval reaches 1.019).

## The nudge: what N0 did with "Yes, go ahead."

- **All 45 nudges ran as the rule asks:** each resumed session 2's own session
  (`same_session`), carried its context (`context_carried`), on the tree session 2 left
  (`tree_kept`), and ended with a result. None timed out, none stopped at its cap, none was cut.
- **The cache was warm:** a nudge's first request read a median 23,213 cached tokens against
  session 2's last request's 22,406, and wrote a median 375; no nudge wrote session 2's context
  again.
- **Its cost:** median 0.0232 USD (named 0.0270, bare 0.0213), from 0.0088 to 0.0549, 1.10 USD
  over the 45; a median 20.5 s of wall time.
- **What N0 did** (read from the 45 nudges' streams, post hoc and descriptive; the streams are not
  published):
  - 30 wrote code, but not step 2 as session 1 specified it: a function under another name or
    signature, or changes to step 1's code. In `h_batch`, where session 1 asked for
    `ship_all(orders, carrier)`, the nudge answered: "I added `ship_labels(orders, carrier)` to
    `app/labels.py`, and all 6 tests pass".
  - 11 only cleaned the repository (a `.gitignore`, untracking the committed `__pycache__`):
    "I added a `.gitignore` for `__pycache__/`, `*.pyc` and `.pytest_cache/`."
  - 3 asked again: "\"Go ahead\" could mean a few things, and I don't want to guess. Which do you
    want?"
  - 1 only added tests.
- **What N0's session 2 said without memory** (the same streams): mostly a guess at the next step
  and a question, often beside an offer to clean up the committed bytecode. "There's no saved
  memory or notes about where you were headed." "That's a guess from the code, though, and I
  don't know what you had in mind. What should I work on?" A blind "go ahead" then picked one of
  the options it had offered, or asked again; none of them was step 2 with its C and D.

## What S' gave

- **Session 2, at the prompt, in every S' arm** (`given_in_S` 48 of 48), in both strata:
  memory's continuation cue gave session 1's record at the first prompt, by code. No S' arm was
  nudged.
- **S' ran as S' in every arm:** its memory hook answered both SessionStarts in all 48
  (`hook_starts_below_2` 0), and every S' session listed the `sanchopanza-code` skill.
- **Jev:** 276 decisions, 0 failed, 0.0089 USD; the preflight answered HTTP 200 on
  `jev-1.13.0`.
- **Send-backs:** none. The Stop audit is off by default and stayed off.

## Cost and tokens

**The cost ratio** is, per pair, S's whole cost (its sessions' own `total_cost_usd` plus its Jev
decisions) over N0's whole cost (its sessions and its nudge's own cost); its statistic is the
median over pairs and its interval the sealed percentile bootstrap (10,000 draws, seed 20261021,
pairs in (scene, repetition) order).

| S' / N0 | pairs | median | 95 % interval |
|---|---|---|---|
| **with the nudge (the sealed primary)** | 48 | **1.005** | **[0.949, 1.063]** |
| the same, scenes resampled (12 scenes, each with its pairs; sealed secondary) | 48 | 1.005 | [0.942, 1.068] |
| named stratum | 24 | 0.949 | [0.908, 1.019] |
| bare stratum | 24 | 1.072 | [0.959, 1.089] |
| without the nudge: sessions 1 and 2 and Jev (W17's reading, its seed 20261017) | 48 | 1.247 | [1.178, 1.295] |
| without the nudge, named / bare | 24 / 24 | 1.178 / 1.277 | [1.106, 1.291] / [1.206, 1.347] |
| session 1 only (the same prompt and work in both arms; W17's seed) | 48 | 1.077 | [1.040, 1.152] |

- **Cost per arm, median (Jev included):** N0⁺ 0.1224 USD, S' 0.1219 USD. In all: N0⁺ 6.00 USD,
  S' 5.98 USD.
- **Per session, median:** session 1 N0 0.0574, S' 0.0627 USD; session 2 N0 0.0402, S'
  0.0611 USD; N0's session 2 and nudge together 0.0659 USD per pair.
- **Where a median near 1.00 comes from** (descriptive, post hoc, not part of the verdict): in
  the 45 pairs where N0 was nudged the ratio's median is 1.011; in the 3 where it was not,
  1.073, 0.822 and 0.890. S' pays for building step 2 in session 2; N0⁺ pays about as much for a session 2
  that asks and a nudge that does something else.
- **The install's overhead shows in session 1 on this lot:** on the same work in both arms S'
  cost 1.077x N0 [1.040, 1.152]. On W17's Sonnet lot it was not shown (1.052 [0.961, 1.079]).
- **The secondary W17 reading** of these rows (no nudge): "S' better than N0; no gana (cost)",
  scoreboard "no gana".

**Tokens per arm, median** (input / output / cache read / cache write): N0⁺ 18 / 2,810 / 192,481
/ 13,868; S' 14 / 2,805 / 150,675 / 15,693.

**Wall time, median:** session 1 28.85 s (N0) and 33.85 s (S'); session 2 22.1 s and 30.75 s;
N0's nudge 20.5 s more. The lot took 1 h 55 min.

## Against W17's Sonnet lot (descriptive, not part of the verdict)

| Sonnet 5.5 | W17 (src cbfd932) | this lot (src 4c143e1, the same installed files) |
|---|---|---|
| S' kept all | 48 of 48 | 48 of 48 |
| N0 kept all after session 2 | 9 of 48 | 3 of 48 |
| N0 kept all after the nudge | (no nudge) | 3 of 48 |
| S' / N0 cost without the nudge, median [interval] | 1.187 [1.148, 1.244] | 1.247 [1.178, 1.295] |
| session 1, S' / N0, median [interval] | 1.052 [0.961, 1.079] | 1.077 [1.040, 1.152] |

A different night and a different N0 draw: Claude Code saved its auto memory after 9 sessions 1 in
W17 and after 3 here, and N0 kept all exactly there both times.

## Exclusions and items reported whatever the result

- **NOT RUN: none.** 48 of 48 pairs ran. No timeout, session error, usage limit, call stopped
  by its cap, charged call, subagent or midnight crossing. No pair lost to a nudge NOT RUN
  (`lost_to_nudge` 0); no N0 arm at zero cost.
- **The two readings of the checks agree:** in every arm not nudged, the checks after session 2
  (on a copy) and at the end (in the agent's tree) gave the same result (`checks_disagree` 0 in
  both arms).
- **init, all 237 calls** (192 sessions, 45 nudges): Claude Code 2.1.287, `claude-sonnet-5-5`,
  `apiKeySource` `none` (the subscription's OAuth token), no MCP server. Every N0 call listed 3
  plugins, 19 skills and 5 agents, all Claude Code 2.1.287's own built-ins; every S' session the
  same plus `sanchopanza-code`.
- **Permission mode:** session 1 `auto`, session 2 `default`, the nudge `default`, in both arms
  alike.
- **No cache tilt between the arms:** the first request of session 1 read 16,183 cached tokens in
  all 96 arms, N0 and S' alike (from the streams; not in the published rows).
- **Folders the agent touched** (`handoff_call.TOUCH`): Claude Code's configuration folder
  (`claude-config`), that is Claude Code's own memory at work: N0 named it in 3 sessions 1 and 10
  sessions 2, S' in 1 session 1. No nudge named any harness file or folder. No call of either arm
  named `..\..`, another arm's folder, the run's key or Jev files, S's store or logs, `.claude/`,
  `.mcp.json` or `carry_hook`.
- **`cost_source` of the nudges** reads `running total minus session 1` in the rows, the label
  the recorded run gives every running reading: the nudge's own cost is the running total less
  session 2's cost (the session it resumed), which equals its tokens at Claude Code's rates.
- **Secrets:** no token or TypeSafe key in any published file.

## Spend

- **11.98 USD at Claude Code's list price, through the subscription** (11.9813 in the run's
  ledger): Claude Code 11.972 plus Jev 0.0089 plus the preflight. The 45 nudges are 1.10 of it.
- The prereg expected 12.5 to 13.7 USD; the run cap was 22 USD; the dearest call cost 0.088
  against its 0.25 cap.

## What it means for the product

- **On Sonnet 5.5, against clean Claude Code that a person tells once "Yes, go ahead.", the
  default install is "gana (éxito)" by the scoreboard's rule 2.4 as this lot sealed it:** 48 of
  48 against 3, at 1.005x the cost [0.949, 1.063], with no harm. With these scenes, S' reaches
  step 2 done with more success than clean Claude Code told to go on once, at no more than 1.10x
  its cost.
- **It is not a saving.** S' costs what N0⁺ costs; it is not "S' is cheaper than Claude Code".
  The parity comes from N0's extra round, which did step 2 in 0 of 45 pairs. Without that round
  S' costs 1.25x [1.18, 1.30] (W17's reading of the same rows).
- **The person here answers blind.** A person who answers with the task itself would close part
  of N0's gap by hand, at the cost of their own time; that is not measured here. The nearest
  measured case is F2's handoff ritual (session 1 writes a handoff that is pasted into session 2):
  there S, at project scope, did the next step in 48 of 48 triples against the ritual's 44, at
  0.92x its cost [0.85, 0.95] (`docs/results/2026-10-16-memory-f2`).
- **Next:** a lot whose person repeats the task (a comparator that does memory's work by hand),
  or new scenes, sealed before their data.

## What this does not show

- **The person's time and the round trip's latency** (wall time is reported, not deciding); a
  person who answers with information; more than one nudge.
- **Scenes written by us**, F2's twelve, chosen knowing that N0 stops in them; with F2's note on
  the checks a natural implementation may pass without knowing C or D (`h_loud`, `h_nomutate`,
  `h_batch`, `h_merge`). Generalising needs new scenes.
- **Repetitions are correlated:** by scene the evidence is 12 scenes (S' ahead in 12 of 12; the
  cost interval with scenes resampled [0.942, 1.068]), not 48 independent trials.
- **Headless, one prompt per session plus the nudge.**
- **Sonnet 5.5 only, clean Claude Code 2.1.287 only.** No Opus lot (on Opus, N0 already kept all
  in 31 of 36 W17 pairs). If a later Claude Code stops less often to ask, or its own auto memory
  always keeps the plan (as on Opus), the gap goes away.

## Files

| file | what it is |
|---|---|
| `prereg.md`, `prereg.manifest.json`, `prereg.sha256` | the sealed pre-registration and its seal (commit d1c39af) |
| `ew-sonnet-table.json` | the sealed reading (`handoff_ew.analyse`) of the lot's rows |
| `rows-ew-sonnet.json` | every arm's row with numbers and flags only: no text the agent or the model wrote, no session id, no path; the checks after session 2 and the nudge's numbers |
| `costs.json` | what the lot spent |

`python benchmarks/memory_carry/handoff_publish.py <the lot's folder> <this folder> ew-sonnet`
rebuilds these files, byte for byte on a repeat. It checks that the reading gives the same text
from the full rows and from the public rows, and that it equals, in every field, the table the
night wrote. The night's reading can be run again free with
`python benchmarks/memory_carry/handoff_ew.py <the lot's folder>/ew-sonnet`.
