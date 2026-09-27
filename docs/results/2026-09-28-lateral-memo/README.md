# The tournament still asks some groups twice; remembering them keeps the same pages with fewer calls

Descriptive, free: every number here replays existing recordings, no call was made, and nothing
was pre-registered because nothing was measured live.

## The defect

`hierarchy.tournament` regroups each round's survivors in their order. The 2026-09-27 fix stops
a round that prunes **nothing** from asking the same groups again. A round that prunes **a
little**, only from later groups, can still hand the next round a first group made of the same
pages in the same order: 38 paragraphs are judged as 0-18 and 19-37; one page of the second
group falls; the 37 survivors regroup as 19 + 18, and 0-18 is asked again. Same state, same
question: Jev is not deterministic, so the repeat buys noise, costs a call, and a replay (which
has one answer per state) walks a different path from the live run. It happened on 2026-09-28:
the whole-document confirmation made 855 tournament calls live and 853 on replay
(`../2026-09-28-lateral-wholedocs/`).

## Measured on every recorded tournament

`benchmarks/lateral/memo/run.py` runs each recorded tournament twice through the shipped
`hierarchy.tournament`, once as shipped and once with the judge wrapped in `memoize` (a group
already judged returns its first answers).

| recording | questions | calls as shipped | calls remembered | repeated | questions with a repeat | same pages kept |
|---|---|---|---|---|---|---|
| QASPER papers, 2026-09-27 (`fixtures/longdocs.jsonl`) | 300 | 1,359 | 1,299 | **60 (4.4 %)** | 36 | 300 / 300 |
| QASPER, 2026-09-28 confirmation | 219 | 853 | 839 | 14 (1.6 %) | 14 | 219 / 219 |
| HotpotQA, 100 pages, held out (`fixtures/hierarchy.jsonl`) | 200 | 1,000 | 1,000 | 0 | 0 | 200 / 200 |

On long documents 2-4 % of the tournament's calls are repeats; on the 100-page sets none,
because four balanced groups of 25 never regroup into one of themselves there. On replay the
kept pages are identical by construction (a recording holds one answer per state); live, the
change also removes the divergence between a run and its replay.

## Proposed library change (not made: `src/` is out of scope for this run)

In `sanchopanza/points/hierarchy.py`, give `tournament` a per-call cache and consult it in
`_judge_all`:

```python
seen: dict[tuple[int, ...], float | None] = {}   # in tournament(), passed to _judge_all

async def _judge_all(ids, judge, size, seen):
    parts = [[ids[i] for i in g] for g in groups(len(ids), size)]
    fresh = [p for p in parts if tuple(p) not in seen]
    for part, ps in zip(fresh, await asyncio.gather(*(judge(p) for p in fresh))):
        seen[tuple(part)] = list(ps)
    probs = {i: p for part in parts for i, p in zip(part, seen[tuple(part)])}
    return probs, len(fresh)
```

It also covers the 2026-09-27 stall case (a round that prunes nothing would find every group in
the cache), though that early exit can stay as it is; `calls` then counts only calls made. `tests/test_lateral_memo.py` holds the
38-page case that reproduces the repeat, and the replays above.

## Reproducing

```bash
python benchmarks/lateral/memo/run.py --qasper QASPER-TEST.jsonl --hotpot HOTPOT.jsonl
```

`analysis.json` holds the table. Cost: 0 USD.

## Applied (2026-09-28)

`hierarchy.tournament` now keeps a per-tournament table of the groups it asked and reuses their
answers (`_judge_all(..., seen)`), so the shipped method makes exactly the memoized calls. The
figures above (60 repeats of 1,359, 14 of 853) describe the method before the fix;
`tests/test_lateral_memo.py` now pins zero repeats with the same pages kept.
