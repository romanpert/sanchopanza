# After the specific-gate fix and the threshold split

Cases: 291 - decision calls: 291 - input tokens: 210049 - cost: 0.0088 USD

| Point | n | Coverage | Agreement when deciding | Wilson 95 % | Median latency |
|---|---|---|---|---|---|
| memory_collision | 16 | 100% | 14/16 = 88% | [64%, 97%] | 235 ms |
| memory_write | 100 | 100% | 88/100 = 88% | [80%, 93%] | 250 ms |
| recall | 50 | 100% | 50/50 = 100% | [93%, 100%] | 250 ms |
| redundant_page | 125 | 100% | 116/125 = 93% | [87%, 96%] | 250 ms |

| Binary point | n | Correct at 0.5 | AUC | Brier | ECE |
|---|---|---|---|---|---|
| memory_write | 100 | 92/100 | 0.98 | 0.107 | 0.183 |
| recall | 50 | 50/50 | 1.00 | 0.007 | 0.070 |
| redundant_page | 125 | 120/125 | 1.00 | 0.048 | 0.153 |

## Agreement by confidence band

| Band | n | Agreement |
|---|---|---|
| 0.00-0.40 | 68 | 46/68 = 68% |
| 0.40-0.60 | 41 | 41/41 = 100% |
| 0.60-0.75 | 42 | 41/42 = 98% |
| 0.75-0.90 | 65 | 65/65 = 100% |
| 0.90-1.00 | 75 | 75/75 = 100% |

## Calibration by primitive (declared confidence vs. agreement)

| Primitive | n | Agreement | Mean confidence | ECE |
|---|---|---|---|---|
| truth | 291 | 92% | 0.64 | 0.279 |
