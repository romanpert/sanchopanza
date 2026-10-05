# Memory v8.3: the supersession check, asked as "did the person ask for its opposite?"

Before a confirmed send-back, memory v8.2 asked one Choice: does something said since *replace*
the rule? On 37 recorded send-backs it suppressed none, the two real ones included. In those
cases the person asks for something the old rule forbids without saying that the rule changed.

Bench: `benchmarks/memory_carry/supersede_bench.py`, with the cases in `supersede_cases.py`. It
holds 98 cases, each labelled by hand with a one-line reason, and was sealed in bc08d38 before
any call:

- 27 positives: 3 real send-backs, 5 real contradiction pairs, the 8 stale scenes (rule A, with
  A' stored since) and 11 written cases.
- 66 negatives: 24 carry rules against their own session-2 prompt, 4 real send-backs, 20 real
  restatements or refinements, the 8 stale scenes without A', and 10 written cases.
- 5 ambiguous, reported apart.

Real texts never enter the repository. Real cases are stored as hashes and resolved from the
local store. A seeded draw held out one third of each family and label.

The cut rule was fixed before the run. It is the first 0.05 step at least 0.01 above every dev
negative, and never below 0.5. The most dev positives wins, and the winner ships only with no
false suppression held out.

| variant | cut | dev suppressed (of 17) | dev highest negative | dev AUC | held out suppressed (of 10) | held out false | held out highest negative | held out AUC |
|---|---|---|---|---|---|---|---|---|
| a: v8.2 Choice | 0.50 | 10 | 0.24 | 0.94 | 7 | 0 | 0.18 | 0.97 |
| b: Truth on the request | 0.75 | 9 | 0.70 | 0.77 | 2 | 0 | 0.74 | 0.53 |
| **b+d: that Truth on the request and on each stored rule since** | **0.75** | **15** | 0.70 | 0.96 | **7** | **0** | **0.74** | 0.91 |
| c: contradicts / refines / unrelated Choice | 0.80 | 14 | 0.76 | 0.98 | 7 | 0 | 0.63 | 0.94 |

Shipped: b+d (`memory_rules.SUPERSEDE`, `SUPERSEDED_AT = 0.75`).

Not to be trusted yet:

- **Held out, b+d does no better than v8.2.** Both suppress 7 of 10.
- **The margin is 0.01.** One own carry rule ("make the errors more helpful" against "keep the
  wording") scored 0.74 against a cut of 0.75. The request half of b+d mistakes a task that would
  break the rule for a request for its opposite. The stored half is clean: negatives scored 0.15
  or less, positives 0.89 or more.
- **Real request-path positives: 3 of 8 caught** (v8.2: 0 of 8). All 3 were in dev. None of the
  3 held out was caught by any variant.
- The same agent wrote the labels, the written cases and the question.

Calls: 353 Jev decisions, 0.0105 USD (ledger in `~/.cache/sanchopanza/memory-supersede/`).
`b+d` was first scored on 29 cases because of a bug: cases with no stored rule were dropped
instead of scored as `b`. The bug was fixed before the selection was read, and the selection
rule did not change.
