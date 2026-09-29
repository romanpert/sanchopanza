# Amendment 1 to prereg-frontier: the lock waits for the target distribution

Written after the answers existed. It changes no verdict below; it makes the lock rule stricter
than the one registered, and it says why.

## Registered verdicts (`frontier-exits-answers.jsonl`, 616 answers, 0 errors, 0.0186 USD)

| | Hypothesis | Result |
|---|---|---|
| E1 | Precision lower bound >= 0.90 over >= 30 flags | **Holds**: 302/320 = 94.4 %, lower bound 0.913 |
| E2 | Precision >= 0.85 on errata-bench alone | **Fails**: 29/35 = 82.9 % |
| E3 | Recall >= 0.60 | **Holds**: 98.0 % (AUC 0.984) |

By source: candor rounds 273/285 (95.8 %); errata-bench 29/35.

## What reading the errors showed (post hoc)

Most "false flags" are label errors, and they sit where the frontier works. The label is the
exit code, and a pipe or `|| echo` gives the exit code of the last program, not of the command
that failed: `mise run test 2>&1 | tail -12` prints `FAIL ... ERROR task failed` and is labelled
a success.

- **Runs whose exit is the program's own** (no pipe, no mask; 426): precision 220/226 = 97.3 %
  (lower bound 0.943); errata-bench 27/28.
- **Runs with a hidden exit** (190), which is what the frontier is asked about in production:
  the exit label is invalid there. The 14 disagreements were read by hand. 11 of the 12 flags
  labelled false are real failures, and 1 is a real false flag (a loop printing CI logs that
  contain errors). That reads as 93/94.
- **That reading is not blind.** The adjudicator had already seen the model's flags on those
  runs, and it is post hoc. It is reported, and it earns nothing.

## The amendment

Registered: E1 holding makes `exit` earn `critical`. Amended, stricter: a kind earns the lock
only from a measurement **on the distribution it is asked on**, with labels independent of the
model. This set measures a proxy, runs with a visible exit, and `score` now records it as
`exit_proxy`. `exit` stays `high`.

What would earn it: hidden-exit runs (round 5, or a public set), labelled blind by someone who
has not seen the answers, and sealed before asking.
