# redundant_page on Jev 1.14 with 90 more `drop` cases: the derivation clears, but at 0.04, and no cut is proposed

Jev only, no call to Claude. Both versions were asked live on 2026-10-16 over 530 cases:

- the 125 hand-written `benches/retrieval*.jsonl` cases, asked again so every case is one draw;
- 405 cases rendered from 45 invented fact records, with labels by construction.

**The seal.** Pre-registered in `prereg.md`, sealed by `prereg.sha256` (`39fdec51…`, one hash
over `prereg.md`, the cases, the launcher and the code). Every case's request and label is fixed
in `data.sha256` (`d659027b…`).

- The sealing commit `303dcc4` adds those two files and nothing else, on top of `aff4cff`.
- Its message carries only the data hash, although the registration says it carries both.
- Before sealing, `revisor-prereg` reviewed the registration against the code in two passes.

## Verdict

**No proposal: `adds_nothing` for 1.14 stays at 0.61 in `policy.MODEL_PROFILES`.** Two of the
sealed checks fail.

- **Q1, the derivation: it clears, and it is stable, at 0.04.**
  - With 141 `drop` cases in calibration, rule D (90 % target on the Wilson lower bound, most
    recall) returns 0.04 for 1.14 and 0.17 for 1.13.
  - Removing any one calibration case moves neither cut (span 0.00).
  - So the derivation no longer hinges on `rd-118`. It now sits at the floor of the `keep`
    pages' scores instead.
- **Q2, the evaluation, at 0.04 against 1.13 at 0.59.**
  - **The stratified primary is "no concluyente":** −0.2 points [−6.4, +5.5]. The hand-written
    stratum differs by 0.0 and the template stratum by −0.4.
  - **The count guard holds.** On the 50 hand-written pages 1.14 wins 2 and loses 2, and catches
    18 of the 18 hand-written drops against 16.
  - **The costly-drops guard fails.** 1.14 drops 8 `keep` pages of the evaluation part, against
    0 for 1.13, where the limit was +2.
- Every case has an answer from both versions, and the launch completed.

**What failed is the cut, not the ranking.** On the evaluation part 1.14's AUC is 1.000 and
1.13's 0.9999.

- Over all 530 cases, 1.14 scores every `keep` page between 0.00 and 0.11, except `rd-118` at
  0.65.
- It scores every `drop` page at 0.15 or more.
- At 0.04 the cut sits inside the `keep` scores. The "independent source" pages, for example,
  score 0.02 to 0.08.

**Rule D did what it says, and it is the wrong rule for this point once drops are plentiful and
easy.** Rule D keeps the cut with the most recall whose precision bound clears 90 %. With 141
drops, a handful of keeps in the acted set still clears, so the cut slides to the keep pages'
noise floor. The leave-one-out check cannot see that, since no single case moves the cut. The
costly-drops guard did see it.

## What ran

| | |
|---|---|
| Cases | 530: calibration 210 (141 drop / 69 keep), evaluation 320 (198 / 122), 62 clusters |
| Calls | 1,060, plus 2 preflights; all answered in pass 1, none missing |
| Launch | one, by WMI, from a worktree detached at `303dcc4`; 11:19:05 to 11:22:17, exit 0 |
| Order | the registered shuffle (seed 20261016), both versions per case in one slot |

## Results

### The derivation (calibration part)

| | 1.14 | 1.13 |
|---|---|---|
| **Rule D on the registered calibration part** (retrieval-c + 15 records) | **0.04** | 0.17 |
| Leave-one-out, 210 runs: range, span | 0.04-0.04, 0.00: stable | 0.17-0.17, 0.00: stable |
| Rule D on `retrieval-c` alone (descriptive) | unreachable | 0.57 |
| Rule D on the 15 records alone (descriptive) | 0.06 | 0.20 |

**On `retrieval-c` alone, 1.14's 90 % derivation is unreachable in this draw.** `rd-118`, the
off-purpose `keep` page with no figures, scored 0.65 (0.60 in L1). It is the highest score 1.14
gives any hand-written `keep` page; the next is 0.09.

### The evaluation part, at the cuts used

| Arm | Right | Drops | Costly drops (keep pages dropped) | Recall of drops |
|---|---|---|---|---|
| 1.13 at 0.59 | 313 / 320 | 191 | 0 | 0.965 |
| **1.14 at 0.04** | **312 / 320** | 206 | **8** | 1.000 |

| Check | Value | Rule | Result |
|---|---|---|---|
| **Stratified primary**: hand and templates, equal weight | −0.2 points [−6.4, +5.5]; hand 0.0, templates −0.4 | "no peor" if the lower bound is above −2 | **no concluyente** |
| **Hand count guard** | wins 2 (rd-08, rd-33), losses 2 (rd-41, rd-42); drop hits 18 against 16 | net loss ≤ 1 and hits ≥ 1.13's | **holds** |
| **Costly drops** | 8 against 0 | at most +2 | **fails** |
| Hand stratum's own interval (reported, not required) | 0.0 [−10.9, +9.8] | | no concluyente |

**The 8 costly drops:**

- 2 hand-written: rd-41 (0.09) and rd-42 (0.05), both Aristo Global pages.
- 6 generated: 5 `independent` pages at 0.04 to 0.06, and 1 `offpurpose` page at 0.11.

Over all 530 cases, 1.14 at 0.04 drops 9 of the 27 `independent` pages, 2 of 27 `offpurpose`
and 1 of 27 `qualify`. The `independent` label is the one the registration declared a
convention: a different primary body reaching the same figures.

**Per family, over all cases** (right for 1.13 at 0.59 / 1.14 at 0.04):

| Family | Right (1.13 / 1.14) | Note |
|---|---|---|
| wire, headline, ficha, release, partial | 45 / 45 each | |
| rounded | 38 / 45 | 1.13 at 0.59 misses 7 rounded-down summaries |
| revision, extra | 27 / 27 each | |
| qualify | 27 / 26 | |
| offpurpose | 27 / 25 | |
| independent | **27 / 18** | |
| hand-written (125) | 113 / 122 | 1.14 catches every drop and drops 3 keeps; 1.13 drops no keep and misses 12 drops |

### Descriptive

- **The profile's current cut, 0.61, against 1.13 at 0.59**, through the same stratified
  comparison:
  - **−6.0 points [−11.6, −1.7], "peor"**: hand −6.0, templates −5.9.
  - At 0.61, 1.14 misses 26 of the 198 evaluation drops, and 1.13 at 0.59 misses 7.
  - This is the third draw to find 0.61 losing drops, after L1 and recalconf.
- **Hand-written pages at the cuts used:**
  - calibration: 1.13 at 0.59 gets 65 of 75 (precision 1.00, recall 0.80); 1.14 at 0.04 gets
    74 of 75 (0.98, 1.00);
  - evaluation: 48 against 48 of 50.
- **AUC on the evaluation part:** 1.000 against 0.9999, difference +0.0001 [0.0, +0.0004].

### Post hoc, not registered and not proposed

On the evaluation part, 1.14 at any cut from 0.10 to 0.20 would be right on 319 or 320 of 320
(all 320 from 0.12 to 0.19), with 0 or 1 costly drop and 50 of 50 hand-written. That cut was read off the evaluation data after the
fact, so it licenses nothing. It only says where a better rule might land.

- Rule D could be bounded from below, for example by the highest `keep` score in calibration
  or a precision target on `keep` pages.
- The independent-source convention could be made explicit in the question.

Either would be a new registration on new cases.

## Power against what came out

- The registration expected the hand stratum to decide. It did not: the hand stratum came out
  2 / 2, and the count guard holds.
- The primary came out "no concluyente" with a wide interval, [−6.4, +5.5]. Resampling the 11
  families as units turns a few `independent` drops into a large template-stratum variance.
- The proposal fails on two checks, the primary and the costly-drops guard, which the power
  section had treated as passing.

## What this licenses

- **No change to the 1.14 profile.** `adds_nothing` stays at 0.61, `DEFAULT_MODEL` stays 1.13,
  and 1.13 keeps 0.59.
- **The opt-in caveat stands, and is now measured three times.** Under 1.14, `redundant_page`
  at 0.61 drops fewer redundant pages than 1.13 at 0.59. It loses no `keep` page; it loses
  savings.
- **The roadmap item is answered.** About 90 more `drop` cases do let the 90 % derivation clear
  without hinging on one page. They also expose that rule D, at that sample size, returns a cut
  too low to use.

## Bill

| | |
|---|---|
| Jev, ledger (input tokens × list price) | **0.0277 USD** for batch `jev114-redundant-drop`: 0.0139 per version and two preflights, median 26 µUSD a call. Expected 0.034; cap 0.10. |
| Shared ledger | 3.9886 → 4.0163 of 4.50 USD |
| Claude | 0 |

## Not done

- **A cut between 0.10 and 0.20 on fresh cases.** It needs a rule fixed before the data, and
  cases not used here.
- **A second draw.** One draw per version; L1 and recalconf supply two more on the 125
  hand-written cases only.
- **Templates harder than these.** Every `drop` family except `rounded` is caught by both
  versions at their own cuts.

## Reproducing

```bash
python benchmarks/jev114/redundant_gen.py --check
python benchmarks/jev114/redundant_drop.py rows            # replays fixtures/jev114/redundant-drop-*.jsonl
python benchmarks/jev114/redundant_drop_analysis.py        # analysis.json
python -m pytest tests/test_redundant_drop.py tests/test_jev114_lot.py
```

## Files

- `prereg.md`, `prereg.sha256`, `data.sha256`: the sealed registration and inputs.
- `cases.jsonl`: the 405 generated cases, invented content.
- `launches.jsonl`: the one launch, with HEAD and HEAD^ and the recordings' line counts.
- `drop-scored.jsonl`: per case, its id, file, half, family, label, record, cluster and both
  probabilities. No text.
- `analysis.json`: every number above.
- `fixtures/jev114/redundant-drop-{13r,14}.jsonl`: the answers, under hashed keys. No text.
