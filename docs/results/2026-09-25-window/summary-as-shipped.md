### One task per session (97)

| arm | sessions | calls | misses | sessions with a miss | groups held at end | of those unused | schema tok x req | USD schema | USD misses | USD decisions | USD total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| full | 97 | 339 | 0 | 0 | 16.0 | 14.5 | 78,732 | 5.7750 | 0.0000 | 0.0000 | **5.7750** |
| search | 97 | 339 | 148 | 97 | 1.5 | 0.0 | 6,876 | 0.6517 | 0.2531 | 0.0000 | **0.9048** |
| once | 97 | 339 | 6 | 6 | 3.1 | 1.6 | 19,179 | 1.2881 | 0.0121 | 0.0131 | **1.3133** |
| once+pre | 97 | 339 | 3 | 3 | 4.0 | 2.5 | 21,151 | 1.4343 | 0.0070 | 0.0131 | **1.4544** |
| turns+pre | 97 | 339 | 3 | 3 | 4.0 | 2.5 | 21,151 | 1.4343 | 0.0070 | 0.0131 | **1.4544** |
| window+pre | 97 | 339 | 3 | 2 | 3.3 | 1.7 | 15,637 | 1.1188 | 0.0061 | 0.0637 | **1.1885** |
| window-noscan | 97 | 339 | 3 | 2 | 3.3 | 1.7 | 15,637 | 1.1188 | 0.0061 | 0.0520 | **1.1768** |

### Three tasks per session, three suites (40, seed 7)

| arm | sessions | calls | misses | sessions with a miss | groups held at end | of those unused | schema tok x req | USD schema | USD misses | USD decisions | USD total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| full | 40 | 484 | 0 | 0 | 16.0 | 11.4 | 264,492 | 3.8675 | 0.0000 | 0.0000 | **3.8675** |
| search | 40 | 484 | 183 | 40 | 4.6 | 0.0 | 54,245 | 1.0513 | 0.4091 | 0.0000 | **1.4604** |
| once | 40 | 484 | 122 | 38 | 5.6 | 1.1 | 76,428 | 1.3373 | 0.3169 | 0.0054 | **1.6596** |
| once+pre | 40 | 484 | 119 | 38 | 6.7 | 2.1 | 84,768 | 1.4643 | 0.3221 | 0.0054 | **1.7917** |
| turns+pre | 40 | 484 | 13 | 11 | 7.5 | 3.0 | 97,637 | 1.6501 | 0.0378 | 0.0137 | **1.7016** |
| window+pre | 40 | 484 | 6 | 3 | 7.8 | 3.3 | 95,727 | 1.6592 | 0.0154 | 0.0754 | **1.7500** |
| window-noscan | 40 | 484 | 6 | 3 | 7.8 | 3.3 | 95,727 | 1.6592 | 0.0154 | 0.0606 | **1.7352** |

### Modelled USD as the base context grows (replayed; decisions unchanged)

| arm | 4k single | 4k multi | 20k single | 20k multi | 50k single | 50k multi |
|---|---|---|---|---|---|---|
| full | 5.775 | 3.868 | 5.775 | 3.868 | 5.775 | 3.868 |
| search | 0.905 | 1.460 | 1.378 | 2.046 | 2.266 | 3.144 |
| once | 1.313 | 1.660 | 1.333 | 2.050 | 1.369 | 2.782 |
| once+pre | 1.454 | 1.792 | 1.464 | 2.173 | 1.482 | 2.887 |
| turns+pre | 1.454 | 1.702 | 1.464 | 1.743 | 1.482 | 1.821 |
| window+pre | 1.189 | 1.750 | 1.198 | 1.769 | 1.216 | 1.805 |
| window-noscan | 1.177 | 1.735 | 1.186 | 1.754 | 1.204 | 1.790 |

### Deriving `window_add` (derive half / report half, by task id hash)

Observe answers: 1830 to derive on, 2418 to report on; positives 3 / 13.

| target | derived cut | report: added | of those needed later | precision | Wilson low | recall |
|---|---|---|---|---|---|---|
| 50% | none clears it | | | | | |
| 70% | none clears it | | | | | |
| 80% | none clears it | | | | | |
| 90% | none clears it | | | | | |

