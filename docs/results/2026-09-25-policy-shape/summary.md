## memory_write, 100 cases, three raw probabilities

| policy | fitted on | hits | costly (store when skip) |
|---|---|---|---|
| shipped conjunction (0.70 / 0.70 / 0.75) | nothing | 72 | 5 |
| plain 0.5 cut on the weakest margin | nothing | 86 | 4 |
| one cut on the weakest margin, derived per fold | training folds | 89.6 | 6.4 |
| logistic regression on the three probabilities | training folds | 87.8 | 9.4 |

Cross-validation: 10-fold, 5 repeats, hits averaged per run of 100. Derived cuts across folds: min 0.44, median 0.45, max 0.45. Regression on all cases (bias, durable, specific, derivable): [-1.83, 2.54, 1.95, -2.71]. Wilson 95 % of the shipped accuracy: 0.625-0.799.

## Platt scaling, leave-one-out, on the deciding probability of each binary point

| point | n | ECE before | ECE after | Brier before | Brier after |
|---|---|---|---|---|---|
| memory_write | 34 | 0.223 | 0.027 | 0.091 | 0.032 |
| redundant_page | 34 | 0.146 | 0.018 | 0.04 | 0.004 |
| goal_met | 36 | 0.109 | 0.055 | 0.038 | 0.042 |
| repeats_check | 38 | 0.133 | 0.011 | 0.03 | 0.001 |
| extract_gate | 34 | 0.073 | 0.085 | 0.071 | 0.087 |
| recall | 36 | 0.077 | 0.002 | 0.009 | 0.0 |
