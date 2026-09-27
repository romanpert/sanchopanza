# Pre-registration: the tournament on whole scientific papers, cuts transferred, nothing derived

Written 2026-09-27 before any call of this run. `benchmarks/longdocs/run.py --live` refuses to
spend unless the sha256 of this file (line endings normalised to LF) matches `prereg.sha256`.

## Why

Indagis reads long documents: a 117,000-character PDF in one real job. `triage_many` was
confirmed on 100 short Wikipedia paragraphs per question (`../2026-09-27-hierarchy/`). A long
document is a large set of paragraphs, so the same shipped method should apply with no new
parameter. This run tests that transfer on data with human evidence labels, and it tunes
nothing: if the cuts fixed on HotpotQA do not carry over, that is the result.

## Data

QASPER, test split (Dasigi et al., NAACL 2021; CC BY 4.0), `allenai/qasper` on Hugging Face:
416 NLP papers, full text as sections of paragraphs, questions written by NLP practitioners who
read only the title and abstract, answers and evidence paragraphs marked by other practitioners
who read the paper.

- One question per paper, drawn with `random.Random("2030-<paper id>")` among the paper's
  eligible questions. A question is eligible when its **first** annotator's answer is not
  `unanswerable`, has at least one evidence string, and every evidence string equals a
  paragraph of the full text after stripping whitespace (evidence from figures and tables,
  `FLOAT SELECTED`, does not). Papers with no eligible question are skipped.
- The first 300 such papers in `random.Random(2030)` order.
- A page is `(section name, paragraph)` for every non-empty paragraph, in document order.

## Arms

- **MANY**: `Squire.triage_many(purpose=question, pages=paragraphs)` exactly as shipped:
  groups of at most 30 at `pages_first_round` 0.18, survivors together at `pages_in_context`
  0.40. `chunks.context_questions` shows each paragraph truncated to 900 characters; that is
  part of what is tested.
- **BM25**: paragraphs ranked by BM25 of the question against `section paragraph` (the triage
  runs' tokeniser), top k, with k the mean number of paragraphs MANY keeps, rounded up.

## Metrics

**Evidence recall, all**: every evidence paragraph of the question kept. **Any**: at least one.
**Kept share**: characters kept over the characters of the paper's paragraphs.

## Criteria

- **P28**: MANY keeps all evidence in >= 85 % of questions with a kept share <= 25 %.
- **P29**: MANY's all-evidence recall exceeds BM25's at the same paragraph count by >= 10 points.

Verdict: P28 and P29 = **the tournament transfers to long documents**; otherwise reported as
it falls, and no cut is re-derived on these papers.

## Cost

About 5 to 8 Jev calls per paper of about 10k tokens: about 0.6 USD at 0.042 USD per million
input tokens. Recorded in `fixtures/longdocs.jsonl`.
