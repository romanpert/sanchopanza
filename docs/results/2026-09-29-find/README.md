# Repository search on SWE-bench Verified: which files does an issue need?

**The result:** given a real GitHub issue, `find_in_repo` names a file the accepted fix edits
**first in 51 % of issues and in the top five in 65 %**. BM25 over whole files, the SWE-bench
paper's retrieval baseline, does it in 14 % and 35 %. That costs a median 0.0016 USD and
0.74 s of Jev per issue. All three registered hypotheses hold.

Pre-registered in `prereg.md` (commit 16f8479, sealed before any arm ran on the sample). Jev
spent 0.215 USD in all, under the 0.50 cap. Every answer is recorded (`answers.jsonl`: answers,
costs and hashed keys, no text) and replays free.

## Data

- **Dataset:** SWE-bench Verified, 117 issues sampled with a seed, at most 12 per repository
  across all 12 repositories.
- **Checkout:** each repository at the issue's base commit.
- **Label:** the files the accepted patch edits (141 in all; 102 issues edit a single file).
  Nobody here labelled anything.

## Registered verdicts (`summary.json`)

| | Hypothesis | Result |
|---|---|---|
| F1 | The judged arm's any@5 is >= file BM25 + 10 points | **Holds**: 65.0 % against 35.0 % (+30.0) |
| F2 | The judged arm's any@1 is >= fragment BM25 + 5 points | **Holds**: 51.3 % against 13.7 % (+37.6) |
| F3 | The judge's median cost is <= 0.005 USD per issue | **Holds**: 0.0016 USD |

## Every arm

| Arm | any@1 | any@3 | any@5 | any@10 | all@5 |
|---|---|---|---|---|---|
| BM25 over whole files | 13.7 % | 31.6 % | 35.0 % | 48.7 % | 31.6 % |
| BM25 over fragments (`find_in_repo` with no key) | 13.7 % | 34.2 % | 42.7 % | 52.1 % | 38.5 % |
| Fragments judged in context (`find_in_repo` with Jev) | **51.3 %** | **59.8 %** | **65.0 %** | **69.2 %** | **58.1 %** |

- **Ceiling.** A gold file was among the 60 shortlisted fragments in 72.7 % of issues. That is
  the most the judge can reach, and it reached 65.0 % at five files. The rest of the gap is
  the shortlist, not the judge: the shortlist is lexical, and an issue that never names the
  code it breaks leaves BM25 nothing to find.
- **Per repository**, any@5 of the judged arm against file BM25:

  | Repository | Judged | File BM25 | Issues |
  |---|---|---|---|
  | django | 9 | 3 | 12 |
  | scikit-learn | 11 | 6 | 12 |
  | xarray | 8 | 1 | 12 |
  | requests | 6 | 3 | 8 |
  | pylint | 6 | 3 | 10 |
  | sphinx | 5 | 1 | 12 |
  | matplotlib | 5 | 3 | 12 |
  | astropy | 7 | 6 | 12 |
  | sympy | 8 | 7 | 12 |
  | pytest | 8 | 6 | 12 |

  The judge never scored below BM25 in any repository.
- **Three issues where the judge kept nothing.** In psf__requests-2317, pydata__xarray-2905
  and pylint-dev__pylint-7080, Jev answered (and was paid) but kept no fragment. The ranking
  then fell back to BM25, as `select` does by design. `judge_answered` in `scored.jsonl` means
  "kept at least one", not "answered at all".
- **Fragments per repository:** 1,395 for requests at the smallest, 33,000 or more for django.
  Indexing takes 3-35 s per checkout, in memory, rebuilt when a file changes.

## What this does and does not show

- **It shows** a retrieval step: the files an agent should open first for an issue, from the
  issue text alone, before it reads anything.
  - At no cost and with no key, fragments beat whole files by 8 points at five.
  - One cheap judge over the shortlist nearly quadruples the first-file hit rate.
- **It does not show** that an agent solves more issues with the tool, or spends less. That is
  an end-to-end question, not measured here.
  - Agents already search with `grep` and `Glob`, and the tool competes with those, not with
    nothing.
  - Published agent-based localisation reports higher any@5. It reads the repository with a
    generative model over many turns, which is another cost class.
- **Instances:** SWE-bench issues are public, and the repositories are well known to generative
  models. Jev does not generate. It was asked to judge fragments against the first 400
  characters of the issue.

## Raising the shortlist ceiling (after the registered run; `benchmarks/find/ceiling.py`)

The judge can keep only what the BM25 shortlist holds. Six code-only strategies were compared
on a dev sample of 48 SWE-bench Verified issues, disjoint from the 117. One was chosen there
(commit 8aa608f), before it ran on the 117. Free: no model.

| Strategy | Dev (48) | Test (117) |
|---|---|---|
| `base`: BM25 over fragments (the registered arm) | 36 | 85 (72.6 %) |
| `ident`: identifiers repeated in the query | 36 | 85 |
| `files`: files first, then their fragments | 28 | 72 |
| `paths`: files the issue names first | 37 | 88 |
| `rrf`: rank fusion of fragments and files | 39 | 89 |
| `combo`: `paths` then `rrf` | 38 | 91 |
| **`rrf_ident`** (chosen on dev): `rrf` plus a query of the issue's identifiers alone | **42** | **88 (75.2 %)** |

- **The chosen strategy does not replicate its dev gain.** It went from +6 on dev to +3 on test
  (5 issues gained, 2 lost), which is within noise.
- `combo` scores highest on test. It was not the one chosen, and choosing it now would be
  choosing on the test.
- **Why `ident` does nothing.** `BM25Index.scores` counts each query word once, and the
  tokeniser keeps `snake_case` whole. So repeating identifiers weighs nothing, and
  `refund_payment` never matches "refund a payment". The symbol source (`context.sources`) splits
  names into words for that reason.
- **What stays true:** the ceiling is lexical. An issue that never names the code it breaks
  leaves every code-only strategy tried here little to find.
