# Fifty-case bench under the derived memory_write cut

Cases: 212 - decision calls: 212 - input tokens: 143338 - cost: 0.0060 USD

| Point | n | Coverage | Agreement when deciding | Wilson 95 % | Median latency |
|---|---|---|---|---|---|
| extract_gate | 34 | 100% | 30/34 = 88% | [73%, 95%] | 250 ms |
| goal_met | 36 | 100% | 34/36 = 94% | [82%, 98%] | 250 ms |
| memory_write | 34 | 100% | 29/34 = 85% | [70%, 94%] | 242 ms |
| recall | 36 | 100% | 36/36 = 100% | [90%, 100%] | 250 ms |
| redundant_page | 34 | 100% | 33/34 = 97% | [85%, 99%] | 233 ms |
| repeats_check | 38 | 100% | 38/38 = 100% | [91%, 100%] | 250 ms |

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
| 0.00-0.40 | 28 | 18/28 = 64% |
| 0.40-0.60 | 23 | 22/23 = 96% |
| 0.60-0.75 | 31 | 30/31 = 97% |
| 0.75-0.90 | 83 | 83/83 = 100% |
| 0.90-1.00 | 47 | 47/47 = 100% |

## Calibration by primitive (declared confidence vs. agreement)

| Primitive | n | Agreement | Mean confidence | ECE |
|---|---|---|---|---|
| truth | 212 | 94% | 0.72 | 0.224 |
