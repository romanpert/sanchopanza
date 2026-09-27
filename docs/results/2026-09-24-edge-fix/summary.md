# edge, with the direction gate read first

Cases: 96 - decision calls: 89 - input tokens: 54875 - cost: 0.0023 USD

| Point | n | Coverage | Agreement when deciding | Wilson 95 % | Median latency |
|---|---|---|---|---|---|
| edge | 50 | 76% | 31/38 = 82% | [67%, 91%] | 235 ms |
| extract_gate | 16 | 100% | 15/16 = 94% | [72%, 99%] | 242 ms |
| facts | 30 | 80% | 21/24 = 88% | [69%, 96%] | 250 ms |

| Binary point | n | Correct at 0.5 | AUC | Brier | ECE |
|---|---|---|---|---|---|
| extract_gate | 16 | 15/16 | 1.00 | 0.031 | 0.102 |

## Agreement by confidence band

| Band | n | Agreement |
|---|---|---|
| 0.00-0.40 | 2 | 1/2 = 50% |
| 0.40-0.60 | 1 | 1/1 = 100% |
| 0.60-0.75 | 6 | 4/6 = 67% |
| 0.75-0.90 | 14 | 12/14 = 86% |
| 0.90-1.00 | 55 | 49/55 = 89% |

## Calibration by primitive (declared confidence vs. agreement)

| Primitive | n | Agreement | Mean confidence | ECE |
|---|---|---|---|---|
| choice | 24 | 88% | 0.93 | 0.057 |
| truth | 54 | 85% | 0.88 | 0.103 |
