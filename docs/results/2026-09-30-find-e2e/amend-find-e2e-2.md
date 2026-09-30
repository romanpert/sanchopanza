# Amendment 2 to prereg-find-e2e, after the run, accounting only

Written 2026-09-30 after all sessions ran and after the first `score`, which reported
`jev_usd: 0.0` for arm F although six F sessions called `find_in_repo` and their results carry
Jev's probabilities.

- **The bug.** `e2e.jev_spent` summed a top-level `cost_usd` per journal line; the journal
  nests it (`{"kind": "decision", "data": {"cost_usd": ...}}`). Every session read 0, so the
  0.30 USD Jev cap was never enforced during the run. It was never needed: the six sessions
  that called the tool spent **0.0132 USD** of Jev in all.
- **The fix.** `jev_spent` reads `data.cost_usd`; each `row.json`'s `jev_usd` is recomputed
  from its journal. Nothing else in a row, and no verdict, depends on it.
- **Sessions interrupted from outside.** Three sessions (scikit-learn-14141 F, sphinx-10449 N
  and F) were killed by another process on this machine that was restarting unrelated services
  (its filter matched `claude -p` command lines). They were voided like the pilot's
  (`void/*-killed`, charged by usage) and rerun one at a time within the ceiling.
