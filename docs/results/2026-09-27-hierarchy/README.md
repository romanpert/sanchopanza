# A tournament of in-context calls for sets larger than one call holds

Pre-registered in `prereg.md` (hash in `prereg.sha256`) before any call. HotpotQA distractor,
validation (CC BY-SA 4.0): 300 questions nothing earlier used, each given **100 pages**, its own
10 plus 90 paragraphs from other questions, shuffled. Derivation: the first 100. Held out: 200.

## The confirmed result, on the 200 held-out questions

| arm | both supporting pages kept | text kept | pages kept | Jev calls |
|---|---|---|---|---|
| **TOUR**: groups of 25 at 0.18, survivors judged together at 0.40 (`Squire.triage_many`) | **96.5 %** | **3.1 %** | 3.7 | 5 |
| BLEND (secondary): 0.5 round one + 0.5 final, at 0.40 | 97.0 % | 3.6 % | 4.3 | 5 |
| FLAT: the same groups of 25, kept at 0.40, no second look | 94.0 % | 4.3 % | 5.0 | 4 |
| BM25, top 4 (TOUR's page count) | 50.5 % | 3.3 % | 4.0 | 0 |

- **P25 holds**: 96.5 % with 3.1 % of the text (criteria: >= 95 % at <= 8 %).
- **P26 holds**: the second look keeps more than the groups alone (96.5 against 94.0) with
  less text (3.1 against 4.3). Judging the survivors among their real rivals does not only
  prune: it recovers pages a group of strangers had scored too low.
- **P27 holds** by far: 46 points over BM25 at the same page count.

The round-one cut, 0.18, came from the derivation set by the registered rule (the largest cut
at which round one alone keeps both pages in >= 99 % of questions). The final cut, 0.40, is the
one confirmed on sets of ten (`../2026-09-27-chunks/`) and was not tuned.

## The bench and the shipped method

The bench wrote its two rounds by hand rather than calling `Squire.triage_many`.
`tests/test_hierarchy_bench.py` replays every question through `triage_many` itself, on the same
recordings, and demands the same pages kept: all 200 held-out questions match. One derivation
question had 32 survivors; the bench judged them as a final in two groups, the shipped method
prunes once more first. It is the only difference.

`prereg.sha256` hashes `points/hierarchy.py` as it was when the run started. The file changed
afterwards: it was reformatted, and a code review found that a round which prunes nothing asked
the same groups again. That case never occurred here (the first round always pruned), so no
number above depends on it. The script now refuses to overwrite a registered hash.

## Where it sits

`triage_pages` asks one Truth per page with every page in view and is confirmed on ten pages.
One call holds 30 pages (`chunks.PAGE_MAX`) and 32k tokens of state. `triage_many` keeps that
shape past the cap: it is `triage_pages` below 30 and a tournament above. The idea is LATTICE's
(arXiv:2510.13217): score each node among its siblings, then look again at what survived. The
hierarchy here is free, the order the pages came in; no summary is written by any model.

## What this does not settle

- **The 90 added pages are off-topic.** This shows that a crowd of pages and a split into
  groups do not hurt the judgement; it does not show that hard distractors are separated in a
  crowd of hard distractors. The 8 retrieved distractors of each question are still there.
- **English Wikipedia paragraphs, about 530 characters.** Search results and long documents are
  longer and often Spanish in Indagis.
- **No answering model** on these kept sets. On ten pages the question is open: with free
  replies an answering model scored 4 points lower from the in-context cut than from all pages,
  with a scoring that rewards long replies (`../2026-09-27-answers/`).
- Two rounds were enough here (100 pages). A third round for thousands of pages is in the code
  (`hierarchy.MAX_ROUNDS`) and unmeasured.

## Cost and reproducing

1,501 Jev decisions, 0.53 USD (`fixtures/hierarchy.jsonl`).

```bash
python benchmarks/hierarchy/run.py --hotpot HOTPOT.jsonl      # free, from the recordings
```

`tests/test_hierarchy_bench.py` pins these numbers (needs `SANCHOPANZA_HOTPOT`).
