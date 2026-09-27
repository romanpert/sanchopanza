# Fifty-case bench under the 0.3.0 policy

Cases: 212 - decision calls: 212 - input tokens: 143338 - cost: 0.0060 USD

| Point | n | Coverage | Agreement when deciding | Wilson 95 % | Median latency |
|---|---|---|---|---|---|
| extract_gate | 34 | 100% | 30/34 = 88% | [73%, 95%] | 250 ms |
| goal_met | 36 | 100% | 34/36 = 94% | [82%, 98%] | 250 ms |
| memory_write | 34 | 100% | 26/34 = 76% | [60%, 88%] | 242 ms |
| recall | 36 | 100% | 36/36 = 100% | [90%, 100%] | 250 ms |
| redundant_page | 34 | 100% | 33/34 = 97% | [85%, 99%] | 233 ms |
| repeats_check | 38 | 100% | 38/38 = 100% | [91%, 100%] | 250 ms |

Replayed from `fixtures/new-points-50-v2.jsonl`; these are the figures of paper Sections 5.10
and 5.13, and `tests/test_fifty_benches.py` pins them. Agreement is scored under the shipped
policy, 197/212. The loop points speak only from `Thresholds.saturated` = 0.70, so `gm-19`
(p 0.66, true) stays silent and `rp-37` (p 0.50, false) raises no alarm. The "Correct at 0.5"
column below reads the same probabilities at a plain 0.5 cut, 202/212 (35/36 and 37/38 for the
loop points): the first measures the policy, the second the model's ordering. The band and
primitive tables count agreement under the policy.

| Binary point | n | Correct at 0.5 | AUC | Brier | ECE |
|---|---|---|---|---|---|
| extract_gate | 34 | 30/34 | 0.97 | 0.071 | 0.073 |
| goal_met | 36 | 35/36 | 0.99 | 0.038 | 0.109 |
| memory_write | 34 | 31/34 | 0.99 | 0.091 | 0.223 |
| recall | 36 | 36/36 | 1.00 | 0.009 | 0.077 |
| redundant_page | 34 | 33/34 | 1.00 | 0.040 | 0.146 |
| repeats_check | 38 | 37/38 | 1.00 | 0.030 | 0.133 |

## Agreement by confidence band

| Band | n | Agreement |
|---|---|---|
| 0.00-0.40 | 28 | 15/28 = 54% |
| 0.40-0.60 | 23 | 22/23 = 96% |
| 0.60-0.75 | 31 | 30/31 = 97% |
| 0.75-0.90 | 83 | 83/83 = 100% |
| 0.90-1.00 | 47 | 47/47 = 100% |

## Calibration by primitive (declared confidence vs. agreement)

| Primitive | n | Agreement | Mean confidence | ECE |
|---|---|---|---|---|
| truth | 212 | 93% | 0.72 | 0.210 |
