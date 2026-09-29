# check_done on tau2-bench: pre-registration

Written 2026-09-29, before any answer on these items. The sample has been drawn and the items
built, and nothing else has been computed. `prereg-tau2.sha256` holds the hash of this file
together with the code it names.

## What is replicated, and what differs

`check_done` (`points.completion`, Jev) asks whether an agent finished the task, from the
request and the record. On 655 AgentDojo trajectories labelled by AgentDojo's `utility`, it
scored 93.7 % accuracy and AUC 0.98 (`docs/results/2026-09-25-completion`).

tau2-bench (`sierra-research/tau2-bench`, MIT, commit
`5bfa7e37b36656b37dc6d022156be6563c1007f3`) publishes its simulations with the environment's
reward. Three differences from AgentDojo:

- **The label is not the question.** The reward says the agent followed its policy and left the
  database right. A refusal the policy requires scores 1, even though the customer did not get
  what they asked for.
- **The request unfolds over a dialogue** with a simulated customer, so the record includes the
  customer's later messages.
- **The agents are other models:** Claude 3.7 Sonnet, GPT-4.1, GPT-4.1-mini and o4-mini.

## Items (`benchmarks/candor_external/tau2.py`, seed 20260929)

- The airline and retail result files of the four models (the `default` setting; `base` for
  GPT-4.1-mini, which has no `default` file). 40 simulations are drawn per file, 320 in all:
  213 with reward 1 and 107 without.
- The task is the customer's first message. The record holds:
  - the agent's text;
  - its tool calls;
  - their results, cut at 1,500 characters as in the original;
  - the customer's later messages.
- `done` means reward = 1.0.

## Hypotheses

- **T1:** Jev's p(done) separates reward 1 from reward < 1 at AUC >= 0.75.
- **T2:** Jev at p >= 0.5 is right on >= 10 points more simulations than trusting the agent
  (every run done: 66.6 % on this sample).

Also reported, with no verdict: AUC and accuracy per model and domain.

## Budget

Jev only: 320 calls, about 0.02 USD. The cap is 0.10 USD, set in code (`tau2.JEV_CAP_USD`).

Whatever does not hold is reported as not holding.
