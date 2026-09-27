# facts, edge and memory_collision to 50

Cases: 241 - decision calls: 233 - input tokens: 190855 - cost: 0.0080 USD

| Point | n | Coverage | Agreement when deciding | Wilson 95 % | Median latency |
|---|---|---|---|---|---|
| dependency | 20 | 100% | 20/20 = 100% | [84%, 100%] | 492 ms |
| edge | 50 | 74% | 28/37 = 76% | [60%, 87%] | 235 ms |
| entity | 24 | 100% | 24/24 = 100% | [86%, 100%] | 242 ms |
| extract_gate | 16 | 100% | 15/16 = 94% | [72%, 99%] | 242 ms |
| facts | 50 | 78% | 35/39 = 90% | [76%, 96%] | 250 ms |
| memory_collision | 50 | 100% | 46/50 = 92% | [81%, 97%] | 250 ms |
| memory_write | 16 | 100% | 16/16 = 100% | [81%, 100%] | 250 ms |
| recall | 14 | 100% | 14/14 = 100% | [78%, 100%] | 250 ms |

| Binary point | n | Correct at 0.5 | AUC | Brier | ECE |
|---|---|---|---|---|---|
| dependency | 20 | 20/20 | 1.00 | 0.035 | 0.142 |
| entity | 24 | 24/24 | 1.00 | 0.005 | 0.059 |
| extract_gate | 16 | 15/16 | 1.00 | 0.031 | 0.102 |
| memory_write | 16 | 16/16 | 1.00 | 0.072 | 0.223 |
| recall | 14 | 14/14 | 1.00 | 0.003 | 0.049 |

## Agreement by confidence band

| Band | n | Agreement |
|---|---|---|
| 0.00-0.40 | 11 | 9/11 = 82% |
| 0.40-0.60 | 3 | 3/3 = 100% |
| 0.60-0.75 | 13 | 10/13 = 77% |
| 0.75-0.90 | 53 | 50/53 = 94% |
| 0.90-1.00 | 136 | 126/136 = 93% |

## Calibration by primitive (declared confidence vs. agreement)

| Primitive | n | Agreement | Mean confidence | ECE |
|---|---|---|---|---|
| choice | 39 | 90% | 0.92 | 0.048 |
| truth | 177 | 92% | 0.85 | 0.075 |

## Plan `plan-register`: 56 ordered pairs, 9 reference edges

- Raw (p >= 0.5): 20 edges, precision 40%, recall 89%, AUC 0.94; waves [['L1', 'L2'], ['L3', 'L4'], ['L5', 'L6', 'L7', 'L8']]
- After dag.py: 7 edges, precision 100%, recall 88% (closure 100% / 95%); waves [['L1', 'L2'], ['L3', 'L4'], ['L5'], ['L6'], ['L7'], ['L8']]; missing [('L2', 'L8')]
- Reference waves: [['L1', 'L2'], ['L3', 'L4'], ['L5'], ['L6'], ['L7'], ['L8']]
