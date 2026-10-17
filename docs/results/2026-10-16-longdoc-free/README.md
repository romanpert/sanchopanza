# Long documents with free-text answers: Jev's passages and gate on ∞Bench En.QA (dev)

**Status: the dev phase of a sealed lot, run 2026-10-17; by its sealed rule no confirmation is
sealed.** Sonnet 5.5 and Haiku 4.5 in clean Claude Code 2.1.287, Jev 1.13.0. Pre-registration
`prereg-dev-a1.md` (sealed `d8f266f`; the original registration `prereg-dev.md`, sealed `6fd9747`,
and its amendment 1, section 9); design `design.md`.

## The question

`points.longdoc` substitutes the frontier model on four-option questions about long documents.
On free-text answers Jev writes nothing, so it can only decide what is read and who answers.
Design (b): Jev keeps the passages of a long novel that a question needs
(`select_passages`, `fit_chars=60000`) and judges with one Truth whether they suffice; at
p ≥ the cut, Haiku 4.5 answers from those passages, elsewhere Sonnet 5.5 answers from the whole
novel. Does that router (R) answer as well as Sonnet alone (N), for less?

## Setup

- ∞Bench En.QA (`longbook_qa_eng`, Hugging Face revision `90f0394`), graded by ∞Bench's own
  `qa_f1_score` (token F1 over normalised text, the best reference), vendored unchanged. The dev:
  41 questions on 8 whole novels (298,903 to 1,186,368 characters), drawn from metadata only;
  the other 310 on 61 novels were held for a confirmation.
- Every arm is one headless session in clean Claude Code 2.1.287 (pinned), a clean user and
  `CLAUDE_CONFIG_DIR` per session, the web taken away, ∞Bench's own instruction ("Be very
  concise") with the book as `document.txt` and a last `ANSWER:` line:
  N, Sonnet 5.5 with the whole novel; H, Haiku 4.5 with Jev's kept passages; H0, Haiku 4.5 with
  the whole novel; HC, Haiku 4.5 with no file (closed book).
- Jev 1.13.0 (the 0.3.2 default), no long context: the page tournament over the novel in
  900-character pages, the sentence stage, then the gate "`passages` are excerpts of one novel.
  They state everything needed to answer `question`."

## Results (dev, 41 questions; descriptive, not a verdict)

Intervals are percentile bootstraps resampling the 8 novels (10,000 draws): with 8 clusters they
are wide and only descriptive.

| Arm | Mean F1 (points) | Mean cost a question (USD) |
|---|---|---|
| N: Sonnet 5.5, the whole novel | **55.0** | 0.069 |
| H: Haiku 4.5, Jev's passages | 44.6 | 0.031 + Jev 0.039 |
| H0: Haiku 4.5, the whole novel | 45.1 | 0.079 |
| HC: Haiku 4.5, closed book | 1.0 | 0.018 |

- **The router at the dev's cut (0.6, 33 of 41 questions covered):** R − N −0.6 F1 points
  [−8.2, +7.9]; **its cost 25 % above N's** (saving −25.1 % [−36 %, −13 %]).
- **Jev's passages did not help Haiku:** H − H0 −0.5 [−10.2, +9.3]. Sonnet over Haiku with the
  whole novel: N − H0 +10.0 [−1.5, +23.7].
- **The gate's p tracks where Haiku is level** (descriptive: every interval below includes 0):
  on the questions it covers, H − N is −3.7 points at a cut of 0.5 (34 covered), −0.7 at 0.6
  (33), +5.6 at 0.7 (24) and +11.4 at 0.8 (9 questions on 7 novels); the 8 it leaves to Sonnet
  at 0.6 have H − N −50.6.
- **Memory answers almost nothing** (HC 1.0 F1): the entity substitution holds.
- Every session was served by its model, none met its cap, every reply had an ANSWER line;
  median answer 3-4 words (HC 7), and F1 cut to the first 12 tokens moves no arm by more than 0.2.

## The sealed reading

By `prereg-dev-a1.md` section 5 (`dev_read.py`, `dev.json`): 41 of 41 questions complete; HC
far below N (no memory stop); the cut 0.6 (the lowest covering at least 29 % and 8 questions
whose covered H − N is at least −2 points). For the confirmation's 310 questions, 80 % power
for R − N > −5 needs **541 questions** (the dev's SD of the per-question difference, 29.9
points, a design effect of 1.5): **above 310, so no confirmation is sealed on En.QA.** Its money
would not have fitted either: Claude's ceilings by the registered formula bring the lot to 143 USD
against 105 (Haiku's H0 sessions reach 0.23 USD at their 95th percentile), and Jev's phase is
12.35 USD expected, 14.8 with the registered 1.2 margin, over its 12.50 cap.

## Why it does not pay here

The substitution saves what Haiku costs less than Sonnet on the covered questions, minus Jev on
every question. Here that is about 0.80 × (0.069 − 0.031) ≈ 0.030 USD a question (0.022 on the
questions it actually covered) against
**0.039 of Jev** (0.037 of it the page tournament): over a dev novel of a median 550,000
characters a question, the tournament made about 68
calls a question (2,787 over 41), and Sonnet in Claude Code does not read the novel either, it
searches it, as its cost shows (0.069 USD and a median of 4 turns a question). So on these
novels Jev's passage selection costs more than replacing the frontier model saves, whatever the
quality.

## What it does not say

- Nothing about the router's quality beyond these 41 questions: the dev was not built to test
  it, and its interval spans ±8 points.
- Nothing about Opus 5.5, other budgets than 60,000 characters, or documents that Claude Code
  cannot search as cheaply (no plain text, no grep-able names).
- One session per question and arm.

## Next

A proposal, not measured: a free pre-filter before the tournament (BM25 over the pages, as
`text.bm25_scores`, keeping a few hundred), so Jev judges a fraction of the novel; it would have
to bring Jev's cost a question well under 0.03 USD before a new dev is worth running.

## Cost

Jev 1.6072 USD (phase J, its cap raised to 1.80 by amendment 1 before any outcome); Claude
8.20 USD at list price (smoke 0.10, N 2.84, the Haiku arms 5.25), on the subscription.

## Files

`ids.json` (the frozen draw), `jev-dev.jsonl` (the gate's p, kept characters, per question),
`dev-sonnet-rows.jsonl`, `dev-haiku-rows.jsonl`, `smoke-rows.jsonl` (per session: F1, cost,
turns; no answer text) and their `*-stop.json`, `dev.json` (the sealed reading),
`fixtures/longdoc-free/jev-dev.jsonl.gz`
(Jev's recorded decisions, for replay only; decompress to `jev-dev.jsonl` to replay). Code:
`benchmarks/longdoc_free/`, `benchmarks/h2h/h2h_lfree.py`.
