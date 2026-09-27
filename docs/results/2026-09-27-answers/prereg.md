# Pre-registration: does the model still answer from the sentences that were kept?

Written 2026-09-27 before any call of this run. `benchmarks/chunks/answers.py --live` refuses
to spend unless the sha256 of this file matches `prereg.sha256`.

## Question

The confirmed chunk run (`../2026-09-27-chunks/prereg-confirm.md`) showed that judging pages in
each other's context and then sentences inside the kept pages returns every supporting sentence
in 90.3 % of 300 new HotpotQA questions with 22 % of the text. Keeping the supporting sentences
is necessary for a correct answer, not sufficient: the sentences around them may carry the
bridge entity, a pronoun's referent or the date that disambiguates. This run asks an answering
model.

## Data and kept sets

The 300 confirmatory questions of the chunk run (seed 2028), with the keep masks rebuilt from
`fixtures/chunks-confirm.jsonl` exactly as the confirmatory analysis computed them, with the cuts
it fixed from the earlier 600 questions:

- `all`: the 10 paragraphs.
- `C`: the pages with P(contributes, in context) >= 0.40, whole.
- `CB`: inside the pages C keeps, the sentences with P(contributes) >= 0.28.
- `B`: the sentences with P(contributes) >= 0.31, every page, no page gate.

A page keeps its dataset order and its title; inside a page, kept sentences keep their order and
are joined with a space. A page with no kept sentence is absent. An arm with nothing kept is
still asked, with no paragraphs.

## Model, path and prompt, fixed here

`claude-haiku-4-5-20251001` through the Claude Code CLI (`sanchopanza.providers.claude_cli`,
Claude Code 2.1.282): our system prompt replaces Claude Code's, no tools, no settings, no MCP,
thinking off, no session persistence. Billed to the logged-in account, not an API key. The CLI
has no `max_tokens`; replies are scored as they come.

System: "Answer the question using only the paragraphs given. Reply with the answer only: a
short span, a name, a number, or yes or no. If the paragraphs do not contain the answer, reply:
unknown." User: the paragraphs as `Title: text` blocks separated by a blank line, then
`Question: <question>`. Identical to `../2026-09-25-triage/prereg-answers.md`.

## Scoring, fixed here

As in `prereg-answers.md`: HotpotQA's normalisation; **correct** when the normalised gold answer
equals the normalised reply or appears in it as a whole-word substring. Token F1 beside it.
Input tokens from the session's usage.

## Path check

The CLI is not the Messages API. Before the arms are compared to anything measured through the
API, `all` is also asked, through the CLI, on the 300 questions of the confirmatory triage run
(seed 2027), whose `all` answers through the Batch API scored 67.7 %
(`../2026-09-25-triage/answers-analysis.json`).

## Criteria

- **P21**: `CB` accuracy >= `all` accuracy minus 3 points, on the same 300 questions.
- **P22**: `C` accuracy >= `all` accuracy minus 3 points.
- **P23** (secondary): `B` accuracy, and every arm's input tokens as a share of `all`'s,
  reported either way.
- **P24** (path): CLI `all` on the seed-2027 set within 3 points of the API's 67.7 %, with the
  per-question agreement of the two replies reported. If P24 fails, this run's numbers are
  compared only among themselves.

Verdict: P21 and P22 = **the sentences answer as well as the pages**; P22 alone = the page
cut is safe and the sentence cut costs answers; otherwise reported as it falls.

## Cost

1,500 sessions of Haiku 4.5 (1,200 arms plus 300 path check), about 700 tokens of fixed prefix
each: about 4 USD at list price, billed to the subscription, 0 USD to any API key. Ceiling in
code: 8 USD at list price. Answers cached on disk: a rerun costs nothing.
