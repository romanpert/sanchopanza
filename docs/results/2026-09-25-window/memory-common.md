| batch | policy | agree | stored what should be skipped (costly) | skipped what should be stored | no answer |
|---|---|---|---|---|---|
| new (48) | shipped | 25 | 3 | 20 | 0 |
| new (48) | shipped_on_4q | 24 | 3 | 21 | 0 |
| new (48) | P1 | 45 | 1 | 2 | 0 |
| new (48) | P2 | 27 | 0 | 21 | 0 |
| new (48) | P3 | 45 | 0 | 3 | 0 |
| new (48) | P4 | 46 | 0 | 2 | 0 |
| new2 (36) | shipped | 23 | 1 | 12 | 0 |
| new2 (36) | shipped_on_4q | 23 | 1 | 12 | 0 |
| new2 (36) | P1 | 28 | 8 | 0 | 0 |
| new2 (36) | P2 | 23 | 1 | 12 | 0 |
| new2 (36) | P3 | 32 | 3 | 1 | 0 |
| new2 (36) | P4 | 33 | 3 | 0 | 0 |
| new3 (24) | shipped | 12 | 0 | 12 | 0 |
| new3 (24) | shipped_on_4q | 12 | 0 | 12 | 0 |
| new3 (24) | P1 | 20 | 3 | 1 | 0 |
| new3 (24) | P2 | 12 | 0 | 12 | 0 |
| new3 (24) | P3 | 22 | 0 | 2 | 0 |
| new3 (24) | P4 | 22 | 0 | 2 | 0 |
| old (100) | shipped | 70 | 7 | 23 | 0 |
| old (100) | shipped_on_4q | 70 | 7 | 23 | 0 |
| old (100) | P1 | 86 | 9 | 5 | 0 |
| old (100) | P2 | 70 | 6 | 24 | 0 |
| old (100) | P3 | 88 | 7 | 5 | 0 |
| old (100) | P4 | 88 | 7 | 5 | 0 |

New batches by family (agree / 12):

| family | shipped | P1 | P2 | P3 | P4 |
|---|---|---|---|---|---|
| A instructions | 0 | 12 | 0 | 11 | 12 |
| B general knowledge | 9 | 12 | 12 | 12 | 12 |
| C findings | 4 | 10 | 3 | 10 | 10 |
| D transient | 12 | 11 | 12 | 12 | 12 |
| E pointers | 12 | 7 | 12 | 12 | 12 |
| F instructions | 0 | 12 | 0 | 11 | 12 |
| H verbatim of a held document | 11 | 9 | 11 | 9 | 9 |
| E2 pointers | 12 | 9 | 12 | 12 | 12 |
| F2 instructions | 0 | 11 | 0 | 10 | 10 |

Pre-registered criterion on the new batch: P1 45 vs shipped 25 agreement, costly errors 1 vs 3: **PASSES**.
Pre-registered criterion for P3 on memory-f: pointers 12 vs 7, instructions kept 11 vs 12, costly 3 vs 8: **FAILS**.
Pre-registered criterion for P4 on memory-g: instructions kept 10 vs 11, pointers stored 0 vs 3, costly 0 vs 3: **FAILS**.
