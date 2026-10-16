# B3 at the 0.6 cut: the −2-point confirmation was not run, because it cannot decide (the −10-point one ran as lb162)

**The result.** Lot L6 proposed a confirmation of its one post hoc number: on LongBench v2,
Jev 1.14 with the long window answering alone where its confidence is >= 0.6, and Sonnet 5.5
elsewhere, tied Sonnet's 31/50 at 43 % of its cost. Before paying for it, the power of that
confirmation was measured for free from L6's recorded answers.

- **50 fresh tasks with Jev alone reach a verdict about 4 % of the time.** With no Sonnet
  answer on the fresh tasks, the hybrid is compared with Sonnet's mean accuracy measured on L6's
  tasks. The 95 % CI of hybrid minus Sonnet is ±12 points, against a −2-point margin. P("no
  peor") is 3.7 % and P("peor") 0.1 %.
- **With Sonnet answering the fresh tasks, it is not much better.** 50 paired tasks decide
  about 8 % of the time. All 162 fresh eligible tasks of LongBench v2 decide about 10 % of the
  time.
- **The −2-point rule needs about 3,200 paired tasks** if the hybrid truly ties Sonnet.
  LongBench v2 has 503 tasks in all.
- **Jev 1.14 was not called. 0 USD of Jev, 0 of Claude.**

The −2-point rule cannot confirm this hybrid on LongBench v2, with Claude or without. The
hypothesis stays open, not refuted. No product claim follows from it.

The design this lot named as deciding, 162 tasks at −10 points with Sonnet on the covered ones,
was run as [lb162](../2026-10-15-lb162/README.md): no worse than Sonnet 5.5 (+1.2 points
[−3.1, +5.6]), "sustituye", with coverage 37 % rather than L6's 54 %, Jev's precision on the
covered tasks 52 %, and Sonnet's cost on them 5.76 USD against the 12 estimated here.
[lb162x](../2026-10-16-lb162x/README.md) then measured the whole saving (33.9 % [24.0, 44.0] of
Sonnet's cost) and the hybrid against Opus 5.5 (no worse at −10, −3.7 [−8.0, +0.6]). The
−2-point question stays as above.

## Why the confirmation cannot decide

Hybrid minus Sonnet only moves on the tasks Jev covers: there it is Jev's answer minus
Sonnet's. In L6 at 0.6 (cell 1.14 L, the primary cell):

- **Covered:** 27 of 50 tasks.
- **Right on them:** Jev 17, Sonnet 17.
- **Disagreements:** 8, split 4 and 4.

The tie rests on 8 tasks that split evenly. A confirmation has to bound that split within
2 points of 50 tasks, which is one task.

**Measurable with Jev alone.**
- Coverage and Jev's precision on the covered tasks, on fresh tasks.
- The hybrid then reads: hybrid minus Sonnet = coverage × (precision − Sonnet's accuracy on the
  covered tasks).

**The limitation.** Sonnet's accuracy on the fresh covered tasks is not known. The only
stand-in is Sonnet's mean accuracy, 31/50 (62 %), measured on other tasks.
- In L6 the stand-in happens to hold: Sonnet was right on 63 % of the covered tasks and on 61 %
  of the rest.
- At 0.9 it does not hold: Sonnet was right on 6 of the 7 covered tasks, 86 %.
- Its own sampling error on 50 tasks (±13 points, times coverage) puts a floor of about ±7
  points under the CI, however many fresh tasks Jev answers.

**The original rule fails by construction.** L6's "sustituye" also needs precision >= 90 % on
the covered tasks. At 0.6, Jev's precision was 63 %. Confirming the hybrid at 0.6 means dropping
that condition before the data, so it would be a different rule from L6's.

## Power, resampled from L6's 50 tasks (`b3conf_power.py`, seed 20261015, 5,000 draws)

L6's 50 tasks stand in for the fresh population. The tables give the chance that a confirmation
of n tasks reaches each verdict, if the truth is what L6 saw.

**Jev alone, against Sonnet's mean of 31/50:**

| Margin | n | P("no peor") | P("peor") | CI half-width |
|---|---|---|---|---|
| **−2 points (the rule)** | **50** | **3.7 %** | **0.1 %** | **12.2** |
| −2 points | 162 | 1.1 % | 0 | 9.1 |
| −5 points | 50 | 10.7 % | 0.04 % | 12.2 |
| −10 points | 50 | 37.4 % | 0 | 12.2 |
| −10 points | 162 | 69.2 % | 0 | 9.1 |

**Paired, with Sonnet answering the fresh covered tasks:**

| Margin | n | P("no peor") | P("peor") | CI half-width |
|---|---|---|---|---|
| **−2 points (the rule)** | **50** | **6.9 %** | **1.1 %** | **11.1** |
| −2 points | 100 | 7.2 % | 0.5 % | 7.9 |
| −2 points | 162 | 9.8 % | 0.5 % | 6.2 |
| −5 points | 162 | 36.7 % | 0.02 % | 6.2 |
| −10 points | 50 | 47.2 % | 0 | 11.1 |
| −10 points | 162 | 88.2 % | 0 | 6.2 |

**Paired tasks for 80 % power at the −2-point rule** (per-task SD 0.40):

| True gain of the hybrid | 0 | +2 points | +4 points |
|---|---|---|---|
| Tasks needed | 3,204 | 801 | 356 |

## What a confirmation that can decide would cost

The fresh pool is counted by metadata only: ids, domain and length, no answers read.
- 162 tasks, outside the 60 drawn on 2026-10-06.
- Same filter: Single- and Multi-Document QA, over 100,000 characters.
- 134 of them fit in the 900,000-character window.

Costs are estimated from L6's means:
- **Jev 1.14 L:** 0.0048 USD a task.
- **Sonnet 5.5 in clean Claude Code 2.1.287:** list cost 0.123 USD a task, and 0.138 on the
  tasks Jev covers.

Sonnet is only needed on the covered tasks, about 54 % of them.

| Design | n | Jev USD | Sonnet list USD | Decides at −2 | Decides at −10 |
|---|---|---|---|---|---|
| Jev alone (proposed, within the 0.35 cap) | 50 | 0.24 | 0 | 4 % | 37 % |
| Sonnet on the covered tasks | 50 | 0.24 | about 3.7 | 8 % | 47 % |
| Sonnet on the covered tasks | 162 | about 0.78 | about 12 | 10 % | 88 % |
| Sonnet on every task (also cost ratio) | 162 | about 0.78 | about 20 | 10 % | 88 % |

**The only design that decides more often than not:** all 162 fresh tasks, Sonnet on the
covered ones, and a margin of −10 points fixed beforehand. It costs about 0.8 USD of Jev and
12 USD of Claude. A −10-point margin is a product decision, not a statistical one. It accepts
giving up up to 5 tasks in 50 for a saving of about half of Sonnet's cost.

## What was not done

- No Jev call and no Claude call.
- No fresh task was drawn: the pool was counted, not sampled.
- No pre-registration was sealed, because nothing was run.

**Ledger after this lot:** 3.6539 of 4.50 USD, of which 0 is this lot's.

## Files

- **Power analysis:** `benchmarks/jev114/b3conf_power.py`.
- **Tests:** `tests/test_jev114_b3conf.py`. They hold the analysis to L6's published counts.

Reproduce for free:

```bash
PYTHONPATH=src python benchmarks/jev114/b3conf_power.py
PYTHONPATH=src python benchmarks/jev114/b3conf_power.py --pool   # needs the LongBench v2 cache
```

The first reads only `docs/results/2026-10-15-jev114-l6/b3-scored.jsonl`.
