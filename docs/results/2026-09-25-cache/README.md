# Cost accounting in end-to-end benchmarks: where the cache breakpoint sits decides the ratios

Measured 2026-09-25 while tracing where the money of the end-to-end runs went. Two probes
(0.11 USD) and a free re-pricing of every recorded run
(`benchmarks/agentdojo/reprice_shared_prefix.py`, output `reprice.json`, `count_tokens`
only). `tests/test_cache_reprice.py` pins the figures below.

**The finding:** a benchmark that compares ways of presenting a tool catalog must share the
`tools` + `system` prefix between tasks the way a production harness does, or it charges the
arms with a fixed prefix for a cache write on every task. On the 74-tool catalog that moves
the window from 0.45-0.60x of `full`'s cost as run to an estimated 0.77-0.88x with the prefix
shared; on the 398-tool catalog the ordering holds.

## The mechanism

With top-level automatic caching only, the breakpoint sits on the last message, and **a cache
read can only land where an earlier request wrote a breakpoint**. A task can then read its own
earlier turns but never the `tools` + `system` prefix another task wrote: every task pays its
catalog as a cache write (1.25x input) instead of a read (0.1x).

Measured, 74-tool catalog, two tasks with different first messages, same prefix:

| breakpoint on `system` | task 2 cache write | task 2 cache read |
|---|---|---|
| no | 12,296 | 0 |
| yes | 86 | 12,211 |

Same result with `max_tokens: 0` requests and with normal ones. The end-to-end runs of
2026-09-25 used top-level automatic caching only: in `runs-10.jsonl`, the headline run, `full`
wrote at least 12,378 tokens in 38 of its 40 tasks - its prefix, again and again. The small
writes in `runs-10-parallel.jsonl` and in the wide run come from requests byte-identical to
recent ones (the same task re-run, or the twin process of the wide run), not from sharing
between tasks.

A production harness with a fixed catalog puts that breakpoint (Claude Code does). Without it,
the arms whose prefix does not depend on the request - `full` and `search` - are overcharged,
while the window, whose prefix depends on the groups each request opens, loses little. So a
missing breakpoint flatters the window. It is an instance of the rule "if a result favours
you, find whose cache it inherited".

## Re-priced, as an estimate

Every task after the first on the same prefix has its prefix tokens moved from the write price
to the read price, bounded by what the task actually wrote. `sancho` tasks are re-priced only
when their window matches an earlier task's (17-18 of 40). Concurrent cold starts are ignored
(a pre-warm removes them). This is an estimate from recorded usage, not a run.

| run | arm | USD as run | USD, shared prefix | x `full`, as run | x `full`, shared prefix |
|---|---|---|---|---|---|
| `runs-10` (74 tools) | full | 1.955 | 0.909 | 1.00 | 1.00 |
| | sancho | 0.888 | 0.798 | 0.45 | **0.88** |
| | search | 1.416 | 1.346 | 0.72 | **1.48** |
| `runs-10-parallel` | full | 1.261 | 0.889 | 1.00 | 1.00 |
| | sancho | 0.751 | 0.685 | 0.60 | **0.77** |
| wide (398 tools) | full | 5.854 | 2.731 | 1.00 | 1.00 |
| | sancho | 1.693 | 1.463 | 0.29 | **0.54** |
| | search | 0.968 | 0.938 | 0.17 | **0.34** |

The shared-prefix column is the comparable one, and it is the one the end-to-end reports
quote.

## What it means for the end-to-end results

- **On the 74-tool catalog the window is modestly cheaper than `full`**: an estimated
  0.77-0.88x. Success and time are unaffected by the pricing.
- **On the wide catalog the ordering holds:** search is the cheapest (0.34x), the window
  second (0.54x) - the conclusion of `../2026-09-25-wide/`.
- **The platform's search is not cheaper on the small catalog once `full` shares its prefix**
  (1.48x): its deferred catalog is small, but its extra search turns are not.

## The harness

`e2e_window.py` puts a breakpoint on `system` for every arm and pre-warms the shared prefixes
of `full` and `search` with one `max_tokens: 0` request before launching tasks in parallel (N
concurrent first requests all pay the write: none can read what another is still writing). A
run with this harness measures the shared-prefix cost directly rather than estimating it.

## Cheaper benchmarks

- **Breakpoint + pre-warm** (above): the wide run's `full` arm spent 3.86 USD writing cache and
  1.82 reading it; with a shared prefix most of the writes become reads.
- **Batch API (50 % off):** fits evaluations and probes that do not measure wall time. An agent
  loop can run in lockstep, one batch per turn across all tasks; latency per turn is minutes,
  so time columns are not measurable that way. `max_tokens: 0` is rejected inside a batch, and
  cache hits in batches are best-effort. Not used yet.
