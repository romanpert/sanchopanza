### One task per session (97)

| arm | sessions | calls | misses | sessions with a miss | groups held at end | of those unused | schema tok x req | USD schema | USD misses | USD decisions | USD total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| full | 97 | 341 | 0 | 0 | 16.0 | 14.5 | 79,093 | 5.7820 | 0.0000 | 0.0000 | **5.7820** |
| search | 97 | 341 | 149 | 97 | 1.5 | 0.0 | 6,954 | 0.6547 | 0.2549 | 0.0000 | **0.9097** |
| once | 97 | 341 | 6 | 6 | 3.1 | 1.6 | 19,540 | 1.2952 | 0.0121 | 0.0131 | **1.3203** |
| once+pre | 97 | 341 | 3 | 3 | 4.0 | 2.5 | 21,512 | 1.4413 | 0.0070 | 0.0131 | **1.4614** |
| turns+pre | 97 | 341 | 3 | 3 | 4.0 | 2.5 | 21,512 | 1.4413 | 0.0070 | 0.0131 | **1.4614** |
| window+pre | 97 | 341 | 0 | 0 | 3.3 | 1.7 | 15,784 | 1.1216 | 0.0000 | 0.0639 | **1.1856** |
| window-noscan | 97 | 341 | 0 | 0 | 3.3 | 1.7 | 15,784 | 1.1216 | 0.0000 | 0.0522 | **1.1738** |

### Three tasks per session, three suites (40, seed 7)

| arm | sessions | calls | misses | sessions with a miss | groups held at end | of those unused | schema tok x req | USD schema | USD misses | USD decisions | USD total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| full | 40 | 488 | 0 | 0 | 16.0 | 11.3 | 266,243 | 3.8815 | 0.0000 | 0.0000 | **3.8815** |
| search | 40 | 488 | 186 | 40 | 4.7 | 0.0 | 55,312 | 1.0645 | 0.4165 | 0.0000 | **1.4810** |
| once | 40 | 488 | 124 | 38 | 5.7 | 1.0 | 77,605 | 1.3499 | 0.3222 | 0.0054 | **1.6774** |
| once+pre | 40 | 488 | 121 | 38 | 6.8 | 2.1 | 85,980 | 1.4771 | 0.3273 | 0.0054 | **1.8098** |
| turns+pre | 40 | 488 | 13 | 11 | 7.5 | 2.9 | 98,636 | 1.6581 | 0.0378 | 0.0137 | **1.7096** |
| window+pre | 40 | 488 | 0 | 0 | 7.8 | 3.2 | 96,938 | 1.6689 | 0.0000 | 0.0757 | **1.7446** |
| window-noscan | 40 | 488 | 0 | 0 | 7.8 | 3.2 | 96,938 | 1.6689 | 0.0000 | 0.0608 | **1.7297** |

### Modelled USD as the base context grows (replayed; decisions unchanged)

| arm | 4k single | 4k multi | 20k single | 20k multi | 50k single | 50k multi |
|---|---|---|---|---|---|---|
| full | 5.782 | 3.882 | 5.782 | 3.882 | 5.782 | 3.882 |
| search | 0.910 | 1.481 | 1.386 | 2.076 | 2.280 | 3.192 |
| once | 1.320 | 1.677 | 1.340 | 2.074 | 1.376 | 2.818 |
| once+pre | 1.461 | 1.810 | 1.471 | 2.197 | 1.489 | 2.923 |
| turns+pre | 1.461 | 1.710 | 1.471 | 1.751 | 1.489 | 1.829 |
| window+pre | 1.186 | 1.745 | 1.186 | 1.745 | 1.186 | 1.745 |
| window-noscan | 1.174 | 1.730 | 1.174 | 1.730 | 1.174 | 1.730 |

### Deriving `window_add` (derive half / report half, by task id hash)

Observe answers: 1843 to derive on, 2425 to report on; positives 5 / 8.

| target | derived cut | report: added | of those needed later | precision | Wilson low | recall |
|---|---|---|---|---|---|---|
| 50% | none clears it | | | | | |
| 70% | none clears it | | | | | |
| 80% | none clears it | | | | | |
| 90% | none clears it | | | | | |

