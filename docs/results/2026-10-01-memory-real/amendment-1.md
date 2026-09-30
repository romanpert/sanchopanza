# Amendment 1: the selector to confirm on held-out groups, and what counts as success

Written 2026-10-01 after development, before any held-out item was scored. Sealed with the code
it names (`amendment-1.sha256`); held-out items are scored once, with `replay.py --split held`
and `score.py --split held --select decider`.

## What changed on development data (declared)

- Labels: unchanged in substance. `build.py` also records, per request, the files it opened or
  changed in order (`touched`), used by the touch replay.
- `episodes.is_request` no longer counts "[Request interrupted by user]" as a request (40 of 993
  development "requests" were that mark): development items were rebuilt with it (953).
- The metric credits a record already shown to an earlier request of the same session (it is
  in the context; SWE-chat sessions rarely compact), for every selector alike.
- Development results (`scores-dev.json`, `variants-dev.json`, `replay-dev.json`), all requests,
  label `lineage or file`: shipped v2 (every prompt, BM25 then the decider at 0.2) recall 0.248,
  precision 0.026, noise 0.393; v3 through the hook's own code recall 0.944, precision 0.603,
  noise 0.049. With `lineage` only: v2 0.317 / 0.014 / 0.382, v3 0.800 / 0.146 / 0.084.

## The selector confirmed: memory v3 as `install --memory` ships it

`memory_hook.touch` on every Read, Edit, MultiEdit, Write and NotebookEdit (the 2 newest records
that changed the file, once per session), plus recall at the session's first request with the
decider at 0.7. Compared with v2 on the same held-out items.

## Success (all four, all requests, label `lineage or file`)

1. v3 recall >= 0.80.
2. v3 precision >= 0.40.
3. v3 noise <= 0.10.
4. v3 better than v2 on each of recall, precision and noise.

Reported as well, not criteria: the same with `lineage` only, first requests only, and records
given per request. Decider spend on held-out items capped at 0.50 USD in code.
