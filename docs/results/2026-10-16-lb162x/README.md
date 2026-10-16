# The lb162 router against Opus 5.5, and its saving measured, on 162 LongBench v2 tasks (lot lb162x)

**The result.** Lot lb162 routed long-document multiple-choice questions: Jev 1.14 answers alone
where its top choice is ≥ 0.6, the expensive model answers the rest. This lot ran the
expensive model wherever lb162 had not, reusing Jev's lb162 answers as recorded.

- **Against Opus 5.5 (phase B, the primary verdict):** **"no peor"** at the sealed −10-point
  margin. Hybrid minus Opus alone is **−3.7 points**, 95 % CI **[−8.0, +0.6]**, over 162 tasks.
  Coverage is 37 %, so the product claim also holds: **"sustituye"**.
  - **Read plainly:** the hybrid holds against Opus at −10 too, and Opus was right more often
    than Jev on the tasks Jev covers: on those 60, Opus on 37 and Jev on 31 (McNemar 10 against
    4, p 0.18).
  - The point estimate is a loss, and the CI's upper bound is barely above 0. Only the −10
    margin decides; a −2 or −5 margin would read "no concluyente".
- **The saving of Sonnet 5.5's cost, now measured (phase A):** **33.9 %**, 95 % CI
  **[24.0 %, 44.0 %]**, reading **"ahorra"**. That is 4.88 of 14.40 USD over the 162 tasks.
  lb162's estimate of 26.7 % falls inside the CI.
- **The saving of Opus 5.5's cost:** **29.5 %**, 95 % CI **[21.7 %, 37.7 %]**, reading
  **"ahorra"**. That is 5.35 of 18.15 USD.
- **The two expensive models alone, both now measured on all 162:**
  - Opus 5.5 right on **105 (64.8 %)**, Sonnet 5.5 on **89 (54.9 %)**: McNemar 26 against 10,
    p 0.011.
  - Opus cost 18.15 USD, Sonnet 14.40: **1.26 x**, not the 2 x the plan assumed.

The setup:
- **Arms:**
  - Jev `jev-1.14.0`, lb162's recorded answers with the long-context header and up to 900,000
    characters (no new Jev call);
  - Opus 5.5 (`claude-opus-5-5`) and Sonnet 5.5 (`claude-sonnet-5-5`), each in clean Claude
    Code 2.1.287 (arm N of the 2026-10-06 confirmation, as in lb162).
- **Pre-registration:** `prereg.md`, sealed at 24adf4a (`prereg.sha256` a6feb6d5…). It was
  reviewed by `revisor-prereg` before the seal. The seal also covers lb162's recordings and the
  pinned Claude Code build.
- **The run:** live on 2026-10-16 from a detached worktree of the sealed commit.
- **Reproducibility:**
  - A free replay of lb162's Jev answers gives its `jev-scored.jsonl` exactly.
  - Exporting the sessions again and recomputing give the same `opus-rows.jsonl`,
    `sonnet-rows.jsonl`, `smoke-rows.jsonl` and `summary.json`, byte for byte.

## Design

- **Tasks.** lb162's 162 LongBench v2 tasks (Single- and Multi-Document QA, contexts over
  100,000 characters, frozen before any answer).
  - Phase B: all 162, in a seeded random order (`opus-ids.txt`).
  - Phase A: the 102 Jev did not cover at 0.6, in a seeded random order (`uncovered-ids.txt`).
  - Both orders are derived in code from lb162's rows.
- **The cut.** lb162's, unchanged: covered when Jev's top-choice probability is ≥ 0.6, 60 of
  162.
- **Sessions.**
  - One clean Claude Code session per task, graded by LongBench v2's official `extract_answer`.
  - Per-session caps: Opus 6.00 USD, Sonnet 3.00. Phase ceilings: 45 and 16 USD.
  - Before phase B, one Opus smoke session on a dev task outside the 162 checked the path.
- **Statistics.**
  - Paired bootstrap over the 162 tasks (10,000 draws, seed 20261015, all kept).
  - Exact McNemar on the covered disagreements.
  - The −10-point margin and the 20 % coverage rule are lb162's, fixed before the data.

## Primary result: the hybrid against Opus 5.5 alone

| | Value |
|---|---|
| Tasks (n) | 162 |
| Covered at 0.6 | 60 (**37.0 %**) |
| Opus sessions on them | 60 of 60 |
| Jev right on the covered tasks | 31 of 60, **51.7 %** |
| Opus right on the same tasks | 37 of 60, **61.7 %** |
| Disagreements | 14: Jev only 4, Opus only 10 (McNemar p 0.18) |
| Hybrid minus Opus | **−3.7 points**, 95 % CI **[−8.0, +0.6]** (normal approximation [−8.2, +0.8]) |
| Verdict at −10 points | **no peor** |
| Product claim (also coverage ≥ 20 %) | **sustituye** |

**What the margin allows.** Over all 162 tasks, −10 points at 37 % coverage means Jev could be up
to 27 points less accurate than Opus on the tasks it answers.
- Measured, Jev is 10 points less accurate there (51.7 % against 61.7 %).
- The CI on those 60 tasks is about [−22, +2] points.

**Sensitivity reading** (registered): no Opus session ended in an infrastructure error, hit a
cap, ran on a lowered cap, or was served by another model. So counting such sessions as wrong
changes nothing: −3.7 points, [−8.0, +0.6], "no peor".

**The saving of Opus's cost** (registered, secondary):

| | USD |
|---|---|
| Opus 5.5 alone on the 162 | 18.148 (covered 6.227, uncovered 11.921) |
| Hybrid (Jev on all 162 + Opus on the 102 uncovered) | 12.795 |
| Saving | **5.353, 29.5 %**, 95 % CI [21.7 %, 37.7 %]: **ahorra** |

## Secondary result: the saving of Sonnet 5.5's cost, measured

| | USD |
|---|---|
| Sonnet 5.5 alone on the 162 | 14.400 (covered 5.757 from lb162, uncovered 8.643 from this lot) |
| Hybrid (Jev on all 162 + Sonnet on the 102 uncovered) | 9.517 |
| Saving | **4.883, 33.9 %**, 95 % CI [24.0 %, 44.0 %]: **ahorra** |
| lb162's estimate (26.7 %) | inside the CI |

- The sensitivity readings change nothing: no Sonnet session errored, hit its cap or ran on a
  lowered cap.
- lb162's verdict against Sonnet stands as sealed. The re-read on all 162 gives its +1.2 points,
  [−3.1, +5.6]: an uncovered task adds 0 to hybrid minus Sonnet.

## Accuracy on the 162, every answer measured (descriptive)

| | Right | Accuracy (Wilson 95 %) | USD | USD per right answer |
|---|---|---|---|---|
| Opus 5.5 alone | 105 | 64.8 % (57.2-71.8) | 18.15 | 0.173 |
| Jev where covered, Opus elsewhere | 99 | 61.1 % | 12.79 | 0.129 |
| Sonnet 5.5 alone | 89 | 54.9 % (47.3-62.4) | 14.40 | 0.162 |
| Jev where covered, Sonnet elsewhere | 91 | 56.2 % | 9.52 | 0.105 |
| Jev alone (lb162) | 64 | 39.5 % | 0.87 | 0.014 |

- **On the 102 tasks Jev did not cover,** Jev alone would have given up a lot. It was right on
  33 of 102, against 68 for Opus (McNemar 7 against 42) and 60 for Sonnet (11 against 38). The
  0.6 cut does its job.
- **Opus against Sonnet** on the same 162: Opus only right on 26, Sonnet only on 10 (p 0.011).

## By band (descriptive)

| Length | Tasks | Covered | Jev / Opus right on them | Hybrid minus Opus | Opus saving | Sonnet saving | Opus / Sonnet right on all |
|---|---|---|---|---|---|---|---|
| Short | 38 | 18 | 11 / 12 | −2.6 points | 39.2 % | 43.5 % | 27 / 23 |
| Medium | 88 | 35 | 16 / 20 | −4.5 | 32.6 % | 38.1 % | 54 / 46 |
| Long | 36 | 7 | 4 / 5 | −2.8 | 11.8 % | 2.4 % | 24 / 20 |

| Difficulty | Tasks | Covered | Jev / Opus right on them | Hybrid minus Opus | Opus saving | Sonnet saving | Opus / Sonnet right on all |
|---|---|---|---|---|---|---|---|
| Easy | 50 | 19 | 13 / 12 | +2.0 points | 31.8 % | 34.3 % | 37 / 33 |
| Hard | 112 | 41 | 18 / 25 | −6.3 | 28.6 % | 33.7 % | 68 / 56 |

- The gap to Opus sits in the hard tasks (Jev 18, Opus 25 of the 41 covered).
- The saving sits in the short and medium documents: Jev covers 7 of the 36 long ones.
- The bands are small; none is a finding on its own.

**Higher cuts against Opus** (descriptive, not registered, post hoc on these data):

| Cut | Covered | Jev / Opus right on them | Hybrid minus Opus | Opus cost avoided |
|---|---|---|---|---|
| 0.7 | 41 | 21 / 25 | −2.5 points | 4.27 USD |
| 0.8 | 27 | 17 / 18 | −0.6 | 2.81 |
| 0.9 | 12 | 9 / 10 | −0.6 | 1.33 |

This is what a confirmation of a higher cut for Opus would test; it is not a result.

## Cost and time

| | USD | |
|---|---|---|
| Smoke: one Opus 5.5 session, dev task outside the 162 | 0.216 | measured; answered right |
| Opus 5.5, all 162 tasks | 18.148 | measured: 0.112 a session (median 0.098, max 0.45); plan expected 29.7 |
| Sonnet 5.5, the 102 uncovered tasks | 8.643 | measured: 0.085 a session (median 0.058, max 0.38); plan expected 9.1 |
| **This lot, Claude Code list price** | **27.01** | under the 45 + 16 USD ceilings |
| Jev | 0 | lb162's recorded answers (0.874 USD on the 162 tasks in lb162, 0.875 with the smoke) |

- **Sessions:** 162 Opus and 102 Sonnet sessions. None hit its cap, none ran on a lowered cap,
  none errored, all gave a letter, and all were served by their phase's model.
- **Turns:** Opus 3.9 on average, Sonnet 4.7.
- **Opus's cost** was planned at 2 x Sonnet's (its token rates in Claude Code). It came to
  1.26 x over the same 162 tasks: Opus used fewer turns (3.9 against 4.7).
- **Wall time:** 1 hour 34 minutes from launch to exit (08:01 to 09:35), one session at a time.
  - Smoke: 16 s.
  - Phase B: 59.7 minutes of sessions (median 19.5 s, mean 22.1 s, longest 155 s).
  - Phase A: 33.7 minutes (median 16.2 s, mean 19.8 s, longest 69 s).

## What this licenses, and what it does not

**It licenses,** for **long-document multiple-choice questions** in the conditions measured
(Jev 1.14 with the long window answering alone at ≥ 0.6, the expensive model in clean Claude
Code 2.1.287 answering the rest):
- with **Sonnet 5.5**: about a third of Sonnet's cost saved (33.9 %, [24.0, 44.0], measured),
  at no measurable loss of accuracy (lb162's +1.2 points, [−3.1, +5.6]);
- with **Opus 5.5**: about 30 % of Opus's cost saved (29.5 %, [21.7, 37.7]), within the −10
  margin. The point estimate is a loss of 3.7 points, and the data are compatible with a loss
  of up to 8.

**It does not license:**
- Jev as a general substitute for either model.
- Open-ended answers: these are four-option questions graded by the letter.
- Other document kinds: Single- and Multi-Document QA only.
- A claim that the hybrid matches Opus: Opus was right more often than Jev on the tasks Jev
  covers (37 against 31 of 60; McNemar 10 against 4, p 0.18). "No peor" here means within the
  −10-point margin. That margin is the owner's product decision,
  fixed before the data, not a statistical one.

**Limits of the evidence:**
- **One draw:** one session per task and model, one set of 162 tasks.
- **Hard tasks for both models:** over all 162, Opus alone is right on 65 % and Sonnet on
  55 %.
- **The band and cut readings are post hoc and small.**

## Recommendation

**What would ship.** The opt-in point lb162 proposed: an answer to a multiple-choice question
over a long document from Jev, with an escalation flag, in the shape of `navigate`'s
`escalate_below`.
- It returns Jev's letter and probability when the top choice is ≥ 0.6.
- Otherwise it flags the caller to ask its own model.
- It lives in `src/sanchopanza/points/`, off by default and not in `install`. Nothing in
  `policy.py` or `DEFAULT_MODEL` changes.

**Who it is for:**
- **Sonnet 5.5 users:** the case is good. About a third of the cost saved, measured, and no
  measured loss.
- **Opus 5.5 users:** the case is weaker. About 30 % saved, but the measured accuracy drops by
  3.7 points (CI to −8.0): where Jev is sure, Opus was right more often (37 against 31 of
  60; p 0.18).
  - The point's documentation should say so.
  - A user who wants to keep Opus's accuracy can raise the cut: descriptively, at 0.8 the gap
    was 0.6 points for a smaller saving (1.93 USD of 18.15 net of Jev's 0.87; 2.81 USD of
    Opus's cost avoided). That would need its own confirmation.
- **Choosing between the two models:** on these tasks, Jev with Sonnet (56.2 %, 9.52 USD) costs
  half of Opus alone (64.8 %, 18.15 USD) and is 8.6 points less accurate.

**What to measure next:**
1. A higher cut for Opus users (0.8), pre-registered on fresh tasks.
2. A long-document set graded on free-text answers, where the letter grading here does not
   apply.

## Files

- `prereg.md`, `prereg.manifest.json`, `prereg.sha256`: the sealed registration.
- `opus-ids.txt`, `uncovered-ids.txt`: the two frozen orders.
- `opus-rows.jsonl`, `sonnet-rows.jsonl`, `smoke-rows.jsonl`: per session, the letter, grade,
  cost, time, how it ended, its cap and whether its model served it. No text.
- `opus-stop.json`, `sonnet-stop.json`, `smoke-stop.json`: how each phase ended (`done`).
- `summary.json`: the analysis.

Reproduce for free (needs the LongBench v2 cache):

```bash
PYTHONPATH=src python benchmarks/jev114/lb162x.py            # summary.json from the rows
PYTHONPATH=src python benchmarks/jev114/lb162x.py --dry      # both phases' plan, money and power
```
