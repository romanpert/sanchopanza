# Bench results

Cases: 65 - decision calls: 64 - input tokens: 76851 - cost: 0.0032 USD

Re-recorded after pseudonymization hardening (2026-09-28): the cases whose text concerned
pseudonymized persons were reworded and asked again; the figures below are re-derived.

| Point | n | Coverage | Agreement when deciding | Wilson 95 % | Median latency |
|---|---|---|---|---|---|
| dependency | 20 | 100% | 19/20 = 95% | [76%, 99%] | 546 ms |
| entity | 24 | 100% | 24/24 = 100% | [86%, 100%] | 250 ms |
| facts | 20 | 80% | 15/16 = 94% | [72%, 99%] | 250 ms |

| Binary point | n | Correct at 0.5 | AUC | Brier | ECE |
|---|---|---|---|---|---|
| dependency | 20 | 19/20 | 1.00 | 0.040 | 0.148 |
| entity | 24 | 24/24 | 1.00 | 0.006 | 0.064 |

## Agreement by confidence band

| Band | n | Agreement |
|---|---|---|
| 0.00-0.40 | 3 | 2/3 = 67% |
| 0.60-0.75 | 8 | 8/8 = 100% |
| 0.75-0.90 | 27 | 26/27 = 96% |
| 0.90-1.00 | 22 | 22/22 = 100% |

## Calibration by primitive (declared confidence vs. agreement)

| Primitive | n | Agreement | Mean confidence | ECE |
|---|---|---|---|---|
| choice | 16 | 94% | 0.90 | 0.041 |
| truth | 44 | 98% | 0.80 | 0.180 |

## Plan `plan-register`: 56 ordered pairs, 9 reference edges

- Raw (p >= 0.5): 20 edges, precision 40%, recall 89%, AUC 0.93; waves [['L1', 'L2'], ['L3', 'L4'], ['L5', 'L6', 'L7', 'L8']]
- After dag.py: 7 edges, precision 100%, recall 88% (closure 100% / 95%); waves [['L1', 'L2'], ['L3', 'L4'], ['L5'], ['L6'], ['L7'], ['L8']]; missing [('L2', 'L8')]
- Reference waves: [['L1', 'L2'], ['L3', 'L4'], ['L5'], ['L6'], ['L7'], ['L8']]
