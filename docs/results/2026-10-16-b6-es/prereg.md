# B6: page triage and passage selection in Spanish, against English on the same questions: pre-registration

Written 2026-10-16 and **sealed** before any Jev answer on these questions, after two
independent `revisor-prereg` reviews against the code, within the owner's standing approval of
the agreed lots (each capped in code, none above 10 USD). The seal is `prereg.sha256` (`python -I benchmarks/b6_es/b6_run.py --seal`): one sha256
(`b6_run.digest`) over this file, `bench-manifest.json`, the runner and its modules
(`b6_run.py`, `b6_analysis.py`, `b6_score.py`, `b6_build.py`, `b6_wiki.py`), their tests, the
launcher `b6-es-run.cmd` (its four local values read as placeholders, below) and every file of
`src/sanchopanza/**/*.py`, text hashed with LF line ends. `--seal` writes it once: it refuses
when a seal exists or `fixtures/b6-es.jsonl` holds any answer. It is committed alone, in its
own commit, on top of the instrument: a live launch refuses unless HEAD has one parent and
changes only `prereg.sha256` (`b6_run.require_seal_commit`), and records that parent, the
instrument, in its launch row. The live paths check the hash before reading the key and spend
nothing if anything changed. The seal commit's message carries the hash.

## The question

What is confirmed is English (README, "What it decides"): `triage_pages` keeps every supporting
page in **98.3 %** of 300 HotpotQA questions at **34 %** of the text
([chunks](../2026-09-27-chunks/README.md)); `select_passages` keeps every answer sentence in
**87.2 %** of 219 QASPER questions at **21.0 %**
([wholedocs](../2026-09-28-lateral-wholedocs/README.md)). The one known consumer, an agent with
its own harness, asks in Spanish, cuts each page to 900 characters and preselects by BM25 past
90 paragraphs; none of that is measured (ROADMAP B6).

**On the same questions, does the shipped code keep the needed page or sentence at most 5
points less often in Spanish than in English, at no more than 5 points more of the text? And
what do the consumer's two conditions cost in Spanish?** The comparison is Spanish Wikipedia as
it is against English Wikipedia as it is, on the same question: the two articles are written
independently, so a difference is the language and its encyclopaedia together, not a
translation of one text.

## Data: labels by construction

**MLQA v1.0** (Lewis et al., ACL 2020, `facebookresearch/MLQA`), **CC BY-SA 3.0**; the article
text is Wikipedia's, **CC BY-SA 4.0**. Both allow use and redistribution with attribution;
nothing downloaded is committed anyway: `benchmarks/b6_es/b6_build.py` downloads the archive
(checked against its SHA-256, `246e8089…2baac8`) and the articles, under `--data` outside the
repository (`$SANCHOPANZA_B6_DATA`, else `~/.cache/sanchopanza/b6-es`), and the committed
`bench-manifest.json` holds only ids, Wikipedia revision ids, counts, exclusion reasons and the
SHA-256 of each built file. Public encyclopaedic text: no pseudonymisation.

Why MLQA: its Spanish paragraphs are **native Spanish Wikipedia**, not translations; each
question was written in English and translated by professionals, and its answer span was
marked in the Spanish paragraph. Every Spanish test item has the same id in the English test
file, with its English question, answer and English Wikipedia paragraph: a **paired English
control on the same questions**, where a comparison with the published HotpotQA and QASPER
numbers would confound the language with the dataset. Those stay as descriptive anchors. No
label comes from a model, and none from Jev.

Draw: the MLQA test items present and well-formed in both languages (5,253), in a seeded order
(seed 20261016), **one question per Spanish article** (2,503 articles). The docs bench takes
every article that qualifies; the pages bench takes the first 300 questions whose article the
docs bench did not take. Smoke sets: two MLQA dev questions per bench, drawn the same way.

- **pages** (`triage_pages`, HotpotQA's shape): the question's own MLQA paragraph and nine
  distractor paragraphs from the same split, chosen by BM25 in both languages at once (the
  smallest sum of the Spanish and English ranks), none holding the answer's letters in either
  language, no paragraph twice. The **gold page** is the question's own paragraph. The same ten
  units in the same seeded order in both languages, titled by their article. One gold page per
  question, where HotpotQA had two. The answer ends past character 900 of its gold page in
  **11 Spanish and 30 English** questions; **264** have it within 900 in both languages.
- **docs** (`select_passages`, QASPER's shape): the **whole Wikipedia article**, Spanish and
  English, at the revision first fetched (pinned in the manifest; a rebuild fetches it by
  revision id), as its `<p>` paragraphs titled by section, outside tables, figures, boxes and
  reference lists, footnote `<sup>` dropped. The **gold sentence** is the one that holds the
  answer: the MLQA sentence around the answer span (its anchor) is located in the article on
  letters and digits only, exactly once (`exact`); failing that, a fuzzy match is accepted only
  when one paragraph alone covers 85 % of the anchor in blocks of 8 or more letters within 1.5
  times its length and the answer's letters are still there, inside one matched block
  (`fuzzy-block`) or exactly once near it (`fuzzy-search`) (`b6_build.locate`). Gold sentences
  are the sentences of `text.split_sentences` (the one `select_passages` uses) that overlap the
  located answer. An article under 20 paragraphs, unavailable, or where the anchor is not
  located once is excluded, in either language. Each row records its route.

**The docs bench: 614 questions**, every one of the 2,503 articles that qualified. Excluded:
1,076 Spanish articles under 20 paragraphs, 364 Spanish and 307 English anchors not found, 71
and 22 answers gone from an edited anchor, 30 English articles under 20 paragraphs, 10 Spanish
articles unavailable (one of them a network timeout on the day of the draw), 4 Spanish anchors
too short, 2 Spanish and 3 English anchors found more than once (`bench-manifest.json`).
Routes: Spanish 527 exact, 85 fuzzy-block, 2 fuzzy-search; English 476 exact, 138
fuzzy-block; **420 rows exact in both**. Spanish articles: median 43 paragraphs (10th-90th
percentile 23-107), **86 over 90**; English: median 61, 148 over 90. Gold sentences per question:
1.02. The gold sentence starts past character 900 of its paragraph, where the tournament does
not see it, in **24 Spanish and 17 English** rows. The answer's letters occur only in the gold
sentence, in both languages, in 309 rows.

The parse API renders an old revision with today's templates: a rebuild by someone else, later,
may not reproduce the manifest's SHA-256 at the same revisions. A rebuild here from the cache
reproduces every file.

### What the text goes through

Both languages alike, before anything is asked: whitespace collapsed; **numeric footnote marks
dropped** (`[12]`, `[n. 3]`, `[nota 3]`), which MLQA left in 1,370 of the 3,000 Spanish pages
of the pages bench and 5 English ones, while today's HTML holds them in `<sup>`, which the parser
skips: kept, they would be markup on one side only. **Zero-width
characters are kept**: Spanish Wikipedia writes one after every footnote mark (19,423 of 33,739
Spanish paragraphs, 138 of 43,087 English ones), and since `29c433b` `text.split_sentences`
cuts through them (Spanish sentences: 122,367 with them, 122,248 without), so the bench reads
them as the consumer's text would hold them.

## Arms (`benchmarks/b6_es/b6_run.py`)

One model: **jev-1.13.0** (the production `DEFAULT_MODEL`, the model of both English
confirmations), pinned. Shipped thresholds and limits (`Thresholds()`, `Limits()`):
`pages_in_context` 0.40, `pages_first_round` 0.18, `document_paragraphs` 0.75,
`document_window` 2, `sentences` 0.28, 30 pages a call, no `max_calls`. **The decider sees each
page's first 900 characters** (`chunks.PAGE_LIMIT`, followed by " [...]" when cut): in
`triage_pages` and in every tournament call of `select_passages`. No answering model.

| arm | point | input |
|---|---|---|
| `P-es` | `Squire.triage_pages` | Spanish question, the ten Spanish pages, of which the decider sees 900 characters each |
| `P-en` | `Squire.triage_pages` | English question, the ten English pages, the same way |
| `D-es` | `Squire.select_passages` | Spanish question, every paragraph of the Spanish article |
| `D-en` | `Squire.select_passages` | English question, every paragraph of the English article |
| `D-es90` | `Squire.select_passages` | Spanish, **past 90 paragraphs only the 90 best by BM25** over section and text (`select.index_of`, ties and zero scores by page order), sent in page order (the consumer); an article of 90 or fewer reuses D-es |

**The consumer's cut to 900 characters is not an arm.** Cutting a page to 900 before
`triage_pages` sends the decider the same 900 characters, without the " [...]" marker; what it
changes is what is delivered. C1 is therefore scored free from P-es: a kept gold page delivers
its answer only when the answer ends within character 900. The difference against P-es is the
11 Spanish questions whose answer ends past 900, whenever P-es keeps their page. The marker's
own effect and a second draw are not measured.

Within one bench, an identical call is asked once: D-es90 sends some of D-es's exact sentence
calls again (the same paragraph and question), and gets D-es's answer, recorded or in memory.

The questions are launched in a seeded order (seed 20261016); within a question the arms run
one after the other, Spanish first on even launch positions and English first on odd ones. At
most 4 calls in flight. Answers are recorded in `fixtures/b6-es.jsonl` (hashed keys, no text).

**One bench a run, pages first.** `--bench pages` runs to completion (or to terminal) before
`--bench docs` is allowed (`b6_run.launch_gate`); a pages bench ended by its cap blocks docs
until a sealed amendment. Each bench is scored when it is complete. Nothing in this
pre-registration changes after the pages result is read.

## Metrics

Per question, by construction:

- pages: **hit** = the gold page kept; **delivered** = kept and the answer ends within the
  first 900 characters; **answer kept** = the answer's letters appear in some kept page. Text
  kept = characters of the kept pages over the characters of the ten pages.
- docs: **all gold** = every gold sentence kept (one gold sentence nearly always); **answer
  kept** = the answer's letters appear in some kept sentence; text kept = characters of the
  kept sentences over the whole article's. For D-es90 a paragraph not preselected counts as
  not kept, and the share is of the whole article.

Absolute kept characters, kept pages and kept sentences per arm are reported, descriptive.
Free, beside them: BM25 at the same text per question (pages within each arm's kept
characters; sentences within each docs arm's), and the share of Spanish articles over 90
paragraphs whose gold paragraph survives the BM25 preselection.

## Verdict rules (decided now)

Statistics from `sanchopanza.eval.stats`: paired bootstrap over questions (2,000 resamples,
seed 7, percentile 95 % CI) for every difference; exact McNemar reported beside it; Wilson
intervals for single rates. Margin **5 points** (`b6_score.MARGIN`).

- **H1, pages** (primary): hit(P-es) − hit(P-en), on the **264 questions whose answer ends
  within 900 characters in both languages**: the decider sees 900 characters of a page, and the
  answer lies past them in 30 English gold pages against 11 Spanish ones, which would bias an
  all-rows comparison by several points against English. All 300 rows: secondary, no verdict.
- **H2, docs** (primary): all gold(D-es) − all gold(D-en), all 614 rows.

For each, on its own (two separate claims about two points, so no correction across them):

1. **"no worse"** if the CI's lower bound is above −5 points, written "no worse (but lower)"
   when its upper bound is also below 0;
2. **"worse by more than 5 points"** if the CI's upper bound is below −5 points;
3. **"inconclusive"** otherwise.

**Pareto label**, with each primary: the paired CI of Spanish minus English text kept (on the
same rows); **"no worse on both"** needs rule 1 and that CI's upper bound below +5 points;
otherwise "no worse on recall only (more text)" or "not shown on recall"
(`b6_score.pareto`).

**C1, the consumer's cut** (pages, all 300): delivered(P-es) − hit(P-es), with the same rule and
labels, read as "what the cut costs in Spanish".

Descriptive only, no verdict:

- **C2, the consumer's preselection**: all gold(D-es90) − all gold(D-es) on the 86 Spanish
  articles over 90 paragraphs, with its CI; and the free rate at which the preselection keeps
  the gold paragraph (84 of 86 Spanish, 147 of 148 English, known before any answer).
- **Sensitivity:** H2 on the 420 rows exact in both languages, and on the 194 with a fuzzy
  route, reported apart.
- **Fairness:** H2 on the 309 rows where the answer's letters occur only in the gold sentence
  in both languages; H2 on the 581 rows where the gold sentence starts within 900 characters of
  its paragraph in both; "answer kept" Spanish against English, pages and docs.
- H1 on all 300 rows; any gold (docs); BM25 at the same text; Spanish and English rates against
  the published English numbers (98.3 % at 33.6 %; 87.2 % at 21.0 %); D-en as an English
  document type outside QASPER (encyclopaedic articles).

**A bench is scored only when every call answered**, from jev-1.13.0, with every question it
asked answered: a live answer missing a question is an unanswered call, and a recording from
another model or a partial one is a miss asked again (below, "Stops"). Jev is not deterministic across a day, so each question's Spanish-English
disagreement includes the draw's own noise, which the CI carries.

## Power

`python -I benchmarks/b6_es/b6_run.py --power`, free. The paired difference's 95 % CI has a
half-width of about 1.96 √(d / n), d the share of questions where the two languages disagree;
rule 1 at −5 points, if the languages are truly equal, needs n = 7.85 d / 0.05², and the chance
of reading "no worse" at n is Φ(0.05 / √(d / n) − 1.96) (`b6_score.n_noninferiority`,
`power_no_worse`).

d is unknown before any answer. Free readings bound it:

- **Proxy, BM25 at the same text** on these questions: pages (the 264 primary rows), BM25
  within a third of the text, Spanish 67.4 % against English 75.4 %, d = 61/264 = 0.23; docs,
  BM25 sentences within a fifth of the article, 81.3 % against 89.3 %, **d = 105/614 = 0.17**.
  A ranking that does not read the question is a loose proxy for one that does, and Jev's own
  draw-to-draw noise adds to d: the docs reading is taken at **d ≈ 0.20-0.23**.
- **The English rates**: pages near 98 % (HotpotQA 98.3 %) leave little room to disagree,
  d ≈ 0.03-0.05; docs near 87 % (QASPER 87.2 %) leave d ≈ 0.15-0.23.

| d | n for 80 % at −5 if equal | power at 264 | at 400 | at 614 | half-width at 614 |
|---|---|---|---|---|---|
| 0.05 | 157 | 0.95 | 0.99 | 1.00 | 1.8 points |
| 0.10 | 314 | 0.73 | 0.89 | 0.97 | 2.5 points |
| 0.16 | 503 | 0.53 | 0.71 | 0.87 | 3.2 points |
| 0.20 | 628 | 0.44 | 0.61 | 0.79 | 3.5 points |
| 0.23 | 723 | 0.40 | 0.55 | 0.73 | 3.8 points |

So:

- **Pages, 264 primary rows**: power 0.95 **only if d is about 0.05**, which needs both hit
  rates at about 95 % or more (HotpotQA's 98.3 % suggests so). At the BM25 proxy's d of 0.23 it
  would be 0.39; at 0.10, 0.73. The pages power is an assumption on Jev's hit rates, not a
  measurement.
- **Docs, 614 rows** (every MLQA test article that qualifies; no more exist in the split):
  **0.85 at the proxy's d of 0.171**, 0.79 at 0.20 and 0.73 at 0.23, the range Jev's draw noise
  makes likely.
- A true drop of 5 points or more is detected (McNemar, 80 %) with about the same n as "no
  worse" when the languages are equal. C2's 86 rows give a half-width of about 5.6 points at
  d 0.07: descriptive.
- **C1 is known in advance to land near −3.7 points** (11 of 300 Spanish answers end past
  character 900, each a loss whenever P-es keeps its page), with a CI that will most likely
  cross −5: expect "inconclusive", which here describes a fixed, small, known loss rather than
  an unknown.

**A free finding before any answer:** BM25 itself is 8 points worse in Spanish at the same
text (pages 67.4 % against 75.4 %; docs 81.3 % against 89.3 %), on the same questions. The
package's BM25 folds accents and has no stemming; the consumer's BM25 preselection inherits it.

## Spend, caps and stops

`python -I benchmarks/b6_es/b6_run.py --dry`, free: each bench through the shipped code with a
stub decider (in each in-context call the 8 best pages by BM25 at 0.9, the next 4 at 0.5, the
rest at 0.05: QASPER's 8.1 paragraphs a question past the 0.75 gate), counting every call a live
run would make (a recorded answer is free) and pricing it from its size. Jev bills 42
micro-dollars per thousand input tokens (every published fixture: 42.0 exactly);
`CappedDecider` reserves a token per three characters, which on the HotpotQA fixtures is 1.23
times the billed tokens of an in-context call and 2.6 times those of a sentence call (the
expected cost divides by those factors, measured on English; Spanish may take more tokens a
character).

| bench, arm | calls (in-context + sentences) | expected | pessimistic |
|---|---|---|---|
| pages, P-es | 300 | 0.053 | 0.066 |
| pages, P-en | 300 | 0.055 | 0.068 |
| **pages** | **600** | **0.108 USD** | **0.134 USD** |
| docs, D-es | 6,853 (2,281 + 4,572) | 1.030 | 1.426 |
| docs, D-es90 | 878 (503 + 375) | 0.224 | 0.287 |
| docs, D-en | 7,892 (2,980 + 4,912) | 1.354 | 1.853 |
| **docs** | **15,623** | **2.607 USD** | **3.566 USD** |
| **Jev, both** | **16,223** | **2.72 USD** | **3.70 USD** |

At the median of 71 micro-dollars a request the same calls would be 1.15 USD; that median
under-prices these calls, which carry up to 30 pages of 900 characters (QASPER's tournament
calls cost 339 micro-dollars each, its sentence calls 58). If every page passed every cut, docs
would make 87,967 calls; the cap stops it long before. Duration: about 16,000 calls at 4 in
flight, roughly 1-1.5 hours, docs nearly all of it.

- **Claude: 0 USD.** No answering model. The English confirmations' primary metrics were this
  same recall at a share of the text, by construction; an answering step would add the answering
  model's own Spanish-English gap to the one measured here. If H2 reads "no worse", an answer
  check in QASPER Run 2's shape (Haiku through clean Claude Code 2.1.287, about 0.026 USD a
  question) can follow under its own prereg.
- **Hard caps in code:** this bench's own ledger (`$SANCHOPANZA_B6_RUN/ledger.json`) capped at
  **5.50 USD**; batch `b6-es-pages` at **0.30 USD**, `b6-es-docs` at **5.00 USD** (the
  pessimistic 3.57 and room for Spanish tokens); each smoke on its own batch
  (`b6-es-smoke-pages`, `b6-es-smoke-docs`) at **0.10 USD**. Every live call goes through
  `CappedDecider` (a pessimistic reservation before the call; refused when it does not fit). A
  live launch refuses to start when the dry estimate of what is left to ask does not fit in
  what its bench's cap has left (the cap minus what the ledger already counts for that batch).
  The roadmap's "< 0.10 USD of Jev" was a guess this dry run replaces; the owner approves the
  2.72 USD expected (5.50 capped) before the seal.
- **What the ledger counts** is the client's estimate, input tokens × the list price, not
  TypeSafe's bill. A call cut by the client's timeout settles at 0 although Jev may have billed
  it; one cancelled in flight stands at its estimate (`CappedDecider`). The preflight (one call,
  `providers.jev.apreflight` for jev-1.13.0) is off the ledger.
- **Stops**, each refusing every later call, those waiting for a slot included:
  - **cap**: a reservation the ledger or the bench refuses. The bench ends there; raising the cap
    is a sealed amendment written before any score is read.
  - **pause**: HTTP 401, 402, 403, 429 or a 5xx (after the client's bounded retries on 529; its
    retries on 429 are switched off), or no connection. A pause is never a result: nothing is
    scored, and it does not count as a launch. A 402 is a pause like the others (no balance
    check is possible meanwhile): relaunch after the top-up.
  - **3 failed calls in a row** of any kind (a timeout, an HTTP 400): the launch ends incomplete.
  - **an answer served live by another model** ends the process at once; the launch is left
    without an outcome and counts as incomplete (a retired model ends terminal). Its line is
    written to the fixture and ignored when read, as below.
- **Recordings from another model, or partial ones, are misses.** The fixture is read keeping
  only jev-1.13.0's lines (`b6_run.recordings`); a recorded answer that misses any question it
  asked is not used either. Such a query is asked again live on the next launch, and its new
  line, written after the old one, is the one every later replay reads.
  - No retries within a launch. A relaunch replays every recorded answer free and asks the
    rest, **including the calls that timed out or failed: a retry by another name**, bounded by
    the rule below.

### Relaunch rule (in code: `b6_run.launch_gate`, `launches.jsonl`)

Every live launch of a bench is written to `$SANCHOPANZA_B6_RUN/launches.jsonl` with the seal,
the commit (`git rev-parse HEAD`; refused when a tracked file differs from it, and when
`prereg.sha256` is not a tracked file, so the seal is the one HEAD holds and an unsealed tree
cannot seal itself and start a fresh count), `sys.version` and `httpx.__version__`, and on exit
its outcome and the ids of the questions with an unanswered call. Outcomes: **complete** (scored;
never asked again, a replay is free), **cap** (ended, above), **pause** (not counted),
**incomplete** (counted), and a launch with no outcome (killed, crashed, a wrong model) counts as
incomplete. **At most 3 counted launches** a bench: the first and two relaunches. After the
third, the bench is **terminal: "no verdict"**, and the report lists the ids still unanswered
(a request Jev keeps refusing, a 400 for size, a model retired). A sealed amendment starts its own
count.

## Running it

From a `git worktree add --detach` at the sealed commit, with the bench rebuilt there
(`b6_build.py` without `--fresh` fetches each article by its pinned revision, or reads it from
the cache, and refuses unless every built file matches the manifest's SHA-256), outside the
session, by WMI in its own process group, not between 02:00 and 08:00, through the launcher.
The repository's `b6-es-run.cmd` holds four placeholders, never a local path: `set
"PY=<PYTHON>"`, `set "SANCHOPANZA_KEYS_ENV=<KEYS_ENV_PATH>"`, `set "WT=<WORKTREE>"` and `set
"SANCHOPANZA_B6_DATA=<DATA_DIR>"`, the last passed as `--data` to every call. The owner fills them
in an untracked copy (e.g. `C:\sp-runs\b6-es\b6-es-run.cmd`); the seal and the runner read those
four lines as their placeholders, so filling them keeps the seal and any other change to the
copy is refused (`b6_run.require_launcher`, which every live run checks against the copy it was
started from). The launcher refuses its placeholders. It is checked out with CRLF line ends
(`.gitattributes`), which cmd.exe needs for its labels; the seal hashes it with LF.

    <copy>\b6-es-run.cmd pages dry     free: what is left to ask, and its cost
    <copy>\b6-es-run.cmd smoke         two dev questions of each bench, a smoke cap each
    <copy>\b6-es-run.cmd pages         the pages bench, to completion
    <copy>\b6-es-run.cmd docs          then the docs bench
    python -I benchmarks/b6_es/b6_run.py --bench pages     free replay and analysis

The key is read inside the process (`b6_run.load_key`: `TYPESAFE_API_KEY`, else the file
`SANCHOPANZA_KEYS_ENV` names), before the preflight; never printed. Jev's HTTP client is built
inside the run's one event loop (`b6_run.make_live`); the preflight uses its own client in its
own loop, closed first. The smoke checks the live path, the caps and the recording end to end;
nothing in it changes these rules.

## What is not done

No jev-1.14.0, no long-context header, no threshold or limit changed, no `max_calls`, no
answering model, no change to `policy.py`. The consumer's BM25 and cut are assumed to be the
package's BM25 and a head cut of 900 characters; its own may differ (to be confirmed with it
before the seal).
