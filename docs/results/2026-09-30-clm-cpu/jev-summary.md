# Bench results

Cases: 224 - decision calls: 207 - input tokens: 107732 - cost: 0.0045 USD

| Point | n | Coverage | Agreement when deciding | Wilson 95 % | Median latency |
|---|---|---|---|---|---|
| citation | 20 | 90% | 18/18 = 100% | [82%, 100%] | 266 ms |
| command | 32 | 47% | 15/15 = 100% | [80%, 100%] | 0 ms |
| injection | 28 | 100% | 27/28 = 96% | [82%, 99%] | 264 ms |
| numeric_citation | 24 | 92% | 22/22 = 100% | [85%, 100%] | 250 ms |
| redundant_page | 16 | 100% | 10/16 = 62% | [39%, 82%] | 0 ms |
| routing | 20 | 100% | 14/20 = 70% | [48%, 85%] | 272 ms |
| search | 18 | 100% | 17/18 = 94% | [74%, 99%] | 258 ms |
| steerability | 28 | 100% | 14/28 = 50% | [33%, 67%] | 0 ms |
| triage | 16 | 100% | 14/16 = 88% | [64%, 97%] | 257 ms |
| unsourced | 22 | 100% | 21/22 = 95% | [78%, 99%] | 250 ms |

| Binary point | n | Correct at 0.5 | AUC | Brier | ECE |
|---|---|---|---|---|---|
| command | 15 | 15/15 | nan | 0.005 | 0.058 |
| injection | 28 | 28/28 | 1.00 | 0.007 | 0.037 |
| redundant_page | 16 | 10/16 | 0.50 | 0.375 | 0.375 |
| unsourced | 22 | 21/22 | 1.00 | 0.030 | 0.082 |

`command`: the code deny-list fired on 17 cases, 17 of them labelled dangerous; code or model together: 32/32 correct.

## Agreement by confidence band

| Band | n | Agreement |
|---|---|---|
| 0.00-0.40 | 5 | 1/5 = 20% |
| 0.40-0.60 | 7 | 2/7 = 29% |
| 0.60-0.75 | 4 | 3/4 = 75% |
| 0.75-0.90 | 24 | 24/24 = 100% |
| 0.90-1.00 | 163 | 142/163 = 87% |

## Calibration by primitive (declared confidence vs. agreement)

| Primitive | n | Agreement | Mean confidence | ECE |
|---|---|---|---|---|
| choice | 40 | 100% | 0.98 | 0.019 |
| score | 20 | 70% | 0.72 | 0.168 |
| truth | 143 | 83% | 0.93 | 0.118 |
