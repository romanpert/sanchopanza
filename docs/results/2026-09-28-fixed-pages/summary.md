# Fetch-heavy A/B, fixed document sequence

9 pairs, 173 documents walked per arm, lever `pages`.

Dropped: 81 by triage, 0 as redundant, of 173 documents served; 2042 passages removed from documents that stayed.

| | bare | squire | paired ratio [95 %] |
|---|---|---|---|
| Input tokens | 500030 | 102660 | -79.5% [-86.5%, -72.9%] |
| Cost USD | 2.40216 | 0.595036 | -75.2% [-82.9%, -68.0%] |
| Correct | 9/9 | 9/9 | lower bounds 0.701 / 0.701 |

The squire's own cost: 0.094039 USD. **Read the correctness row before the cost row**: a cheaper arm that answers fewer questions is measuring the cost of not delivering, which this project has mistaken for a saving twice.
