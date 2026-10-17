# Final scoreboard: Claude Code alone (N) against Claude Code + sanchopanza (S) (2026-10-13)

The scoreboard of `docs/PLAN-COMPARACION-FINAL.md`, section 5, filled with what is already
measured. Nothing new was run for this page: every figure is copied from the folder or file named
under its table. One table per axis, one row per model. Nothing is pooled across models or axes.

Verdicts, as the plan fixes them: **gana**, **no gana**, **sin margen** (clean N leaves no room to
win). Two more states: **no corrido** (not run) and **pending, running** (a cell another session
is running today; its figures are not anticipated here).

- **N** is clean Claude Code 2.1.287: an empty `CLAUDE_CONFIG_DIR` per pair, none of the owner's
  plugins, skills, MCP servers, hooks or CLAUDE.md. A row that departs from this says so.
- **S** is the line the row names. In the web confirmations it is S0, sealed at h2h 671cfd7 with S
  from main aad9903 (`2026-10-06-h2h-conf/prereg.md`).
- **S−N** is success in points. **Cost** and **wall** are S/N ratios of list price (Jev included)
  and wall time, with their 95 % interval where the source gives one.
- **gana**, per model: the cost interval below 1 with success not worse than the margin, or more
  success at p < 0.05 without losing on cost (plan section 2.4; `gaia_stats.verdict` in the web
  prereg).

## Web search and reading

| Axis | Model | S−N (success) | 95 % CI | p | Cost S/N | Wall S/N | Verdict |
|---|---|---|---|---|---|---|---|
| GAIA validation, 132 paired tasks | Sonnet 5.5 | +3.8 pts (102 vs 97) | [−1.5, +9.9] | 0.30 | 1.074 [0.908, 1.255] | 1.39 [1.12, 1.79] | **no gana** |
| BrowseComp-Plus, 90 queries | Sonnet 5.5 | +7.8 pts (56 vs 49) | [0.0, +15.6] | 0.092 | 1.17 [1.007, 1.356] | 1.26 [1.10, 1.45] | **no gana** |
| LongBench v2, 50 tasks | Sonnet 5.5 | −6 pts (28 vs 31) | [−18, +6] | 0.55 | 0.785 [0.634, 1.008] | 0.994 [0.772, 1.255] | **no gana** |
| GAIA, BrowseComp-Plus, LongBench v2 | Opus 5.5 | — | — | — | — | — | **no corrido** |
| GAIA, BrowseComp-Plus, LongBench v2 | Fable 5.1 | — | — | — | — | — | **no corrido** |

Sources: [GAIA](../2026-10-05-h2h-gaia/README-conf.md), [BrowseComp-Plus](../2026-10-06-h2h-bcp/README-conf.md),
[LongBench v2](../2026-10-06-h2h-longdoc/README-conf.md), the sealed rule in
[h2h-conf](../2026-10-06-h2h-conf/prereg.md). McNemar exact p; one session per task and arm.

Beside the scoreboard (mechanism, not S−N):

- **Jev barely acted.** The share of Jev decisions that changed what the model saw: GAIA ≤ 1.7 %,
  BrowseComp-Plus 0 %, LongBench ≤ 0.3 %. In these S0 web runs memory made 2,308 decisions and
  delivered nothing, its store empty by construction; the injection scan 435 and nothing, the Bash
  guard 130 and nothing (`docs/PLAN-GANAR-H2H.md` 2.2).
- **BrowseComp-Plus's gain is Claude Code's compaction window.** Clean N with only
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW=193000` (NE), on the 26 queries where N passed 150k: 7 right
  against S0's 6 and N's 4, cost NE/S0 0.954 [0.80, 1.15]. The guard's re-injection added nothing
  measurable on top ([h2h-ne](../2026-10-07-h2h-ne/README.md)).
- **S2** (S0 without the parts that did not act), dev of 10 tasks a suite: cheaper than S0 in all
  three, cheaper than N in none (GAIA 1.085, LongBench 1.281, BrowseComp-Plus 1.408)
  ([h2h-s2](../2026-10-07-h2h-s2/README.md)). No confirmation, by the owner's decision.
- **D and E closed with no lever**: checking the returned document has a ceiling of about 3
  answers in 180 sessions ([h2h-d](../2026-10-07-h2h-d/README.md)); no checkable signal separates
  GAIA's wrong answers ([h2h-e](../2026-10-07-h2h-e/README.md)).

## Code: SWE-bench Verified, one issue a session

| Axis | Model | S−N (success) | 95 % CI | p | Cost S/N | Wall S/N | Verdict |
|---|---|---|---|---|---|---|---|
| 26 Verified singles × 3 (phase D) | Haiku 4.5 | +1.3 pts (46/78 vs 45/78) | one-sided 1 % bound −5.1, margin −7.7: non-inferior | not in the seal | 1.007 [0.933, 1.143] (median per instance) | not in the seal | **no gana** |
| Verified singles | Sonnet 5.5 | — | — | — | — | — | **no corrido** |
| Verified singles | Opus 5.5 | — | — | — | — | — | **no corrido** |

Source: [adopt-d](../2026-10-03-adopt-d/results.md). Phase D does not meet the plan's N: both arms
loaded the owner's setup, on Claude Code 2.1.285, and Haiku is the plan's mechanism model (plan
section 1). It is the only code measure there is. It shows no loss in success and no saving: the
sealed "no more than 10 % dearer" did not hold. find was called in 2 of 78 S sessions.

## Long code: 60 bugs in one session (long60 chains)

Headroom gate, N only, 2026-10-07: Sonnet 5.5 resolved 44 of 60 on both chains (27 % room); Opus
5.5 resolved 57 of 60 on conan (**sin margen**) and 53 of 60 on pydantic (12 % room). N never
compacted up to 452k ([STATUS-launch.md](../../history/STATUS-launch.md), "Gate").

The whole S line never ran on these chains. What ran is the S part built for them: bet A, N plus
only `passages-hook` (Jev keeps the pertinent passages of large Bash and Read outputs on arrival).
Within a chain bugs are not independent, so the run is the unit and there is no per-bug p (N
against itself on conan: 0 vs 7, p 0.016; `docs/PLAN-GANAR-H2H.md` 7).

| Axis | Model | S−N (success) | 95 % CI | p | Cost S/N | Wall S/N | Verdict |
|---|---|---|---|---|---|---|---|
| A against N, conan-long60-1 (k = 2) and pydantic-long60-1 (A k = 1, N k = 2) | Sonnet 5.5 | conan A 46-47 vs N 44-47; pydantic A 48 vs N 44-46 | none (run ranges) | none (per-bug p withdrawn) | conan at call 50: 0.80-1.07 (0.93 on means), N against itself 0.90; pydantic whole chain 1.019 | not reported | **no gana** |
| Long code | Opus 5.5 | — | — | — | — | — | **sin margen** on conan; **no corrido** on pydantic |

Sources: [pilot-a](../2026-10-07-pilot-a/README.md), `docs/PLAN-GANAR-H2H.md` ("Repetición en
conan"), [STATUS-launch.md](../../history/STATUS-launch.md) ("Conan repeat round").

Beside the scoreboard:

- **Ne** (clean N + the 193k window, a setting, no Jev): cost 0.46-0.66 of N on conan (0.56 on
  means) and 0.59 on pydantic; resolved 37-51 against N's 44-47 on conan, 44 against 44-46 on
  pydantic. No evidence of a quality loss, none of a gain.
- **A on Ne**, replayed free on Ne's transcripts: net 2.2-4.3 %, under the plan's 5 % rule. A is
  archived for long code (commit dfba8ef).
- **Where Jev could pay with Ne as the bar: nowhere found.** The best possible compaction placement
  (an oracle) beats a turn-end threshold by 1.2-2.0 %; reading the summary is 2.7-5.1 % of the
  cost; carrying context costs about five times a re-read (commit 4a5411a).

## Context: when to compact on long code

The bar for everything long is Ne, not bare N (`docs/PLAN-GANAR-H2H.md` 6). Here the treatment is
compacting early, at turn end at 60-70k, against Ne. It is a Claude Code setting, not a Jev
decision. The replay gave −20 to −25 % as a first-order upper bound, with quality unmeasured.
Whatever the cell gives is a configuration result and is reported as one.

| Axis | Model | S−N (success) | 95 % CI | p | Cost S/N | Wall S/N | Verdict |
|---|---|---|---|---|---|---|---|
| Early compaction (60-70k) against Ne, 5 long60 chains (conan ×2, pydantic, moto ×2), k = 1 | Sonnet 5.5 | −1.4 pts (249/278 vs 253/278 bugs both were asked) | [−3.8, +1.1] (chains resampled); one-sided bound −3.5, margin −10: non-inferior | none (the unit is the run) | 0.900 [0.741, 1.093] | 1.09 [0.85, 1.41] | **no gana** (no saving shown) (under the post-data amendment: conan-2 repeated, still no gana: R1 0.875 [0.754, 1.015], R2 0.887 [0.750, 1.050]) |
| Early compaction against Ne | Opus 5.5 | — | — | — | — | — | **no corrido** |

Source: [2026-10-13-long-compact](../2026-10-13-long-compact/README.md) (sealed prereg fb42fa4; 173.11 USD). With the call of conan-2 cut by a PC reboot metered at what it cost (0.35) instead of its 4.50 cap, the ratio would be 0.858 [0.748, 0.984]; the sealed rule does not use that, and the verdict stands. The conan-2 repeat (2026-10-15, post-data amendment, 33.69 USD; 206.80 in all) gave 0.952 on that chain: no gana either. Even a win at 67k would not be an install default: the owner's real sessions start near 68k.

## Memory: a fact said in an earlier session

F1 headroom gate, N only, 8 scenes a cell: a cell opens when N breaks the fact, with the task
done, in at least 3 of 8 ([memory-frontier](../2026-10-05-memory-frontier/gate-result.md)).

| Axis | Model | S−N (success) | 95 % CI | p | Cost S/N | Wall S/N | Verdict |
|---|---|---|---|---|---|---|---|
| F1 (iii), parallel session (N broke 3/8 at the gate) | Sonnet 5.5 | **+45.8** (fact kept: S 24/24, N 13/24) | [+12.5, +79.2] (bootstrap by scene) | 0.00049 (McNemar on pairs, 11 to 0; by scene 4 to 0, 0.0625) | 1.117 [1.05, 1.15] | 1.12 | **gana** |
| F1 (i), principle | Sonnet 5.5 | — | — | — | — | — | **sin margen** (N broke 2/8) |
| F1 (ii), stale rule | Sonnet 5.5 | — | — | — | — | — | **sin margen** (N broke 0/8) |
| F1 (i), (ii), (iii) | Opus 5.5 | — | — | — | — | — | **sin margen** (N broke 0/8, 0/8, 1/8) |
| F2, continuing a two-step feature in a new session (N0: a plain "let's continue") | Sonnet 5.5 | **+91.7** (kept all: S 48/48, N0 4/48; the handoff ritual H 44/48) | one-sided lower bound +81.4 (Tango); S − H +8.3, lower bound +2.6, margin −12.5 | 5.7e-14 (McNemar, 44 to 0) | 1.226 [1.141, 1.261] (median per triple, descriptive bootstrap; S/H 0.917 [0.853, 0.946]) | 1.31 (session 2 medians, 26.8 s / 20.4 s) | **S better than N0, not worse than H** (F2's sealed verdict; not "gana": the cost interval lies above 1) |
| F2, as above | Opus 5.5 | +4.2 (S 22/24, N0 21/24; H 17/24) | S − N0 lower bound −6.4; S − H +20.8, lower bound +8.6 | 0.5 | 1.105 [1.011, 1.158] (S/H 1.060 [1.009, 1.183]) | 1.09 (44.45 s / 40.8 s) | **sin margen** (F2's sealed reading: direction only, S not worse than H; Claude Code's own auto memory saved the plan after every Opus session 1, in every arm) |
| W17, continuing in a new session with the default USER-scope install as it ships (src cbfd932: lean install, C8 fixes), named line and bare "Let's continue." | Sonnet 5.5 | **+81.3** (kept all: S' 48/48, N0 9/48; bare line 24/24 vs 3/24) | one-sided Tango lower bound +70.4 | 1.8e-12 (McNemar, 39 to 0) | 1.187 [1.148, 1.244] (median per pair, sealed bound 1.10) | 1.31 (session 2 medians, 35.3 s / 26.95 s) | **no gana** (W17's sealed verdict: "S' better than N0; no gana (cost)") |
| W17, as above (bare line on repetition 3 only) | Opus 5.5 | +8.3 (kept all: S' 34/36, N0 31/36; named 22/24 vs 21/24, bare 12/12 vs 10/12) | one-sided Tango lower bound +0.8, margin −12.5: not worse | 0.125 (McNemar, 3 to 0) | 0.999 [0.965, 1.055] (median per pair, sealed bound 1.05) | 1.10 (session 2 medians, 44.9 s / 40.95 s) | **no gana** (W17's sealed verdict: "not determined"; Claude Code's own auto memory saved after every Opus session 1, in both arms) |
| Equal work (rule R3): W17's arms, scenes and strata, each arm resumed once with "Yes, go ahead." when its session 2 left step 2 undone; N departs: N0⁺ is clean Claude Code told once to go on (src 4c143e1, the same installed files as W17) | Sonnet 5.5 | **+93.8** (kept all: S' 48/48, N0⁺ 3/48; N0 nudged in 45 pairs, after the nudge step 2 as session 1 specified it in 0, a step 2 of its own in 30) | one-sided Tango lower bound +83.4, margin −12.5 | 2.8e-14 (McNemar, 45 to 0) | 1.005 [0.949, 1.063] (median per pair, the nudge counted; sealed bound 1.10; without the nudge 1.247 [1.178, 1.295]) | 1.39 (session 2 medians, 30.75 s / 22.1 s; N0's nudge a median 20.5 s more) | **gana (éxito), against N0⁺** (the lot's sealed rule: the scoreboard's 2.4 made exact as W17 made it; not a saving: S' costs what N0⁺ costs, and N0's extra round did step 2 as specified in 0 of 45 pairs) |

Source: [2026-10-13-memory-cell](../2026-10-13-memory-cell/README.md) (sealed prereg d42d261).
Cost is the median S/N per pair; its interval is the geometric mean's, bootstrapped over scenes.
S is the default install plus `--memory` (project scope); the default left memory off when this
was measured and has wired it since 2026-10-14 (`--no-memory` leaves it out), so S is now the
default install. The other cells' S ran without memory.

W17: [2026-10-16-memory-w17](../2026-10-16-memory-w17/README.md) (Sonnet sealed 5d416fa, 11.18 USD;
Opus sealed 941c9a9 under the prereg's Amendment 1, 21.32 USD; clean Claude Code 2.1.287 against
`install --scope user` as it ships, F2's 12 scenes, 48 Sonnet and 36 Opus pairs).

Equal work: [2026-10-17-memory-equal-work](../2026-10-17-memory-equal-work/README.md) (sealed
d1c39af, 11.98 USD; clean Claude Code 2.1.287 against `install --scope user` as it ships, F2's
12 scenes, 48 Sonnet pairs, each arm resumed once with "Yes, go ahead." when `task` failed after
session 2). Its verdict rule is this page's rule 2.4, made exact as W17 made it ("gana (coste)":
the cost interval's upper bound below 1.00 with Tango's bound above −12.5 points; "gana
(éxito)": McNemar p < 0.05 with the upper bound at most 1.10; no harm in both). The prereg
declares the nudge, in both arms, as its deviation from W17, and names the comparator: "clean
Claude Code that a person tells to go on once" (N0⁺), not bare N; its "gana" is against N0⁺.
It models a person who answers blind, without repeating the task; a person who repeats it is
not measured.

F2: [2026-10-16-memory-f2](../2026-10-16-memory-f2/README.md) (sealed 763dafd; 42.25 USD; clean
Claude Code 2.1.287 against `install --scope project` as it ships, 12 synthetic scenes,
headless). Its sealed verdict is "S not worse than H; S better than N0", with no harm; its prereg
seals no cost condition. The scoreboard's "gana" also asks that S not lose on cost, and on Sonnet
S cost 1.23x N0 with an interval entirely above 1: F2's Sonnet row is a trade against doing
nothing and a substitute for the handoff ritual, not a "gana". Its cost intervals are a paired
bootstrap over triples (10,000 draws, seed 20261016), descriptive and post hoc.

- In family (ii), Claude Code's own auto memory followed the newer rule in 16 of 16 sessions over
  both models: where it already resolves precedence, S can only tie or harm.
- Earlier evidence, outside the scoreboard: the carry v6.2 confirmation on Sonnet 5.5, S 23/24
  against N 14/24, one-sided McNemar p 0.002, cost S/N 0.971; on Opus 5.5, 16/16 against 14/16, p
  0.25, no room ([memory-carry](../2026-10-02-memory-carry/README.md)). Its N was Claude Code
  2.1.285 with the owner's setup loaded, so it does not fill a cell; the Sonnet cell above is its
  clean test.

## What wins, what does not, and why

- **Two measured rows are a win for S, both memory on Sonnet 5.5, plus F2's sealed positive
  verdict:** a fact said in a parallel session, and continuing a two-step feature against clean
  Claude Code told once to go on (equal work). A fact said in a parallel session or sibling
  worktree: S broke it in 0 of 24 pairs,
  N in 11 (McNemar p 0.00049), at a median cost of 1.117 (+12 %, within the sealed 1.15); the
  gain is in the 4 of 8 scenes where the fact is not in the code. Continuing a two-step feature
  in a new session (F2, Sonnet 5.5, clean Claude Code 2.1.287): S did the next step in 48 of 48
  triples, N with a plain "let's continue" in 4 (44 to 0), and N with the owner's handoff ritual
  in 44 (S not worse by the sealed margin; 4 to 0, p 0.0625). S cost 1.23x N [1.14, 1.26] and
  0.92x the ritual [0.85, 0.95]: it replaces the ritual with no loss shown, at lower cost, and
  beats doing nothing at a higher one, so it is F2's sealed verdict, not a "gana". What S
  carried was the plan: no session in any arm that built step 2 lost the constraint or the
  decision. Memory is on by default in the install since 2026-10-14. Measured again as it ships
  (W17, user scope, after the C8 fixes): 48 of 48 against 9, and 24 of 24 against 3 with a bare
  "Let's continue.", at 1.19x [1.15, 1.24] the cost: better, not a "gana". At equal work (the
  same install and scenes, each arm resumed once with "Yes, go ahead." when session 2 left step
  2 undone): 48 of 48 against 3, at 1.005x [0.949, 1.063] the cost, "gana (éxito)", against
  Claude Code told once to go on. It is not a saving: Claude Code alone was nudged in 45 pairs
  and after the nudge did step 2 as session 1 specified it (its name, signature and
  constraints) in none, in 30 writing a step 2 of its own; that extra round brought its cost up
  to S's, and without it S cost 1.25x [1.18, 1.30]. On Opus 5.5 memory had no
  room in either family: Claude Code's own auto memory carried the fact and the plan. As it ships
  (W17), on Opus it kept the plan in 34 of 36 pairs against 31 (p 0.125) at a median 0.999x
  [0.965, 1.055]; that it costs no more is not shown (sealed O1: upper bound 1.055 over 1.05):
  "not determined", no gana.
- **No other measured cell is a win.** Three web suites are "no gana" on Sonnet 5.5; code on Haiku
  4.5 is non-inferior with no saving shown; on long code the Jev part (A) did not hold its edge.
  Early compaction near 67k on long code: cost 0.900 [0.741, 1.093], no saving shown. The rest is "sin margen" or not run.
- **Why the rest did not: a Jev decision saves only when it replaces a call or tokens of the
  expensive model.** It costs 24 to 119 times less than that call. Added on top of what the model
  already does, it only adds prefix and latency, however right it is (`docs/PLAN-GANAR-H2H.md` 3).
  S0 added about 970 fixed tokens (40 % of GAIA's cost delta) and was 39 % slower on GAIA; its
  hooks ran thousands of times with no output; `fetch_passages` replaced WebFetch's cheap reader
  with about four times more text into Sonnet. The memory win is not a saving: a Jev decision
  stored a fact the model could not see in the code, and S cost 12 % more. Nor is the equal-work
  one: S cost what Claude Code told to go on cost (1.005x).
- **What moved results in context was the compaction window, which is configuration.**
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW` alone matched the whole S line on BrowseComp-Plus and cut the
  cost of long coding sessions by a third to a half with no evidence of lost quality. A clean
  Claude Code gets it with one line of settings: it is not a case for S over N.
- **Where the components keep their value**: substituting a judgment some model was going to make
  (the component benches in the top-level README), not as a default layer on Claude Code. The
  first measured substitution of a frontier session came after this scoreboard (next section):
  on long-document multiple choice, Jev answering where its top choice reached 0.6 saved 33.9 % [24.0, 44.0] of
  Sonnet 5.5's cost and 29.5 % [21.7, 37.7] of Opus 5.5's, no worse at −10 points, as an opt-in
  point (`points.longdoc`) outside the install.

## After the scoreboard: components measured on 2026-10-15 and 16

Not S−N cells: none is the install line against clean Claude Code. Each is a component against
what it would replace or against its shipped setting, pre-registered and sealed before any
answer.

| Measure | Model | Result | 95 % CI | Verdict by the sealed rule |
|---|---|---|---|---|
| Jev where its top choice is ≥ 0.6, Sonnet elsewhere, against Sonnet alone, 162 fresh LongBench v2 tasks | Jev 1.14 long window; Sonnet 5.5 in clean Claude Code 2.1.287 | +1.2 pts (coverage 37 %; on the 60 covered, Jev 31 and Sonnet 29 right); 33.9 % [24.0, 44.0] of Sonnet's cost saved | [−3.1, +5.6] | **no peor** at −10 |
| The router at a 0.8 cut against Opus 5.5 alone, 78 fresh tasks under 100,000 characters | Jev 1.14 long window; Opus 5.5 in clean Claude Code 2.1.287 | −6.4 pts (coverage 38 %; on the 30 covered, Jev 20 and Opus 25 right); 30.8 % [20.9, 41.4] of Opus's cost saved | [−14.1, −1.4] | **no concluyente** at −5 |
| The same router against Opus 5.5 alone, the same 162 tasks | Jev 1.14 long window; Opus 5.5 in clean Claude Code 2.1.287 | −3.7 pts (on the 60 covered, Opus right on 37 and Jev on 31; McNemar 10 against 4, p 0.18); 29.5 % [21.7, 37.7] of Opus's cost saved | [−8.0, +0.6] | **no peor** at −10 |
| The memory gate reading whole sessions in one call against the shipped short window, 84 unseen LongMemEval questions | Jev 1.13 | recall 0.905 against 0.726; against BM25 top 3 +8.9 pts [0.0, +17.3], "alcanza" | [+10.7, +25.7] pts | **confirmado** |
| The installed memory hook with the long window against its shipped short window, 905 SWE-chat first requests | jev-1.13.0 | related record given on 45 against 29 of 126 hittable requests (+12.7 pts); a record given where nothing is related on 42 against 24 of 483 (+3.7 pts) | hits [+6.3, +19.8]; false alarms [+1.5, +6.2], guard's wider bound 6.3 against +5 | **peor en ruido** (the hook stays short) |
| check_done under Jev 1.14 at 0.30 against 1.13 at 0.5, 950 unseen AgentDojo stops | jev-1.14.0, jev-1.13.0 | right on 745 against 737 (+0.8 pts); both block about one finished stop in five (150 and 165 of 795), block precision 0.39-0.40, AUC 0.81, tool results cut at 1,500 characters | [−1.1, +3.2] | **confirmado (no peor)** |
| `redundant_page`'s `adds_nothing` cut for 1.14, rederived with 90 more `drop` cases, 530 cases | jev-1.14.0, jev-1.13.0 | the derivation clears at 0.04; primary −0.2 pts; at 0.04, 1.14 drops 8 `keep` pages against 0 (limit +2) | [−6.4, +5.5] | **no proposal** (the cut stays 0.61) |
| The `actions` point in the hook for MCP calls (`install --guard-mcp`), replayed over 500 ATBench-Codex trajectories | jev-1.13.0, the hook's own code, no Claude Code session | 185 of 250 unsafe caught (74.0 %), today's hook 0; 82 of 250 safe flagged (32.8 %) | recall floor 75.2 % | **not confirmed** (recall 3 trajectories short; stays opt-in) |
| `relate_facts` accepting `unrelated` at 0.65 below the confidence gate, 1,500 new pairs | jev-1.13.0 | 39 added verdicts, all right, 0 missed conflicts | Wilson lower bound 0.910 | **beats the shipped policy** (licenses a proposal for 0.65) |
| Ordering `select_passages`' paragraphs by a four-level Score before a 3,400-character cut, 233 QASPER questions | jev-1.13.0 | answer-sentence recall 81.0 % against 65.1 % in page order; +2.3 and +1.8 pts against the two free orders | [−1.5, +6.2], [−2.3, +5.7] | **not confirmed** (stays opt-in) |
| Page triage and passage selection in Spanish against English, the same MLQA questions | jev-1.13.0 | pages 95.5 % against 98.9 % (−3.4 pts); whole articles 85.8 % against 91.7 % (−5.9 pts) | [−6.1, −0.8]; [−9.0, −2.9] | **inconclusive** at −5 (both) |
| The most imposing `find_in_repo` could save, free and offline, 19 recorded long-chain sessions (1,046 bugs); not pre-registered | Sonnet 5.5 in clean Claude Code 2.1.287 | 3.05 % of the model's cost spent before first reaching a fixed file, on bugs where find's top 5 holds it | [2.36, 3.78] % | **under the 5 % rule** (closed without spending) |

Sources: [lb162](../2026-10-15-lb162/README.md) (sealed c483beb; 0.874 USD of Jev on the 162
tasks (0.875 with the smoke), 5.757 of Claude), [lb162x](../2026-10-16-lb162x/README.md) (sealed 24adf4a; Opus on all
162 and Sonnet on the 102 uncovered tasks, 27.01 USD of Claude, no Jev call),
[memgate-long](../2026-10-15-memgate-long/README.md) (sealed c8d1da1; 0.53 USD of Jev),
[memgate-hook](../2026-10-16-memgate-hook/README.md) (sealed 211227c; 0.18 USD of Jev),
[checkdone114](../2026-10-16-checkdone114/README.md) (sealed aff4cff; 0.14 USD of Jev),
[redundant-drop](../2026-10-16-redundant-drop/README.md) (sealed 303dcc4; 0.03 USD of Jev),
[A3](../2026-10-16-a3-mcp/README.md) (sealed 65528af; 0.08 USD of Jev with its amendment's control),
[A5](../2026-10-16-a5-unrelated/README.md) (sealed f392ee8; 0.03 USD of Jev),
[B4](../2026-10-16-b4-order/README.md) (sealed 7f8bca6; 0.06 USD of Jev),
[B6](../2026-10-16-b6-es/README.md) (sealed 1f54dd4; 2.64 USD of Jev),
[A6](../2026-10-16-a6-ceiling/README.md) (free replay, 0 USD). None called Claude but lb162 and
lb162x.

- **The router (lb162, lb162x)** is a Jev decision that replaces calls of the expensive model,
  the case this page names as the only one where a decision saves; it covers multiple choice
  over one long document and one draw.
- **The memory gate's long window** is a recall gain on the library gate (memgate-long), where it
  is the default (`SANCHOPANZA_MEMORY_WINDOW=short` turns it off). On the installed hook's first
  prompt (memgate-hook) the same window gave more noise than the sealed guard allows, so the hook
  stays on the short one.
- **The rest** are checks of a cut or an opt-in: check_done's 1.14 profile holds, the MCP guard
  and the Score ordering stay opt-in, `redundant_page` keeps its cut, A5 licenses a proposal, and
  B6 measures the Spanish drop without settling the margin.

## What was not run

By decision:

- **Code on Sonnet 5.5 and Opus 5.5**: about 357 USD of list price estimated (cap 465) for Sonnet
  78×1 and Opus 52×1 (plan section 3). Only Haiku exists (phase D).
- **Fable 5.1**: no suite.
- **The memory cell on Opus 5.5**: sin margen at the gate.

Also not run, and why:

- **Web on Opus 5.5**: not in the web prereg (section 6b); spending on one-question suites stopped on
  2026-10-07, since S did not win there and the one thing that moved was a setting
  (`docs/PLAN-GANAR-H2H.md` 6).
- **The S2 confirmation**: owner's decision after its dev.
- **Ne against Ne+A, paid**: seeing a −7 % needs about 43 chains (`docs/PLAN-GANAR-H2H.md`, "Replay de
  A sobre N-early").
- **The whole S line on long chains.**

## Filling the pending cells

Each session replaces the `_pending_` cells of its row with the figures from its folder and the
verdict by the rule its own prereg seals, then links that folder here and in
[the index](../README.md). If either verdict is **gana**, the first bullet of "What wins" changes
with it, and so does the head-to-head line in the top-level README and in `docs/where-it-pays.md`.

Both cells were filled on 2026-10-14: memory **gana** (Sonnet 5.5, parallel sessions), early
compaction on long code **no gana**. No cell is pending. The equal-work row (2026-10-17) is the
second "gana", against Claude Code told once to go on.
