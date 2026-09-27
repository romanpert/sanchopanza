# Fetch-heavy A/B, fixed document sequence

10 pairs, 193 documents walked per arm, lever `redundancy`.

Dropped: 0 by triage, 4 as redundant, 4 of 193 served.

| | bare | squire | paired ratio [95 %] |
|---|---|---|---|
| Input tokens | 342042 | 329949 | -3.5% [-12.1%, +0.0%] |
| Cost USD | 0.692604 | 0.678887 | -2.0% [-10.1%, +1.5%] |
| Correct | 9/10 | 9/10 | lower bounds 0.596 / 0.596 |

The squire's own cost: 0.009549 USD. **Read the correctness row before the cost row**: a cheaper arm that answers fewer questions is measuring the cost of not delivering, not a saving.
