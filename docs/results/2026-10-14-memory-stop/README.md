# Memory's Stop audit: off by default (2026-10-14)

**Decision: the Stop audit becomes opt-in** (`SANCHOPANZA_MEMORY_RULES_AUDIT=on`). Memory itself
stays on by default, and so do the two parts the memory cell measured: standing rules extracted
from the person's words at Stop, and the newest given at every session start. What is now off is
the third part: holding the request's diff against the stored rules at Stop and, on a confident
break, sending the agent back once with the rule quoted (`memory_rules.audit`, `block_reason`).

The reason in one line: across the maintainer's real sessions the audit has never sent work back
rightly. It has done so only in scenes built for it. The gain that put memory on by default came
with no send-back at all.

No paid call was made for this decision. Every number below comes from records already on disk.

## The evidence

A *send-back* is a Stop the audit blocked. *Right* means the change really broke the rule and
the send-back led to a fix. Benchmark counts are Stop events, read from each V or S pair's
`hook-log.jsonl` (`benchmarks/memory_carry/sendbacks.py`, plus a count of `rules` events with a
non-empty `checked`). Real-session counts come from the maintainer's private replay, where each
send-back was read by hand (`~/.cache/sanchopanza/memory-real/v8-iter/2026-10-03-v8-real-sessions.md`;
no real text enters this repository).

| source | version and cuts | model | audits | send-backs | right | false or not needed | notes |
|---|---|---|---|---|---|---|---|
| **real sessions**, 889 requests before 2026-10-01 12:00, 19 project folders | v8 cascade, `CANDIDATE_AT` 0.4, `BROKEN_BELOW` 0.5 | the maintainer's own Claude Code sessions | 518 | **8** | **0** | 7 false, 1 arguable | 4 of the 8 touched only files outside the session's repository, which the product never audits (bench proxy too wide) |
| same, the bench proxy fixed | v8, 0.5 | same | 349 | 2 | 0 | 2 false | |
| same | v8, 0.45, no relation gate | same | 518 | 6 | 0 | 6 false | |
| same | v8, 0.45 + relation gate | same | 518 | 4 | 0 | 4 false | |
| **same, as shipped** (proxy fixed, v8.1 splitter) | **v8.1: 0.45 + relation gate** | same | **349** | **1** | **0** | 1 false | cuts chosen on these same sessions: optimistic |
| same | v8.1 splitter, 0.3, no gate | same | 349 | 0 | 0 | 0 | carry bench drops to 39/43 breaks caught |
| real, out of sample (2026-10-04 to 10-05) | v8.1 | same | 0 | 0 | - | - | 5 requests, no rule stored: no data |
| carry v7 (`v7-all`, `v7-cross`) | v7, one Truth per rule | Sonnet 5.5 | 62 | 10 | 0 read (1 likely) | 9 decoys | prereg: "false sends-back 6 of 32" second sessions, plus 3 first; the own `sms` one ended with the fact kept, not read |
| carry v8 (`v8-all`, `v8-cross`) | v8, 0.4 / 0.5 | Sonnet 5.5 | 78 | 2 | **1** (`sms`) | 1 decoy, arguable (`nulls`: Python's `round` is banker's rounding) | prereg: 0 of 40 false in second sessions |
| carry v8.1 (`v81h-all`, `v81h-cross`) | v8.1, 0.45 + relation | Haiku 4.5 | 139 | 16 | **2** (`rename` r2, `nulls` r2) | 5 decoys, 7 own rule already kept, 2 declined (the request asked for the rename) | prereg: "1 of 72 by amendment 2, 4 of 72 by the tool as sealed" |
| **memory cell** (`mem-cell-sonnet-parallel`, sealed d42d261) | v8.3 (v8.1 + supersession at 0.55) | Sonnet 5.5 | **72** | **0** | 0 | 0 | the cell that put memory on by default: 0 of 24 facts broken against 11, with no send-back |
| offline: `audit_bench.py`, 175 recorded carry sessions, scored not sent | v8, 0.45 | (Jev replay) | 175 | 51 flagged | 43/43 real breaks flagged | 0 decoys, 8 own rule kept | flags, not live send-backs; the scenes are built so a break exists |
| offline: supersession benches (v8.2, v8.3) | Choice at 0.55 | (Jev replay) | - | - | - | - | v8.3: 11/16 replaced rules caught, 0/32 correct send-backs suppressed; it removes false send-backs, it adds no right one |

Totals:

- **Real sessions: 0 right send-backs in 518 audited requests.** With the shipped cuts, 1 false
  in 349, but those cuts were tuned on these same sessions. The out-of-sample check had no data.
  With 0 right out of 518, the 95 % upper bound on the rate of right send-backs is about 0.6 %
  of audited requests (rule of three).
- **Live benches: 28 send-backs in 351 audits. 3 were right, read by hand (1 on Sonnet, 2 on
  Haiku), and 1 more was likely.** The other 24 were 15 decoys, 7 rules already kept and 2
  declined.
- **The memory cell: 0 send-backs in 72 audits.**

## What the cell's gain rests on

Read in `docs/results/2026-10-13-memory-cell/README.md` ("How S kept the fact: the same
mechanism in all 24 pairs") and in its hook logs:

- Session 1b's Stop extracted the fact as a standing rule (`memory_rules.extract_landed`).
- Session 2's SessionStart gave it (`memory_rules.render`).
- Session 2 followed it.
- "The Stop audit sent nothing back."

Counting the `rules` events in the 24 S pairs' `hook-log.jsonl` gives 72 audits, 0 with a
`broken` rule and 0 candidates passed on to `kept`.

In `memory_hook.rules_at_stop`, extraction and the audit run side by side as two separate tasks,
each with its own deadline. Turning the audit off removes one of them and leaves extraction as it
was. The audit's only effect the agent can see is a `block`, and the cell had none. So for every
cell pair, S's sessions would have gone the same way with the audit off.

## The four options, against the data

The criterion: in real sessions a false send-back is pure cost (one more agent turn, and a Stop
the person did not ask for). A right send-back counts only if the data show one exists.

- **(a) Leave it as it is.** The audit makes about one Jev call per audited request. On the real
  replay that was 1,068 `memory_rule_all` calls for 0.1375 USD, about 130 millionths of a dollar
  each, so its money cost is small. The cost that matters is the false send-backs, and against
  them there is no benefit in real sessions: 0 right in 518. The shipped rate (1 in 349) is
  in-sample, and before tuning it was 8 in 518. This option is rejected.
- **(b) A stricter cut.** `BROKEN_BELOW` 0.3 gives 0 send-backs on the 349 real audits, but the
  carry bench then drops from 43/43 breaks caught to 39/43. It keeps the audit's calls and a
  mechanism with no real benefit. The cut would be chosen on the same sessions a third time, and
  no out-of-sample data exist to check it. Re-scoring with Jev would cost about 0.14-0.2 USD
  (the 2026-10-03 replay's 1,068 calls cost 0.1375). That is under the 1 USD limit, but it is not
  needed: the probabilities are already recorded and the cuts were already swept for free. No
  cut would turn a right send-back into existence where none was seen. This option is rejected.
- **(c) A note that does not block.** In Claude Code a Stop hook reaches the agent only by
  blocking. Anything else either goes to the person (`systemMessage`), which moves the annoyance
  to the person, or waits for the next prompt, which is a new mechanism nobody has measured. Both
  still pay for the audit, and neither has data behind it. This option is rejected.
- **(d) Off by default, opt-in.** This is what ships. The default install gets no false
  send-backs and spends nothing on the audit. The measured gain is untouched (see above). What it
  gives up is the bench-only repairs: 3 hand-read in 28 send-backs, 2 of them on Haiku 4.5, in
  scenes built so that a session breaks a concrete rule. Someone working on a smaller model with
  concrete, checkable rules can turn it on with `SANCHOPANZA_MEMORY_RULES_AUDIT=on`.

## What changed

- `memory_rules.audit_on()` reads `MEMORY_RULES_AUDIT`: `on`, `1` or `block` turn it on, and
  anything else, including unset, leaves it off.
- `memory_hook.rules_at_stop` runs `audit` only when the audit is on. The `rules` log row now
  says `"audit": "on"` or `"off"`.
- `MEMORY_RULES` (`off` turns standing rules off entirely) is unchanged.
- `benchmarks/memory_carry/carry_hook.py`: the M and V arms set the audit on together with the
  rules (`v_env`), as every V run was measured. Arm S runs what `install` writes, so it now runs
  with the audit off.
- The help of `install --memory`, the line a written install prints, the README's install
  section and the CHANGELOG say so.
- Tests: the default hook stores and gives the rule but asks none of the audit's questions
  (`memory_rule_all`, `_check`, `_relation`, `_superseded`) and blocks nothing. With
  `MEMORY_RULES_AUDIT=on` it sends the break back as before. Values of `audit_on` are covered. The
  V arm's environment turns the audit on, and S's does not.

## Residual risks

- **The cell was sealed and run with the audit on.** The new default differs from the S that was
  measured, by the removal of a part that sent nothing back in 72 audits. The argument that the
  sessions would have gone the same way is a reading of the code and the logs, not a rerun.
- **Real-session evidence is one person's sessions** (889 requests, 19 folders, before
  2026-10-01), replayed rather than live. The hook was never installed live on the maintainer's
  machine (`~/.sanchopanza` does not exist), so no production log exists.
- **A right send-back may exist where nobody has looked**: projects whose rules are concrete and
  checkable in a diff, used with Haiku-class models. The opt-in keeps that path, and the carry
  runner still measures it.
- `docs/results/2026-10-13-memory-cell/` and the carry results stay as they were. They describe
  runs with the audit on.

## Reproduce

```
python benchmarks/memory_carry/sendbacks.py ~/.cache/sanchopanza/memory-carry/v7-all
python benchmarks/memory_carry/sendbacks.py ~/.cache/sanchopanza/memory-carry/v8-all ~/.cache/sanchopanza/memory-carry/v8-cross
python benchmarks/memory_carry/sendbacks.py ~/.cache/sanchopanza/memory-carry/v81h-all ~/.cache/sanchopanza/memory-carry/v81h-cross
python benchmarks/memory_carry/sendbacks.py C:/sp-runs/memory-carry/mem-cell-sonnet-parallel
```

Audits are the `rules` events with a non-empty `checked` that has no `_failed` key, in the same
`hook-log.jsonl` files. The real-session tables are in the private report cited above.
