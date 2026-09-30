# CLM on CPU

Cases: 224 - decision calls: 207 - input tokens: 46673 - cost: 0.0000 USD

| Point | n | Coverage | Agreement when deciding | Wilson 95 % | Median latency |
|---|---|---|---|---|---|
| citation | 20 | 20% | 3/4 = 75% | [30%, 95%] | 4936 ms |
| command | 32 | 47% | 1/15 = 7% | [1%, 30%] | 0 ms |
| injection | 28 | 100% | 12/28 = 43% | [27%, 61%] | 5194 ms |
| numeric_citation | 24 | 21% | 5/5 = 100% | [57%, 100%] | 3616 ms |
| redundant_page | 16 | 100% | 10/16 = 62% | [39%, 82%] | 6546 ms |
| routing | 20 | 100% | 3/20 = 15% | [5%, 36%] | 0 ms |
| search | 18 | 100% | 6/18 = 33% | [16%, 56%] | 0 ms |
| steerability | 28 | 100% | 14/28 = 50% | [33%, 67%] | 27952 ms |
| triage | 16 | 100% | 7/16 = 44% | [23%, 67%] | 31414 ms |
| unsourced | 22 | 100% | 11/22 = 50% | [31%, 69%] | 16796 ms |

| Binary point | n | Correct at 0.5 | AUC | Brier | ECE |
|---|---|---|---|---|---|
| command | 15 | 1/15 | nan | 0.466 | 0.676 |
| injection | 28 | 12/28 | 0.38 | 0.571 | 0.571 |
| redundant_page | 16 | 10/16 | 0.28 | 0.324 | 0.290 |
| unsourced | 22 | 11/22 | 0.28 | 0.490 | 0.494 |

`command`: the code deny-list fired on 17 cases, 17 of them labelled dangerous; code or model together: 18/32 correct.

## Agreement by confidence band

| Band | n | Agreement |
|---|---|---|
| 0.00-0.40 | 23 | 3/23 = 13% |
| 0.40-0.60 | 11 | 2/11 = 18% |
| 0.60-0.75 | 8 | 5/8 = 62% |
| 0.75-0.90 | 17 | 11/17 = 65% |
| 0.90-1.00 | 113 | 51/113 = 45% |

## Calibration by primitive (declared confidence vs. agreement)

| Primitive | n | Agreement | Mean confidence | ECE |
|---|---|---|---|---|
| choice | 9 | 89% | 0.91 | 0.024 |
| score | 20 | 15% | 0.32 | 0.181 |
| truth | 143 | 43% | 0.89 | 0.480 |
