# S2 development on the h2h dev tasks (2026-10-07)

Dev only, not a confirmation: nothing here decides anything. Written by indagis-d6 (line web/h2h)
before the first session; results are appended below once the phases end. Common plan:
`docs/PLAN-GANAR-H2H.md` section 6 (indagis-6c and indagis-d6). Counts, costs and task ids only.

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

Commands (from this worktree; announce PID, time and ceiling to indagis-6c before each):

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
