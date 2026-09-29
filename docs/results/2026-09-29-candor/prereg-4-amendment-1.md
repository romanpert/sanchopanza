# Candor round 4, amendment 1 (2026-09-29, during the session run)

Registered in git before any round-4 rule verdict, model answer or counterfactual was computed.

## What happened

While the round-4 sessions were running, I changed the candor hook in the working tree. The
change was a new feature, `SANCHOPANZA_CANDOR_ASK_BLOCK`, to ask for the status block on the
prompt or at the stop. The benchmark sessions run the hook from the working tree, so for about
a minute and a half (13:35:15 to 13:36:53 local time) new hook events ran other code than the
sealed one:

- **At first,** a missing import made the new code raise. `main()` lets any error pass
  through, so those events did nothing.
- **Then,** with the import in place, the prompt hook appended the block request as
  `additionalContext`. The task prompt already carried it word for word.

At 13:36:53 the default was set to `off`. With it off, the hook behaves as the sealed one:
the prompt hook returns nothing, and the stop check returns before doing anything.

## Sessions whose run overlaps that window

Seven Haiku 4.5 sessions:

- S2-sqlite-haiku-3
- S3-typecheck-haiku-3
- S4-version-bump-haiku-3
- S1-refresh-haiku-4
- S2-sqlite-haiku-4
- S3-typecheck-haiku-4
- S4-version-bump-haiku-4

## What had been seen

The progress lines of the session process (name, cost, `misreport` label) and the files of
those sessions checked for this amendment (stream result types, whether a Stop event was
recorded). No rule verdict, monitor answer or counterfactual.

## What changes

- **Both analyses are reported.** `confirm4.py` computes the registered verdicts on every
  session, as registered, and again without the seven sessions above.
- **The analysis without them is primary,** because they may have run with another instrument.
- No session is rerun, and no label, rule or threshold changes.
