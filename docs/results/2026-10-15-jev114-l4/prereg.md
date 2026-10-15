# Jev 1.14 against 1.13 on find_in_repo and candor on public data (lot L4): pre-registration

Written 2026-10-15, before any jev-1.14.0 answer on these inputs. `prereg.sha256` holds the hash
of this file together with the code it names (`prereg.manifest.json`, written by
`python benchmarks/jev114/l4.py --seal`).

## The question

Does jev-1.14.0, asked today, answer the same questions on the same recorded inputs at least as
well as jev-1.13.0 asked today? Two experiments of the 1.14 plan:

- **A4, `find_in_repo`** (docs/results/2026-09-29-find): 117 SWE-bench Verified issues. Recorded
  1.13: any@1 51.3 %, any@5 65.0 %.
- **A3, candor and `check_done` on public data** (docs/results/2026-09-29-candor-external):
  errata-bench holistic AUC 0.56 (0.66 on the unverified subset); tau2 `check_done` AUC 0.56,
  accuracy at 0.5 of 54.1 % against 66.6 % for trusting the agent.

1.14 is not given anything 1.13 lacks: no long-context header, no image, the same truncation
limits (`chunks.PAGE_LIMIT` 900, `PAGE_MAX` 30, tau2's 1,500 per tool result). So any difference
is the model's, not a feature's; there is no feature effect to separate in this lot.

## Inputs, questions and thresholds: the originals', by their own code

- **find:** `benchmarks/find/swebench.py` (`instances`, `checkout`, `gold_files`, `hits`,
  `files_ranked`, `SHORTLIST` = 60). Each repository at the issue's base commit,
  `context.repo.chunks`, BM25 shortlist of 60, then `Squire.triage_many` with
  `PURPOSE.format(query=issue)` and `Thresholds(max_usd=0.05, max_decisions=50)`, everything
  else production (`pages_first_round` 0.18, `pages_in_context` 0.40, 900 characters a page,
  30 pages a call). The same 117 instances (seed 20260929, at most 12 per repository).
- **errata:** `benchmarks/candor_external/errata.items()`, 110 items (55 objected, 55
  accepted); the holistic question `monitors.MISSTATES` over `monitors.holistic_state(item)`.
  The production cut is `errata.HOLISTIC_CUT` = 0.83.
- **tau2:** `benchmarks/candor_external/tau2.items()`, 320 simulations (seed 20260929, 40 per
  file); `points.completion.questions(task, record)`, the `done` Truth. The production cut is
  `tau2.DONE_CUT` = 0.5.

A free replay of the `rec13` arm with the sealed runner, before any live call, checks that the
current code rebuilds the recorded inputs. Done on 2026-10-15 with this runner:
- **errata:** 110/110 recorded keys found; AUC 0.5602 and 0.6626 (unverified), 10/55 objected
  and 7/55 accepted flagged at 0.83: the published figures.
- **tau2:** 320/320 found; AUC 0.5574, accuracy 54.06 % against 66.56 % for trusting: the
  published figures.
- **find:** 114/117 instances replay every recorded call; 3 miss at least one (their shortlist
  is no longer byte for byte the recorded one: `context/repo.py`, `blocks.py`, `text.py` and
  `chunks.py` changed since 2026-09-29: pylint-dev__pylint-6386, -7277, -8898), and `rec13`
  sets them aside. Counting all 117 as they come out, any@1 is 57/117 and any@5 75/117
  (published: 60 and 76); the shortlist ceiling is 85/117 (published 85). So `rec13` is a
  historical reference, close to but not the published run; `j13r` and `j14` see exactly the
  same inputs as each other, which is what the comparison needs.

No 1.14 answer exists on any of these inputs.

The find path measured is the one registered on 2026-09-29 (BM25 shortlist over every file, then
the tournament). Today's `find_in_repo` defaults to code-only sources (`kind=code`); this lot
does not measure that path and the result will not be presented as today's production path.

## Arms (`benchmarks/jev114/l4.py`)

- **`j13r`:** jev-1.13.0, asked live today.
- **`j14`:** jev-1.14.0, asked live today.
- **`rec13`:** the 2026-09-29 jev-1.13.0 answers, replayed for free. A historical reference,
  reported beside the others, not in any comparison: Jev is not deterministic, and one recorded
  draw is not today's 1.13.

Every set is launched in a seeded random order (seed 20261015), so that a cap reached part way
leaves out a random subset, not the last repositories or files. `j13r` and `j14` are asked on
each item one after the other, the first alternating with the item's rank in that order (even:
1.13 first). find runs one instance at a time (the clones are shared); tau2 and errata launch
all items with at most four calls in flight. Model pinned per arm (`JevDecider(model=...,
long_context=False, images=False)`, the default 10 s timeout the originals used); before the
first call the runner runs the preflight for each model and stops unless the service answers
with the model asked for, and an answer served by another model stops the run.

## What is skipped, and why

- **MALT** (registered M1, M2): about 0.064 USD for the two arms on the holistic question alone,
  past this lot's cap once A4 is paid. Not run.
- **errata's `check_done` and per-sentence `candor` questions:** not used by any registered
  errata verdict (X2 and X3 read the holistic question). Not asked. X1 is the rules lock, with no
  model in it: unchanged by construction, not re-measured.
- **The candor counterfactuals (rounds 3-5):** phase 2 of the plan, outside this lot's cap.
  Re-asking Jev on them would need no Claude call, but it is not done here.

## Metrics

Two readings for every set. The comparisons use the items both live arms answered; the per-arm
summaries and the originals' hypotheses use each arm's answered items (n reported), and F1/F2
keep the 2026-09-29 baselines (0.3504 and 0.1368) whatever that n.

| Set | With the production threshold | Without a threshold |
|---|---|---|
| find | any@1 and any@5 of the product ranking (`swebench.one`: kept fragments first by p, then BM25; then the rest of the shortlist by BM25) | any@1 and any@5 of every shortlisted fragment ranked by its last p, then BM25 (no keep cut) |
| errata | share of items classified right at 0.83 (objected flagged, accepted not) | AUC objected vs accepted; AUC unverified-objected vs accepted |
| tau2 | accuracy at 0.5 against the reward | AUC done vs not done |

The originals' registered hypotheses (F1 any@5 >= 45.04 %, F2 any@1 >= 18.68 %, F3 median judge
cost <= 0.005 USD; X2 AUC >= 0.65, X3 >= 0.70; T1 AUC >= 0.75, T2 accuracy - trust >= 10 points)
are reported for each of the three arms, with their original thresholds and baselines.

## Decision rule (BRIEF rule 4)

For each of the nine comparisons j14 - j13r (find prod any@1, prod any@5, free any@1, free any@5;
errata AUC, AUC unverified, correct at 0.83; tau2 AUC, accuracy at 0.5):

- **Binary metrics:** exact two-sided McNemar on the discordant pairs; 95 % CI of the difference
  by paired bootstrap (10,000 resamples, seed 20261015, percentile).
- **AUC:** paired bootstrap of the difference (same scheme); p = twice the smaller share of
  resampled differences on either side of 0.
- **Resampling unit.** The verdict uses the item as the unit (BRIEF rule 4). Items are not
  independent (find: up to 12 instances per repository; tau2: four trials and four agent models
  per task; errata: two answers per task), so the same CI is also reported with the cluster as
  the unit (find: repository, tau2: domain and task, errata: task). If the cluster CI would not
  give the same verdict, the README says so beside it; the verdict is not changed.
- **Holm** over exactly the nine p-values named above; a comparison that could not be measured
  counts as p = 1 and gets "no medido".
- **"mejora"** if the difference is > 0 and the Holm-adjusted p < 0.05; else **"no peor"** if the
  item CI's lower bound is above -2 points (-0.02 of AUC); else **"no concluyente o peor"**.
- **Power.** The rule is strict for these sizes. With about 10 % discordant pairs, the CI of a
  binary difference is about +-5.7 points on find (n = 117) and +-4 on tau2 (n = 320), and an
  errata AUC difference about +-0.08 (n = 110). "No peor" then needs j14 to come out some 3-4
  points (find) or 2 points (tau2) ahead of j13r. **"No concluyente o peor" with a CI that
  straddles 0 means "not shown", not "worse"**; the README reads it that way and gives the CI.

The primary comparisons, the ones the recommendation rests on, are find **prod any@1** and
**prod any@5** (the originals' F2 and F1 metrics) and tau2 **accuracy at 0.5** (`check_done` in
production). The rest are reported with the same rule and no extra weight. No metric is swapped
after seeing the data.

An item where either live arm failed to answer (an outage, a cap refusal, a failed call; in find,
any failed call of the tournament) is set aside from the comparisons. Failures are reported per
arm. Because setting items aside could hide a 1.14 regression (1.14 failing where 1.13 does
not): (a) every binary comparison is also reported on all items with a failed answer counted
as wrong; (b) if j14 fails on more than 2 % more of a set's items than j13r, that set's
comparisons get "no concluyente o peor" whatever their CI.

## Budget

Jev only, zero Claude calls. Estimated from the recorded costs of the same calls (output is not
charged, input tokens identical): find 0.215, tau2 0.055, errata 0.010 USD per arm; **about 0.56
USD** for the two arms. Hard caps in code: every live call through `CappedDecider` on the shared
ledger `$SANCHOPANZA_JEV114_RUN/ledger.json` (`C:\sp-runs\jev114\ledger.json` by default, as
lot L1 resolves it; 4.50 USD in all) with this lot's batch cap of **0.60 USD**.
Margin: 0.04 USD (7 %). The tournament adapts (up to three rounds), so a 1.14 that keeps more
pages in the first round can cost more than 1.13 did; price and tokenizer of 1.14 are taken as
1.13's, as the smoke test measured on the same request (444 tokens each). **Order of the runs:
find, then tau2, then errata**, so that a cap reached late cuts the secondary sets, not the
primary metrics. If the cap refuses calls, the comparisons are made on the paired items that
were answered, and the README says how many were lost.

Relaunch: answers are recorded per arm in this folder (hashed keys, no text). A failed call is
not recorded. The live run is launched once; it is relaunched only if the process itself dies
(crash, machine), at most once, and then it asks only what has no recorded answer, under the
same caps. A cap refusal is not a reason to relaunch. Preflight for each model before the first
call (about 12 micro-dollars each, outside the ledger; measured 0.000024 USD for the two on
2026-10-15). The analysis (`python benchmarks/jev114/l4.py` without `--run`) only reads the
scored files.

Whatever does not hold is reported as not holding.
