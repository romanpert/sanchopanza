# lbo8: the longdoc router at the 0.8 cut against Opus 5.5, on 78 fresh LongBench v2 tasks

**The result:** by the sealed rule, **"no concluyente"**. Jev 1.14 answering where its top choice
reached 0.8 and Opus 5.5 elsewhere, against Opus 5.5 alone: **−6.4 points, Tango 95 %
[−14.1, −1.4]**, against a −5-point margin. The interval lies wholly below zero and is not wholly
below the margin. The router saved **30.8 % [20.9, 41.4]** of Opus's cost ("ahorra").

On these shorter documents the 0.8 cut covered 30 of 78 tasks (38 %), more than the 17 % it would
have covered on lb162x's longer ones, and Jev was right on 20 of the 30 it answered against 25
for Opus. Every disagreement on the covered tasks went Opus's way (5 to 0, McNemar p 0.0625). So
the 0.8 cut does not license a tighter claim than the 0.6 cut's "no worse at −10" on documents
over 100,000 characters, and on documents of 49,000 to 100,000 characters the router should not
be used as it stands.

Pre-registered in [`prereg.md`](prereg.md):
- sealed in `2f232f1`, `prereg.sha256` `8adfca45…`, after a `revisor-prereg` review against the
  code; the owner's decisions (margin −5, the 78 tasks, 31 USD at worst) are in it;
- run on 2026-10-16 from a detached worktree at the seal commit, launched outside the session by
  WMI through `launch.ps1`, Claude Code 2.1.287 pinned, clean user per session (arm N, as in
  lb162x); 19:32 to 20:05, exit 0, no relaunch, no 429.

## Design

- **Tasks:** the 78 fresh LongBench v2 tasks left in the router's two domains (55 Single-Document
  QA, 23 Multi-Document QA), all under 100,000 characters (48,765 to 99,827, median 72,731), 53
  hard and 25 easy, frozen by metadata in `ids.txt` before any answer.
- **Phase J:** Jev `jev-1.14.0` with the long-context window, lb162's request (`lb162.run_j`), on
  its own ledger: 78 answered, 0 failed, 0.0649 USD.
- **Cut:** a task is covered when Jev's top-choice probability is at least 0.8.
- **Phase O:** Opus 5.5 (`claude-opus-5-5`) in clean Claude Code 2.1.287, one session per task on
  all 78 in a seeded order, LongBench v2's official template and grade.
- **Smoke:** one Opus session on lb162x's smoke task outside the 78: right, 0.21 USD.

## Primary result

| | n | Covered | Jev only right | Opus only right | Hybrid minus Opus | Tango 95 % | Verdict at −5 |
|---|---|---|---|---|---|---|---|
| Primary | 78 | 30 | 0 | 5 | **−6.4 points** | **[−14.1, −1.4]** | **no concluyente** |
| Sensitivity (infrastructure errors as wrong) | 78 | 30 | 0 | 5 | −6.4 | [−14.1, −1.4] | no concluyente |

No session had an infrastructure error, hit its cap or ended without a letter, so the two
readings agree. McNemar on the five disagreements: p 0.0625.

## Secondary results

- **The saving of Opus's cost:** Opus alone 8.96 USD; the router 6.20 (Jev on all 78, 0.065, and
  Opus on the 48 uncovered, 6.13): **30.8 % [20.9, 41.4]** saved, paired bootstrap over the tasks
  (10,000 draws, seed 20261016), "ahorra". The same in both sensitivity readings.
- **On the 30 covered tasks:** Jev right on 20 (66.7 %, Wilson [48.8, 80.8]), Opus on 25 (83.3 %,
  [66.4, 92.7]). Hard tasks: Jev 11 of 18, Opus 15; easy: Jev 9 of 12, Opus 10 (descriptive).
- **Overall:** Opus alone right on 56 of 78 (71.8 %), the router on 51 (65.4 %).
- **The other cuts, descriptive, on the same answers:** 0.7 covers 47 tasks, −5.1 points
  [−14.8, +4.0], 50.8 % saved; 0.6 covers 55, −10.3 [−20.9, −0.2], 61.8 % saved.

## What this licenses, and what it does not

- **No tighter claim for 0.8.** The lot existed to show the 0.8 cut keeps Opus's accuracy within
  5 points; it does not show it, and the direction is against it.
- **Not a "peor".** The upper bound, −1.4, is above the −5 margin: the data cannot say the router
  is more than 5 points worse either.
- **Shorter documents behave differently.** On lb162x's documents over 100,000 characters the 0.8
  cut, descriptively, covered 17 % (27 of 162) with one disagreement, Opus's way; here, at 49,000
  to 100,000 characters, it covers 38 % with five, all Opus's way. The population and the cut changed
  together, as the prereg said, so this lot cannot tell which moved the result.
- **What stands:** the 0.6 router's "no worse at −10" against Opus 5.5 and Sonnet 5.5 on
  documents over 100,000 characters (lb162, lb162x), which this lot does not touch.
  `points.longdoc` does not refuse a shorter document; its docstring says it was measured over
  100,000 characters, and this lot is the first measurement below that, at 0.8.

## Cost and time

| | USD |
|---|---|
| Smoke, one Opus session | 0.2134 |
| Phase J, Jev on 78 (own ledger) | 0.0649 |
| Phase O, Opus on 78 (list price) | 8.9566 |
| **Lot** | **9.235** |

Under the 22.36 USD of caps and the approved 31 at worst. Opus sessions: median 0.104 USD, mean
0.115, maximum 0.319; 15 ran under a lowered cap (none reached it). Wall time 33 minutes.

## Files

- `ids.txt`: the 78 task ids, frozen before any answer.
- `jev-answers-j14-L.jsonl`, `jev-scored.jsonl`: Jev's answers (letter, probabilities, cost,
  tokens), no text.
- `opus-rows.jsonl`, `smoke-rows.jsonl`: each session's letter, grade, cost and turns, no text.
- `summary.json`: the analysis (`python benchmarks/jev114/lbo8.py --analyse`, free).
- `prereg.md`, `prereg.sha256`, `prereg.manifest.json`: the seal.
