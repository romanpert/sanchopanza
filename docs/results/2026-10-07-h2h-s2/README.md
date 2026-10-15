# S2 development on the h2h dev tasks (2026-10-07)

Dev only, not a confirmation: nothing here decides anything. Written by session d6 (line web/h2h)
before the first session; results are appended below once the phases end. Common plan:
`docs/PLAN-GANAR-H2H.md` section 6 (session 6c and session d6). Counts, costs and task ids only.

## Why S2

In the Sonnet 5.5 confirmations of 2026-10-06 (S0 against clean N) the three suites gave "no
gana", and the hand reads found two S parts that changed answers: check-done (GAIA: 2 wrong to
right, 0 harmed) and early compaction with the guard putting the request back (BCP: 2-3 net
pairs). Everything else was overhead with no effect on answers. S2 keeps those two and drops the
rest. One measured reason for dropping fetch: in GAIA conf the passages of `fetch_passages` put
a median of 2,858 characters per page read into Sonnet's context, against 693 for WebFetch's
summary (9,278 against 2,388 per session with page reads), so the tool replaced a cheap reader
with expensive context.

## Lines (unsealed; null source and commit freeze this worktree's HEAD at each preflight)

| Line | File | Flags |
|---|---|---|
| S2 | `benchmarks/h2h/s2_install.json` | `--guard --guard-profile coding --context-budget 160000 --check-done --provider jev`, `GUARD_CHOOSER=keep` |
| S2F | `benchmarks/h2h/s2f_install.json` | S2 + `--fetch`, `FETCH_VERSION=3` (falls back to WebFetch, e6c04ff) |

Declared difference from S0 beyond the flags: on main the guard's block goes out split over 6
SessionStart hooks (guard-split cb0062e).

## Phases

Only the S arm runs, against the N and S0 rows of the dev phases already done (N is the same
pinned clean Claude Code 2.1.287), as S1 was measured; `compare_lines.py --lines` puts them side
by side. Same dev task lists as before, out of every confirmation.

| Phase | Suite | Line | Tasks | Expected (S0 dev mean) | Ceiling |
|---|---|---|---|---|---|
| `dev-s2` | GAIA | S2 | 20 | ~1.8 USD (0.09) | 4.5 |
| `dev-s2f` | GAIA | S2F | 20 | ~2.2 USD | 4.5 |
| `longdoc-dev-s2` | LongBench v2 | S2 | 10 | ~1.2 USD (0.12) | 4.5 |
| `bcp-dev-s2` | BrowseComp-Plus | S2 | 10 | ~7.8 USD (0.78) | 20 minus the spend of the three above |

Expected about 13 USD of list price on the subscription; a hard total of 20 USD (owner's OK,
2026-10-07): the phases run one after another and BCP's ceiling is what is left. Each phase stops
before a session whose cap (1.50 GAIA, 3.00 others) would cross its ceiling. Jev: cents.

Commands (from this worktree; announce PID, time and ceiling to session 6c before each):

```
powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_gaia.py -RunnerArgs "--phase dev-s2 --brazos SP --ids benchmarks/h2h/gaia-dev-ids.txt --s-line benchmarks/h2h/s2_install.json --unsealed-ok --ceiling 4.5" -Log C:\sp-runs\h2h\dev-s2.log -PidFile C:\sp-runs\h2h\dev-s2.pids
powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_gaia.py -RunnerArgs "--phase dev-s2f --brazos SP --ids benchmarks/h2h/gaia-dev-ids.txt --s-line benchmarks/h2h/s2f_install.json --unsealed-ok --ceiling 4.5" -Log C:\sp-runs\h2h\dev-s2f.log -PidFile C:\sp-runs\h2h\dev-s2f.pids
powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_longdoc.py -RunnerArgs "--phase longdoc-dev-s2 --brazos SP --ids benchmarks/h2h/longdoc-dev-ids.txt --s-line benchmarks/h2h/s2_install.json --unsealed-ok --ceiling 4.5" -Log C:\sp-runs\h2h\longdoc-dev-s2.log -PidFile C:\sp-runs\h2h\longdoc-dev-s2.pids
powershell -File benchmarks/h2h/launch.ps1 -Runner h2h_bcp.py -RunnerArgs "--phase bcp-dev-s2 --brazos SP --ids benchmarks/h2h/bcp-dev-ids.txt --s-line benchmarks/h2h/s2_install.json --unsealed-ok --ceiling <20 - spent>" -Log C:\sp-runs\h2h\bcp-dev-s2.log -PidFile C:\sp-runs\h2h\bcp-dev-s2.pids
```

## What the dev is for

1. The line runs end to end in each suite (install, hooks, Jev, compaction, check-done), with no
   component the line left out showing up in the side logs.
2. S2 against S0 on cost per session, with success not visibly worse (10-20 tasks: direction
   only). The expectation, written before: S2 cheaper than S0 in GAIA and LongBench (no memory,
   candor, scan or crawl latency and prefix), about the same in BCP (compaction is its cost).
3. S2F against S2 in GAIA: tokens reaching Sonnet per page read and cost per session. Fetch v3
   goes into the confirmation only if S2F is not dearer than S2 here.

Then a sealed confirmation of S2 with its own prereg (margin of non-inferiority at the interval's
half-width; each mechanism also measured where it fires), asked of the owner with its cost.

## Results (2026-10-07, 12:09-13:21)

Spend: 11.4 USD of list price on the subscription (GAIA S2 1.98, S2F 2.09, LongBench 0.83, BCP
6.48, judge a few cents), Jev 0.002 USD.
Every row valid, none at its cap, no Jev errors. Files: `compare-gaia.json`, `compare-longdoc.json`,
`compare-bcp.json` (`compare_lines.py --lines ...`; counts, costs and task ids only).

Tasks with a valid row in every line (N and S0 from the dev phases of 2026-10-05/06):

| Suite | Tasks | Right N / S0 / S2 | Cost S2/N [95 %] | Cost S2/S0 [95 %] | Wall mean s N / S0 / S2 |
|---|---|---|---|---|---|
| GAIA | 10 | 8 / 8 / 8 | 1.085 [0.62, 1.65] | 0.886 [0.68, 1.24] | 47 / 58 / 33 |
| LongBench v2 | 10 | 7 / 7 / 8 | 1.281 [0.96, 1.80] | **0.675 [0.60, 0.75]** | 18 / 39 / 21 |
| BrowseComp-Plus | 10 | 5 / 7 / 6 | 1.408 [0.92, 2.19] | **0.832 [0.54, 0.98]** | 66 / 106 / 96 |

- **S2 against S0**: cheaper in all three, with the interval below 1 in LongBench and BCP, no
  answer lost that S0 had (discordant S2/S0: GAIA 1/1, LongBench 1/0, BCP 0/1). As expected.
- **S2 against N**: not cheaper in any. 10 tasks only, and N ran a day earlier: direction only.
  In LongBench S2 wrote 150k cache tokens against N's 111k on the same tasks, about 0.15 of the
  0.18 USD gap; why it writes more is not read yet.
- **The mechanisms are alive**: in BCP S2 compacted in 2 sessions (4 compactions), as S0 did in
  the same dev (2 sessions, 3), N in none; check-done made 16 Jev decisions in GAIA, none in
  LongBench (gate A) and none in BCP.
- **S2F against S2** on the 20 GAIA dev tasks: right 16 against 15 (discordant 2/1), cost
  **1.054 [0.83, 1.36]**, 0.95 more turns and 9 s more per session. Sonnet's spend +0.28 USD
  (+22 %), Haiku's -0.18: the money moves from WebFetch's reader to the main model, as session 6c
  predicted from the confirmation's numbers. Per session with page reads, 6,143 characters reached
  Sonnet with S2F against 1,621 with S2. By the rule written above, **fetch v3 stays out of the
  S2 confirmation**.

### Found on the way, not part of the dev's question

- **check-done's probability does not separate its useful send-backs** (GAIA conf, scored in
  memory with GAIA's scorer): of 18 send-backs, 2 wrong to right (p 0.12 and 0.20), 10 right
  answers sent back for nothing (p 0.04 to 0.49), 6 wrong that stayed wrong (p 0.04 to 0.25), none
  harmed. Any stricter cut loses both fixes: a more demanding check-done has to change the
  question, not the threshold.
- **Search stops on its own when the answer arrives** (BCP conf, official gold qrels): in the
  right sessions the first gold document came at search 4-5 and a median of 0 searches followed,
  in both arms. The money is in the wrong sessions (N 43.7 of 61.0 USD, S 45.4 of 71.4), most of
  which never saw a gold document (N 33 of 41, S 25 of 34). 8 N and 9 S sessions got a gold
  document and still answered wrong (S then searched a median of 10 more times): the room for a
  check of the returned documents is there, not in an early stop.
- **Order of the arms in an S2 confirmation**: S0's prefix differs from N's (its tools and skill),
  so S0 could not read N's cache, and in the confirmations it wrote less cache than N in only
  26/50, 21/135 and 31/90 pairs. S2 adds nothing to the prefix, so with N always first it could
  read N's cache: the S2 confirmation alternates which arm goes first.
