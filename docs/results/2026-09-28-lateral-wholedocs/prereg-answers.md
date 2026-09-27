# Pre-registration: answering from what the whole-document rule keeps, against the whole paper

Written 2026-09-28 before any call of this run, while the Jev calls of `prereg.md` were still
running and before its analysis was read. Hash in `prereg-answers.sha256` (LF-normalised).
`benchmarks/lateral/wholedocs/answers.py` refuses `--live` unless the hash matches.

## Claim

Keeping the answer's sentences is necessary for an answer, not sufficient. On HotpotQA the kept
sentences answered as well as all ten pages (`docs/results/2026-09-27-answers/`, short field).
Here the input is a whole paper, the kept text is the GW rule of `prereg.md` (gate 0.75, cut
0.28, window 2), and the questions are the 219 of `prereg.md`, which nobody had answered in this
repository. Claim: **a second answering model, given only what GW keeps, answers with QASPER
answer F1 no more than 3 points below the same model given the whole paper.** The claim is
equality within a margin, not gain.

## Fixed here

- Model and path: Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) through the Claude Code CLI
  (`sanchopanza.providers.claude_cli.ClaudeCLI`, the logged-in subscription, no API key), thinking
  off, no tools, the reply forced into one short field with `--json-schema {"answer": string}`.
- System prompt: "Answer the question using only the paper text given. Reply with the answer
  only: a short phrase, a short list of phrases, a number, or yes or no. If the text does not
  contain the answer, reply: unknown."
- User message, **FULL**: every paragraph of the paper in order, each as `section: paragraph`,
  blank-line separated, then `Question: ...`. **GW**: the same, with each paragraph reduced to
  the sentences GW keeps (paragraphs with none omitted), rebuilt from
  `fixtures/lateral-wholedocs.jsonl`.
- Scoring: QASPER's answer F1: normalised tokens (lower case, punctuation and articles removed),
  maximum over every annotator's answer (yes/no as "Yes"/"No", extractive spans joined by ", ",
  else the free-form answer). Exact match reported beside it.

## Sample size from a cost pilot (registered rule)

Questions are ordered by (paper id, question), shuffled with `Random(2033)`. The first 10 run
first, both arms, as a pilot that also counts in the analysis. With `c` the pilot's list-price
cost per question (both arms), the run answers the first `N = min(219, floor(4.30 / (1.15 c)))`
questions. Nothing else is decided between the pilot and the run.

## Criteria (on the questions both arms answered)

- **A1**: mean F1 of GW >= mean F1 of FULL minus 3 points.
- **A2**: the paired bootstrap 95 % lower bound of GW minus FULL (mean F1, 2,000 resamples by
  question, seed 7) is at least -6 points.

Both = **confirmed**; otherwise **not confirmed**, reported as it falls. A session without a
structured answer is retried once; a question either arm still fails is excluded from both and
listed.

## Prediction

FULL mean F1 0.40-0.55; GW within 3 points of it (between -3 and +1); GW's input at 20-30 % of
FULL's tokens. The risk is the 13 % of questions where GW drops an answer sentence and the 7 %
where it drops every one; a long input also gives more room to be wrong, which may offset it.

## Cost and caps

Per question about 0.012-0.020 USD at list price for both arms (FULL is a whole paper, about
6,000 tokens, read twice by the structured-output turn). Hard caps in code: 4.50 USD ceiling on
the `ClaudeCLI` (counting the cache, so a resumed run gets no fresh ceiling), 0.15 USD per
session, 4 sessions at once, and `benchmarks/lateral/ledger.py` refuses the run if the CLI spend
of every lateral run could pass 5.00 USD. Sessions cached in
`fixtures/cli/lateral-wholedocs-answers.jsonl`.
