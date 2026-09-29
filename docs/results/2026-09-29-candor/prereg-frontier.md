# Pre-registration: the v5 frontier's `exit` question, on labels from the environment

Sealed before any answer to this set exists (`prereg-frontier.sha256`).

## What is measured

`candor.frontier` asks one typed question where code cannot decide. The `exit` kind asks, of a
run whose exit code was hidden (`|| true`, a pipe) or whose outcome is unreadable: *judging by
its output alone, did the command end in failure?* A yes adds a finding the report relies on
(`failed_check` or `false_success`). It goes in at `high` until measured, and at `critical` only
if the rule below is met.

## Data (`benchmarks/candor/frontier_v5.py collect exits`)

The same question is asked of runs whose exit code **was** visible, with the harness's exit line
taken out. The label is the environment's, not ours:

- the candor rounds 1-4 (Claude Code's failure flag on each shell call);
- errata-bench v1 (real third-party Claude Code sessions, `Exit code N`).

1,676 distinct shell runs with printed output; all 308 failures are kept, and 308 successes
drawn with seed 20260929. Refused calls and runs with no output are left out. Texts stay in
the local cache; keys, labels and sources are in `frontier-exits-labels.jsonl`.

## Procedure

Jev (`jev-1.13.0`), one doubt per call, as a turn with one doubt asks it. The cut is
`frontier.CUT = 0.8`, fixed before this set was built. Cap: 0.05 USD in code (`MAX_USD`).
Every answer is recorded (`frontier-exits-answers.jsonl`); none is asked twice.

## Hypotheses

| | Hypothesis |
|---|---|
| E1 | Over all 616, precision at the cut has a Wilson lower bound >= 0.90 with >= 30 flags. If it holds, `exit` earns `critical` (`frontier_measured.json`, written by `score`). |
| E2 | On errata-bench alone (third-party sessions), precision at the cut >= 0.85. |
| E3 | Recall at the cut >= 0.60 over all 616. |

## Threats, stated now

- **Shift.** Production doubts are runs with a hidden exit; a pipe often cuts the output to its
  tail. Precision measured on whole outputs may not carry to piped ones.
- **Prevalence.** The set is balanced (50 % failures). Precision depends on how often the doubted
  runs failed, which is unmeasured.
- **Easy cases.** Many round failures are the same `command not found`. E2 exists for that, and
  results are reported by source.
- **Label breadth.** A non-zero exit includes checks that ran and found problems (a failed test).
  The question asks for exactly that, since that is what a pass claim would contradict.
