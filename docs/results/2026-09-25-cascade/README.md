# A calibrated first stage in front of an LLM judge

Pre-registered in `prereg.md` (R-Judge and the Indagis register) and `prereg-codex.md`
(ATBench-Codex). The question: can a calibrated non-generative model be the first stage of a
permission or classification gate, the role a single-token Sonnet 4.6 pass plays in Claude
Code's auto mode, answering alone when confident and handing the rest to an LLM?

**The primary verdicts P1, P2 and P9 were not run.** They compare the cascade with
`claude-sonnet-5`. Its Message Batches sat unprocessed for over an hour and were cancelled
before any request ran, to keep the session inside its spending limit; running them costs
about 2.7 USD at batch prices (`run.py --submit sonnet`). Everything below comes from the arms
that returned: Jev, Haiku 4.5 and Opus 5 (Opus on R-Judge and the register only; it was a
secondary arm).

## Data

- **R-Judge** (EMNLP Findings 2024, github.com/Lordog/R-Judge at `83ce301`): 571 agent
  interaction records, human labels, 301 unsafe. The paper's best model, GPT-4o, 74.4 %.
- **Indagis defamation register**: 298 closed-vocabulary classifications, labels from a
  register reviewed before these questions existed.
- **ATBench-Codex** (arXiv 2604.14858, April 2026, Apache-2.0): 500 trajectories of a
  Codex-style coding agent with MCP tools, 250 unsafe. Published on the full set with the
  authors' own prompts: a guard model fine-tuned for it (AgentDoG-Qwen3-4B) 82.2 %,
  Qwen3.5-397B 76.6 %, Llama-3.3-70B 68.2 %, Llama-Guard-4-12B 64.6 %.

Neither dataset is redistributed. The question for R-Judge and ATBench-Codex is
`points/actions.QUESTION`, written and hashed before any record was read beyond its format.

## Alone

Accuracy over the cases each model answered; Jev in brackets on the same cases. A cancelled
request is not a wrong answer: 30 R-Judge and 13 register requests of the Opus batch were
cancelled before they ran.

| | R-Judge | register | ATBench-Codex |
|---|---|---|---|
| `jev-1.13.0` | 88.1 % (571) | 82.6 % (298) | 78.0 % (500) |
| `claude-haiku-4-5` | 72.5 % (571) [Jev 88.1] | 74.5 % (298) [82.6] | 73.8 % (500) [78.0] |
| `claude-opus-5` | **95.0 %** (541) [Jev 88.0] | **89.1 %** (285) [82.8] | not run |
| `claude-sonnet-5` | not run | not run | not run |

Every LLM arm answers the same question through the same forced-tool schema, one request per
case, no chain of thought: the analogue of a single-token first stage, not of a reasoning pass.
An LLM label is matched to the options after decoding escapes and folding accents and case
(`providers.llm.match_option`): before that fix Haiku lost 16 register labels it had right.

On R-Judge, with unsafe as the positive class (the rates auto mode reports), on answered cases:

| | false positives | false negatives |
|---|---|---|
| Jev | 13.7 % | 10.3 % |
| Haiku 4.5 | 49.3 % | 8.0 % |
| Opus 5 | 3.9 % | 6.0 % |

Jev's confidence sorts its own answers: on R-Judge, 99.3 % right on the 304 cases above
confidence 0.75 and 56.9 % on the 102 below 0.25; on ATBench-Codex, 90.8 % and 62.6 %.

## Cascaded, on the held-out half

tau is derived on the derivation half as the pre-registration fixes it.

| X | set | tau | cascade | X alone | difference [95 %] | cost of X alone | registered test |
|---|---|---|---|---|---|---|---|
| Haiku 4.5 | R-Judge | 0.00 | 86.5 % | 67.5 % | +19.0 [+13.5, +24.5] | 2 % | passes |
| Haiku 4.5 | register | 0.45 | 84.9 % | 68.6 % | +16.3 [+9.9, +23.3] | 10 % | passes |
| Haiku 4.5 | ATBench-Codex | 0.00 | 78.5 % | 72.7 % | +5.8 [+0.4, +11.6] | 3 % | passes |
| Opus 5 | R-Judge | 0.80 | 93.2 % | 93.2 % | 0.0 [0.0, 0.0] | 57 % | **fails, on cost** |
| Opus 5 | register | 0.85 | 89.0 % | 89.6 % | -0.6 [-3.1, +1.2] | 36 % | passes |

- **A cheap LLM is the worse first stage on all three sets.** Against Haiku the cascade barely
  escalates, because Jev alone is better, at 2 to 10 % of Haiku's cost.
- **Opus alone is better than Jev alone**, by 7 points on R-Judge and 6 on the register, and
  with a quarter of Jev's false positives on R-Judge. The cascade reaches Opus's accuracy on
  both sets. On R-Judge it does so at 57 % of Opus's cost on the registered split, over the 50 %
  registered: a fail. Over 500 random splits the median is 32 %, which is exactly why the
  split was fixed in advance, and why the fail stands.

## Contamination, stated

R-Judge is from 2024 and public on GitHub; any of these models may have seen it. ATBench-Codex
was published in April 2026. Jev's lead over Haiku holds on both, and is smaller on the newer
one (4.2 points against 15.6).

## Reproducing

```bash
python benchmarks/cascade/run.py --analyze --rjudge R-JUDGE-CLONE --register REGISTER.json
python benchmarks/cascade/run.py --submit sonnet ... --env-file PATH/TO/.env   # the primary arm, ~2.7 USD
SANCHOPANZA_RJUDGE=... SANCHOPANZA_REGISTER=... SANCHOPANZA_ATBENCH_CODEX=... python -m pytest tests/test_cascade_bench.py
```
