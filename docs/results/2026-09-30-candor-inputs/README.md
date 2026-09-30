# candor v6 on held-out data: which paths a request names as inputs (SWE-chat, 2026-09-30)

Registered in `prereg-inputs.md` (sealed before any v6 answer on held-out data) and
`prereg-inputs-code.md` (the reader, sealed before any turn was scored). Code:
`benchmarks/candor_external/swechat.py`. Jev: 0.0226 USD (cap 0.15).

**Question.** `substituted_input` locks a "done" report when the request names a file to work
from and nothing read it. On errata-bench every one of its flags was false: paths pasted into
long requests. v6 drops URL pieces and harness paths everywhere, and in long requests hands
the call to a question (`input`) instead of locking. Does that hold on sessions it was never
shaped on?

**Answer: v6 removes 96 % of the flags and nearly all the locks; no real substitution was found
in either arm.**

## Data

`SALT-NLP/SWE-chat` (ODC-BY): 300 Claude Code sessions sampled with seed 20260930, none from
an errata-bench repository. 277 turns (from 167 sessions) whose request names a path under
v5's rules. Both arms read the prose plus the block derived from it (one Jev answer, shared).
No text of any session is published here: `swechat-answers.jsonl` holds hashed keys and Jev's
answers, `swechat-labels.jsonl` hashed pair ids and labels.

## Verdicts (`swechat-verdicts.json`)

| | Hypothesis | Result | Verdict |
|---|---|---|---|
| O1 | v6 flags <= 1/3 of v5's (turn, path) pairs | 32 against 721 (4.4 %) | **holds** |
| O2 | v6 keeps >= 80 % of the pairs the reader calls real | 0 real pairs among the 200 read | **no verdict** (needs 5) |
| O3 | v6's precision >= v5's + 20 points | 0/11 against 0/200 | **fails** |

O3 fails the way the registration wrote it: with no real substitution in the data, neither arm
has a true flag to be precise about. What the numbers do say:

- **The locks.** v5 would have locked (a `critical` finding from code) **49 of the 277 turns
  (18 %)**, through 234 pairs; every one of the 200 pairs read was not a real substitution
  (192 `not_input`, 8 `used`; Wilson 95 % upper bound on v5's precision 1.9 %). v6 locks **5
  turns (1.8 %)**, 6 pairs, all in short requests where code still decides.
- **The review tier.** v6's other 26 flags are `high`: 7 from the derived block in short
  requests, 19 from the `input` question in long ones. They go to a person, never to the lock.
  Of the 11 v6 flags in the read sample: 9 `not_input`, 2 `used`.
- **What the flags were.** The readers' notes: build and CI logs pasted into the request,
  stack-trace places, a plan's transcript pointer, URL pieces, import paths, package names,
  and files the request asked to change that the agent then read.

## Deviations, stated

- **Five readers, not one.** The 200 pairs (2.9 MB) did not fit one reader's context; they
  were split into five seeded, consecutive blocks of 40, each read by a Claude subagent with the
  registered instructions verbatim and blind to the arm. One reader labelled 17 of its 40 pairs
  from excerpts because single lines exceeded its read limit (10 pasted logs, 7 non-file
  paths); another had to split lines with a script to read them.
- **The turns.** A first cleaning left 162 background-task notifications counted as requests;
  it was fixed before anything was scored (`prereg-inputs-code.md`). A free dry replay without
  Jev (code rules only: 234 v5 pairs, 6 v6 pairs) was run to check the pipeline before the
  live run; the registered arms include the derived block.

## What it means for the product

v6 is what ships. On third-party sessions without the status block, `substituted_input` stays
a review signal and almost never a lock. The lock rate on real work drops from 18 % of turns to
1.8 %, still not zero: the six remaining locks are short requests, the family candor was built
for, and there the reader found no real case either. Confirming that the lock is right when it
fires still needs data where agents actually substitute an input; round 5's U2 is the closest
we have (agents that invent the missing input), and that is v7's question, not this one.
