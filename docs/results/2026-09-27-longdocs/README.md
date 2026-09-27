# The tournament on whole scientific papers: the recall transfers, the compression does not, with or without sentences

Pre-registered in `prereg.md` (hash in `prereg.sha256`) before any call. QASPER, test split
(CC BY 4.0): 300 NLP papers, one question each, evidence paragraphs marked by practitioners who
read the paper. Papers average 49 paragraphs (up to 290) and 22,000 characters.
`Squire.triage_many` ran exactly as shipped, with the cuts fixed on HotpotQA (0.18, then 0.40);
nothing was derived on these papers.

## Result: not confirmed

| arm | all evidence kept | any evidence kept | text kept | paragraphs kept |
|---|---|---|---|---|
| **MANY** (`triage_many`, shipped cuts) | **94.7 %** | 98.3 % | **48.9 %** | 21.2 |
| BM25, top 22 (the same count) | 78.3 % | 91.0 % | 61.2 % | 21.6 |

- **P28 fails**: recall clears its bar (94.7 % against >= 85 %), the text kept does not
  (48.9 % against <= 25 %).
- **P29 holds**: 16.3 points over BM25 at the same paragraph count, with less text.

## Reading

On HotpotQA the tournament kept 3 % of 100 pages because 90 of them were off-topic. A paper is
one topic from end to end, and the questions were written by people who had read only the title
and abstract, so a large part of any paper plausibly contributes. The contribution question,
asked in context, keeps about half of it. As a filter in front of a reader it cuts the text in
two without losing the evidence in 95 % of questions; it is not the 3-to-1 or 10-to-1 reduction
the short-page runs showed.

The next thing measured was `select_sentences` inside the kept paragraphs (below): it brings
the text to 31 % and loses about 12 points of recall. Paragraphs here average 433 characters,
under the 900 each one is shown by (`chunks.PAGE_LIMIT`); the longest are judged on part of it.

## The fixed tournament, replayed (2026-09-27, later the same day)

The code review of the same day found that a round which prunes nothing asked the same groups
again; the fix reuses that round's answers. The first execution had that defect: 247 of its
1,515 calls repeated an earlier call, and Jev is not deterministic, so a replay with the fixed
method walked a different path and needed 42 calls that were never made. TypeSafe answered
HTTP 402 when they were first attempted.

With credit restored, the fixed method ran live over the same recording: **54 new calls** (the
42 missing, and 12 more further down paths whose answers changed), 0.02 USD. The table above is
that run. Against the defective first execution it moved by rounding: all evidence 94.67 % in
both, text kept 48.86 % then 48.92 % now, paragraphs kept 21.1 then 21.2. The verdict does not
change: **P28 fails on compression, P29 holds**. The run now replays from the recording with no
live call, and `tests/test_longdocs_bench.py` pins it.

## Sentences inside the kept paragraphs: not confirmed either

Pre-registered in `prereg-sentences.md` (hash in `prereg-sentences.sha256`) after the paragraph
verdict and before any sentence call. The same 300 questions; QASPER's `highlighted_evidence`
(the spans inside the evidence paragraphs that answer) marks the gold sentences. 261 questions
have every span locatable in its paragraph; the 39 others are excluded and listed in
`sentences-analysis.json`. Papers average 164 sentences, questions 2.5 gold sentences.
`Squire.select_sentences` at the shipped cut (0.28) on every paragraph the tournament kept:
5,308 calls, 0.30 USD. The tournament replays and was not asked again.

| arm, 261 questions | all gold sentences kept | any kept | text kept |
|---|---|---|---|
| M: the kept paragraphs, whole | 95.8 % | 98.9 % | 49.1 % |
| **MS: sentences inside them** (shipped two stages) | **83.1 %** | 98.1 % | **31.5 %** |
| BM25 over sentences, at least MS's text per question | 52.1 % | 82.4 % | 32.0 % |

- **P30 fails** on both counts: 83.1 % against >= 85 %, 31.5 % of the text against <= 25 %.
- **P31 holds** by far: 31 points over BM25 with the same text.

The prediction written before the run (85-87 % at 30-32 %) was right on the text and two to four
points optimistic on recall. The sentence stage cuts a third of what the paragraph stage keeps
and loses 12.7 points of "every gold sentence"; "at least one" barely moves (98.9 to 98.1 %),
so what it drops is the second and third sentence of a multi-sentence answer. On HotpotQA the
same stage lost 8 points at a 35 % cut; here it loses more at the same cut.

Reading, not a result: on whole papers the two stages keep about a third of the text with the
answer's sentences whole in five questions of six. It is a filter in front of a reader, with a
large margin over lexical retrieval, and not the 10-to-1 reduction of short, off-topic pages.
No cut was derived here and none moves.

## Cost and reproducing

1,569 recorded Jev decisions, 0.53 USD in all (`fixtures/longdocs.jsonl`): the first execution and the 54 calls of the fixed replay.

```bash
python benchmarks/longdocs/run.py --qasper QASPER-TEST.jsonl        # free, from the recordings
python benchmarks/longdocs/sentences.py --qasper QASPER-TEST.jsonl  # free, sentence stage
```

The QASPER test parquet (`allenai/qasper`) is converted to JSONL row by row; it is not
redistributed here. `tests/test_longdocs_bench.py` and `tests/test_longdocs_sentences.py` pin both runs (need `SANCHO_QASPER`); the sentence calls are in `fixtures/longdocs-sentences.jsonl`.
