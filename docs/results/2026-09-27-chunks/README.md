# Judge pages in each other's context, then keep only the sentences that contribute

Two pre-registered runs on HotpotQA (distractor, validation, CC BY-SA 4.0), whose
`supporting_facts` mark the exact sentences an answer needs: labels by construction.

- `prereg.md`: first run, 600 questions (300 to derive, 300 held out). P15 missed by 0.3
  points, P16 failed, P17 held.
- `prereg-confirm.md`: 300 new questions, every cut fixed from the first 600. **Confirmed.**

## The confirmed result

| arm | what it keeps | supporting pieces kept | text kept | Jev calls per question |
|---|---|---|---|---|
| A: each page asked alone (`triage_part`, 0.28) | pages | 94.3 % of questions keep every page | 52.9 % | 10 |
| **C: every page asked in one call, the others in view** (`triage_pages`, 0.40) | pages | **98.3 %** | **33.6 %** | **1** |
| B: each sentence, read inside its page (`select_sentences` alone, 0.31) | sentences | 88.7 % keep every sentence | 34.9 % | 10 |
| **C then B inside the kept pages** (0.40, then 0.28) | sentences | **90.3 %** | **22.3 %** | 11 |

- **P18 holds**: C keeps every supporting page in 98.3 % of questions with 34 % of the text.
- **P19 holds**: C beats judging each page alone on the same questions, with more recall,
  less text and one call instead of ten.
- **P20 holds**: sentences alone reach 88.7 % at 35 %.
- Combined, the answer's sentences all come back in nine questions of ten with a fifth of the
  text. Against BM25 over sentences, given at least as much text, sentence selection was 16
  points ahead in the first run.

The one-call Choice over the same pages (`triage.set_questions`) failed on 2026-09-25: a Choice
spends its mass on one page. What changed is one Truth per page over a shared state: each page
keeps its own probability while the model reads all of them.

## How the first run went wrong, and why it does not count against this

Its derivation rule targeted *sentence* recall for C, which keeps whole pages, and picked an
aggressive cut (0.77) that held out at 86.3 %. The descriptive curve showed 99 % at a moderate
cut; the confirmatory run fixed the cut from 600 questions with a page-recall target and
tested it on 300 nobody had seen.

## What this does not settle

- **No answering model on these kept sets.** On the page arm (A) an answering model lost
  nothing from half the tokens (`../2026-09-25-triage/`); for sentences it is untested.
- **Short, clean paragraphs** (about 530 characters). A page longer than the 900 characters
  that `context_questions` shows of each page is judged by its excerpt; long documents need
  chunking first, and sentences past the 40th of a page are kept unjudged (3 pages of 6,000
  here).
- **English Wikipedia questions.** Indagis's purposes are often Spanish.
- **Jev's state limit** (32k tokens) bounds a set: 30 pages of 900 characters fit.

## Cost and reproducing

12,900 Jev decisions, 0.79 USD (`fixtures/chunks.jsonl`, `fixtures/chunks-confirm.jsonl`).

```bash
python benchmarks/chunks/run.py --analyze --hotpot HOTPOT.jsonl
python benchmarks/chunks/confirm.py --hotpot HOTPOT.jsonl
```
