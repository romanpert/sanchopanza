# Page triage and passage selection in Spanish, against English on the same questions (B6)

**The result.** On the same MLQA questions, the shipped code keeps the needed page or sentence
less often in Spanish than in English, by about 3 to 6 points, at the same share of the text.
- **Pages** (`triage_pages`, 264 questions whose answer ends within the 900 characters the
  decider sees, in both languages): Spanish **95.5 %**, English **98.9 %**, **−3.4 points**,
  95 % CI **[−6.1, −0.8]**, McNemar 2 against 11, p 0.023. Verdict by the sealed rule:
  **"inconclusive"**.
- **Documents** (`select_passages`, 614 whole Wikipedia articles): Spanish **85.8 %**, English
  **91.7 %** of questions keep the sentence holding the answer, **−5.9 points**, CI **[−9.0,
  −2.9]**, McNemar 26 against 62, p 0.0002. Verdict: **"inconclusive"**.
- **Text kept** is the same in both languages, inside the 5-point margin: pages 19.3 % against
  18.4 % (+0.9 [−0.7, +2.4]); documents 9.9 % against 9.4 % of the article (+0.6 [−0.2, +1.3]).
- **BM25 loses more.** Given the same characters per question, BM25 finds the page in 61.0 % of
  Spanish questions against 70.7 % of English ones, and the sentence in 69.2 % against 80.1 %:
  a 10-11 point drop where Jev's is 3-6.

"Inconclusive" here is not "no difference". Both CIs exclude 0: Spanish is lower. Both reach
past −5: the 5-point margin can be neither cleared nor shown exceeded. The drop lies between
about 1 and 6 points for pages and 3 and 9 for documents.

The setup:
- **Data:** MLQA v1.0 (CC BY-SA 3.0), whose Spanish paragraphs are native Spanish Wikipedia,
  each question professionally translated, with the same id in the English file; and the whole
  Wikipedia articles (CC BY-SA 4.0) at pinned revisions. Labels by construction: the gold page
  is the question's own paragraph, the gold sentence the one holding the answer span. No label
  comes from a model.
- **Arms:** jev-1.13.0 (the production `DEFAULT_MODEL`), shipped thresholds and limits, no
  answering model. P-es and P-en (ten pages, one gold); D-es, D-en and D-es90 (the consumer's
  BM25 preselection past 90 paragraphs).
- **Pre-registration:** [`prereg.md`](prereg.md), sealed at `1f54dd4` (`prereg.sha256`
  `781e5f13…`; instrument `71f88fe`), after two `revisor-prereg` reviews. Run from a detached
  worktree at the seal commit, launched by WMI through a filled copy of `b6-es-run.cmd`.

## What ran

| launch | when (2026-10-16) | Jev calls | spend | outcome |
|---|---|---|---|---|
| smoke, 2 dev questions per bench | 11:42:03-11:42:10 | 31 | 0.0082 USD | exit 0 |
| pages, 300 questions | 11:54:45-11:55:24 | 600 | 0.1087 USD | complete, no failed call |
| docs, 614 questions | 11:56:15-12:10:39 | 11,202 | 2.5277 USD | complete, no failed call |

One launch per bench, no relaunch, no pause, no stop. Every answer came from jev-1.13.0: 11,833
lines, hashed keys and numbers only. A replay from the recordings reproduces both
`analysis-*.json` files exactly, apart from the `head` field, which a replay writes as "replay".

The recordings ship gzipped, as `fixtures/b6-es.jsonl.gz` (993,359 bytes, sha256
`a2d0156d9ba05aa8834ce164bae7834790131efda965d9a1544673e1879e13b7`; gzip level 9, no name,
mtime 0). The sealed runner reads plain JSON lines, so a replay first decompresses it to
`fixtures/b6-es.jsonl` (21,551,231 bytes, sha256
`e200d7f2432045bfb928e0bb9289dd94fa2ccc4d6bb868108c3a9ac921da0e4c`, ignored by git):

    python -c "import gzip,shutil; shutil.copyfileobj(gzip.open('fixtures/b6-es.jsonl.gz'), open('fixtures/b6-es.jsonl', 'wb'))"
    python -I benchmarks/b6_es/b6_run.py --bench pages
    python -I benchmarks/b6_es/b6_run.py --bench docs

## Pages (`triage_pages`)

| reading | rows | Spanish | English | Spanish − English, 95 % CI | McNemar |
|---|---|---|---|---|---|
| **H1, primary: answer within 900 characters in both** | 264 | **95.5 %** | **98.9 %** | **−3.4 [−6.1, −0.8]** | 2 / 11, p 0.023 |
| all rows (secondary) | 300 | 95.0 % | 95.7 % | −0.7 [−4.0, +2.3] | 10 / 12, p 0.83 |
| text kept, primary rows | 264 | 19.3 % | 18.4 % | +0.9 [−0.7, +2.4] | |
| BM25 at the same characters | 300 | 61.0 % | 70.7 % | | |

- **Why the primary leaves rows out.** The decider sees each page's first 900 characters. The
  answer ends past them in 30 English gold pages and 11 Spanish ones. On the 36 rows outside the
  primary, English keeps 26 and Spanish 33: English is penalised there for its longer
  paragraphs, not its language, and the all-rows reading mixes the two.
- **Pages kept:** 1.96 a question in Spanish, 1.90 in English, of ten. Characters kept: 1,213
  against 1,781 (English paragraphs are longer).
- **The answer string in the kept text** matches the gold page exactly, as built: no distractor
  holds the answer.
- **Against HotpotQA** (98.3 % at 33.6 %, two gold pages among ten): English on MLQA reaches
  98.9 % at 18.4 % on its primary rows. The datasets differ, so this is an anchor, not a test.

**C1, the consumer's cut of each page to 900 characters.** Scored free from P-es, since the
decider already sees 900 characters a page. Delivered 92.0 % against kept 95.0 %, **−3.0
[−5.0, −1.3]**, "inconclusive" by the sealed rule (the lower bound is −5.0). The prereg said so
in advance: the cut loses exactly the kept gold pages whose answer ends past character 900.
That happens in 9 of the 11 Spanish questions where the answer lies there. It is a fixed, known
loss, not an uncertainty.

## Documents (`select_passages`)

| reading | rows | Spanish | English | Spanish − English, 95 % CI | McNemar |
|---|---|---|---|---|---|
| **H2, primary: every gold sentence kept** | 614 | **85.8 %** | **91.7 %** | **−5.9 [−9.0, −2.9]** | 26 / 62, p 0.0002 |
| both anchors located exactly | 420 | 86.2 % | 91.4 % | −5.2 [−8.8, −1.9] | 17 / 39 |
| a fuzzy route in either language | 194 | 85.1 % | 92.3 % | −7.2 [−12.9, −1.6] | 9 / 23 |
| answer only in the gold sentence, both | 309 | 85.8 % | 91.9 % | −6.1 [−10.0, −2.3] | 10 / 29 |
| gold sentence within 900 characters of its paragraph, both | 581 | 88.6 % | 93.1 % | −4.5 [−7.2, −1.9] | 21 / 47 |
| the answer string anywhere in the kept text | 614 | 88.1 % | 93.3 % | −5.2 [−8.0, −2.6] | 21 / 53 |
| text kept | 614 | 9.9 % | 9.4 % | +0.6 [−0.2, +1.3] | |
| BM25 sentences at the same characters | 614 | 69.2 % | 80.1 % | | |

- **Every reading agrees.** The gap is 4.5 to 7.2 points whichever rows are kept. It is
  smallest where the gold sentence lies within the 900 characters of its paragraph that the
  tournament sees (−4.5), and the gold starts past them in 24 Spanish rows against 17 English.
- **Kept per question:** 17.1 sentences and 2,709 characters in Spanish, 21.5 and 3,023 in
  English, about a tenth of the article in both. Spanish articles are shorter (median 43
  paragraphs against 61).
- **Any gold equals all gold**: there is one gold sentence per question (1.02 on average).
- **English outside QASPER.** On encyclopaedic articles, English keeps the answer sentence in
  91.7 % at 9.4 % of the text, against QASPER's 87.2 % at 21.0 % on scientific papers. That is
  an anchor across datasets, not a test.

**C2, the consumer's BM25 preselection past 90 paragraphs** (descriptive, 86 Spanish articles).
D-es90 80.2 % against D-es 81.4 %, −1.2 [−7.0, +4.7], McNemar 3 against 4. The preselection
itself keeps the gold paragraph in 84 of 86 articles (97.7 %, Wilson 91.9-99.4). On these 86
rows, sending 90 BM25-chosen paragraphs instead of the whole article cost no measurable recall.

## Power against what came out

| | assumed before | observed |
|---|---|---|
| pages, disagreement d | 0.05 (if both hit rates ≥ 95 %) | 13 / 264 = **0.049** |
| docs, disagreement d | 0.17 (BM25 proxy), 0.20-0.23 with Jev's noise | 88 / 614 = **0.143** |

The power table was computed for languages truly equal. They are not: both differences are
significant. With a true drop of 3-6 points and a 5-point margin, "inconclusive" is the
expected reading at these n. Deciding against the margin needs the CI entirely on one side of
−5. At the observed differences and discordances, the normal approximation (80 % power) asks
for about 1,490 page questions to show "no worse" at −3.4 (5.7 times the 264), and about 14,700
articles to show "worse by more than 5" at −5.9. MLQA's test split holds 614 that qualify.

## Cost

- **Jev: 2.6445 USD** on this bench's own ledger (pages 0.1087, docs 2.5277, smoke 0.0082),
  with no reservation left open. Expected 2.72 USD, capped at 5.50 in code. The dry run
  over-counted sentence calls: docs made 11,202 calls against 15,623 predicted (5,518 sentence
  calls against 9,859), at a higher cost a call.
- **Claude: 0 USD.** No answering model.
- **Wall time:** 39 seconds for pages, 14 minutes 24 seconds for docs.

## What it means for the consumer

- **Asking in Spanish costs a few points of recall, not a different regime.** With the shipped
  thresholds, Spanish keeps the needed page about 3 points less often and the needed sentence
  about 6 points less often than English on the same questions, at the same share of the
  text. BM25 alone loses 10 to 11 points in Spanish, so the in-context judge narrows the
  language gap rather than widening it.
- **The 900-character cut is a known, small loss.** The decider already sees only 900
  characters a page. What the consumer's own cut adds is losing the text past it: 3 points of
  Spanish questions here, where the answer lay past character 900.
- **The BM25 preselection past 90 paragraphs** kept the gold paragraph in 84 of 86 long
  Spanish articles, and the selection after it did as well as on the whole article (−1.2
  points, a wide CI over 86 rows).
- **Not licensed:** a claim that Spanish is "no worse" within 5 points, for either point.

## Found on the way (free)

- **Zero-width spaces.** Spanish Wikipedia writes a zero-width space after every footnote mark,
  in 58 % of its paragraphs. `text.split_sentences` used not to cut there. It does since
  `29c433b`, which this bench was rebuilt on: 122,367 Spanish sentences with the marks kept,
  against 122,248 with them stripped.
- **BM25 without stemming** (the package's, accent-folded) is 10 points weaker in Spanish on
  these questions. The consumer's preselection inherits it.

## Not done

- No answering model, so no answer F1 from the kept text (QASPER Run 2's shape); a separate
  prereg can add it.
- No jev-1.14.0, no long-context header, no threshold or limit changed.
- One draw per arm: Jev's draw-to-draw noise is inside each CI, not measured apart.
- One dataset family: encyclopaedic Wikipedia text with MLQA's translated questions, one gold
  page per question (HotpotQA has two). No Spanish document type beyond Wikipedia.
- The consumer's own BM25 and cut were assumed to be the package's BM25 and a head cut at 900;
  not checked against its code.
- The bench is selected: articles of at least 20 paragraphs whose answer sentence survived
  editing since 2019 in both languages (614 of 2,503).

## Files

- [`prereg.md`](prereg.md), `prereg.sha256`: the sealed rules.
- `bench-manifest.json`: ids, revision ids, exclusions, the SHA-256 of each built file. The
  bench itself is rebuilt by `benchmarks/b6_es/b6_build.py`, outside the repository.
- `analysis-pages.json`, `analysis-docs.json`: every reading above, as the run wrote it.
- `fixtures/b6-es.jsonl.gz`: the 11,833 recorded answers, decompressed to `fixtures/b6-es.jsonl`
  and replayed by `python -I benchmarks/b6_es/b6_run.py --bench pages|docs` (free, above).
  `tests/test_b6_es_replay.py` checks both hashes and replays from a temporary copy.
- `benchmarks/b6_es/`, `b6-es-run.cmd`, `tests/test_b6_es.py`: the instrument and its tests.
