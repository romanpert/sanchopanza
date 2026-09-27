# Pre-registration: a calibrated "is it done?" check against labels by construction

Written 2026-09-25 before any call. The runner (`benchmarks/completion/run.py`) refuses to
spend unless the sha256 of this file plus `src/sanchopanza/points/completion.py` matches
`prereg.sha256`.

## Why

A harness decides when an agent is done, and the default is the agent's own word. browser-use
shipped a second LLM judge on top of the agent's self-reported `done` because that word was
not trustworthy; Claude Code users write Stop hooks for the same reason. Nobody we found
publishes how often such a check is right.

## Data

Every AgentDojo v1.2.2 run recorded in this repository on 2026-09-24
(`docs/results/2026-09-24-agentdojo-e2e/runs/`, `docs/results/2026-09-24-agentdojo-haiku/runs/`):
655 trajectories of the `slack` suite, five pipelines (Sonnet 5 undefended, spotlighting,
two sanchopanza defenses; Haiku 4.5 undefended), with and without injected attacks. The label
is AgentDojo's `utility`, computed by the benchmark from the environment's final state: did
the user task succeed. 342 true, 313 false. No annotator.

Correlation, stated before running: trajectories share 21 user tasks, and one pipeline
(sanchopanza redacting) fails mostly because its defense removed content the task needed.
Results are also reported per pipeline.

## Arms

- `trust`: the agent is always believed (every trajectory "done"). The status quo.
- `jev`: `completion.QUESTION`, `jev-1.13.0`, done at p >= 0.5.
- `sonnet`: `claude-sonnet-5` through the Message Batches API, same question via the
  provider's schema, no chain of thought.
- `cascade(jev>sonnet)`: offline from the recordings, tau derived as in the cascade
  pre-registration (`../2026-09-25-cascade/prereg.md`): hash-parity split of the file path,
  smallest tau on the derivation half whose cascade accuracy reaches sonnet's.

State: `task` = the user message; `record` = one line per agent text (thinking blocks
dropped), per tool call (`AGENT ACTION: name(args)`) and per tool result (`TOOL RESULT:`,
each cut to 1,500 characters, `ERROR:` when the tool failed). The system prompt, the
`utility`/`security` fields and the injection metadata reach no arm.

## Criteria, on the held-out half

- **P13**: jev accuracy >= trust accuracy + 15 points.
- **P14**: cascade accuracy >= sonnet accuracy - 2 points, paired bootstrap lower bound
  >= -6 points, cascade cost <= 50 % of sonnet alone.

Secondary: jev and sonnet alone on all 655, precision of "done" (a false "done" is the
costly error: the harness stops on unfinished work), AUC of jev's probability, per pipeline.

## Cost

About 0.85 MTok of input. Jev about 0.04 USD; Sonnet 5 in batch about 0.9 USD.
