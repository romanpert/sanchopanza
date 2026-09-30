# The same 211 judgments, against Claude Opus 5.5

The substitution comparison of `2026-09-27-memory-write-cut/fifty` was made against Claude Opus 5.
Opus 5.5 has shipped since, at a lower price per token, so the same cases were asked again of
`claude-opus-5-5`, with the same literal questions, decision rules and system prompt
(`benchmarks/annotate.py`), one case per session, blind to the labels and to the evaluator.

## Result

On the 211 cases of the published comparison (the 212 minus `mw-32`, which Opus 5 left unlabelled):

| | Right, of 211 |
|---|---|
| `jev-1.13.0`, shipped policy | **200** |
| `jev-1.13.0`, plain 0.5 cut | 202 |
| `claude-opus-5-5`, effort `low` | **199** |
| `claude-opus-5`, effort `low` (2026-09-27) | 204 |

Opus 5.5 answered 211 of 212 cases in one word. `rd-46` got two sentences of reasoning instead,
twice, and counts as a miss. Counting it as right would give 200: **a tie with the shipped
policy**, not a win in either direction. Opus 5 is still the better judge on these cases, by 4.

**Cost.** List prices for `claude-opus-5-5` are 4.00 in / 20.00 out USD per MTok. Opus 5.5 cannot
turn thinking off (effort is the only control), so even at `low` it reasons before its one word.
With the same prompt size the Opus 5 run measured through the API (686 input tokens a case on
average), a judgment costs:

| | Per judgment | Per 1,000 | Against 28.4 millionths |
|---|---|---|---|
| Opus 5.5, no reasoning at all (floor) | 2,805 millionths | 2.81 USD | **99x** |
| Opus 5.5, median reasoning implied by the bill (24 tokens) | 3,226 millionths | 3.23 USD | 114x |

So: **the same accuracy as Opus 5.5 on these judgments, for about a hundredth of the price.**
The floor is the number to quote.

## How it was run, and what that changes

- Through our own evaluation harness: one isolated `claude -p` session per case (no tools, no
  settings, no MCP, our system prompt only), billed to a subscription, not through the Messages
  API. Every Opus 5.5 answer went through that path. The Opus 5 answers it is compared with went
  through the API, so the two Opus rows are not a controlled pair: a session can add framing of
  its own. The 211 prompts are byte-identical to the API run's.
- The session bill is not the API bill. Each session writes its prompt to a one-hour cache (2x the
  input price) and makes one small Haiku call of its own (about 0.001 USD). Total list-price spend
  was **2.63 USD** for 212 sessions; the API-equivalent cost above removes both and keeps only
  the input the API run measured plus the output the bill implies. `sessions-usage.jsonl` holds
  every session's tokens and list cost, without the prompts.
- Latency is not reported: sessions queued behind a concurrency gate, so their wall clock is not
  the model's.
- Effort `low`, one word, is close to the cheapest this model can be asked to do this, as it was
  for Opus 5. A realistic effort widens the ratio.

## Files

- `annotator-2.jsonl`: Opus 5.5's label per case (`null` for `rd-46`).
- `sessions-usage.jsonl`: per-session tokens and list cost as the CLI reported them.
- The evaluator's answers are `../2026-09-27-memory-write-cut/fifty/results.json`, unchanged.

Pinned by `tests/test_opus55_substitution.py`.
