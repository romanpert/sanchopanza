# Does the model still answer from what triage kept? Two runs, the first negative

The kept sets are those of the confirmed chunk run (`../2026-09-27-chunks/`): 300 HotpotQA
questions nobody derived a cut on, each answered by `claude-haiku-4-5-20251001` from four inputs:

- `all`: the 10 paragraphs.
- `C`: the pages kept in context, cut 0.40, 34 % of the text.
- `CB`: the sentences kept inside those pages, cut 0.28, 22 % of the text.
- `B`: the sentences kept with no page gate, cut 0.31, 35 % of the text.

Every answer went through the Claude Code CLI (`sanchopanza.providers.claude_cli`), billed to
the logged-in subscription: 0 USD against any API key.

## First run (`prereg.md`): negative as registered

| input | correct (registered score) | exact match | token F1 | median reply, words | input tokens vs `all` |
|---|---|---|---|---|---|
| `all` | **81.0 %** | 20.0 % | 0.34 | 30 | 100 % |
| `C` | 76.7 % | 33.0 % | 0.47 | 9 | 52 % |
| `CB` | 76.0 % | 36.0 % | 0.51 | 4 | 45 % |
| `B` | 76.0 % | 26.3 % | 0.40 | 24 | 55 % |

- **P21 fails**: the sentences score 5.0 points below all pages (criterion: within 3).
- **P22 fails**: the kept pages score 4.3 points below.
- **P24 fails**: the path check. On the 300 questions of the 2026-09-25 triage run, `all` through
  the CLI scored 74.7 % where the Batch API scored 67.7 % on the same prompts; the two replies
  score the same on 89 % of questions. Numbers from the two paths are not interchangeable.

## Why the registered score may not measure the question

The score counts a reply as correct when the normalised gold answer appears inside it. Through
the CLI there is no `max_tokens`; the API run capped replies at 60 tokens. Haiku's replies grow
with the context it gets: median 30 words from ten pages, 9 from the kept pages, 4 from the
kept sentences. A long reply collects the answer by containment. Exact match runs the other
way: 20 % from all pages, 33 % from the kept pages, 36 % from the kept sentences
(`diagnostics.json`). Read descriptively, the kept text may answer as well or better; that is
a hypothesis, not a result. The registered verdict of this run stays negative.

## Second run (`prereg-short.md`): the answer length controlled

The same arms and questions with the reply forced into one short field (`--json-schema`
`{"answer": string}`), registered before any of its calls. It is not independent of the first
run: the questions and kept sets were seen.

**Result: the sentences answer as well as the pages** (P21s, P22s and P24s hold).

| input | correct (registered score) | exact match | token F1 | text kept |
|---|---|---|---|---|
| `all` | 70.0 % | 55.3 % | 0.740 | 100 % |
| `C` | **71.0 %** | 56.3 % | 0.737 | 34 % |
| `CB` | **70.7 %** | 56.3 % | 0.740 | 22 % |
| `B` | 69.0 % | 55.7 % | 0.736 | 35 % |

- **P21s holds**: sentences 70.7 % against all pages 70.0 %.
- **P22s holds**: kept pages 71.0 %.
- These are the numbers the cache replays. The live run printed each arm within one question of
  them (69.7 / 70.7 / 71.0 / 69.3 %): when two arms shared a prompt (an arm that keeps
  everything repeats `all`'s), the live run could ask it twice at once and get two answers,
  and the cache keeps one. Every criterion holds under both.
- **P24s holds**: through the CLI, `all` on the 2026-09-25 questions scored 67.0 %, where the
  Batch API scored 67.7 % on the same prompts. With the reply length controlled, the two paths
  agree, which the first run's 74.7 % did not.

With a short answer the four inputs are within 2 points of each other on every score, and
the kept pages score highest, by a margin well inside the noise of 300
questions (a difference of 1 point is 3 questions). The claim is equality, not gain.

The input-token share of the kept arms (58 % to 65 % of `all`) is higher than the text share
(22 % to 35 %) because each session carries the same fixed prefix and structured-output turn.

## Cost and reproducing

First run: 1,500 prompts (1,406 distinct: an arm that keeps everything repeats `all`'s prompt),
4.46 USD at list price against the subscription. Sessions are cached in `fixtures/cli/`.

```bash
python benchmarks/chunks/answers.py --hotpot HOTPOT.jsonl            # first run, from the cache
python benchmarks/chunks/answers.py --short --hotpot HOTPOT.jsonl    # second run, from the cache
```
