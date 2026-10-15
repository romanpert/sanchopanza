# B6: page triage and passage selection in Spanish, against English on the same questions: pre-registration (DRAFT)

Written 2026-10-16, before any Jev answer on these questions. **A draft, not sealed**: to be
reviewed against the code by an independent `revisor-prereg` agent and its cost approved by the
owner before `python -I benchmarks/b6_es/b6_run.py --seal`. `prereg.sha256` will hold one
sha256 over this file, `bench-manifest.json`, the runner and its modules, their tests, lot L4's
key loader and every file of `src/sanchopanza/**/*.py` (`b6_run.digest`, text hashed with LF
line ends); the live paths check it before reading the key and spend nothing if anything
changed. The sealing commit's message carries the hash.

## The question

What is confirmed is English (README, "What it decides"): `triage_pages` keeps every supporting
page in **98.3 %** of 300 HotpotQA questions at **34 %** of the text
([chunks](../2026-09-27-chunks/README.md)); `select_passages` keeps every answer sentence in
**87.2 %** of 219 QASPER questions at **21.0 %**
([wholedocs](../2026-09-28-lateral-wholedocs/README.md)). The one known consumer, an agent with
its own harness, asks in Spanish, cuts each page to 900 characters and preselects by BM25 past
90 paragraphs; none of that is measured (ROADMAP B6).

**On the same questions, does Spanish keep the needed page or sentence at most 5 points less
often than English, at no more than 5 points more of the text? And what do the consumer's two
conditions cost in Spanish?**

## Data: labels by construction

**MLQA v1.0** (Lewis et al., ACL 2020, `facebookresearch/MLQA`), **CC BY-SA 3.0**; the article
text is Wikipedia's, **CC BY-SA 4.0**. Both allow use and redistribution with attribution;
nothing downloaded is committed anyway: `benchmarks/b6_es/b6_build.py` downloads the archive
(checked against its SHA-256, `246e8089…2baac8`) and the articles, under `--data` outside the
repository, and the committed `bench-manifest.json` holds only ids, Wikipedia revision ids,
counts, exclusion reasons and the SHA-256 of each built file. Public encyclopaedic text: no
pseudonymisation.

Why MLQA: its Spanish paragraphs are **native Spanish Wikipedia**, not translations; each
question was written in English and translated by professionals, and its answer span was
marked in the Spanish paragraph. Every Spanish test item has the same id in the English test
file, with its English question, answer and English Wikipedia paragraph. That gives a **paired
English control on the same questions**, so a Spanish drop is not confounded with a change of
dataset, as a comparison with the published HotpotQA and QASPER numbers would be. Those stay as
descriptive anchors. No label comes from a model, and none from Jev.

Draw: the MLQA test items present and well-formed in both languages (5,253), in a seeded order
(seed 20261016), **one question per Spanish article**. The docs bench is drawn first; the pages
bench takes the next questions whose article the docs bench never tried. Smoke sets: two MLQA
dev questions per bench, drawn the same way.

- **pages** (`triage_pages`, HotpotQA's shape): the question's own MLQA paragraph and nine
  distractor paragraphs from the same split, chosen by BM25 in both languages at once (the
  smallest sum of the Spanish and English ranks), none holding the answer string in either
  language (letters and digits only, footnote marks ignored), no paragraph twice. The **gold
  page** is the question's own paragraph. The same ten units in the same seeded order in both
  languages, titled by their article. One gold page per question, where HotpotQA had two.
- **docs** (`select_passages`, QASPER's shape): the **whole Wikipedia article**, Spanish and
  English, at the revision first fetched (pinned in the manifest; a rebuild fetches it by
  revision id), as its `<p>` paragraphs titled by section, outside tables, figures, boxes and
  reference lists, footnote marks dropped. The **gold sentence** is the one that holds the
  answer: the MLQA sentence around the answer span (its anchor) is located in the article on
  letters and digits only, exactly once; failing that, a fuzzy match is accepted only when one
  paragraph alone covers 85 % of the anchor in blocks of 8 or more letters within 1.5 times its
  length and the answer is still there letter for letter (`b6_build.locate`). Gold sentences
  are the sentences of `text.split_sentences` (B2's splitter, the one `select_passages` uses)
  that overlap the located answer. An article under 20 paragraphs, unavailable, or where the
  anchor is not located once is excluded, in either language; the manifest counts the reasons
  and each row says whether its match was exact or fuzzy. Excluding is a selection: the bench
  is the questions whose sentence survived in both articles since 2019.

## Arms (`benchmarks/b6_es/b6_run.py`)

One model: **jev-1.13.0** (the production `DEFAULT_MODEL`, the model of both English
confirmations), pinned; an answer served by another model stops the run. Shipped thresholds and
limits (`Thresholds()`, `Limits()`): `pages_in_context` 0.40, `pages_first_round` 0.18,
`document_paragraphs` 0.75, `document_window` 2, `sentences` 0.28, 900 characters of each page
in view, 30 pages a call. No `max_calls`. No answering model.

| arm | point | input |
|---|---|---|
| `P-es` | `Squire.triage_pages` | Spanish question, the ten Spanish pages whole |
| `P-en` | `Squire.triage_pages` | English question, the ten English pages whole |
| `P-es900` | `Squire.triage_pages` | Spanish, **each page cut to its first 900 characters before the call** (the consumer); a question whose pages are all 900 or shorter sends exactly P-es's input and reuses its answer |
| `D-es` | `Squire.select_passages` | Spanish question, every paragraph of the Spanish article |
| `D-en` | `Squire.select_passages` | English question, every paragraph of the English article |
| `D-es90` | `Squire.select_passages` | Spanish, **past 90 paragraphs only the 90 best by BM25** over section and text (`select.index_of`, ties and zero scores by page order), sent in page order (the consumer); an article of 90 or fewer reuses D-es |

The questions are launched in a seeded order (seed 20261016); within a question the arms run
one after the other, Spanish first on even launch positions and English first on odd ones. At
most 4 calls in flight. Answers are recorded in `fixtures/b6-es.jsonl` (hashed keys, no text).

## Questions asked

Every built row: **N_PAGES = 300** pages questions and **N_DOCS = 400** docs questions
(`b6_run.N_PAGES`, `N_DOCS`), fixed by the power section below. The docs bench took 1,395 draws
to reach 400: 541 Spanish articles under 20 paragraphs, 201 Spanish and 173 English anchors not
found, 41 and 12 answers gone from an edited anchor, 7 Spanish articles unavailable, 15 English
articles under 20 paragraphs, 6 others (`bench-manifest.json`). Of the 400, the Spanish gold
came from the fuzzy match in 60 and the English in 82. Spanish articles: median 44 paragraphs
(10th-90th percentile 24-118), 56 over 90; English: median 63, 97 over 90. Gold sentences per
question: 1.02. Pages bench: 257 of 300 questions have a Spanish page over 900 characters; the
answer ends past character 900 in 12.

Text cleaning, both languages alike, before anything is asked: whitespace collapsed; zero-width
characters dropped (Spanish Wikipedia writes one after every footnote mark: 58 % of the Spanish
paragraphs, 72 of 28,681 English ones; `text.split_sentences` does not break at ".​ ",
and keeping them would have left 68,479 Spanish sentences instead of 83,616, a coarser Spanish
sentence stage, a difference of markup and not of language); numeric footnote marks (`[12]`,
`[n. 3]`) dropped, which MLQA kept in 1,409 of the 3,000 Spanish pages and 81 English ones.

## Metrics

Per question, by construction:

- pages: **hit** = the gold page kept; for P-es900, **delivered** = kept and the answer ends
  within the first 900 characters (what the consumer passes on). Text kept = characters of the
  kept pages over the characters of the pages sent.
- docs: **all gold** = every gold sentence kept (with one gold sentence per question, nearly
  always the same as any gold); text kept = characters of the kept sentences over the whole
  article's. For D-es90, a paragraph not preselected counts as not kept, and the share is of
  the whole article.

Free, beside them: BM25 at the same text per question (pages by BM25 within P-es's kept
characters; sentences by BM25 within D-es's), the share of questions whose answer ends past
character 900, and the share of all built Spanish articles over 90 paragraphs whose gold
paragraph survives the BM25 preselection.

## Verdict rules (decided now)

Statistics from `sanchopanza.eval.stats`: paired bootstrap over questions (2,000 resamples,
seed 7, percentile 95 % CI) for every difference; exact McNemar reported beside it; Wilson
intervals for single rates. Margin **5 points** (`b6_score.MARGIN`).

- **H1, pages** (primary): hit(P-es) − hit(P-en).
- **H2, docs** (primary): all gold(D-es) − all gold(D-en).

For each, on its own (two separate claims about two points, so no correction across them):

1. **"no worse"** if the CI's lower bound is above −5 points, written "no worse (but lower)"
   when its upper bound is also below 0;
2. **"worse by more than 5 points"** if the CI's upper bound is below −5 points;
3. **"inconclusive"** otherwise.

Text side, reported with each: the paired CI of Spanish minus English text kept; **"no worse
on both"** (Pareto, at these margins) needs rule 1 and an upper bound below +5 points.

Consumer conditions, the same rule and labels, read as "what the condition costs in Spanish":

- **C1**: delivered(P-es900) − hit(P-es), every pages question.
- **C2**: all gold(D-es90) − all gold(D-es), on the docs questions whose Spanish article has more
  than 90 paragraphs (about one in six; see Power: a descriptive reading unless that subset is
  large enough). The free preselection rate over every built article is reported beside it.

Descriptive only, no verdict: Spanish and English rates against the published English numbers
(98.3 % at 33.6 %; 87.2 % at 21.0 %); D-en as **an English document type outside QASPER**
(encyclopaedic articles); BM25 at the same text; exact-match rows only (fuzzy rows dropped) as a
sensitivity reading.

**A run is complete only if every call answered.** Any unanswered call (a failure, a cap, a
stop) leaves it INCOMPLETE and nothing is scored; a relaunch replays what was paid and asks the
rest. One draw per arm: Jev is not deterministic across a day, so each question's
Spanish-English disagreement includes the draw's own noise, which the CI carries.

## Power

`python -I benchmarks/b6_es/b6_run.py --power`, free. The paired difference's 95 % CI has a
half-width of about 1.96 √(d / n), d the share of questions where the two languages disagree;
rule 1 at −5 points, if the languages are truly equal, needs n = 7.85 d / 0.05², and the chance
of reading "no worse" at a given n is Φ(0.05 / √(d / n) − 1.96) (`b6_score.n_noninferiority`,
`power_no_worse`).

d is unknown before any answer. Two free readings bound it:

- **Proxy, BM25 at the same text** on these questions: pages, BM25 within a third of the text,
  Spanish 65.7 % against English 76.3 %, d = 78/300 = 0.26; docs, BM25 sentences within a fifth
  of the article, 81.8 % against 90.3 %, **d = 64/400 = 0.16**. A ranking that does not read the
  question stays a loose proxy for one that does, and Jev's own draw-to-draw noise adds to d.
- **The English rates**: pages near 98 % (HotpotQA 98.3 %) leave little room to disagree,
  d ≈ 0.03-0.05; docs near 87 % (QASPER 87.2 %) leave d ≈ 0.12-0.20.

| d | n for 80 % at −5 if equal | power at 240 | at 300 | at 400 | half-width at 400 |
|---|---|---|---|---|---|
| 0.05 | 157 | 0.93 | 0.97 | 0.99 | 2.2 points |
| 0.10 | 314 | 0.69 | 0.78 | 0.89 | 3.1 points |
| 0.15 | 471 | 0.52 | 0.61 | 0.73 | 3.8 points |
| 0.20 | 628 | 0.41 | 0.49 | 0.61 | 4.4 points |

So: **pages, 300 questions** decide H1 with power about 0.97 if d is 0.05. **Docs, 400
questions** (all the bench holds) give power about 0.73 at the proxy's d of 0.16, 0.61 at
0.20; 80 % would take about 470-630, past what the Spanish articles of MLQA's test split yield
at this draw rate (about 270 more at most). A true drop of 5 points or more is detected
(McNemar, 80 %) with the same n as "no worse" when the languages are equal. 240 docs would cost
37 % less and decide a coin flip (0.52 at d 0.15). C2 runs on the 56 Spanish articles over 90
paragraphs: half-width about 7 points at d 0.07, a descriptive reading; its free ceiling is
already known: the BM25 preselection keeps the gold paragraph in **54 of 56** Spanish articles
(96.4 %, Wilson 87.9-99.0) and 96 of 97 English ones.

## Spend, caps and stops

`python -I benchmarks/b6_es/b6_run.py --dry`, free: the whole run through the shipped code with
a stub decider (in each in-context call the 8 best pages by BM25 at 0.9, the next 4 at 0.5, the
rest at 0.05: QASPER's 8.1 paragraphs a question past the 0.75 gate), counting every call a
live run would make and pricing it from its size. Jev bills 42 micro-dollars per thousand input
tokens (every published fixture: 42.0 exactly); `CappedDecider` reserves a token per three
characters, which on the HotpotQA fixtures is 1.23 times the billed tokens of an in-context
call and 2.6 times those of a sentence call (the expected cost divides by those factors).

| arm | calls (in-context + sentences) | expected | pessimistic |
|---|---|---|---|
| P-es | 300 | 0.053 | 0.065 |
| P-es900 | 257 | 0.046 | 0.056 |
| P-en | 300 | 0.055 | 0.068 |
| D-es | 4,483 (1,520 + 2,963) | 0.691 | 0.957 |
| D-es90 | 591 (326 + 265) | 0.144 | 0.186 |
| D-en | 5,189 (1,989 + 3,200) | 0.906 | 1.239 |
| **Jev, total** | **11,120** | **1.90 USD** | **2.57 USD** |

At the median of 71 micro-dollars a request the same calls would be 0.79 USD; that median
under-prices these calls, which carry up to 30 pages of 900 characters (QASPER's tournament
calls cost 339 micro-dollars each, its sentence calls 58). If every page passed every cut the
run would make 59,486 calls; the cap stops it long before. With 240 docs: 7,040 calls, 1.21 USD
expected, 1.63 pessimistic. Duration: about 11,000 calls at 4 in flight, roughly 45-75 minutes.

- **Claude: 0 USD.** No answering model. The English confirmations' primary metrics were this
  same recall at a share of the text, by construction; an answering step would add the answering
  model's own Spanish-English gap to the one measured here. If H2 reads "no worse", an answer
  check in QASPER Run 2's shape (Haiku through clean Claude Code 2.1.287, about 0.026 USD a
  question) can follow under its own prereg.
- **Hard caps in code:** this bench's own ledger (`C:/sp-runs/b6-es/ledger.json`,
  `SANCHOPANZA_B6_RUN` to move it) capped at **4.10 USD**; batch `b6-es` at **4.00 USD** (the
  pessimistic 2.57 plus room for Spanish taking more tokens a character than the English the
  factors were measured on); the smoke on batch `b6-es-smoke` at **0.10 USD**. The roadmap's
  "< 0.10 USD of Jev" was a guess this dry run replaces: the owner approves the 1.90 USD
  expected (4.00 capped) before the seal, or the smaller docs bench. Every live call goes
  through `CappedDecider` (a pessimistic reservation, a token per three characters, before the
  call; refused when it does not fit). The live run refuses to start when the dry run's
  pessimistic estimate does not fit under the batch cap.
- **Stops:** a cap refusal, HTTP 401/402/403/429 or 5xx (after the client's bounded retries on
  529; the retries on 429 are switched off), no connection, or 3 failed calls in a row of any
  kind: every later call is refused unasked, including those waiting for a slot. An answer from
  another model ends the process. No retries. Before the first call, the preflight
  (`providers.jev.apreflight` for jev-1.13.0, what `sanchopanza jev-preflight` runs) must
  answer with that model; it is off the ledger.

## Running it

From a `git worktree add --detach` at the sealed commit, with the bench rebuilt there
(`b6_build.py` without `--fresh` fetches each article by its pinned revision, or reads it from
the cache, and refuses unless every built file matches the manifest's SHA-256; a rebuild from
the cache reproduced all four), outside the session, not between 02:00 and 08:00. `DIR` is
`$SANCHOPANZA_B6_DATA`, else `~/.cache/sanchopanza/b6-es`:

    python -I benchmarks/b6_es/b6_build.py --data DIR
    python -I benchmarks/b6_es/b6_run.py --data DIR --dry
    python -I benchmarks/b6_es/b6_run.py --data DIR --smoke --live
    python -I benchmarks/b6_es/b6_run.py --data DIR --live
    python -I benchmarks/b6_es/b6_run.py --data DIR      # free replay and analysis

`-I` because the bench is built from downloaded data; the scripts put this repository's `src`
on the path themselves. The smoke (two dev questions per bench) checks the live path, the caps
and the recording end to end; nothing in it changes these rules.

## What is not done

No jev-1.14.0, no long-context header, no threshold or limit changed, no `max_calls`, no
answering model, no change to `policy.py`. The consumer's BM25 and cut are assumed to be the
package's BM25 and a head cut of 900 characters; its own may differ (to be confirmed with it
before the seal).
