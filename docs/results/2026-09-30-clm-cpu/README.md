# CLM-8B beside Jev on sanchopanza's benches, on a CPU (2026-09-30)

**What was asked.** Can an open model of the same family (CLM-8B, Contrastive-LM, Apache-2.0,
self-hosted behind `clm-serve`) stand in for Jev on the decision points sanchopanza ships?
Same 224 cases (`benches/core.jsonl`, `safety.jsonl`, `retrieval.jsonl`, `steerability.jsonl`),
same policies and thresholds, through the `clm` provider (`bench_clm.py`, one case at a time).
Free: everything runs on this PC.

**Answer: not zero-shot.** On every point where both could be compared CLM agrees with the
labels far less often than Jev, and its probabilities do not separate the classes. Where it
decides at all on the citation points, it is right, but it decides on a fifth of the cases.

## How it ran, and why it is not the reference setup

- **The encoder is not CLM's reference.** CLM expects `vllm serve Qwen/Qwen3-8B --runner
  pooling` on an NVIDIA GPU. This PC has an AMD RX 5700 XT, which vLLM does not run on, so
  `emb_server.py` serves the same weights, unquantised, with `transformers` on the CPU in
  **float32** (bfloat16 was ten times slower), and returns the last token's final hidden state,
  as the reference does. Same numbers up to float rounding is the claim; it is not proven.
- **The model card's own example is not reproduced exactly.** "My invoice was charged twice"
  gives `department = billing` at **0.988 here against 0.939 published** (`clm_probe.py`,
  rerun on 2026-09-30). Same answer, a different probability: the encoder path changes the
  numbers, so everything below is "CLM on this encoder", not CLM as published.
- **The translation is not the suspect.** sanchopanza's `clm` provider was checked against
  CLM's official client on the same requests (indagis-2b, 2026-09-30) and sends the same
  thing. The question wording is sanchopanza's, written for Jev.
- **Zero-shot.** CLM ships heads that can be fine-tuned per question; none were trained. Jev
  is also used zero-shot here, but it is the model these questions and thresholds were tuned
  on, so the comparison favours Jev by construction.
- **Two runs.** The first (`bench-clm`) is void: the provider's default 10 s timeout cut four
  points. This is the second, with `timeout_s=1800`. Median latency 3.6-31 s a decision
  (Ryzen 5 7500F); not comparable with Jev's ~250 ms or with CLM's GPU figures. The 0 ms
  latencies in `routing` and `search` are the server's vector cache, warmed by the void first
  run: fresh servers gave the same predictions for `rt-01` and `se-01` in 37 s and 46 s.

## Per point (`clm-summary.md`, `jev-summary.md`, same cases)

Agreement is over the cases each model decided; coverage is how many it decided.

| Point | n | CLM agreement | CLM coverage | Jev agreement | Jev coverage |
|---|---|---|---|---|---|
| injection | 28 | 12/28 (43 %) | 100 % | 27/28 (96 %) | 100 % |
| unsourced | 22 | 11/22 (50 %) | 100 % | 21/22 (95 %) | 100 % |
| search | 18 | 6/18 (33 %) | 100 % | 17/18 (94 %) | 100 % |
| triage | 16 | 7/16 (44 %) | 100 % | 14/16 (88 %) | 100 % |
| routing | 20 | 3/20 (15 %) | 100 % | 14/20 (70 %) | 100 % |
| command (model part) | 15 | 1/15 (7 %) | 47 % | 15/15 (100 %) | 47 % |
| citation | 20 | 3/4 (75 %) | 20 % | 18/18 (100 %) | 90 % |
| numeric_citation | 24 | 5/5 (100 %) | 21 % | 22/22 (100 %) | 92 % |

`command`: the code deny-list decides 17 of the 32 cases before any model is asked, the same in
both runs.

| Binary point | CLM AUC | CLM ECE | Jev AUC | Jev ECE |
|---|---|---|---|---|
| injection | 0.38 | 0.571 | 1.00 | 0.037 |
| unsourced | 0.28 | 0.494 | 1.00 | 0.082 |
| command | - | 0.676 | - | 0.058 |

What the numbers look like from inside: on `injection` CLM gives p >= 0.998 to every case,
benign ones included (in-13, benign, 0.99997 on a fresh server); on `unsourced` every case is
under 0.24, so an AUC below 0.5 is an order among near-constant values, not an inverted
signal. `routing` answers `default` on all 20; `search` answers `full` on 16 of 18.

**Not compared.** The Jev run is a replay of recorded answers, and it holds none for
`redundant_page` and `steerability` (0 ms, the policy's default). CLM's own numbers there:
`redundant_page` 10/16 with AUC 0.28, `steerability` 14/28, pair accuracy at chance.

## What this does and does not say

- It says that CLM, zero-shot, on this encoder, with questions written for Jev, cannot replace
  Jev at sanchopanza's thresholds. A deployment that wants an open model today should budget for
  training CLM's heads on its own labelled cases, which sanchopanza's benches already are.
- It does not say CLM is a weak model. Its GPU encoder was not run, the heads were not
  trained, and the questions were not reworded for it.
- The provider works: requests go out, answers come back in Jev's wire format and the policies
  consume them. `clm` stays in the provider table as "runs; zero-shot quality measured low".
