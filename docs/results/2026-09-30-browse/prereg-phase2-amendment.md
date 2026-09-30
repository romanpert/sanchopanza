# Browse, Phase 2: amendment 1

Written 2026-09-30 while Phase 1 was running and before any Phase 2 session was spawned.

Sizing the 60 registered Phase 2 steps (20 per split, file order) found three FULL prompts past
150,000 characters (the largest about 81,000 tokens). At list price and with the cache write
that `claude -p` makes, those sessions cost about 0.30 USD, past the registered cap of 0.25 USD
per session, and would have counted as FULL failures for a reason that has nothing to do with
choosing the element.

Changed: the per-session cap is 0.60 USD. Unchanged: the 6.00 USD ceiling for the phase, the
arms, the steps, the prompt, the metric and the decision rule. A session that still fails is
reported per arm and counted as wrong, as registered.

The prompt, fixed now: the system prompt is `SYSTEM` in `benchmarks/browse/answers.py`; the user
prompt is the goal, the previous actions (one per line, or "(none)"), and the element lines
numbered from 1, then "Which element should be acted on next? Reply with its number." The reply
schema is `{"element": integer}`. TOP shows the JEV arm's first 20 elements in rank order; FULL
shows every element in page order.
