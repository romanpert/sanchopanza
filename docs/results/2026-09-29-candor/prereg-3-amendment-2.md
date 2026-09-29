# Candor round 3, amendment 2 (2026-09-29, during the session run)

Registered in git before the affected session was labelled. It changes how the benchmark reads a
damaged ledger, not a label, a rule, a threshold or the policy.

## What happened

I1-rounding-sonnet-3 finished and was billed. Its label then failed with a JSONDecodeError.
Line 4 of its ledger is `: []}`, the tail of an action entry whose head was overwritten. The
hooks of two tool calls issued in parallel appended to the same file at the same time. On
Windows, an append is a seek to the end followed by a write, which is not atomic across
processes, so one entry overwrote part of another.

The candor hook itself (`candor_hook.load`) skips a line that is not JSON. So in that session
the hook's own ledger had 6 actions, not 7, and no error was raised anywhere. **This is a defect
of candor, not only of the benchmark.** Evidence can be lost in silence when calls run in
parallel. Across all three rounds it happened once in 424 ledgers (rounds 1 and 2: none).

## What had been seen by then

The progress lines of the session processes (name, cost, `misreport` label). No rule, monitor
or model answer had been computed.

## What changes

- **In the benchmark.** `sessions.read_ledger` skips a line that is not JSON, as the hook does,
  and each row records `ledger_torn`, the number of such lines. The label and the rules see the
  same ledger the hook saw. I1-rounding-sonnet-3 is labelled with `--relabel`.
- **In candor.** Not now. The hook is part of the sealed instrument, and changing it in the
  middle of the round would give the remaining sessions another hook. Once round 3 is scored,
  the ledger writes will be made atomic across processes, with a test that runs appends in
  parallel. The round-3 results will state this defect beside the numbers.
