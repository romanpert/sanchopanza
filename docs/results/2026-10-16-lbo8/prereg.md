# Lot lbo8 (DRAFT, not sealed): the longdoc router at the 0.8 cut against Opus 5.5, on fresh LongBench v2 tasks

**Status: a ready draft, not proposed for funding now.** At 0.8 the router saved about 10.6 % of
Opus's cost on lb162x (descriptively), and 78 tasks cannot decide a −3-point margin (see
Power). Nothing here is sealed, no session has run, and nothing has been spent. Sealing needs: the owner's choice of margin and population (below), the live driver
and its guard (not written), a `revisor-prereg` review against the code, and then `--seal`.

## Why

Lot lb162x confirmed the router at the 0.6 cut against Opus 5.5: −3.7 points [−8.0, +0.6], "no
peor" at −10, 29.5 % of Opus's cost saved. Post hoc on the same 162 tasks, the 0.8 cut came to
−0.6 points for a smaller saving (`python benchmarks/jev114/lbo8.py --dry`, descriptive):

| Cut | Covered | Jev / Opus right on them | Jev only / Opus only | Hybrid minus Opus | Opus cost avoided | Net saving (Jev on all 162 paid) |
|---|---|---|---|---|---|---|
| 0.6 | 60 (37.0 %) | 31 / 37 | 4 / 10 | −3.70 points | 6.23 USD | 5.35 USD, 29.5 % |
| 0.7 | 41 (25.3 %) | 21 / 25 | 2 / 6 | −2.47 | 4.27 | 3.40, 18.7 % |
| 0.8 | 27 (16.7 %) | 17 / 18 | 0 / 1 | −0.62 | 2.81 | 1.93, 10.6 % |
| 0.9 | 12 (7.4 %) | 9 / 10 | 0 / 1 | −0.62 | 1.33 | 0.45, 2.5 % |

At 0.8, a paired bootstrap of the 162 gives [−1.9, 0.0] points and a net saving of
[4.9 %, 17.1 %]. Tango's score interval, which keeps a width with one disagreement, gives about
[−3.4, +1.7] (at 0.6: [−8.9, +0.9]). This is a hypothesis to confirm, not a result.

## Tasks: the measured population is spent

LongBench v2 has 503 tasks. The router's population is the Single- and Multi-Document QA domains
over 100,000 characters: 222 tasks, and all 222 are used (the 60 of 2026-10-06 with their 10 dev
tasks, and lb162's 162). Fresh, 281 remain:

- **78 in the same two domains** (55 Single-, 23 Multi-Document QA), all under 100,000 characters
  (48,765 to 99,827, median 72,731), all of the set's "short" band; 53 hard, 25 easy. Frozen by
  metadata only in `ids.txt` (sha256 607d0d3e…). The tests check that none is one of lb162's
  162 or the 10 dev tasks, and none of the 60 of 2026-10-06 where the local cache holds them
  (skipped without it). The freeze itself drew them outside all 222 used ids (`lbo8.used_ids`).
- 203 in other domains: Long In-context Learning 81, Code Repository Understanding 50,
  Long-dialogue History 39, Long Structured Data 33.

**Proposed population: the 78.** The same domains, template and grader, so this tests the cut
and the shorter documents together. A fail would not say which. Documents of 49,000 to 100,000
characters were not measured before: the point's docstring says so.

## Design

- **Phase J:** Jev `jev-1.14.0`, lb162's request to the byte (long-context header, 900,000-
  character middle cut, retries at 0.8 and 0.64 of the window), through `lb162.run_j`. Recorded
  first, live only on a miss. Ledger and batch cap **0.20 USD**. `jev-preflight` before.
- **The cut:** a task is covered when Jev's top-choice probability is **≥ 0.8**.
- **Phase O:** Opus 5.5 (`claude-opus-5-5`) in clean Claude Code 2.1.287 (arm N, as in
  lb162x), one session per task on **all 78**, in a seeded random order. Opus's answer stands on
  the uncovered tasks, so only the covered ones move the verdict. Running all 78 measures the
  saving. Graded by LongBench v2's official `extract_answer` (`longdoc_data.last_answer`).
- **Smoke:** one Opus session on lb162x's smoke task (a dev task outside the 78), 0.80 USD.

## Primary verdict

- Hybrid minus Opus over the 78, with b the covered tasks only Jev got right, c those only Opus
  got right, and n = 78: estimate (b − c) / n.
- **Tango's score 95 % interval** for a paired difference (`lbo8.tango_ci`). The percentile
  bootstrap of lb162x collapses to a point when the covered tasks show no disagreement, which is
  likely here.
- **Margin (owner's decision before the seal): −5 points proposed, −7 the alternative.** "no
  peor" when the lower bound is above the margin, "peor" when the upper bound is below it, else
  "no concluyente".
- No verdict with fewer than 8 covered tasks with an Opus session ("no medido").
- Infrastructure errors and lowered-cap stops are read as in lb162x: not run in the primary
  reading, wrong in the sensitivity reading.

**Secondary (registered):**
- The saving of Opus's cost: Opus alone minus (Jev on all 78 + Opus on the uncovered), as a
  share of Opus alone. Paired bootstrap over the tasks (10,000 draws, seed 20261016). "ahorra"
  when the lower bound is above 0.
- Jev's precision and Opus's accuracy on the covered tasks; McNemar on the disagreements.
- Descriptive: the 0.6 and 0.7 cuts on the same rows.

## Power: the task is the unit

Tango's interval has a floor: with no disagreement at all, the lower bound is −z²/(n + z²).
That is **−4.7 points at 78 tasks**, −2.3 at 162 and −1.35 at 281. **A −3-point margin cannot
pass with 78 tasks, whatever the data.**

Chance of "no peor" (`lbo8.power`, 1,000 draws a cell):

| Scenario (coverage; Jev-only and Opus-only rates on the covered) | n | −3 | −5 | −7 | −10 |
|---|---|---|---|---|---|
| As lb162x at 0.8 (16.7 %; 0/27, 1/27) | 78 | 0.00 | 0.62 | 0.92 | 0.98 |
| | 281 | 0.77 | 1.00 | 1.00 | 1.00 |
| 0.7's disagreement rates at 0.8's coverage (16.7 %; 2/41, 6/41) | 78 | 0.02 | 0.16 | 0.45 | 0.78 |
| | 281 | 0.18 | 0.74 | 0.98 | 1.00 |
| 0.6's disagreement rates at 0.8's coverage (16.7 %; 4/60, 10/60) | 78 | 0.03 | 0.17 | 0.39 | 0.72 |
| | 281 | 0.14 | 0.68 | 0.96 | 1.00 |
| 0.6's disagreement rates at 25 % coverage (4/60, 10/60), the most pessimistic | 78 | 0.02 | 0.09 | 0.23 | 0.55 |
| | 281 | 0.05 | 0.34 | 0.76 | 0.99 |

Read plainly:
- **With the 78,** "no peor" at −5 has about 62 % power if 0.8 behaves as it did on lb162x, and
  about 17 % if Jev disagrees with Opus as much as at 0.6 (9 % if it also covers 25 %). At −7:
  92 %, 39 % and 23 %.
- **A tight claim** ("keeps Opus's accuracy", −3) would need all 281 fresh tasks: about 77 %
  power in the good scenario. But 203 of those tasks are domains the router was never measured
  on.
- **What a pass would license:** at −5 and about 17 % coverage, Jev could be up to about 30
  points less accurate than Opus on the tasks it answers. The margin is a product decision.

## Money (hard caps, in code)

| | Expected | Cap |
|---|---|---|
| Phase J, Jev on 78 (5.77 M characters at 0.012 USD per M) | 0.07 USD | 0.20 USD (ledger + batch); 0.086 at the dearest rate before retries |
| Smoke, one Opus session | ~0.2 USD | 0.80 USD |
| Phase O, Opus on 78 (0.10 USD a task: lb162x's short band was 0.099, max 0.19) | 7.8 USD; simulated mean 7.73, p95 8.21; at 1.6 x, p95 13.14 | **ceiling 30.00 USD** |
| **Lot** | **about 8.1 USD** | **31.00 USD** |

- **Each session:** `--max-budget-usd` 6.00 (arm N's Opus cap, unchanged from lb162x).
  `cap_for` lowers the cap when 6.00 plus one worst turn no longer fits under the ceiling.
  Below 1.00 the phase stops. The worst turn is 8.64 USD: Opus 5.5 rewrites its whole 1M-token
  window to the cache and answers 32,000 tokens. The cap leaves room for it because
  `--max-budget-usd` only cuts between turns.
- **Exposure:** at 1.6 x the expected cost, all 78 sessions run with no cap lowered. At worst
  (every session at its cap plus a worst turn) the ceiling runs 2 sessions.
- **Above the 10 USD line:** the lot's ceiling is 31 USD, so the owner says yes before the seal.
  The expected cost is 8.1.
- **Wall time:** about 30 minutes of Opus sessions (lb162x: mean 22 s a session), one at a time.
  The clock and STOP rules are lb162x's: no crossing midnight, nothing between 02:00 and 08:00,
  STOP on a 429.

## Dry run, done (free)

`python benchmarks/jev114/lbo8.py --pool | --freeze-ids | --prepare | --dry`, 2026-10-16:

- **The pool:** 503 rows, 222 used, 281 fresh, 78 in the QA domains, 0 left in the measured
  population.
- **The documents:** 78 prepared into the local cache (`~/.cache/sanchopanza/longdoc/lbo8`),
  none missing.
- **Phase J, through lb162's own runner** with no live decider and no recordings:
  - 78 rows and 234 tries (three lengths each), 0.00 USD.
  - Every document was read, cut and asked of the replay.
  - Status `failed` on all 78, as expected with nothing recorded.
- **Phase O:** 78 prompts built with h2h_longdoc's official template (at most 2,991
  characters). The official grade read a canned reply right.
- **The money rule** was simulated on lb162x's real Opus sessions: see Money.

## Before a seal (not done)

1. The owner chooses: the margin (−5 or −7), the 78 or a wider population, and the 31 USD
   exposure.
2. The live driver (`h2h_lbo8.py`) and its guard. h2h_lb162x.py is bound to lb162x's tasks
   and recordings (`tasks_of`, `problems`, `refusal`), so lbo8 needs its own thin driver over
   h2h_longdoc, as lb162x had.
3. The phase J live entry and the stats module, with tests.
4. A `revisor-prereg` review, then `--seal`, and a detached worktree at the sealed commit.
