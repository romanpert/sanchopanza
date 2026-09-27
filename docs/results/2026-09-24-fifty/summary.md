# Fifty cases per binary point

Cases: 212 - decision calls: 212 - input tokens: 143338 - cost: 0.0060 USD

| Point | n | Coverage | Agreement when deciding | Wilson 95 % | Median latency |
|---|---|---|---|---|---|
| extract_gate | 34 | 100% | 30/34 = 88% | [73%, 95%] | 250 ms |
| goal_met | 36 | 100% | 34/36 = 94% | [82%, 98%] | 250 ms |
| memory_write | 34 | 100% | 26/34 = 76% | [60%, 88%] | 250 ms |
| recall | 36 | 100% | 36/36 = 100% | [90%, 100%] | 250 ms |
| redundant_page | 34 | 100% | 26/34 = 76% | [60%, 88%] | 250 ms |
| repeats_check | 38 | 100% | 38/38 = 100% | [91%, 100%] | 250 ms |

Agreement is scored under the policy in force on 2026-09-24, with `redundant_page` on the
0.80 knob it shared with the search point: 190/212. Under the 0.3.0 policy it is 197/212
(`redundant_page` 33/34), in `docs/results/2026-09-24-fifty-v2/summary.md`. The loop points speak only from
`Thresholds.saturated` = 0.70, so `gm-19` (p 0.66, true) stays silent and `rp-37` (p 0.50,
false) raises no alarm. The "Correct at 0.5" column below reads the same probabilities at a
plain 0.5 cut (35/36 and 37/38 for the loop points): the first measures the policy, the second
the model's ordering. The band and primitive tables count agreement under the policy.

| Binary point | n | Correct at 0.5 | AUC | Brier | ECE |
|---|---|---|---|---|---|
| extract_gate | 34 | 30/34 | 0.97 | 0.071 | 0.073 |
| goal_met | 36 | 35/36 | 0.99 | 0.038 | 0.109 |
| memory_write | 34 | 31/34 | 0.99 | 0.095 | 0.227 |
| recall | 36 | 36/36 | 1.00 | 0.008 | 0.076 |
| redundant_page | 34 | 33/34 | 1.00 | 0.035 | 0.139 |
| repeats_check | 38 | 37/38 | 1.00 | 0.030 | 0.133 |

## Agreement by confidence band

| Band | n | Agreement |
|---|---|---|
| 0.00-0.40 | 24 | 9/24 = 38% |
| 0.40-0.60 | 26 | 20/26 = 77% |
| 0.60-0.75 | 33 | 32/33 = 97% |
| 0.75-0.90 | 81 | 81/81 = 100% |
| 0.90-1.00 | 48 | 48/48 = 100% |

## Calibration by primitive (declared confidence vs. agreement)

| Primitive | n | Agreement | Mean confidence | ECE |
|---|---|---|---|---|
| truth | 212 | 90% | 0.72 | 0.176 |
