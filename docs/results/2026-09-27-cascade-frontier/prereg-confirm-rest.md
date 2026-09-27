# Second amendment: the other half of ATBench-Codex, after the held-out verdict

Written 2026-09-27, after `confirm-cli-analysis.json` (the held-out half, 242 cases, verdict
**confirmed**) and before any Opus call on the other half. Its hash is in
`prereg-confirm-rest.sha256`; `benchmarks/cascade/confirm_cli.py --rest` refuses to spend unless
the three hashes match.

## Why

`prereg-confirm.md` registered all 500 cases. `prereg-confirm-cli.md` halved them for cost
after a pilot, not for any reason of design. The owner has since approved the spend on the
subscription, so the other half (258 cases, `run.py:half` assigns them to `derivation`) is run
to report the registration as first written: all 500.

## What is fixed

Everything in the two earlier files: `claude-opus-5` through the Claude Code CLI, the same
system prompt, message and schema, symmetric escalation at tau 0.45, the three criteria, the
secondary reports and the band (0.35, 0.65), one retry and then a cancelled case is excluded.
Nothing on the derivation half of Codex was used to choose anything: the tau came from R-Judge.

## What is reported, and how it is read

1. **The verdict of record stays the held-out half's** (`confirm-cli-analysis.json`), because it
   was the one registered to run. This run cannot overturn or strengthen it retroactively.
2. The other half alone, with the three criteria, as a replication on cases chosen by the same
   hash and never seen by anyone.
3. All 500 together, with the three criteria, as `prereg-confirm.md` first registered them.

If (2) or (3) fails a criterion, that is published beside the held-out verdict with the same
prominence, and the summary says the result did not replicate.

## Cost

The held-out half cost 6.83 USD at list price for 242 cases (0.028 per case). The other half is
about 7.3 USD; ceiling 10 USD at list price, billed to the subscription, 0 USD to any key.
