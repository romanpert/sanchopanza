# Memory v8.1 on Haiku 4.5, amendment 2: what counts as the scene's own rule (2026-10-05)

Sealed by the commit that adds `prereg-v81-haiku-amendment-2.sha256`. It changes how
`sendbacks.py` labels a send-back, which criterion 3 uses. Nothing else changes.

## Why, and when

- Criterion 3 counts "a V second session sent back by a rule other than its scene's own". The
  prereg names `sendbacks.py` as the means, and it asks for every decoy send-back to be read by
  hand and quoted.
- **When it was found.** `v81h-all` ended at 15:16 with exit 0, and its send-backs were read by
  hand as the prereg asks. At that time `v81h-cross` had one row, `x_tz` arm M. That row was not
  read; arm M has no audit, so it has no send-backs anyway.
- **What `sendbacks.py` reported.** Three second sessions sent back by a decoy, all in `columns`
  (repetitions 0, 1 and 2). The rule quoted in each was:
  "For context: finance's Excel macro reads this CSV by column position, so the order of the
  columns can never change."
- **Why that is wrong.** That sentence is `columns`' own fact (`rules.py:8`) with the lead-in
  "For context: ", which v8.1's splitter keeps in the sentence. `sendbacks.py:33` called a rule
  own only on exact equality (`text == ALL_RULES[scene]`), so it labelled the scene's own fact a
  decoy.
- The decoys in V's store are other scenes' rules, verbatim (`carry.decoys`). None of them
  contains another scene's fact, so a containment test cannot turn a decoy into an own rule.

## Change

`own` is now `ALL_RULES[scene] in text`. Test: `tests/test_memory_carry.py`, a send-back that
quotes `columns`' fact after "For context: " is own, and `fields`' rule in a `columns` pair is not.

## This change favours V, so both counts are reported

- **By the tool as sealed (equality):** 3 of 48 in `v81h-all`.
- **By the definition (containment, read by hand):** 0 of 48.
- The criterion is judged by the definition, which is the prereg's own wording. The report gives
  both counts for both runs, with every quoted rule.
- Session-1 send-backs by a decoy are outside criterion 3. Four of them (`columns` 0-2 by the
  integer-cents rule, `nulls` 0 by the rounding rule) are reported as false alarms all the same.
