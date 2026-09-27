# memory_write to 100 and redundant_page to 125, with the threshold split only

Cases: 291 - decision calls: 291 - input tokens: 200849 - cost: 0.0084 USD

| Point | n | Coverage | Agreement when deciding | Wilson 95 % | Median latency |
|---|---|---|---|---|---|
| memory_collision | 16 | 100% | 14/16 = 88% | [64%, 97%] | 264 ms |
| memory_write | 100 | 100% | 72/100 = 72% | [63%, 80%] | 250 ms |
| recall | 50 | 100% | 50/50 = 100% | [93%, 100%] | 250 ms |
| redundant_page | 125 | 100% | 116/125 = 93% | [87%, 96%] | 235 ms |

| Binary point | n | Correct at 0.5 | AUC | Brier | ECE |
|---|---|---|---|---|---|
| memory_write | 100 | 86/100 | 0.95 | 0.126 | 0.164 |
| recall | 50 | 50/50 | 1.00 | 0.007 | 0.069 |
| redundant_page | 125 | 119/125 | 1.00 | 0.050 | 0.152 |

## Agreement by confidence band

| Band | n | Agreement |
|---|---|---|
| 0.00-0.40 | 76 | 38/76 = 50% |
| 0.40-0.60 | 31 | 31/31 = 100% |
| 0.60-0.75 | 41 | 40/41 = 98% |
| 0.75-0.90 | 64 | 64/64 = 100% |
| 0.90-1.00 | 79 | 79/79 = 100% |

## Calibration by primitive (declared confidence vs. agreement)

| Primitive | n | Agreement | Mean confidence | ECE |
|---|---|---|---|---|
| truth | 291 | 87% | 0.64 | 0.230 |
