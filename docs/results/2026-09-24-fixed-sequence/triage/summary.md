# Fetch-heavy A/B, fixed document sequence

10 pairs, 193 documents walked per arm, lever `triage`.

Dropped: 170 by triage, 0 as redundant, 170 of 193 served.

| | bare | squire | paired ratio [95 %] |
|---|---|---|---|
| Input tokens | 342042 | 84685 | -75.2% [-86.8%, -63.9%] |
| Cost USD | 0.692444 | 0.188237 | -72.8% [-84.1%, -61.6%] |
| Correct | 10/10 | 6/10 | lower bounds 0.722 / 0.313 |

The squire's own cost: 0.010637 USD. **Read the correctness row before the cost row**: a cheaper arm that answers fewer questions is measuring the cost of not delivering, not a saving.
