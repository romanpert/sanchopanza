# Where arm A's tokens went, and what phase B actually saw (exploratory)

**Exploratory.** Written before the pre-registration of the next iteration, on data already
published in aggregate in `docs/results/2026-09-28-context-e2e/`. Nothing here was
registered in advance, nothing ran a model, used the network or a key. It reads the saved
transcripts and result JSON under `~/.cache/sanchopanza/context-e2e/` (arm A:
`runs-r2/<task>/A/`, arm N: `runs/<task>/N/` plus `runs/<task>/A/result.json`) and writes
`attribution.json`. Paths in the output are relative to that folder.

    python docs/results/2026-09-28-context-lean/exploratory/attribution.py

## Main finding: the masked history did not reach the model in phase B

Phase B runs as `claude -p --resume`. Claude Code rebuilds the history from the `parentUuid`
chain of phase B's prompt and cuts it at the compact boundary's `logicalParentUuid`.

- **N, 12 of 12**: the cut entry is on the chain. Phase B starts from the summary (first
  phase-B call 43.4k tokens on average).
- **A, 0 of 12**: the cut entry is not on the chain. The copies of the verbatim-kept tool
  results that were written after the boundary keep the `parentUuid` of the *original*
  assistant entries. In t01, entry 243's parent is the original entry 129. So the chain runs
  back through the original, unmasked phase A to the first prompt. It holds 259 original
  tool results and **0 stubs** across the 12 tasks. The file does contain 139 stubs after the
  boundary, but they are not on the chain.
- **The token counts agree.** First phase-B context: observed 55,317 on average. The
  unmasked prediction is 56,500 minus about 1,453 of phase-A thinking, which is stripped on
  resume, so about 55,050. The masked prediction is 49,742. In every task the observation
  sits within 0.35k of the unmasked estimate and 4-7k above the masked one, and that gap
  grows with the characters the stubs replaced.

So in rounds 2 and 3, arm A's phase B effectively ran **without compaction**. It had the
whole phase-A history, with thinking stripped, plus recall. "12/12 against 6/12" compares
**no compaction plus recall** against the native summary. It is not masking against
summary. The published README's "why it worked" section rests on the saved file, not on
what the model received. This comes from reading the evidence and was not tested live.
Checking it would need the request itself, for example through a logging proxy on
`ANTHROPIC_BASE_URL`.

## Numbers (12 tasks per arm; Haiku 4.5 list price, cache writes at the 1-hour rate)

| | A | N |
|---|---|---|
| input tokens, all phases (transcript; result JSON) | 13,140,479; 13,153,067 | 11,583,174; 11,595,762 |
| USD (transcript; result JSON) | 3.343; 3.356 | 2.942; 2.956 |
| phase A: calls, input tokens, cache-read share | 193, 9.19M, 96.2 % | 143, 6.96M, 94.9 % |
| compaction call, input tokens | 0 | 0.68M |
| phase B: calls, input tokens, cache-read share | 62, 3.95M, 88.2 % | 82, 3.94M, 93.7 % |
| last phase-A call / first phase-B call context, mean | 55,519 / 55,317 | 55,560 / 43,361 |
| re-reads of phase-A files in phase B | 1 | 72 |
| largest tool result, chars | 2,468 | 14,499 (t08, N; no gate in N) |

The per-call sums match the result JSON to within 0.1 % in tokens and 0.4 % in USD. The
small remainder comes from calls that are not in the transcript. Cache writes are 1-hour
(`ephemeral_1h`), billed at 2x input. With that rate the per-call sums reproduce `costUSD`.

**Where A's extra 1.56M tokens came from:**

- **Phase A: +2.24M.** Three A sessions (t06, t07, t09) made 23-26 calls against 11-12 for
  the same 22-25 tool uses: they read one file per call where the others batched. Those
  three tasks account for 1.84M. That is run-to-run variance in phase A, which is not paired
  across arms for t01-t06.
- **Compaction and phase B: -0.68M.** A spent 3.95M. N spent 0.68M on the summary call
  plus 3.94M in phase B. Recall accounts for 0.35M of A's phase B.

**Recall.** There were 64 injections (11 on the prompt, 53 on tool calls), 297,710 chars.
**All of them fell in phase B**: the archive exists only after compaction. The published
README says "in both phases", which is not right. A regression of context growth gives 0.39
tokens per injected char, so the injections come to about 116k tokens. Each is written once
(116k cache-write tokens) and then read 236k times. Counterfactual input totals (USD):

| A as run | A, prompt recall only | A, no recall | N |
|---|---|---|---|
| 13.14M (3.343) | 12.81M (3.099) | 12.79M (3.087) | 11.58M (2.942) |

Tool-call recall is 93 % of recall's token cost. These are mechanical estimates: the agent
might have acted differently without it.

## Did any successful A task use a recall injection's content?

**No, not as the only source.** The release token, probe code and tolerance were in context
before first use in 12 of 12 tasks, both as verbatim kept tool results and in the kept
assistant text. For the window constant (`GRACE_WINDOW_DAYS` and its module):

- *saved-file view* (masked copies only): kept 2, recall only 4 (t04, t05, t07, t08), a
  phase-B grep that recall also had 2, unexplained 4 (t02, t06, t09, t10: the agent quotes
  a value found only in a stubbed Read);
- *resumed-chain view* (what the model received): kept 11, phase-B tool result 1 (t12).

The four "unexplained" cases are explained by the unmasked chain. That also means the four
"recall only" cases had the value in context anyway. Tool results never exceeded 2,468 chars
in A, so the arrival gate had nothing to cut.
