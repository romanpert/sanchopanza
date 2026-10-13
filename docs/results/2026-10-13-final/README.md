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
compacted up to 452k ([STATUS-launch.md](../../../STATUS-launch.md), "Gate").

The whole S line never ran on these chains. What ran is the S part built for them: bet A, N plus
only `passages-hook` (Jev keeps the pertinent passages of large Bash and Read outputs on arrival).
Within a chain bugs are not independent, so the run is the unit and there is no per-bug p (N
against itself on conan: 0 vs 7, p 0.016; `docs/PLAN-GANAR-H2H.md` 7).

| Axis | Model | S−N (success) | 95 % CI | p | Cost S/N | Wall S/N | Verdict |
|---|---|---|---|---|---|---|---|
| A against N, conan-long60-1 (k = 2) and pydantic-long60-1 (A k = 1, N k = 2) | Sonnet 5.5 | conan A 46-47 vs N 44-47; pydantic A 48 vs N 44-46 | none (run ranges) | none (per-bug p withdrawn) | conan at call 50: 0.80-1.07 (0.93 on means), N against itself 0.90; pydantic whole chain 1.019 | not reported | **no gana** |
| Long code | Opus 5.5 | — | — | — | — | — | **sin margen** on conan; **no corrido** on pydantic |

Sources: [pilot-a](../2026-10-07-pilot-a/README.md), `docs/PLAN-GANAR-H2H.md` ("Repetición en
conan"), [STATUS-launch.md](../../../STATUS-launch.md) ("Conan repeat round").

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
| Early compaction (60-70k) against Ne, ≥ 5 long60 chains | Sonnet 5.5 | _pending_ | _pending_ | _pending_ | _pending_ | _pending_ | **pending, running** |
| Early compaction against Ne | Opus 5.5 | — | — | — | — | — | **no corrido** |

Source when it lands: `docs/results/2026-10-13-long-compact/` (branch `cierre-contexto`).

## Memory: a fact said in an earlier session

F1 headroom gate, N only, 8 scenes a cell: a cell opens when N breaks the fact, with the task
done, in at least 3 of 8 ([memory-frontier](../2026-10-05-memory-frontier/gate-result.md)).

| Axis | Model | S−N (success) | 95 % CI | p | Cost S/N | Wall S/N | Verdict |
|---|---|---|---|---|---|---|---|
| F1 (iii), parallel session (N broke 3/8 at the gate) | Sonnet 5.5 | **+45.8** (fact kept: S 24/24, N 13/24) | [+12.5, +79.2] (bootstrap by scene) | 0.00049 (McNemar on pairs, 11 to 0; by scene 4 to 0, 0.0625) | 1.117 [1.05, 1.15] | 1.12 | **gana** |
| F1 (i), principle | Sonnet 5.5 | — | — | — | — | — | **sin margen** (N broke 2/8) |
| F1 (ii), stale rule | Sonnet 5.5 | — | — | — | — | — | **sin margen** (N broke 0/8) |
| F1 (i), (ii), (iii) | Opus 5.5 | — | — | — | — | — | **sin margen** (N broke 0/8, 0/8, 1/8) |
| F2, handoffs | Sonnet 5.5, Opus 5.5 | — | — | — | — | — | **no corrido** |

Source: [2026-10-13-memory-cell](../2026-10-13-memory-cell/README.md) (sealed prereg d42d261).
Cost is the median S/N per pair; its interval is the geometric mean's, bootstrapped over scenes.
S is the default install plus `--memory` (project scope), which the default leaves off.

- In family (ii), Claude Code's own auto memory followed the newer rule in 16 of 16 sessions over
  both models: where it already resolves precedence, S can only tie or harm.
- Earlier evidence, outside the scoreboard: the carry v6.2 confirmation on Sonnet 5.5, S 23/24
  against N 14/24, one-sided McNemar p 0.002, cost S/N 0.971; on Opus 5.5, 16/16 against 14/16, p
  0.25, no room ([memory-carry](../2026-10-02-memory-carry/README.md)). Its N was Claude Code
  2.1.285 with the owner's setup loaded, so it does not fill a cell; the Sonnet cell above is its
  clean test.

## What wins, what does not, and why

- **One measured cell is a win for S: memory on Sonnet 5.5, a fact said in a parallel session
  or sibling worktree.** S broke the fact in 0 of 24 pairs, N in 11 (McNemar p 0.00049), at a
  median cost of 1.117 (+12 %, within the sealed 1.15). The gain is in the 4 of 8 scenes where the
  fact is not in the code. It needs `--memory`, which the default install leaves off. On Opus 5.5
  memory had no room.
- **No other measured cell is a win.** Three web suites are "no gana" on Sonnet 5.5; code on Haiku
  4.5 is non-inferior with no saving shown; on long code the Jev part (A) did not hold its edge.
  The rest is "sin margen" or not run. One cell is pending: early compaction on long code.
- **Why the rest did not: a Jev decision saves only when it replaces a call or tokens of the
  expensive model.** It costs 24 to 119 times less than that call. Added on top of what the model
  already does, it only adds prefix and latency, however right it is (`docs/PLAN-GANAR-H2H.md` 3).
  S0 added about 970 fixed tokens (40 % of GAIA's cost delta) and was 39 % slower on GAIA; its
  hooks ran thousands of times with no output; `fetch_passages` replaced WebFetch's cheap reader
  with about four times more text into Sonnet. The memory win is not a saving: a Jev decision
  stored a fact the model could not see in the code, and S cost 12 % more.
- **What moved results in context was the compaction window, which is configuration.**
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW` alone matched the whole S line on BrowseComp-Plus and cut the
  cost of long coding sessions by a third to a half with no evidence of lost quality. A clean
  Claude Code gets it with one line of settings: it is not a case for S over N.
- **Where the components keep their value**: substituting a judgment some model was going to make
  (the component benches in the top-level README), not as a default layer on Claude Code.

## What was not run

By decision:

- **Code on Sonnet 5.5 and Opus 5.5**: about 357 USD of list price estimated (cap 465) for Sonnet
  78×1 and Opus 52×1 (plan section 3). Only Haiku exists (phase D).
- **Memory F2, handoffs**: about 180.5 USD (`2026-10-05-memory-frontier/prereg-f2-handoff.md`).
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
