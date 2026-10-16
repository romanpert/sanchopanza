# F2: memory against the handoff ritual, Sonnet 5.5 and Opus 5.5 (2026-10-16)

**Verdict, by the sealed rule:**
- **Sonnet 5.5: "S not worse than H; S better than N0."** Claude Code with sanchopanza (S)
  continued a two-step feature correctly in 48 of 48 triples. With the handoff ritual (H) it did
  so in 44. Clean Claude Code with a plain "let's continue" line (N0) did so in 4.
- **Opus 5.5: "direction only: S not worse than H"; S better than N0 is not shown.** S 22,
  H 17, N0 21 of 24. On Opus, Claude Code's own auto memory saved the plan after every
  session 1, in every arm, and the ritual scored lowest (17 against N0's 21; 1 to 5, p 0.11, not
  shown).

**How it reads on the final scoreboard.** F2's prereg seals no cost condition; the scoreboard's
"gana" asks for more success at p < 0.05 without losing on cost. On Sonnet 5.5, S cost 1.23x N0
with a descriptive interval of [1.14, 1.26] (below), entirely above 1, so F2 is reported there by
its sealed verdict and not as "gana": a trade against doing nothing, and a substitute for the
ritual at 0.92x its cost [0.85, 0.95].

The lot is sealed by `prereg.sha256` `b7745da349278df9afce032caac1924b55310edde35e2163fb3281b5480c85f3`
at commit 763dafd (prereg.md sha256 `6094536a…ae072`, launcher `f2-night-run.cmd`
`866ac1dd…c189e`).
- An independent review of the prereg against the code found one blocking issue and eight
  others before sealing. All were fixed before the seal.
- The night ran from a detached worktree at 763dafd with clean Claude Code 2.1.287. It was
  started by WMI at 06:35:10 and ended at 10:49:26 with exit 0: f2-pilot, its automatic gate
  (passed), f2-sonnet, then f2-opus.
- Nothing was resumed, amended or retried.
- `src/` is origin/main 3fb53f1.

## The question and the arms

The owner carries work across sessions with a handoff. At the end of a session he asks for a
prompt to continue in a clean session, and pastes it as the next session's first prompt. Each
of the 12 scenes is one feature in two steps:
- Session 1 gives the plan (step 1 today, step 2 next session) and asks for step 1 only.
- In passing, it states a constraint C (a working preference in six scenes) and a decision D
  about step 2 (in three scenes D reverses a plan made earlier in the same prompt).
- Session 2 must do step 2.

| arm | session 2's prompt |
|---|---|
| N0 | clean Claude Code; a fixed line, "Let's continue with the shipping labels." |
| H | clean Claude Code; session 1 resumed once with "Give me a prompt to continue this work in a clean session.", and its answer pasted as session 2's prompt, verbatim |
| S | clean Claude Code plus `sanchopanza install --scope project` as it ships (memory on by default, Jev deciding, 7 decoy rules in the store); the same line as N0 |

**Kept all** means the step 2 work (`task`), C held (`fact`) and D followed (`decision`), each
checked by code in the repository.

## Result

| | Sonnet N0 | Sonnet H | Sonnet S | Opus N0 | Opus H | Opus S |
|---|---|---|---|---|---|---|
| triples run | 48 | 48 | 48 | 24 | 24 | 24 |
| **kept all** | **4** | **44** | **48** | **21** | **17** | **22** |
| task | 4 | 44 | 48 | 21 | 17 | 22 |
| fact (C) | 4 | 44 | 48 | 21 | 17 | 22 |
| decision (D) | 4 | 44 | 48 | 21 | 17 | 22 |
| intact (step 1) | 48 | 48 | 48 | 24 | 24 | 24 |
| repository tests pass | 48 | 48 | 48 | 24 | 24 | 24 |

| sealed criterion | Sonnet 5.5 | Opus 5.5 (direction only) |
|---|---|---|
| 1. S - H, one-sided 95 % Tango lower bound > -12.5 points | +8.3 points, lower bound **+2.6**: holds | +20.8 points, lower bound **+8.6**: holds |
| 2. S better than N0, one-sided exact McNemar p < 0.05 | 44 to 0, p = 5.7e-14: holds | 1 to 0, p = 0.5: not shown |
| 5. no harm: tests within floor(0.125 x triples) of H | 48 vs 48: holds | 24 vs 24: holds |
| 5. no harm: S session 2 sent back by another rule <= 5 % | 0: holds | 0: holds |

**Every miss in every arm was step 2 not done.**
- Wherever a session built step 2, it kept C and followed D, in all six arm-model cells.
- So this lot measured whether the agent knew what came next and did it. It did not measure a
  constraint said in passing being lost; no session lost one.
- How the misses happened (read on the machine from the final message of each missed session
  2; the transcripts are not published):
  - **N0 on Sonnet** ended its turn with a question or an offer to proceed instead of building
    in 35 of its 44 misses. The other 9 did not build the planned step 2 either.
  - **H's 4 Sonnet misses and 6 of its 7 Opus misses**: the handoff itself listed open choices,
    and session 2 stopped to ask about them.
  - **S's 2 Opus misses** and **2 of N0's 3** are the same scene, `h_judge`. Asked for an
    urgency verdict with no cutoff given, every arm asked for the threshold. The scene leaves
    that choice open; its C forbids a cutoff the code picks itself.

Other comparisons (reported, not deciding):
- **S against H:** 4 to 0 on Sonnet (McNemar p = 0.0625), 5 to 0 on Opus (p = 0.031).
- **H against N0:** on Sonnet the ritual helps a great deal: 41 to 1, +83.3 points (Tango lower
  bound +69.4).
- On Opus the ritual **scored lowest**: H kept all in 17, N0 in 21, 1 to 5, -16.7 points
  (p = 0.11 that N0 is better: not shown). It cost about the same as doing nothing.

## Why Opus has no room: Claude Code's own auto memory

| auto memory saved after session 1 | N0 | H | S |
|---|---|---|---|
| Sonnet 5.5 (of 48) | 4 | 10 | 0 |
| Opus 5.5 (of 24) | 24 | 24 | 24 |

- **On Sonnet, N0 kept all exactly when Claude Code saved its own memory in session 1** (4 of
  4), and never when it did not (0 of 44).
- **Opus saved its own auto memory after every session 1 of every arm** (for example a file
  "Pending step 2 — ship_all(orders, carrier) ...", read on the machine), and opened that
  folder again in most sessions 2.
  - That is why N0 keeps 21 of 24 on Opus, and S cannot add much.
- **Folders the agent touched.** The runner flags any session whose tool calls name Claude
  Code's configuration folder (`claude-config`).
  - Opus did this in every session 1 and in 24 / 13 / 23 of the N0 / H / S sessions 2. Sonnet
    did it in 35 sessions (N0 18, H 17), none of them S's.
  - Every such call is inside Claude Code's project folder for that repository; 275 of 335
    name its `memory/` subfolder. None opened a session transcript.
  - This is Claude Code's native memory working as designed, not a leak from the harness.
  - No session named `.claude/`, `.mcp.json`, `carry_hook` or S's `store`.
- Criteria 1 and 2 recomputed without the triples whose S session 2 touched that folder (as the
  prereg asked):
  - Sonnet: none dropped.
  - Opus: 23 of 24 dropped; the single triple left supports no reading.

## What S gave, and when

- **Session 1.** At its Stop, memory's rule extraction (one Jev decision per prompt sentence)
  stored 1-3 standing rules from session 1's prompt in every S arm.
- **Session 2, at start.** SessionStart gave the standing rules, newest first, after the
  7 decoys.
- **Session 2, the record.** Session 1's record came:
  - at the "continue" prompt in 36 of 48 Sonnet arms and 18 of 24 Opus arms (Jev at the prompt
    gate);
  - through the file-touch path in the other 12 and 6: on Sonnet at a Read of a step-1 file in
    7 and at the first shell write to one in 5 (after that write); on Opus at a Read in all 6.
    The split follows the continue line: in the 9 scenes whose line names a file step 1 wrote,
    the record came at the prompt; in the 3 whose line names none, the prompt gate keeps no
    record that changed files.
- Every S arm got session 1's record in session 2.
- The draft expected the prompt gate to hold the record back at a "continue" line. It did so
  in a quarter of the arms, and the file-touch path covered those.
- **Jev:** 377 decisions on Sonnet and 195 on Opus, 0 failed. Cost 0.012, 0.006 and 0.001 USD
  (pilot), with the preflight answering HTTP 200 on `jev-1.13.0`.
- **Send-backs:** none. The Stop audit is off by default and stayed off.

## The handoffs

- **Captured and pasted every time.** The resumed turn answered in all 48 Sonnet and 24 Opus H
  triples. Each time it reported its cost, carried session 1's context, and stayed in the same
  session id.
  - Session 2's transcript shows the pasted text equal to `handoff.txt` byte for byte in 72 of
    72 (`pasted_verbatim`).
- **Length:**
  - Sonnet median 1,575 characters (max 2,076), 560 output tokens (max 1,352).
  - Opus median 1,372 characters (max 1,792), 556 output tokens (max 894).
- **Content:** every handoff named the scene's C and its D (key phrases fixed before the run):
  48 of 48 and 24 of 24.
  - The ritual did not lose what was said. Where it failed, it handed over questions with the
    plan.
- **User effort.** H takes one more request and one paste per session end. S and N0 take none
  after a one-time install.

## Cost and tokens

**Cost per triple, median, at Claude Code's list price.**
- S includes its Jev decisions.
- H includes its handoff turn at the turn's own cost. For a resumed `claude -p` turn, Claude
  Code 2.1.287 reports `total_cost_usd` as the session's running total (session 1 plus the turn).
  - The turn's own cost is that total minus session 1's.
  - That equals the turn's own tokens priced at Claude Code's rates, to within 2e-17 USD in all
    76 handoffs (`costs.json`).

| | N0 | H | S | S / H (paired median) | S / N0 |
|---|---|---|---|---|---|
| Sonnet 5.5 | 0.105 USD | 0.142 USD | 0.127 USD | **0.917** | 1.226 |
| Opus 5.5 | 0.297 USD | 0.305 USD | 0.325 USD | **1.060** | 1.105 |

**The ratios' spread** (descriptive and post hoc, not in the prereg, never deciding): paired
bootstrap 95 % intervals of the median per triple, resampling triples, 10,000 draws, seed
20261016, the same pairing as the table (H's handoff turn at its own cost, Jev added to S):

| | S / N0 | S / H |
|---|---|---|
| Sonnet 5.5 (48 triples) | 1.226 [1.141, 1.261] | 0.917 [0.853, 0.946] |
| Opus 5.5 (24 triples) | 1.105 [1.011, 1.158] | 1.060 [1.009, 1.183] |

`python benchmarks/memory_carry/handoff_cost_ci.py docs/results/2026-10-16-memory-f2` gives
these from the public rows. On Sonnet S cost more than N0 and less than H across each interval;
on Opus it cost more than both.

H's handoff turn costs:
- a median of 0.012 USD on Sonnet and 0.021 USD on Opus;
- 560 output tokens over about 23,500 cached input tokens.

**Tokens per arm run, median** (input / output / cache read / cache write):

| | N0 | H | S |
|---|---|---|---|
| Sonnet 5.5 | 15 / 2,091 / 157,074 / 13,157 | 18 / 4,161 / 193,079 / 15,695 | 14 / 2,786 / 156,646 / 16,246 |
| Opus 5.5 | 20 / 5,053 / 217,149 / 18,909 | 20 / 5,345 / 217,324 / 18,845 | 20 / 4,956 / 231,662 / 21,695 |

**Wall time** (each session's `seconds` in the public rows): session 2 median 20.4 / 26.75 /
26.8 s on Sonnet and 40.8 / 41.3 / 44.45 s on Opus (N0 / H / S). The night took 4 h 14 min.

## Exclusions and items reported whatever the result

- **NOT RUN: none.**
  - 72 of 72 triples ran, plus the 4 pilot triples (not data).
  - There was no usage limit, timeout, harness cut, exception, cap stop, differing paste or
    midnight crossing.
- **Pilot gate:** (a) to (e) all held, 12 of 12 arms (`gate.md`, `gate.json`).
- **init, all 456 sessions:** Claude Code 2.1.287, the run's model, `apiKeySource` `none` (the
  subscription's OAuth token).
- **Permission mode:** every session 1 ran in mode `auto` and every session 2 in `default`, in
  all three arms alike (the prereg said `default` for both).
- **What a clean session loads:** every N0 and H session reported 3 plugins, 19 skills, 5 agents
  and no MCP server. All are Claude Code 2.1.287's own built-ins (the plugins are its `@builtin`
  ones; the agents are `claude`, `Explore`, `general-purpose`, `Plan` and `statusline-setup`),
  none from the owner's configuration. S's sessions reported the same plus the install's
  `sanchopanza-code` skill and its `sanchopanza` MCP server.
- **S ran as S in every arm.** Its memory hook answered SessionStart in both sessions of all 72
  S arms, and its find server was connected.
- **Subagents:** none.
- **Secrets:** no token or TypeSafe key in any file (nothing to scrub).

## Spend

- **42.25 USD at Claude Code's list price, through the subscription.** Claude Code 42.23 plus
  Jev 0.019 plus the preflights.
- Caps were 11.5 / 109 / 106 USD per run and 230 USD for the night. The dearest Sonnet session
  cost 0.128 against its 0.80 cap.

## What it means for the product

- **On Sonnet 5.5, installing sanchopanza replaces the handoff ritual with no loss** (not
  worse than H by the sealed −12.5-point margin; 48 against 44, 4 to 0, p 0.0625: a gain over
  the ritual is not shown), and beats doing nothing by 44 to 0.
  - Continuing with a bare "let's continue" line, S finished the next step correctly every
    time: 48 of 48, against 44 with a handoff and 4 with nothing.
  - It cost 0.92x the ritual [0.85, 0.95] and 1.23x doing nothing [1.14, 1.26] (descriptive
    intervals): a substitute for the ritual, and a trade against doing nothing.
  - It needs no extra request and no paste.
  - The gain comes from carrying the plan, not from catching a forgotten constraint: every
    session that built step 2, in every arm, kept C and D.
- **On Opus 5.5, Claude Code's own auto memory does the job.**
  - N0 keeps 21 of 24, S 22, and S adds about 10 % to the cost (1.10x [1.01, 1.16]).
  - The handoff ritual scored lowest on Opus (17 of 24; against N0 1 to 5, p 0.11, not shown):
    its prompts hand over open questions, and a fresh session stops to ask them.
  - The product claim there is "no harm, no gain over Claude Code alone".

## What this does not show

- **Scenes written by us.**
  - Twelve synthetic two-step features with in-repo checks.
  - The prereg lists four checks a natural implementation may pass without knowing C or D:
    `h_loud`, `h_nomutate`, `h_batch`, `h_merge`.
  - Since no session lost C or D, the scenes did not test that.
- **Headless, one prompt per session.** A session 2 that asks a question counts as not done.
  In real use the person answers, and N0 and H would recover part of their misses.
  - The handoff is pasted unread. The owner reads and sometimes edits his.
- **One draw per triple.** Four repetitions on Sonnet and two on Opus. Repetitions of a scene
  are correlated, so by scene the evidence is 12 scenes, not 48 independent trials:
  - Sonnet: S beat N0 in 12 of 12 scenes and H in 3 (`h_nomutate`, `h_semicolon`, `h_judge`),
    losing none.
- **Clean Claude Code 2.1.287 only.** Later releases may change auto memory and the resume cost
  report.

## Files

| file | what it is |
|---|---|
| `prereg.md`, `prereg.manifest.json`, `prereg.sha256` | the sealed pre-registration and its seal |
| `f2-sonnet-table.json`, `f2-opus-table.json`, `f2-pilot-table.json` | the sealed analysis (`handoff_analyze.analyse`) of the night's rows, H's handoff turn at its own cost |
| `gate.json`, `gate.md` | the pilot's automatic gate |
| `rows-f2-*.json` | every arm's row with numbers and flags only: no text the agent or the model wrote, no handoff text, no session id, no path |
| `costs.json` | per run, the handoff turn's own cost against its tokens at Claude Code's rates, and the lot's spend |
| `benchmarks/memory_carry/handoff_cost_ci.py` | the descriptive bootstrap intervals of the cost ratios, from `rows-f2-*.json` |

`python benchmarks/memory_carry/handoff_publish.py <run root> <this folder>` rebuilds these
files. It checks two things for each of the three tables:
- the analysis gives the same text from the full rows and from the public rows;
- every field but the costs equals the table the night wrote, verdicts included.
