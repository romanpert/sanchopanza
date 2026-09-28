# In-context page triage on the fixed sequence keeps the answers, at a fifth of the tokens

Pre-registered in `prereg.md` (hash in `prereg.sha256`, registered before the live run). The
fixed-sequence A/B of 2026-09-24 again: 10 tasks, the same deterministic 20 documents per task
in both arms, one answering call per arm (`claude-sonnet-5`, effort low, through `claude -p`),
corpus pinned at `c168363`. The only change is the lever: instead of asking of each document
alone whether it is relevant (`triage_page`), `Squire.triage_many` judges the documents'
passages (paragraphs of at most 900 characters) with the others in view, at the shipped cuts
(0.18 first round, 0.40 final); a document with no passage left is withheld. Both arms were
rerun: the recorded bare arm of 2026-09-24 matches no commit.

## Result: success, on 9 of 10 tasks; the tenth cannot overturn it

| 9 paired tasks | bare | squire | paired ratio [95 %] |
|---|---|---|---|
| Input tokens | 500,030 | 102,660 | **-79.5 %** [-86.5 %, -72.9 %] |
| Cost, list price (Jev included) | 2.402 USD | 0.595 USD | -75.2 % [-82.9 %, -68.0 %] |
| Correct | **9/9** | **9/9** | |

- **Correctness bar (>= 9 of 10) holds**: 9 correct, whatever the tenth would have answered.
- **Token bar (>= 50 % below bare) holds**: -79.5 %. With the tenth pair added at its worst
  (the squire arm sending everything, about 60,000 tokens in both arms) the ratio would be -71 %.
- **Precondition (bare >= 9 of 10) holds**: 9 correct.

**The run did not finish as registered.** The tenth task, `spread-costs`, was stopped by the
3.00 USD hard cap: its bare session hit the ceiling mid-call (`error_max_budget_usd`) and its
squire arm was refused before answering. The plan's cost estimate (1.45 USD of answering, four
characters a token) was low; the sessions read about 1.6 times the estimated tokens. No task was
rerun. Its squire arm's triage did run: every passage holding its three pins was served.

The prediction (8-10 correct at 55-70 % fewer tokens, about 55 % confidence) held on
correctness and undershot the saving.

## Against the run it answers

| | 2026-09-24, `triage_page` per document | 2026-09-28, `triage_many` over passages |
|---|---|---|
| Correct | 10/10 bare, **6/10** squire | 9/9 bare, **9/9** squire |
| Input tokens | -75.2 % | -79.5 % |
| Documents withheld whole | 170 of 193 | 81 of 173, plus 2,042 passages cut from the rest |
| Pins withheld (`attribution.json`) | the answer document in all four misses | **none**, in all ten tasks |

The two failure shapes of 2026-09-24 are both in this set and both answered: the compound
tasks (`spread-adapters`, four pins in four documents, correct; `spread-costs`, three pins, all
served), and the long document judged by its head (`paper-06`, the source of `injection`, `dag`,
`entity` and `classify`, all correct). The numbers are not placed beside each other as a paired
comparison: that run went through the API, this one through the CLI, on different sequences.

## What it cost

- Jev: 219 in-context calls, **0.107 USD** (0.094 on the nine answered tasks, 0.013 on the tenth).
- Answering, list price on the subscription (not the API key): **3.19 USD** as Claude Code
  reported it, 2.90 on the 18 answered sessions and the rest in the aborted tenth. The cap
  checks before each session; the last one overran it by 0.19 USD.

## Limits

- **A pipeline, not an agent loop.** One answering call over a sequence in which 16 to 19 of 20
  documents are useless by construction. In a free agent loop over the same corpus, 64 paired
  runs showed no measurable change in cost (`benchmarks/ab`); this result does not change that.
  One answering call per arm also means no cache-read pricing: inside a warm loop the tokens
  kept out are worth about a tenth of what they cost here.
- 9 tasks, one repeat: 9/9 has a Wilson lower bound of 70 %. The bar is met; equality of
  quality is not proved.
- The Jev decisions were not recorded as a fixture; the passages each arm kept and withheld are
  in `rows.json`, and the answering sessions replay free from `fixtures/cli/fixed-pages.jsonl`.
  A live rerun is a new sample (Jev is not deterministic).
- The corpus is this repository's own documentation at one commit, in English, by one author.

## Reproducing

```bash
python -m benchmarks.ab.fixed --lever pages --via claude-cli --corpus-ref c168363 --repeats 1 \
    --max-usd 3 --cli-cache fixtures/cli/fixed-pages.jsonl --out docs/results/2026-09-28-fixed-pages
```

`live-run.log` is the run's output; `summary.json`, `rows.json`, `attribution.json`
(`pages.attribute`, passage-level) are its files.
