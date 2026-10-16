# Long documents with free-text answers: where a Jev decision can replace frontier tokens (DRAFT)

**Status: DRAFT design, not a pre-registration, not sealed.** No call has been made and nothing
spent. Every cost below is an estimate from this repo's measured sessions; every fact about an
outside dataset is marked *verified* (read at its source on 2026-10-16) or *unverified*.

## Why

`points.longdoc` (C7) substitutes on four-option questions: Jev 1.14 answers alone at a top choice
≥ 0.6 and the frontier model answers the rest. No worse at −10 points against Sonnet 5.5 (+1.2,
[−3.1, +5.6]) and Opus 5.5 (−3.7, [−8.0, +0.6]), 33.9 % and 29.5 % of their cost saved
(`../2026-10-15-lb162/`, `../2026-10-16-lb162x/`). The open half of C7 is a long-document set
graded on free-text answers. Jev writes no text, so here it cannot be the answerer: it can only
decide *what is read* and *who answers*.

Two facts from this repo shape every design:

- **The frontier model in Claude Code does not read the whole file.** It greps and reads parts:
  lb162x measured 0.085-0.112 USD a LongBench v2 session (Sonnet, Opus) and a cost that barely
  grows with the document, 0.0017 USD per million characters (`harness/longdoc_tool.py`).
  "Whole document" means the file in the session's folder, not the file in the prompt.
- **A cheaper model answered as well from Jev's passages as from the whole paper.**
  `select_passages` kept 21.0 % of QASPER papers with every answer sentence in 87.2 % of 219
  questions, and Haiku 4.5 scored F1 48.2 % from it against 44.5 % from the whole paper (146
  questions, CI of the difference [−0.5, +7.8]) (`../2026-09-28-lateral-wholedocs/`). Those papers
  are far shorter than 100,000 characters, and both arms there were Haiku.

## 1. Candidate datasets

| Set | Licence | Size | Document length | Official scorer | Answers | Contamination |
|---|---|---|---|---|---|---|
| **∞Bench En.QA** (`longbook_qa_eng`) | repo MIT, HF card apache-2.0 (*verified*) | 351 questions (*verified*) over novels | 192.6k tokens on average (*verified*), about 750k characters (*estimate*) | `qa_f1_score`: token F1 after lower-casing and removing punctuation, articles and extra spaces (*verified* in `src/compute_scores.py`; the README footnote says "ROUGE F1", the code says token F1) | short, mostly names and phrases (*unverified*) | lower: key entities replaced in the novels (*per the paper, unverified here*); the same novels carry En.MC, 229 four-option items (*verified*) |
| **NarrativeQA**, stories task | Apache-2.0 (*verified*, HF card) | test: 355 stories (177 books, 178 scripts), 10,557 questions; ~30 a story (*secondary source*) | test mean 57,780 tokens, about 230k characters; scripts shorter than books (*secondary source*) | paper: BLEU-1/4, METEOR, ROUGE-L against 2 references (*unverified*); the card names none (*verified*) | short, 4.73 tokens on average (*paper, via search*) | high: Gutenberg classics and film scripts, questions written from Wikipedia summaries |
| **LongBench v1** single- and multi-doc QA | MIT (*unverified*) | NarrativeQA 200, Qasper 200, MultiFieldQA-en 150, HotpotQA 200, 2WikiMQA 200, MuSiQue 200 (*verified*, `task.md`) | mean words 18,409 / 3,619 / 4,559 / 9,151 / 4,887 / 11,214 (*verified*): only NarrativeQA reaches ~100k characters | F1 (`qa_f1_score`) on every one (*verified*) | short spans | high: public since 2023, sources older |
| **LooGLE** long-dependency QA | MIT (*unverified*, a repository listing) | 776 documents, 1,101 long-dependency questions (*paper, via search*) | 19,367 words on average, about 110k characters; scripts 28,483 words (*paper*) | BLEU, ROUGE, METEOR, BERTScore and a GPT-4 judge (*paper*) | often a full sentence: F1/EM fit poorly | moderate: documents after 2022, set public since 2023 |
| **LV-Eval** single/multi-hop QA | *unverified* | 11 sets at 16k-256k words (*paper*) | built by padding to each level | keyword recall gate, then F1 without filler words (*paper*) | short, keyword-checked | lowered by confusing facts and keyword substitution (*paper*); documents are padded haystacks, not one natural text |

**Excluded.** NovelQA: golden answers and evidence are not public, scoring is a Codabench submission
(*verified*, project page): no per-item local score, so no paired analysis. Loong: graded by a
GPT-4 judge (*unverified*), not a mechanical scorer, and this project uses the official one.

**Recommended set: ∞Bench En.QA.** It is the only one that is long throughout (well over
100,000 characters, past Jev's ~262k-token window, so the long-window shortcut of `points.longdoc`
does not apply and passage selection must), has one mechanical scorer in code, short answers and
an anti-contamination step. Its weakness is size: 351 questions, clustered by novel (the number of
novels is *unverified*; the free pool step counts it). Fallback population if the dev phase shows
more items are needed: NarrativeQA test books over 100,000 characters, one question per book,
scored with the same `qa_f1_score` (LongBench v1's choice), read as a separate lot, never pooled.

## 2. Substitution designs

Arms named below: **N** = Sonnet 5.5 (`claude-sonnet-5-5`) in clean Claude Code 2.1.287 with the
novel as `document.txt` (arm N of lb162). **H** = Haiku 4.5 answering in one short field from
Jev's `select_passages` text. **H0** = Haiku 4.5 in clean Claude Code with the whole file, no Jev.

**(b) Router: Jev's passages, a Jev Truth gate, Haiku or the frontier.** `select_passages` over the
novel, then one Truth over (question, kept passages): "the passages state everything needed to
answer the question". At p ≥ cut Haiku answers from the passages; under it, N answers from the
whole file. On covered items a Jev decision replaces the frontier call outright, and the
escalation is a calibrated number, the measured shape of `points.longdoc`. Unmeasured: the Truth
gate on free text and `select_passages` past ~100,000 characters.

**(a) Always Haiku from Jev's passages.** H on every item. The router at cut 0, so it is read from
the same rows at no cost. Biggest saving, biggest risk: no escalation, and a weaker writer.
Measured part: QASPER (Haiku from 21 % ≥ Haiku from all), not Haiku against a frontier model.

**(c) The frontier model from Jev's passages.** Sonnet answers from the kept text instead of the
file. Avoidance, the lowest rung in this project's order (substitution > avoidance >
affordability). It pays little here: Claude Code already reads only what it greps, and inside a
warm loop the tokens dropped would mostly have been cache reads, 0.2 USD per million for Sonnet
against 2.0 for fresh input (`harness/sources_v2.py`, `PRICES`). Least quality risk, least payoff.

**Ranking.** By the project's order, (b) and (a) are substitution and (c) avoidance; (b) first
because it is the measured cascade shape and keeps the frontier where Jev is unsure. By what is
measured, (a) has QASPER behind its passage step and (b) adds one unmeasured question; (c) needs no
new evidence and is not worth a lot. **One run reads (b) and (a) together**: arms N, H and H0 on
every item plus one Truth call each, as lb162x composed the hybrid from per-arm rows.

**The economics, stated before any data** (estimates per item, below): N ≈ 0.10 USD, H ≈ 0.03,
Jev passages + Truth ≈ 0.02. The router costs J + c·H + (1 − c)·N, so it saves c·(N − H) − J:
nothing below about 29 % coverage, ~7 % of N's cost at 40 %, ~22 % at 60 %. Design (a) saves about
half. So (b) is the safe claim and (a) the valuable one; a pass on (b) at low coverage is not
worth shipping.

## 3. The recommended run: (b) then (a), fixed sequence, against Sonnet 5.5

- **Arms on every item:** N, H, H0 (control, not a design: does Jev add anything over just using
  Haiku?), plus Jev `select_passages` and the Truth call. R (router) is composed from them. Opus
  5.5 is a later lot that reuses the Jev, H and H0 rows (the lb162x pattern); the frontier rule
  (Sonnet 5.5 minimum, Opus 5.5) applies before any product claim.
- **Primary endpoint:** mean per-item ∞Bench `qa_f1_score` (max over references), the official
  code vendored unchanged. Every arm ends with the answer in one short field (section 4).
- **Hypotheses, fixed sequence at one-sided 2.5 % each** (family-wise error held without a split):
  1. R − N > −5 F1 points over all items (router, cut fixed in dev). Only if 1 holds:
  2. H − N > −5 F1 points (always Haiku).
  Product reading as lb162: "sustituye" also needs coverage ≥ 20 % and a saving whose bootstrap
  lower bound is above 0.
- **Margin: −5 F1 points over all items** (owner's decision; −7 the alternative, as proposed in
  `../2026-10-16-lbo8/prereg.md`). Why: lb162's −10 was on accuracy at ~55 %; −5 F1 on a baseline
  expected around 40-60 F1 is a similar ~10 % relative loss, and the QASPER answering run used −6.
  What it allows: at 40 % coverage, R may be up to 12.5 F1 points worse than N on the covered items.
- **Pairing:** every arm on every item; paired bootstrap of the per-item difference, **resampling
  novels** (questions on one novel are not independent), 10,000 draws. Order seeded, arms
  interleaved per item, a clean user and an empty `CLAUDE_CONFIG_DIR` per session.
- **Secondary (registered):** R and H against H0 (attribution: if H0 is as good, the saving is
  Haiku's, not Jev's); saving of N's cost with bootstrap CI; coverage; exact match; median answer
  words per arm; F1 with every reply cut to its first 12 tokens (length sensitivity); the share
  of items whose normalised gold answer appears in Jev's kept passages.

### Power (closed form, checked by simulation)

Assumptions: the per-item paired F1 difference has SD 0.255 in this repo's QASPER run (Haiku
against Haiku, from its CI [−0.5, +7.8] at n 146); across models it will be wider, **0.34 assumed**
(per-item F1 SD ~0.38, correlation 0.6), 0.40 pessimistic. n for 80 % power, margin −5 / −7:

| Design | Assumption | n at −5 | n at −7 |
|---|---|---|---|
| (a) H − N | true tie, SD 0.34 | 363 | 186 |
| (a) | H 2 points worse, SD 0.34 | 1,009 | 363 |
| (b) R − N | coverage 40 %, covered tie | 146 | 75 |
| (b) | coverage 40 %, covered 3 points worse | 253 | 109 |
| (b) | coverage 50 %, covered 5 points worse | 734 | 227 |

A bootstrap simulation of (b) at 40 % coverage and −3 on the covered (F1 clipped to [−1, 1],
400 runs) gave 90 % power at n 300; (a) with H 2 points worse gave 33 % at n 300.
**Read plainly:** about 300 items give ~80-90 % power for the router if Jev's covered items lose
≤ 3 F1 points at ~40 % coverage. Hypothesis 2 is a long shot at −5 unless Haiku ties Sonnet; at
−7 it needs ~190-360. The clustering by novel widens all of this by an unknown design effect: the
dev phase estimates it, and n is recomputed before the seal.

**n: dev 40 items, confirmation the remaining ~311** (all of En.QA). If dev's SD, coverage or
design effect put the router's n above 311, the run is not sealed on En.QA alone (no "a ver si").

### Dev phase (held out, not reused)

40 items drawn by novel (whole novels held out), seeded, by metadata only. It decides, before the
seal: the Truth wording and the cut (lowest cut whose covered H − N ≥ −2 F1 on dev), `fit_chars`
for H (a candidate, roadmap B4; proposed 60,000 characters), the answer-length controls, N's answer
extraction, Jev's cost and calls per novel and the `max_calls` cap, the SD and design effect for n.
Plus a closed-book check: Haiku with no document on the 40 (~0.005 USD each) measures what is
answered from memory despite the entity substitution.

### Money (list prices from this repo; hard caps in code)

Prices: Sonnet 2.0 / Opus 5.0 / Haiku 1.0 USD per million input tokens, cache reads 0.2 / 0.5 /
0.1, output 10 / 25 / 5 (`harness/sources_v2.py`, `PRICES`; not 3.0 for Sonnet); Jev 0.042 USD
per million input tokens (`providers/jev.py`, `DEFAULT_PRICE_PER_MTOK`).

| Per item | Estimate | Basis |
|---|---|---|
| N, Sonnet in Claude Code | 0.10 USD (cap 3.00 a session) | lb162/lb162x: 0.085-0.096 a session; grows little with length |
| H, Haiku from passages | 0.03 | ≤ 60k characters ≈ 15k tokens, CLI overhead as in the QASPER run (0.026 a question) |
| H0, Haiku in Claude Code | 0.05 (cap 0.75, GAIA's Haiku cap) | half of N's input price; *no measurement* |
| Jev passages + Truth | 0.02 | ~2× the novel's 192.6k tokens at 0.042 USD/M, plus per-call overhead |

| Phase | Claude (list) | Jev | Cap |
|---|---|---|---|
| Dev, 40 items + closed-book | ~7.4 USD | ~0.8 USD | Claude ceiling 15, Jev ledger 1.50 |
| Confirmation, 311 items | ~56 USD (N 31, H 9, H0 16) | ~6.2 USD | Claude ceiling **90**, Jev ledger **10** |
| **Total** | **~63** | **~7** | **Claude 105, Jev 11.50** |

Above the 10 USD line: the owner says yes, and decides whether H0 runs in the confirmation (it
saves ~16 USD and loses the attribution claim). Jev's balance is small: `jev-preflight` and a
top-up before the confirmation; the 402 breaker in `funds.py` stops it. Session caps follow
`cap_for` (cap + one worst turn fits under the ceiling, since `--max-budget-usd` cuts between
turns). Claude Code sessions draw on the weekly limit: STOP on 429.

## 4. Code to reuse, code to write, risks

**Reuse.**
- `Squire.select_passages` (`max_calls`, `fit_chars`) with `RecordingDecider` into a fixture, so
  every re-read is a free replay (`benchmarks/lateral/wholedocs/confirm.py` is the pattern).
- `benchmarks/lateral/wholedocs/answers.py`: Haiku through `ClaudeCLI` with the one-field
  `SCHEMA`, `SessionCache`, `prompt_kept`, `token_f1`, ceilings; and
  `sanchopanza.eval.stats.bootstrap_difference`.
- `benchmarks/h2h/h2h_longdoc.py` with `offline_common`/the GAIA runner for N and H0 (clean user,
  `document.txt`, web removed, local hook), `h2h_lb162x.py` and `lb162x_guard.py` for caps,
  ceilings, STOP and the served-model check, `benchmarks/jev114/lb162x_stats.py` for the saving
  bootstrap and readings, `lbo8.py` for the metadata freeze (`freeze_ids`, `prepare`) and `--dry`.

**Write (with tests, all free).** A loader for ∞Bench En.QA into
`~/.cache/sanchopanza/longdoc_free`; the official `qa_f1_score`/`normalize_answer` vendored with
their MIT notice and pinned by tests; a free-text template and answer extraction for N and H0
replacing LongBench v2's `extract_answer`; the Truth question; a stats module with the novel-level
bootstrap and the fixed sequence; `--pool`, `--freeze-ids`, `--draw-dev`, `--dry` with the money
simulation; a thin live driver and its guard.

**Risks.**
- **Scorer gaming by length.** On 2026-09-27 containment scoring rewarded long replies (Haiku's
  median reply grew from 4 to 30 words with the context; `../2026-09-27-answers/`). Token F1 runs
  the other way: a verbose N loses precision and *flatters the hybrid*. All arms must give one short
  field (`--json-schema {"answer": string}` as in `prereg-short.md`, or a last `ANSWER:` line with
  a word limit where the agentic arm cannot take a schema: *unverified*, checked in dev); median
  words per arm and the 12-token sensitivity are registered.
- **Passage selection past 100,000 characters is unmeasured.** The tournament was confirmed on
  whole QASPER papers; a 750k-character novel means hundreds of calls, their cost and latency, and
  maybe lower recall. `max_calls` caps it; dev measures it.
- **Coverage moves between draws** (L6 54 %, lb162 37 %). Below ~29 % the router saves nothing.
- **Contamination**: famous novels behind substituted names; the closed-book check sizes it.
- **Clustering by novel** inflates n; small number of novels limits the bootstrap.
- **One draw**: one session per item and arm; the verdict reads as sealed, nothing more.
- **TypeSafe MCA 2.3(b)**: Jev's decisions are recorded for replay only, never for training.

## Sources

- ∞Bench: <https://github.com/OpenBMB/InfiniteBench> (README, `src/compute_scores.py`),
  <https://huggingface.co/datasets/xinrongzhang2022/InfiniteBench>
- NarrativeQA: <https://huggingface.co/datasets/deepmind/narrativeqa>,
  <https://arxiv.org/abs/1712.07040>; test-split statistics via <https://arxiv.org/abs/1907.01686>
- LongBench v1: <https://github.com/THUDM/LongBench/blob/main/LongBench/task.md>
- LooGLE: <https://arxiv.org/abs/2311.04939>
- LV-Eval: <https://arxiv.org/abs/2402.05136>
- NovelQA: <https://github.com/NovelQA/novelqa.github.io>
- This repo: `../2026-10-15-lb162/`, `../2026-10-16-lb162x/`, `../2026-10-16-lbo8/prereg.md`,
  `../2026-09-28-lateral-wholedocs/`, `../2026-09-27-answers/`, `src/sanchopanza/points/longdoc.py`
